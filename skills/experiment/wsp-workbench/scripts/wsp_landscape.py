"""Error-surface diagnostics: loss along paths and slices (L2) and local geometry (L3).

Gradients and Hessian-vector products here are MEASUREMENTS. They never update weights:
every function runs inside `session.scratch()`, which restores the weights and checks the
parameter hashes on exit. Only these trusted functions may use autograd; agent-written code
is still checked by `check_agent_code`.

`batches` is a list of (x, y); `loss_fn(logits, y)` returns a scalar tensor.
"""
from __future__ import annotations

import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).parent))
from wsp_session import BudgetExhausted, WeightSession  # noqa: E402


# ---- helpers ---------------------------------------------------------------
def _loss_no_grad(session: WeightSession, loss_fn, batches) -> float:
    """Mean loss over batches; one budgeted forward pass per batch."""
    return float(sum(float(loss_fn(session.forward(x), y)) for x, y in batches) / len(batches))


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
                k: ((1 - t) * state_a[k].float() + t * state_b[k].float()).to(state_a[k].dtype)
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
        d = torch.randn(p.shape, generator=g, dtype=p.dtype)
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
            v = torch.randn(g.numel(), generator=gen, dtype=g.dtype)
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
                v = torch.randn(g.numel(), generator=gen, dtype=g.dtype)
                v = v / v.norm()
                for _ in range(iters):
                    w = hvp(v) + shift * v
                    v = w / w.norm()
                lam_max = float(v @ hvp(v))
                u = torch.randn(g.numel(), generator=gen, dtype=g.dtype)
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
            "gradient_evaluations": 1 + 5 + 2 * iters}


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


if __name__ == "__main__":
    import argparse

    argparse.ArgumentParser(
        description="Library: landscape_path, landscape_slice, local_geometry (L3), reachability_report. "
        "Import it; it has no CLI."
    ).parse_args()
