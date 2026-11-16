"""Closed-form weight-editing methods, applied through a WeightSession (no gradients).

These are small closed-form variants inspired by published methods; see
references/methods.md for how they differ from the papers.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).parent))
from wsp_compare import paired_counts, per_class_deltas  # noqa: E402
from wsp_session import WeightSession  # noqa: E402


# ---- rank-one key/value edit (ROME-style least squares) -------------------
def rank_one_vectors(W, k, v_target, C=None):
    """Return (a, b) with W' = W + a bᵀ, the minimal change (w.r.t. key covariance C) giving W' k = v."""
    W, k, v = W.double(), k.double().flatten(), v_target.double().flatten()
    ck = k if C is None else torch.linalg.solve(C.double(), k)
    return v - W @ k, ck / (ck @ k)


def rank_one_key_value(W, k, v_target, C=None):
    """W' = W + (v - W k)(C^-1 k)ᵀ / ((C^-1 k)ᵀ k); C defaults to the identity."""
    a, b = rank_one_vectors(W, k, v_target, C)
    return (W.double() + torch.outer(a, b)).to(W.dtype)


def apply_rank_one(session: WeightSession, name, k, v_target, C=None, note="") -> int:
    a, b = rank_one_vectors(session.param(name), k, v_target, C)
    return session.add_rank1(name, a, b, scale=1.0, note=note or "rank_one_key_value")


# ---- LEACE linear concept erasure ----------------------------------------
def leace_fit(X, Z, eps: float = 1e-8) -> dict:
    """Fit the LEACE eraser r(x) = x - W⁺ P W (x - mu) for features X (n, d) and concept Z (n, k).

    W = Sigma_xx^(-1/2) (eigenvalues floored at eps * largest), P projects onto the column
    space of W Sigma_xz. Afterwards no linear map of r(X) is correlated with Z.
    """
    X, Z = X.double(), Z.double().reshape(len(X), -1)
    n = X.shape[0]
    mu = X.mean(0)
    Xc, Zc = X - mu, Z - Z.mean(0)
    sxx = Xc.T @ Xc / (n - 1)
    sxz = Xc.T @ Zc / (n - 1)
    evals, U = torch.linalg.eigh(sxx)
    evals = evals.clamp_min(eps * float(evals.max()))
    W = U @ torch.diag(evals.rsqrt()) @ U.T
    W_pinv = U @ torch.diag(evals.sqrt()) @ U.T
    Uq, S, _ = torch.linalg.svd(W @ sxz, full_matrices=False)
    Q = Uq[:, S > 1e-10 * max(float(S.max()), 1e-300)]
    P = Q @ Q.T
    return {"mean": mu, "W": W, "W_pinv": W_pinv, "P": P, "E": W_pinv @ P @ W}


def apply_eraser(x, eraser):
    """r(x) = x - W⁺ P W (x - mu) for x of shape (n, d)."""
    x = x.double()
    return x - (x - eraser["mean"]) @ eraser["E"].T


def fold_eraser_into_next_linear(W_next, b_next, eraser):
    """Return (W_next (I - E), b_next + W_next E mu) with E = W⁺ P W, so that
    W_next r(x) + b_next == W_new x + b_new."""
    E, mu = eraser["E"], eraser["mean"]
    W = W_next.double()
    b = torch.zeros(W.shape[0], dtype=torch.float64) if b_next is None else b_next.double()
    I = torch.eye(E.shape[0], dtype=torch.float64)
    return (W @ (I - E)).to(W_next.dtype), (b + W @ E @ mu).to(W_next.dtype)


def apply_eraser_to_next_linear(session: WeightSession, weight_name, bias_name, eraser, note="") -> list[int]:
    """Edit the linear layer that consumes the erased features (through the session gate)."""
    W, b = session.param(weight_name), session.param(bias_name)
    W_new, b_new = fold_eraser_into_next_linear(W, b, eraser)
    note = note or "leace folded into next linear"
    i1 = session.assign(weight_name, torch.arange(W.numel()), W_new.flatten(), note=note)
    i2 = session.assign(bias_name, torch.arange(b.numel()), b_new.flatten(), note=note + " (bias)")
    return [i2, i1]  # undo order


# ---- orthogonalisation (Arditi et al.) -----------------------------------
def orthogonalize(session: WeightSession, name, r, cols=None, note="") -> int:
    """W' = W - r rᵀ W (r unit, in W's output space): project_out with alpha=1."""
    return session.project_out(name, r, alpha=1.0, cols=cols, note=note or "orthogonalize")


# ---- task arithmetic (Ilharco et al.) ------------------------------------
def task_vector(finetuned_state, base_state, pattern=".") -> dict[str, torch.Tensor]:
    """tau = finetuned - base for floating tensors whose name matches `pattern` and shapes agree."""
    return {
        k: finetuned_state[k].detach().float() - base_state[k].detach().float()
        for k in base_state
        if re.search(pattern, k)
        and k in finetuned_state
        and finetuned_state[k].shape == base_state[k].shape
        and base_state[k].is_floating_point()
    }


def scaled_state(base_state, tau, lam: float) -> dict[str, torch.Tensor]:
    """base + lam * tau, as a pure function (no session)."""
    out = {k: v.clone() for k, v in base_state.items()}
    for k, t in tau.items():
        out[k] = (base_state[k].float() + lam * t).to(base_state[k].dtype)
    return out


def apply_task_vector(session: WeightSession, tau, lam: float, note="") -> list[int]:
    """Move the session's current weights by lam * tau, tensor by tensor, through the gate.

    lam = 0 changes nothing, so the gate refuses it (a no-op is not an edit).
    """
    ids = []
    for name, t in tau.items():
        cur = session.param(name)
        new = (cur.float() + lam * t).to(cur.dtype)
        ids.append(
            session.assign(name, torch.arange(cur.numel()), new.flatten(), note=note or f"task vector lam={lam}")
        )
    return ids


# ---- localisation by activation patching ----------------------------------
def localize_by_patching(session: WeightSession, layer_names, x_clean, x_corrupt, metric_fn) -> dict:
    """Per-layer effect of patching clean activations into a corrupt run (L2).

    Costs 2 + len(layer_names) forward passes. `metric_fn(logits) -> float` is higher when the
    behaviour is "clean". effect = metric(patched) - metric(corrupt); x_clean and x_corrupt must
    be paired (same batch size).
    """
    out_clean, acts = session.forward(x_clean, capture=list(layer_names))
    m_clean = float(metric_fn(out_clean))
    m_corrupt = float(metric_fn(session.forward(x_corrupt)))
    effects = {}
    for n in layer_names:
        effects[n] = float(metric_fn(session.forward(x_corrupt, patch={n: acts[n]}))) - m_corrupt
    return {"clean": m_clean, "corrupt": m_corrupt, "effects": effects}


# ---- efficacy / generalisation / specificity ------------------------------
def _slice(labels, base, new, idx):
    if not idx:
        return None
    y, b, n = ([s[i] for i in idx] for s in (labels, base, new))
    fixed, broke = paired_counts(y, b, n)
    return {
        "n": len(idx),
        "before": sum(int(p) == int(t) for p, t in zip(b, y)) / len(idx),
        "after": sum(int(p) == int(t) for p, t in zip(n, y)) / len(idx),
        "fixed": fixed,
        "broke": broke,
    }


def edit_report(base_preds, new_preds, labels, target_mask, used_mask=None) -> dict:
    """Efficacy / generalisation / specificity.

    target_mask marks the slice the edit is meant to change. used_mask marks target samples used
    to build the edit: efficacy is measured on those, generalisation on the other target samples.
    Without used_mask all target samples count as generalisation (nothing was used to build it).
    Specificity covers every non-target sample, with per-class deltas.
    """
    base, new, y = (list(map(int, v)) for v in (base_preds, new_preds, labels))
    tgt = [bool(m) for m in target_mask]
    used = [bool(m) for m in used_mask] if used_mask is not None else [False] * len(y)
    ix = lambda f: [i for i in range(len(y)) if f(i)]  # noqa: E731
    non_target = ix(lambda i: not tgt[i])
    return {
        "efficacy": _slice(y, base, new, ix(lambda i: tgt[i] and used[i])),
        "generalisation": _slice(y, base, new, ix(lambda i: tgt[i] and not used[i])),
        "specificity": {
            **(_slice(y, base, new, non_target) or {}),
            "per_class": per_class_deltas(
                [y[i] for i in non_target], [base[i] for i in non_target], [new[i] for i in non_target]
            )
            if non_target
            else {},
        },
    }


if __name__ == "__main__":
    import argparse

    argparse.ArgumentParser(
        description="Library: rank_one_key_value, leace_fit, fold_eraser_into_next_linear, orthogonalize, "
        "task_vector, localize_by_patching, edit_report. Import it; it has no CLI."
    ).parse_args()
