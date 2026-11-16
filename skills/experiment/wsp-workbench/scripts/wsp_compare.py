"""Paired before/after comparison, exact sign test and the pre-registered gate."""
from __future__ import annotations

import math


def paired_counts(y, base_pred, new_pred) -> tuple[int, int]:
    """(fixed, broke): samples wrong->right and right->wrong."""
    fixed = broke = 0
    for t, b, n in zip(y, base_pred, new_pred):
        t, b, n = int(t), int(b), int(n)
        fixed += (b != t) and (n == t)
        broke += (b == t) and (n != t)
    return fixed, broke


def sign_test_p(fixed: int, broke: int) -> float:
    """Exact two-sided sign test (binomial, p=0.5) on the discordant pairs."""
    n = fixed + broke
    if n == 0:
        return 1.0
    k = min(fixed, broke)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


def gate(fixed: int, broke: int, base_failures: int, control_fixed: int | None = None) -> dict:
    """Pass iff fixed >= max(3, 20% of base failures), broke <= fixed/4 (and beats the control).

    Thresholds are fixed in advance; the sign-test p is reported, not used to pass.
    """
    need = max(3, math.ceil(0.2 * base_failures))
    checks = {"enough_fixed": fixed >= need, "few_broke": broke <= fixed / 4}
    if control_fixed is not None:
        checks["beats_control"] = fixed > control_fixed
    return {
        "verdict": "PASS" if all(checks.values()) else "FAIL",
        "fixed": fixed,
        "broke": broke,
        "need_fixed": need,
        "base_failures": base_failures,
        "control_fixed": control_fixed,
        "sign_test_p": sign_test_p(fixed, broke),
        "checks": checks,
    }


def per_class_deltas(y, base_pred, new_pred) -> dict[int, dict]:
    """Per true class: n, recall before/after, delta."""
    out: dict[int, dict] = {}
    for c in sorted({int(t) for t in y}):
        idx = [i for i, t in enumerate(y) if int(t) == c]
        b = sum(int(base_pred[i]) == c for i in idx) / len(idx)
        n = sum(int(new_pred[i]) == c for i in idx) / len(idx)
        out[c] = {"n": len(idx), "before": b, "after": n, "delta": n - b}
    return out


if __name__ == "__main__":
    import argparse

    argparse.ArgumentParser(description="Library: paired_counts, sign_test_p, gate, per_class_deltas. Import it; it has no CLI.").parse_args()
