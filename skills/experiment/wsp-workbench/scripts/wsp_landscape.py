"""Error-surface diagnostics: loss along paths and slices (L2) and local geometry (L3).

Gradients and Hessian-vector products here are MEASUREMENTS. They never update weights:
every function runs inside `session.scratch()`, which restores the weights and checks the
parameter hashes on exit. Only these trusted functions may use autograd; agent-written code
is still checked by `check_agent_code`.

`batches` is a list of (x, y); `loss_fn(logits, y)` returns a scalar tensor.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import torch
except ImportError:  # torch lives in the cpu / cu126 / cu132 extras
    raise SystemExit("""torch is not installed. Set up the skill environment once (pick by the CUDA Version shown by nvidia-smi):
  uv sync --project <skill dir> --extra cu132   # CUDA Version >= 13.2
  uv sync --project <skill dir> --extra cu126   # CUDA 12.x
  uv sync --project <skill dir> --extra cpu     # no NVIDIA GPU
(add --extra dev to run the tests; see README.md)""")

sys.path.insert(0, str(Path(__file__).parent))
from wsp_session import BudgetExhausted, WeightSession  # noqa: E402


# ---- helpers ---------------------------------------------------------------
def _loss_no_grad(session: WeightSession, loss_fn, batches) -> float:
    """Mean loss over batches; one budgeted forward pass per batch."""
    return float(sum(float(loss_fn(session.forward_inputs(x), y)) for x, y in batches) / len(batches))


def _need_passes(session: WeightSession, n: int) -> None:
    session.require_level("L2")
    if session.budget.remaining < n:
        raise BudgetExhausted(
            f"needs {n} forward passes, only {session.budget.remaining} left in the budget"
        )


# ---- L2: loss along the straight line between two weight states ---------------
def landscape_path(session, state_a, state_b, loss_fn, batches, n_points=21, mono_tol=1e-9) -> dict:
    """Loss along (1 - t) a + t b (floating tensors; other buffers come from a).

    barrier = max_t [L(t) - ((1 - t) L(0) + t L(1))] (Frankle et al., ICML 2020).
    monotone is True if the losses never go up (or never go down) along t.
    Costs n_points * len(batches) forward passes.
    """
    _need_passes(session, n_points * len(batches))
    ts = torch.linspace(0, 1, n_points)
    losses = []
    with session.scratch():
        for t in ts.tolist():
            mixed = {
                k: ((1 - t) * state_a[k].float() + t * state_b[k].float().to(state_a[k].device)).to(state_a[k].dtype)
                if state_a[k].is_floating_point()
                else state_a[k]
                for k in state_a
            }
            session.model.load_state_dict(mixed)
            losses.append(_loss_no_grad(session, loss_fn, batches))
    l0, l1 = losses[0], losses[-1]
    barrier = max(l - ((1 - t) * l0 + t * l1) for t, l in zip(ts.tolist(), losses))
    diffs = [b - a for a, b in zip(losses, losses[1:])]
    monotone = all(d <= mono_tol for d in diffs) or all(d >= -mono_tol for d in diffs)
    return {"level": "L2", "t": ts.tolist(), "losses": losses, "barrier": barrier, "monotone": monotone,
            "forward_passes": n_points * len(batches)}


# ---- L2: 1-D slice along a filter-normalised random direction -------------------
def filter_normalized_direction(params, seed: int) -> list[torch.Tensor]:
    """Random direction, rescaled per filter (row) to the weight filter's norm (Li et al., 2018).

    Biases and other 1-D parameters get a zero direction, as in the paper.
    """
    g = torch.Generator().manual_seed(seed)
    out = []
    for p in params:
        if p.ndim < 2:
            out.append(torch.zeros_like(p))
            continue
        d = torch.randn(p.shape, generator=g, dtype=p.dtype).to(p.device)  # CPU generator, then model device
        w = p.detach().reshape(p.shape[0], -1)
        dn = d.reshape(p.shape[0], -1)
        dn = dn / (dn.norm(dim=1, keepdim=True) + 1e-10) * w.norm(dim=1, keepdim=True)
        out.append(dn.reshape(p.shape))
    return out


def landscape_slice(session, loss_fn, batches, n_points=21, seed=0, span=1.0) -> dict:
    """Loss at theta + alpha d for alpha in [-span, span], d filter-normalised. Costs n_points * len(batches)."""
    _need_passes(session, n_points * len(batches))
    params = list(session.model.parameters())
    center = [p.detach().clone() for p in params]
    d = filter_normalized_direction(center, seed)
    alphas = torch.linspace(-span, span, n_points).tolist()
    losses = []
    with session.scratch():
        for a in alphas:
            with torch.no_grad():
                for p, c, di in zip(params, center, d):
                    p.copy_(c + a * di)
            losses.append(_loss_no_grad(session, loss_fn, batches))
    return {"level": "L2", "alpha": alphas, "losses": losses, "seed": seed,
            "forward_passes": n_points * len(batches)}


# ---- L3: local geometry by gradient and Hessian-vector products --------------
def _flat(ts) -> torch.Tensor:
    return torch.cat([t.reshape(-1) for t in ts])


def local_geometry(session, loss_fn, batches, iters=20, grad_tol=1e-2, eig_tol=1e-3, seed=0) -> dict:
    """Gradient norm, lambda_max and lambda_min of the Hessian by power iteration (L3 only).

    Evaluations charged to the gradient budget: 1 (gradient) + 5 (spectral-radius estimate)
    + iters (lambda_max on H + sI) + iters (lambda_min on lambda_max I - H).
    Labels are heuristics: not_critical if |grad| > grad_tol; else saddle if lambda_min < -eig_tol;
    else minimum_like. sharpness = lambda_max. Power iteration is approximate.
    """
    session.require_level("L3")
    session.grad_budget.consume(1 + 5 + 2 * iters)
    params = list(session.model.parameters())
    with session.scratch():
        for p in params:
            p.requires_grad_(True)
        session.model.eval()
        try:
            loss = sum(loss_fn(session.model(x), y) for x, y in batches) / len(batches)
            grads = torch.autograd.grad(loss, params, create_graph=True)
            g = _flat(grads)
            gnorm = float(g.detach().norm())

            def hvp(v: torch.Tensor) -> torch.Tensor:
                hv = torch.autograd.grad(g @ v, params, retain_graph=True)
                return _flat(hv).detach()

            gen = torch.Generator().manual_seed(seed)
            v = torch.randn(g.numel(), generator=gen, dtype=g.dtype).to(g.device)
            v = v / v.norm()
            rho = 0.0
            for _ in range(5):  # crude spectral radius, for a shift that makes the top end dominant
                hv = hvp(v)
                rho = max(rho, float(hv.norm()))
                if float(hv.norm()) == 0.0:
                    break
                v = hv / hv.norm()
            if rho == 0.0:
                lam_max = lam_min = 0.0
            else:
                shift = 1.5 * rho
                v = torch.randn(g.numel(), generator=gen, dtype=g.dtype).to(g.device)
                v = v / v.norm()
                for _ in range(iters):
                    w = hvp(v) + shift * v
                    v = w / w.norm()
                lam_max = float(v @ hvp(v))
                u = torch.randn(g.numel(), generator=gen, dtype=g.dtype).to(g.device)
                u = u / u.norm()
                for _ in range(iters):
                    w = lam_max * u - hvp(u)
                    if float(w.norm()) == 0.0:
                        break
                    u = w / w.norm()
                lam_min = float(u @ hvp(u))
        finally:
            for p in params:
                p.requires_grad_(False)
    if gnorm > grad_tol:
        label = "not_critical"
    elif lam_min < -eig_tol:
        label = "saddle"
    else:
        label = "minimum_like"
    return {"level": "L3", "loss": float(loss.detach()), "grad_norm": gnorm, "lambda_max": lam_max,
            "lambda_min": lam_min, "sharpness": lam_max, "label": label,
            "thresholds": {"grad_tol": grad_tol, "eig_tol": eig_tol, "heuristic": True},
            "gradient_evaluations": 1 + 5 + 2 * iters, "env": session.env}


# ---- combining evidence --------------------------------------------------------
def reachability_report(target_exists, path=None, geometry=None, barrier_tol=0.05) -> dict:
    """Combine WSP existence evidence, a path result and current geometry. Never a guarantee.

    target_exists: True / False / None (an edited or constructed point met the target and passed the gate).
    path: result of landscape_path from the current point to that target point, or None.
    geometry: result of local_geometry at the current point, or None.
    barrier_tol: absolute loss units below which a barrier counts as none (a heuristic; set it to your loss scale).
    """
    path_state = "unknown" if path is None else ("barrier_free" if path["barrier"] <= barrier_tol else "barrier")
    recs: list[dict] = []

    def rec(text):
        recs.append({"text": text, "tag": "heuristic"})

    if target_exists is False:
        verdict = "target_not_found"
        rec("Suspect capacity or missing upstream information (the Petcu L-vs-1 case): a bigger layer or a better "
            "feature may be needed, not a better optimiser.")
    elif target_exists is None:
        verdict = "target_unknown"
        rec("No evidence that a target point exists. Run workflow B (edit and gate) before judging reachability.")
    elif path_state == "barrier_free":
        verdict = "reachable_by_straight_path"
        rec("A straight line to the target does not rise: training has a plausible route; this is not a guarantee.")
    elif path_state == "barrier":
        verdict = "separated_by_barrier"
        rec("Start from the edited point instead of training toward it, or change the optimiser or normalisation "
            "(different basins are connected only through a higher-loss region).")
    else:
        verdict = "target_exists_path_unknown"
        rec("Run landscape_path from the current weights to the target point to see whether a barrier lies between them.")

    if geometry is not None:
        lab = geometry["label"]
        if lab == "not_critical":
            rec("Gradient is clearly non-zero. If loss is also flat, suspect a plateau: lower the learning rate "
                "or use an adaptive optimiser; if sharpness is large, lower the learning rate first.")
        elif lab == "saddle":
            rec("Near a saddle (negative curvature): momentum or small-batch noise helps training escape.")
        else:
            rec("Near a minimum-like point: if loss is still high, training from here is stuck in this basin; "
                "see the path result for whether a lower region is connected.")
    return {
        "verdict": verdict,
        "evidence": {"target_exists": "unknown" if target_exists is None else ("yes" if target_exists else "no"),
                     "path": path_state, "geometry": None if geometry is None else geometry["label"]},
        "levels_used": sorted({r["level"] for r in (path, geometry) if r}),
        "recommendations": recs,
        "caveat": "Heuristic diagnosis from measurements; it never guarantees that training can reach the target.",
    }


# ---- checkpoint trajectory: net displacement between saved checkpoints ----------
def _cos(a: torch.Tensor, b: torch.Tensor):
    na, nb = float(a.norm()), float(b.norm())
    return None if na == 0 or nb == 0 else float(a @ b) / (na * nb)


def _delta_stats(dW: torch.Tensor, w_start: torch.Tensor, top_k: int) -> tuple[dict, torch.Tensor | None]:
    """Norms, top-k singular-value energy share and the principal left subspace of one displacement."""
    fro = float(dW.norm())
    w_norm = float(w_start.norm())
    info = {"fro": fro, "relative": fro / w_norm if w_norm > 0 else None}
    if dW.ndim < 2:
        return info, None
    s_vals_u = torch.linalg.svd(dW.reshape(dW.shape[0], -1), full_matrices=False)
    U, S = s_vals_u[0], s_vals_u[1]
    total = float((S ** 2).sum())
    k = min(top_k, len(S))
    info["top_k_energy_share"] = float((S[:k] ** 2).sum()) / total if total > 0 else None
    rank = int((S > 1e-6 * float(S[0])).sum()) if total > 0 else 0
    kk = min(k, rank)
    return info, (U[:, :kk] if kk > 0 else None)


def checkpoint_trajectory(states, pattern=".", top_k=3, session=None, loss_fn=None, batches=None, n_points=11) -> dict:
    """Describe the net displacement between time-ordered checkpoints (state dicts).

    This is NOT the direction training moved along: checkpoints are snapshots, and the path between
    two of them is not observed. Per segment and matching floating tensor: ||dW||_F, relative norm
    ||dW|| / ||W_start|| and, for >=2-D tensors (viewed as (out, -1)), the top-k singular-value energy
    share of dW. Between consecutive segments (needs >= 3 checkpoints): cosine of the flattened dW and
    principal-subspace overlap ||U_a^T U_b||_F^2 / k, with k the smaller numerical rank (singular values above 1e-6 of the largest; <= top_k).
    If session, loss_fn and batches are all given (L2), also the loss along the straight line between
    each consecutive pair (landscape_path); the budget is checked before anything runs.
    """
    if len(states) < 2:
        raise ValueError("need at least two checkpoints")
    given = [x is not None for x in (session, loss_fn, batches)]
    if any(given) and not all(given):
        raise ValueError("pass session, loss_fn and batches together (or none of them)")
    names = [k for k, v in states[0].items()
             if re.search(pattern, k) and v.is_floating_point() and all(k in s and s[k].shape == v.shape for s in states)]
    if not names:
        raise ValueError(f"no floating tensor matches {pattern!r} in every checkpoint")
    if session is not None:
        _need_passes(session, (len(states) - 1) * n_points * len(batches))

    def dev(st, k):
        return st[k].detach().cpu().double()

    deltas, segments, subspaces = [], [], []
    for i in range(len(states) - 1):
        per, dws, subs = {}, {}, {}
        for k in names:
            dW = dev(states[i + 1], k) - dev(states[i], k)
            per[k], subs[k] = _delta_stats(dW, dev(states[i], k), top_k)
            dws[k] = dW
        flat = torch.cat([d.reshape(-1) for d in dws.values()])
        w0 = torch.cat([dev(states[i], k).reshape(-1) for k in names])
        segments.append({"from": i, "to": i + 1, "tensors": per, "total_fro": float(flat.norm()),
                         "total_relative": float(flat.norm() / w0.norm()) if float(w0.norm()) > 0 else None})
        deltas.append(dws)
        subspaces.append(subs)

    consecutive = []
    for i in range(len(deltas) - 1):
        per = {}
        for k in names:
            row = {"cosine": _cos(deltas[i][k].reshape(-1), deltas[i + 1][k].reshape(-1))}
            ua, ub = subspaces[i][k], subspaces[i + 1][k]
            if ua is not None and ub is not None:
                kk = min(ua.shape[1], ub.shape[1])
                row["subspace_overlap"] = float((ua[:, :kk].T @ ub[:, :kk]).pow(2).sum()) / kk
            per[k] = row
        fa = torch.cat([d.reshape(-1) for d in deltas[i].values()])
        fb = torch.cat([d.reshape(-1) for d in deltas[i + 1].values()])
        consecutive.append({"segments": [i, i + 1], "tensors": per, "global_cosine": _cos(fa, fb)})

    net_per, net_dws = {}, {}
    for k in names:
        dW = dev(states[-1], k) - dev(states[0], k)
        net_per[k], _ = _delta_stats(dW, dev(states[0], k), top_k)
        net_dws[k] = dW
    net_flat = torch.cat([d.reshape(-1) for d in net_dws.values()])
    path_len = sum(s["total_fro"] for s in segments)
    net = {"from": 0, "to": len(states) - 1, "tensors": net_per, "total_fro": float(net_flat.norm()),
           "net_over_path_length": float(net_flat.norm()) / path_len if path_len > 0 else None}

    notes = ["These are net displacements between saved checkpoints, not the direction training moved along: "
             "the path between two checkpoints is unobserved."]
    if len(states) == 2:
        notes.append("Only two checkpoints: one segment. Direction consistency needs at least 3 checkpoints.")
    piecewise = None
    if session is not None:
        paths = [landscape_path(session, states[i], states[i + 1], loss_fn, batches, n_points)
                 for i in range(len(states) - 1)]
        piecewise = {"paths": paths, "max_barrier": max(p["barrier"] for p in paths),
                     "forward_passes": sum(p["forward_passes"] for p in paths)}
    return {"level": "L2" if session is not None else "L1", "env": None if session is None else session.env, "tensors": names, "segments": segments,
            "consecutive": consecutive, "net": net, "piecewise_path": piecewise, "notes": notes}


if __name__ == "__main__":
    import argparse

    argparse.ArgumentParser(
        description="Library: landscape_path, landscape_slice, local_geometry (L3), reachability_report, checkpoint_trajectory. "
        "Import it; it has no CLI."
    ).parse_args()
