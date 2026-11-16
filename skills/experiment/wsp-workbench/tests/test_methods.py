import pytest
import torch

from wsp_compare import gate, paired_counts
from wsp_methods import (
    apply_eraser,
    apply_eraser_to_next_linear,
    apply_task_vector,
    edit_report,
    fold_eraser_into_next_linear,
    leace_fit,
    localize_by_patching,
    orthogonalize,
    rank_one_key_value,
    scaled_state,
    task_vector,
)
from wsp_session import EditPolicy, PolicyViolation, WeightSession, tensor_hash

D = torch.float64


def lin_model(seed=0):
    torch.manual_seed(seed)
    return torch.nn.Sequential(torch.nn.Linear(6, 8), torch.nn.ReLU(), torch.nn.Linear(8, 4))


def open_session(model, level="L1", budget=0):
    return WeightSession(model, EditPolicy(allowed=[r"."], max_fraction_changed=1.0), level=level, budget=budget)


def test_rank_one_hits_target_and_is_minimal():
    g = torch.Generator().manual_seed(0)
    W = torch.randn(5, 7, generator=g, dtype=D)
    k, v = torch.randn(7, generator=g, dtype=D), torch.randn(5, generator=g, dtype=D)
    A = torch.randn(7, 7, generator=g, dtype=D)
    C = A @ A.T + 7 * torch.eye(7, dtype=D)
    for cov in (None, C):
        W2 = rank_one_key_value(W, k, v, cov)
        assert torch.allclose(W2 @ k, v, atol=1e-10)
        # any other W'' with W'' k = v is further away in the C-weighted norm
        Cw = torch.eye(7, dtype=D) if cov is None else cov
        L = torch.linalg.cholesky(Cw)
        X = torch.randn(5, 7, generator=g, dtype=D)
        alt = W2 + X @ (torch.eye(7, dtype=D) - torch.outer(k, k) / (k @ k))
        assert torch.allclose(alt @ k, v, atol=1e-10)
        assert torch.linalg.norm((W2 - W) @ L) < torch.linalg.norm((alt - W) @ L)


def test_leace_erases_linear_information():
    g = torch.Generator().manual_seed(1)
    n, d = 2000, 6
    Z = (torch.rand(n, 1, generator=g) > 0.5).to(D)
    X = torch.randn(n, d, generator=g, dtype=D) @ torch.randn(d, d, generator=g, dtype=D)
    X = X + Z @ torch.randn(1, d, generator=g, dtype=D) * 2.0  # concept leaks into X linearly

    def r2(F):
        F1 = torch.cat([F, torch.ones(n, 1, dtype=D)], 1)
        coef = torch.linalg.lstsq(F1, Z).solution
        res = Z - F1 @ coef
        return 1 - float(res.pow(2).sum() / (Z - Z.mean()).pow(2).sum())

    assert r2(X) > 0.5
    er = leace_fit(X, Z)
    assert r2(apply_eraser(X, er)) < 1e-9


def test_leace_fold_matches_eraser_then_layer():
    g = torch.Generator().manual_seed(2)
    X = torch.randn(300, 5, generator=g, dtype=D) + 3.0
    Z = X[:, :1] * 0.7 + torch.randn(300, 1, generator=g, dtype=D)
    er = leace_fit(X, Z)
    Wn, bn = torch.randn(4, 5, generator=g, dtype=D), torch.randn(4, generator=g, dtype=D)
    W2, b2 = fold_eraser_into_next_linear(Wn, bn, er)
    x = torch.randn(20, 5, generator=g, dtype=D)
    assert torch.allclose(apply_eraser(x, er) @ Wn.T + bn, x @ W2.T + b2, atol=1e-9)


def test_orthogonalize_removes_component():
    s = open_session(lin_model())
    r = torch.tensor([1.0, -2.0, 0.5, 3.0])
    orthogonalize(s, "2.weight", r)
    assert torch.allclose((r / r.norm()) @ s.param("2.weight"), torch.zeros(8), atol=1e-6)


def test_task_vector_lambda_zero_and_one():
    base, ft = lin_model(0).state_dict(), lin_model(1).state_dict()
    tau = task_vector(ft, base, pattern=r"weight|bias")
    assert set(tau) == set(base)
    for k, v in scaled_state(base, tau, 0.0).items():
        assert torch.equal(v, base[k])
    for k, v in scaled_state(base, tau, 1.0).items():
        assert torch.allclose(v, ft[k], atol=1e-6)
    s = open_session(lin_model(0))
    apply_task_vector(s, task_vector(ft, base, r"^2\."), lam=1.0)
    assert torch.allclose(s.param("2.weight"), ft["2.weight"], atol=1e-6)
    assert torch.equal(s.param("0.weight"), base["0.weight"])  # outside the pattern: untouched
    with pytest.raises(PolicyViolation):  # lam=0 is a no-op, refused by the gate
        apply_task_vector(open_session(lin_model(0)), task_vector(ft, base, r"^2\."), lam=0.0)
    capped = WeightSession(lin_model(0), EditPolicy(allowed=[r"^0\."], max_fraction_changed=1.0))
    with pytest.raises(PolicyViolation):  # allowlist still applies
        apply_task_vector(capped, task_vector(ft, base, r"^2\."), lam=1.0)


def test_localize_by_patching_counts_budget_and_finds_layer():
    model = lin_model()
    s = open_session(model, level="L2", budget=5)
    x_clean, x_corrupt = torch.randn(16, 6), torch.randn(16, 6)
    res = localize_by_patching(s, ["0", "2"], x_clean, x_corrupt, lambda out: -float((out - model(x_clean)).abs().mean()))
    assert s.budget.used == 4  # clean + corrupt + one per layer
    # patching the last layer's output reproduces the clean output exactly
    assert res["effects"]["2"] == pytest.approx(res["clean"] - res["corrupt"], abs=1e-6)
    assert res["effects"]["0"] == pytest.approx(res["clean"] - res["corrupt"], abs=1e-6)


def test_edit_report_slices():
    y = [0, 0, 0, 1, 1, 2]
    base = [1, 1, 0, 1, 1, 2]
    new = [0, 1, 0, 1, 2, 2]
    tgt = [True, True, True, False, False, False]
    used = [True, False, False, False, False, False]
    rep = edit_report(base, new, y, tgt, used)
    assert rep["efficacy"]["fixed"] == 1 and rep["efficacy"]["n"] == 1
    assert rep["generalisation"]["n"] == 2 and rep["generalisation"]["fixed"] == 0
    assert rep["specificity"]["broke"] == 1
    assert rep["specificity"]["per_class"][1]["delta"] == pytest.approx(-0.5)


def test_tensor_hash_changes_with_content_and_is_stable():
    t = torch.arange(10, dtype=torch.float32)
    assert tensor_hash(t) == tensor_hash(t.clone())
    u = t.clone()
    u[3] += 1e-6
    assert tensor_hash(u) != tensor_hash(t)
    assert tensor_hash(t[2:]) == tensor_hash(t[2:].clone())  # storage offset handled


# ---- end to end: planted spurious feature fixed by LEACE ------------------
N_CLS, DIM = 4, 16


def spurious_data(n_per_class, seed, correlated):
    g = torch.Generator().manual_seed(seed)
    protos = torch.randn(N_CLS, DIM - 1, generator=torch.Generator().manual_seed(99))
    y = torch.arange(N_CLS).repeat_interleave(n_per_class)
    if correlated:  # training: background tracks class 0 in 95% of cases
        b = torch.where(y == 0, torch.rand(len(y), generator=g) < 0.95, torch.rand(len(y), generator=g) < 0.05)
    else:  # practice / test: background independent of class
        b = torch.rand(len(y), generator=g) < 0.5
    bg = 3.0 * (2.0 * b.float() - 1.0) + 0.3 * torch.randn(len(y), generator=g)
    rest = 0.45 * protos[y] + torch.randn(len(y), DIM - 1, generator=g)
    return torch.cat([bg[:, None], rest], 1), y, b


class Net(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.net = torch.nn.Sequential(torch.nn.Linear(DIM, 32), torch.nn.ReLU(), torch.nn.Linear(32, N_CLS))

    def forward(self, x):
        return self.net(x)


@pytest.fixture(scope="module")
def spurious_model():
    torch.manual_seed(0)
    x, y, _ = spurious_data(300, seed=1, correlated=True)
    model = Net()
    opt = torch.optim.Adam(model.parameters(), lr=1e-2)
    for _ in range(80):  # fixture only: creates the model under test
        opt.zero_grad()
        torch.nn.functional.cross_entropy(model(x), y).backward()
        opt.step()
    return model.eval()


def test_leace_fixes_planted_spurious_feature(spurious_model, capsys):
    model = spurious_model
    original = {k: v.clone() for k, v in model.state_dict().items()}
    xp, yp, bp = spurious_data(200, seed=2, correlated=False)
    xh, yh, bh = spurious_data(300, seed=3, correlated=False)
    yp_l, yh_l = yp.tolist(), yh.tolist()

    policy = EditPolicy(allowed=[r"^net\.2\.(weight|bias)$"], forbidden=[r"^net\.0\."], max_fraction_changed=1.0)
    sess = WeightSession(model, policy, level="L2", budget=5)

    out, acts = sess.forward(xp, capture=["net.1"])
    base_p = out.argmax(1).tolist()
    base_h = sess.forward(xh).argmax(1).tolist()
    base_failures = sum(a != b for a, b in zip(yp_l, base_p))
    assert base_failures / len(yp_l) > 0.2  # the shortcut hurts when the background decorrelates

    hidden = acts["net.1"]
    Z = bp.float()[:, None]
    shuffled = Z[torch.randperm(len(Z), generator=torch.Generator().manual_seed(4))]

    # control first: erase a concept that is independent of the data
    ids = apply_eraser_to_next_linear(sess, "net.2.weight", "net.2.bias", leace_fit(hidden, shuffled))
    c_fixed, _ = paired_counts(yp_l, base_p, sess.forward(xp).argmax(1).tolist())
    for i in ids:
        sess.undo(i)
    sess.assert_baseline()

    apply_eraser_to_next_linear(sess, "net.2.weight", "net.2.bias", leace_fit(hidden, Z), note="erase background")
    fixed, broke = paired_counts(yp_l, base_p, sess.forward(xp).argmax(1).tolist())
    verdict = gate(fixed, broke, base_failures, control_fixed=c_fixed)
    assert verdict["verdict"] == "PASS", verdict

    # held-out, once: efficacy on the failing slice, specificity on the rest
    new_h = sess.forward(xh).argmax(1).tolist()
    # target = class 0 without its usual background; specificity = classes 1-3 (never touched by the shortcut)
    off = [(t == 0 and not bool(b)) for t, b in zip(yh_l, bh)]
    on = [(t == 0 and bool(b)) for t, b in zip(yh_l, bh)]
    rep = edit_report(base_h, new_h, yh_l, [t == 0 for t in yh_l])
    gen_off = edit_report(base_h, new_h, yh_l, off)["generalisation"]
    gen_on = edit_report(base_h, new_h, yh_l, on)["generalisation"]
    spec = rep["specificity"]
    assert gen_off["after"] - gen_off["before"] >= 0.15
    assert spec["after"] >= spec["before"] - 0.02
    for c, d in spec["per_class"].items():
        assert d["delta"] >= -0.05, (c, d)

    sess.undo_all()
    sess.assert_baseline()
    for k, v in original.items():
        assert torch.equal(model.state_dict()[k], v)
    with capsys.disabled():
        print(
            f"\n[leace e2e] practice gate={verdict['verdict']} fixed={fixed} broke={broke} need={verdict['need_fixed']}"
            f" control_fixed={c_fixed} p={verdict['sign_test_p']:.2e}"
            f"\n[leace e2e] held-out class 0, background off: {gen_off['before']:.2f}->{gen_off['after']:.2f}"
            f" (n={gen_off['n']}); class 0, background on: {gen_on['before']:.2f}->{gen_on['after']:.2f}"
            f" (n={gen_on['n']}); classes 1-3 accuracy {spec['before']:.3f}->{spec['after']:.3f} (broke={spec['broke']},"
            f" fixed={spec['fixed']})"
            f"\n[leace e2e] per-class recall (classes 1-3): "
            + ", ".join(f"{c}: {d['before']:.2f}->{d['after']:.2f}" for c, d in spec["per_class"].items())
        )
