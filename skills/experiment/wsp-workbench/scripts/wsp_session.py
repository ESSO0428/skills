"""WeightSession: gated weight edits with a ledger, undo and a forward-pass budget.

The session never optimises. It exposes four edit ops (project_out, add_rank1,
assign, zero_units); every edit goes through one gate before it touches a tensor.
"""
from __future__ import annotations

import ast
import ctypes
import hashlib
import json
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import torch

LEVELS = ("L1", "L2", "L3")


class PolicyViolation(Exception):
    """An edit was refused by the edit gate."""


class BudgetExhausted(Exception):
    """The forward-pass budget is used up (or the access level forbids passes)."""


class AccessDenied(Exception):
    """The session's access level does not allow this operation."""


class ForbiddenCode(Exception):
    """Agent code uses a gradient / optimiser feature that WSP forbids."""


def tensor_hash(t: torch.Tensor) -> str:
    """sha256 over the raw bytes of a tensor (dtype and shape are mixed in)."""
    flat = t.detach().cpu().contiguous().reshape(-1).clone()
    h = hashlib.sha256()
    h.update(f"{t.dtype}|{tuple(t.shape)}|".encode())
    if flat.numel():
        h.update(ctypes.string_at(flat.data_ptr(), flat.numel() * flat.element_size()))
    return h.hexdigest()


@dataclass
class EditPolicy:
    """Which tensors may change and how much. Regexes use re.search on parameter names."""

    allowed: list[str]
    forbidden: list[str] = field(default_factory=list)
    max_fraction_changed: float = 0.05  # per edit, relative to the tensor's size

    def check_name(self, name: str) -> None:
        if any(re.search(p, name) for p in self.forbidden):
            raise PolicyViolation(f"{name}: matches a forbidden pattern")
        if not any(re.search(p, name) for p in self.allowed):
            raise PolicyViolation(f"{name}: not in the allowed list")


class ForwardBudget:
    def __init__(self, max_passes: int, name: str = "forward"):
        self.max_passes = max_passes
        self.name = name
        self.used = 0

    @property
    def remaining(self) -> int:
        return self.max_passes - self.used

    def consume(self, n: int = 1) -> None:
        if self.used + n > self.max_passes:
            raise BudgetExhausted(
                f"{self.name} budget exhausted ({self.used}/{self.max_passes} used)"
            )
        self.used += n


_FORBIDDEN_ATTRS = {"backward", "grad", "vjp", "jvp", "jacrev", "jacfwd", "hessian"}
_FORBIDDEN_MODULES = (["torch", "optim"], ["torch", "autograd"])


def check_agent_code(source: str) -> list[str]:
    """Raise ForbiddenCode if the code would optimise; otherwise return []."""
    tree = ast.parse(source)
    found: list[str] = []

    def is_false(node: ast.AST) -> bool:
        return isinstance(node, ast.Constant) and node.value is False

    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[:2] in _FORBIDDEN_MODULES:
                    found.append(f"line {line}: import {a.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            names = [a.name for a in node.names]
            if mod.split(".")[:2] in _FORBIDDEN_MODULES:
                found.append(f"line {line}: from {mod} import ...")
            elif mod == "torch" and any(n in ("optim", "autograd") for n in names):
                found.append(f"line {line}: from torch import {', '.join(names)}")
        elif isinstance(node, ast.Attribute) and node.attr in ("optim", "autograd"):
            found.append(f"line {line}: use of .{node.attr}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if attr in _FORBIDDEN_ATTRS:
                found.append(f"line {line}: call to .{attr}()")
            elif attr == "requires_grad_" and not (node.args and is_false(node.args[0])):
                found.append(f"line {line}: requires_grad_() without False")
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if (
                    isinstance(t, ast.Attribute)
                    and t.attr == "requires_grad"
                    and not is_false(node.value)
                ):
                    found.append(f"line {line}: requires_grad assigned a non-False value")
    if found:
        raise ForbiddenCode("; ".join(found))
    return found


class WeightSession:
    """Edit and (at L2) probe a model under an EditPolicy.

    L1: code over weights only; forward passes are refused.
    L2: forward passes allowed up to `budget` calls (one call = one pass, any batch size).
    L3: L2 plus gradient / Hessian-vector measurements by the trusted wsp_landscape functions,
        up to `grad_budget` evaluations. Gradients never update weights; agent code still may
        not use autograd (check_agent_code). L3 results are never pooled with L1/L2.
    """

    def __init__(
        self,
        model: torch.nn.Module,
        policy: EditPolicy,
        level: str = "L1",
        budget: int = 0,
        ledger_path: str | Path | None = None,
        access_level: str | None = None,
        grad_budget: int = 0,
    ):
        level = access_level or level
        if level not in LEVELS:
            raise ValueError(f"level must be one of {LEVELS} (L0 has no tools, so no session)")
        self.model = model
        self.policy = policy
        self.level = level
        self.budget = ForwardBudget(budget if level in ("L2", "L3") else 0)
        self.grad_budget = ForwardBudget(grad_budget if level == "L3" else 0, name="gradient")
        self.ledger_path = Path(ledger_path) if ledger_path else None
        self.ledger: list[dict] = []
        self._before: dict[int, torch.Tensor] = {}
        self._next_id = 1
        for p in model.parameters():
            p.requires_grad_(False)
        self.baseline = {k: tensor_hash(v) for k, v in model.state_dict().items()}

    # ---- helpers -------------------------------------------------------
    def _params(self) -> dict[str, torch.Tensor]:
        return dict(self.model.named_parameters())

    def param(self, name: str) -> torch.Tensor:
        """A detached copy for reading; edits must go through the ops."""
        return self._params()[name].detach().clone()

    def match(self, pattern: str) -> list[str]:
        return [n for n in self._params() if re.search(pattern, n)]

    def _log(self, entry: dict) -> None:
        self.ledger.append(entry)
        if self.ledger_path:
            with self.ledger_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    # ---- gate + commit -------------------------------------------------
    def _commit(self, op: str, name: str, new: torch.Tensor, note: str) -> int:
        self.policy.check_name(name)
        p = self._params()[name]
        new = new.to(dtype=p.dtype, device=p.device).reshape(p.shape)
        if not torch.isfinite(new).all():
            raise PolicyViolation(f"{name}: edit produces non-finite values")
        old = p.detach()
        n_changed = int((new != old).sum())
        if n_changed == 0:
            raise PolicyViolation(f"{name}: edit changes nothing")
        if n_changed / p.numel() > self.policy.max_fraction_changed:
            raise PolicyViolation(
                f"{name}: changes {n_changed}/{p.numel()} values, over the cap "
                f"{self.policy.max_fraction_changed:.0%}"
            )
        if n_changed == p.numel() and p.numel() > 1 and bool((old != 0).all()):
            ratio = new / old
            if torch.allclose(ratio, ratio.flatten()[0].expand_as(ratio), rtol=1e-4):
                raise PolicyViolation(f"{name}: whole-tensor scaling is not allowed")
        eid = self._next_id
        self._next_id += 1
        before_hash = tensor_hash(old)
        self._before[eid] = old.clone()
        with torch.no_grad():
            p.copy_(new)
        self._log(
            {
                "event": "edit",
                "edit_id": eid,
                "op": op,
                "tensor": name,
                "n_changed": n_changed,
                "before_hash": before_hash,
                "after_hash": tensor_hash(p),
                "note": note,
                "level": self.level,
            }
        )
        return eid

    # ---- ops -----------------------------------------------------------
    def project_out(self, name, u, alpha=1.0, cols=None, note="") -> int:
        """W' = W - alpha * u (u^T W) on chosen columns; u in the output space (rows), normalised.

        alpha=1 removes the u-component, alpha<1 shrinks it, alpha>1 flips it.
        Tensors with more than 2 dims are viewed as (out, -1).
        """
        W = self.param(name)
        W2 = W.reshape(W.shape[0], -1).float()
        u = torch.as_tensor(u, dtype=torch.float32).flatten()
        if u.numel() != W2.shape[0]:
            raise PolicyViolation(f"{name}: u has {u.numel()} entries, expected {W2.shape[0]}")
        if not torch.isfinite(u).all() or u.norm() == 0:
            raise PolicyViolation("u must be finite and non-zero")
        u = u / u.norm()
        idx = slice(None) if cols is None else torch.as_tensor(cols, dtype=torch.long)
        sub = W2[:, idx]
        W2 = W2.clone()
        W2[:, idx] = sub - alpha * torch.outer(u, u @ sub)
        return self._commit("project_out", name, W2.reshape(W.shape), note)

    def add_rank1(self, name, a, b, scale=1.0, note="") -> int:
        """W' = W + scale * a b^T, with a over rows and b over (flattened) columns."""
        W = self.param(name)
        W2 = W.reshape(W.shape[0], -1).float()
        a = torch.as_tensor(a, dtype=torch.float32).flatten()
        b = torch.as_tensor(b, dtype=torch.float32).flatten()
        if a.numel() != W2.shape[0] or b.numel() != W2.shape[1]:
            raise PolicyViolation(f"{name}: a/b sizes do not match {tuple(W2.shape)}")
        new = (W2 + scale * torch.outer(a, b)).reshape(W.shape)
        return self._commit("add_rank1", name, new, note)

    def assign(self, name, flat_index, values, note="") -> int:
        """Set entries at flat indices to given values."""
        W = self.param(name)
        flat = W.reshape(-1).clone()
        idx = torch.as_tensor(flat_index, dtype=torch.long).flatten()
        vals = torch.as_tensor(values, dtype=flat.dtype).flatten()
        if idx.numel() != vals.numel():
            raise PolicyViolation("index and values differ in length")
        if idx.numel() and (idx.min() < 0 or idx.max() >= flat.numel()):
            raise PolicyViolation(f"{name}: index out of range")
        flat[idx] = vals
        return self._commit("assign", name, flat.reshape(W.shape), note)

    def zero_units(self, name, units, dim=0, note="") -> int:
        """Zero whole rows (dim=0) or columns (dim=1) of a tensor."""
        W = self.param(name)
        units = torch.as_tensor(units, dtype=torch.long).flatten()
        if dim == 0:
            W[units] = 0
        elif dim == 1:
            W[:, units] = 0
        else:
            raise PolicyViolation("dim must be 0 or 1")
        return self._commit("zero_units", name, W, note)

    # ---- scratch space for measurements ---------------------------------
    def _hashes(self) -> dict[str, str]:
        return {k: tensor_hash(v) for k, v in self.model.state_dict().items()}

    @contextmanager
    def scratch(self):
        """Let trusted measurement code move weights temporarily; restore and verify hashes on exit."""
        saved = {k: v.clone() for k, v in self.model.state_dict().items()}
        before = self._hashes()
        was_training = self.model.training
        try:
            yield
        finally:
            self.model.load_state_dict(saved)
            self.model.train(was_training)
            if self._hashes() != before:
                raise AssertionError("weights differ from their state before the measurement")

    def require_level(self, level: str) -> None:
        if LEVELS.index(self.level) < LEVELS.index(level):
            raise AccessDenied(f"this needs access level {level}; the session is {self.level}")

    # ---- undo / baseline ----------------------------------------------
    def undo(self, edit_id: int) -> None:
        entry = next(
            (e for e in self.ledger if e["event"] == "edit" and e["edit_id"] == edit_id), None
        )
        if entry is None or edit_id not in self._before:
            raise KeyError(f"no undoable edit {edit_id}")
        p = self._params()[entry["tensor"]]
        if tensor_hash(p) != entry["after_hash"]:
            raise PolicyViolation(f"edit {edit_id}: tensor changed since; undo later edits first")
        with torch.no_grad():
            p.copy_(self._before.pop(edit_id))
        self._log(
            {
                "event": "undo",
                "edit_id": edit_id,
                "tensor": entry["tensor"],
                "after_hash": tensor_hash(p),
            }
        )

    def undo_all(self) -> None:
        for e in reversed([e for e in self.ledger if e["event"] == "edit"]):
            if e["edit_id"] in self._before:
                self.undo(e["edit_id"])

    def assert_baseline(self) -> None:
        now = {k: tensor_hash(v) for k, v in self.model.state_dict().items()}
        bad = [k for k in self.baseline if now.get(k) != self.baseline[k]]
        if bad or now.keys() != self.baseline.keys():
            raise AssertionError(f"state differs from baseline: {bad}")

    # ---- forward passes (L2) ------------------------------------------
    def forward(self, x, capture: list[str] | None = None, patch: dict[str, torch.Tensor] | None = None):
        """One budgeted forward pass.

        `capture` lists module names whose outputs to return; `patch` maps module names to
        tensors that replace those modules' outputs (activation patching).
        """
        if self.level not in ("L2", "L3"):
            raise BudgetExhausted(f"{self.level} does not allow forward passes")
        self.budget.consume(1)
        acts: dict[str, torch.Tensor] = {}
        handles = []
        modules = dict(self.model.named_modules())
        for n in capture or []:
            handles.append(
                modules[n].register_forward_hook(
                    lambda m, i, o, n=n: acts.__setitem__(n, o.detach().clone())
                )
            )
        for n, val in (patch or {}).items():
            handles.append(modules[n].register_forward_hook(lambda m, i, o, val=val: val))
        was_training = self.model.training
        self.model.eval()
        try:
            with torch.no_grad():
                out = self.model(x)
        finally:
            for h in handles:
                h.remove()
            self.model.train(was_training)
        return (out, acts) if capture else out


if __name__ == "__main__":
    import argparse

    argparse.ArgumentParser(description="Library: WeightSession, EditPolicy, ForwardBudget, check_agent_code. Import it; it has no CLI.").parse_args()
