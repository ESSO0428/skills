import pytest
import torch

from wsp_landscape import (
    landscape_path,
    landscape_slice,
    local_geometry,
    reachability_report,
)
from wsp_session import AccessDenied, BudgetExhausted, EditPolicy, WeightSession, check_agent_code

POLICY = EditPolicy(allowed=["."], max_fraction_changed=1.0)
CE = torch.nn.functional.cross_entropy


class MLP(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.net = torch.nn.Sequential(torch.nn.Linear(16, 32), torch.nn.ReLU(), torch.nn.Linear(32, 3))

    def forward(self, x):
        return self.net(x)


@pytest.fixture(scope="module")
def trained():
    torch.manual_seed(0)
    protos = torch.randn(3, 16) * 1.0
    y = torch.arange(3).repeat_interleave(60)
    x = protos[y] + torch.randn(len(y), 16)
    model = MLP()
    opt = torch.optim.Adam(model.parameters(), lr=1e-2)
    for _ in range(300):  # fixture only: creates the model under test
        opt.zero_grad()
        CE(model(x), y).backward()
        opt.step()
    return model.eval(), [(x, y)]


def permuted_state(model, seed=1):
    st = {k: v.clone() for k, v in model.state_dict().items()}
    perm = torch.randperm(32, generator=torch.Generator().manual_seed(seed))
    st["net.0.weight"] = st["net.0.weight"][perm]
    st["net.0.bias"] = st["net.0.bias"][perm]
    st["net.2.weight"] = st["net.2.weight"][:, perm]
    return st


def test_barrier_between_permuted_copies_and_flat_self_path(trained, capsys):
    model, batches = trained
    a = {k: v.clone() for k, v in model.state_dict().items()}
    b = permuted_state(model)
    with torch.no_grad():  # the permuted copy is functionally identical
        clone = MLP()
        clone.load_state_dict(b)
        assert torch.allclose(clone(batches[0][0]), model(batches[0][0]), atol=1e-5)
    sess = WeightSession(model, POLICY, access_level="L2", budget=100)
    before = sess._hashes()
    res = landscape_path(sess, a, b, CE, batches, n_points=21)
    assert sess._hashes() == before
    assert sess.budget.used == 21 * len(batches) == res["forward_passes"]
    assert res["losses"][0] == pytest.approx(res["losses"][-1], abs=1e-5)
    assert res["barrier"] > 0.05 and not res["monotone"]
    flat = landscape_path(sess, a, a, CE, batches, n_points=11)
    assert abs(flat["barrier"]) < 1e-6 and flat["monotone"]
    assert max(flat["losses"]) - min(flat["losses"]) < 1e-6
    assert sess._hashes() == before
    with capsys.disabled():
        print(f"\n[landscape] permuted-copy path: ends={res['losses'][0]:.4f} max={max(res['losses']):.4f} "
              f"barrier={res['barrier']:.4f}; self path barrier={flat['barrier']:.2e}")


def test_path_refuses_without_budget(trained):
    model, batches = trained
    st = {k: v.clone() for k, v in model.state_dict().items()}
    sess = WeightSession(model, POLICY, access_level="L2", budget=5)
    with pytest.raises(BudgetExhausted):
        landscape_path(sess, st, st, CE, batches, n_points=21)
    assert sess.budget.used == 0  # refused before spending anything
    with pytest.raises(AccessDenied):
        landscape_path(WeightSession(model, POLICY, access_level="L1"), st, st, CE, batches)


def test_slice_restores_weights_and_counts_passes(trained):
    model, batches = trained
    sess = WeightSession(model, POLICY, access_level="L2", budget=50)
    before = sess._hashes()
    res = landscape_slice(sess, CE, batches * 2, n_points=9, seed=3)
    assert sess._hashes() == before
    assert sess.budget.used == 18 == res["forward_passes"]
    mid = res["losses"][4]
    assert res["alpha"][4] == 0.0
    assert max(res["losses"]) > mid  # moving away from a trained point raises the loss
    again = landscape_slice(WeightSession(model, POLICY, access_level="L2", budget=50), CE, batches * 2, 9, seed=3)
    assert again["losses"] == res["losses"]  # same seed, same slice


class Product(torch.nn.Module):
    """y = w1 * w2 * x."""

    def __init__(self, w1, w2):
        super().__init__()
        self.w1 = torch.nn.Parameter(torch.tensor(float(w1)))
        self.w2 = torch.nn.Parameter(torch.tensor(float(w2)))

    def forward(self, x):
        return self.w1 * self.w2 * x


MSE = torch.nn.functional.mse_loss
ONE = [(torch.tensor([1.0]), torch.tensor([1.0]))]


def test_saddle_and_minimum_labels_match_analytic_values(capsys):
    saddle = WeightSession(Product(0, 0), POLICY, access_level="L3", grad_budget=100)
    g0 = local_geometry(saddle, MSE, ONE, iters=20)
    assert g0["label"] == "saddle" and g0["grad_norm"] < 1e-8
    assert g0["lambda_max"] == pytest.approx(2.0, abs=1e-3)
    assert g0["lambda_min"] == pytest.approx(-2.0, abs=1e-3)

    mini = WeightSession(Product(1, 1), POLICY, access_level="L3", grad_budget=100)
    g1 = local_geometry(mini, MSE, ONE, iters=20)
    assert g1["label"] == "minimum_like"
    assert g1["lambda_max"] == pytest.approx(4.0, abs=1e-3)  # H = [[2,2],[2,2]]
    assert g1["lambda_min"] == pytest.approx(0.0, abs=1e-3)
    assert g1["sharpness"] == g1["lambda_max"] and g1["level"] == "L3"

    away = WeightSession(Product(2, 2), POLICY, access_level="L3", grad_budget=100)
    assert local_geometry(away, MSE, ONE)["label"] == "not_critical"
    with capsys.disabled():
        print(f"\n[geometry] saddle (0,0): lam_max={g0['lambda_max']:.5f} (2) lam_min={g0['lambda_min']:.5f} (-2) "
              f"grad={g0['grad_norm']:.1e}; minimum (1,1): lam_max={g1['lambda_max']:.5f} (4) "
              f"lam_min={g1['lambda_min']:.5f} (0)")


def test_l3_refusal_budget_and_weights_unchanged(trained):
    model, batches = trained
    for level in ("L1", "L2"):
        with pytest.raises(AccessDenied):
            local_geometry(WeightSession(model, POLICY, access_level=level, budget=10), CE, batches)
    sess = WeightSession(model, POLICY, access_level="L3", grad_budget=10)
    with pytest.raises(BudgetExhausted):  # needs 1 + 5 + 2*iters = 46
        local_geometry(sess, CE, batches, iters=20)
    sess = WeightSession(model, POLICY, access_level="L3", grad_budget=46)
    before = sess._hashes()
    res = local_geometry(sess, CE, batches, iters=20)
    assert sess._hashes() == before and sess.grad_budget.used == 46 == res["gradient_evaluations"]
    assert all(not p.requires_grad for p in model.parameters())
    with pytest.raises(BudgetExhausted):
        local_geometry(sess, CE, batches, iters=1)
    assert sess._hashes() == before


def test_agent_code_still_cannot_use_autograd():
    from wsp_session import ForbiddenCode

    with pytest.raises(ForbiddenCode):
        check_agent_code("g = torch.autograd.grad(loss, params)")


def test_reachability_report_scenarios():
    free = {"barrier": 0.0, "level": "L2"}
    bar = {"barrier": 1.2, "level": "L2"}
    sad = {"label": "saddle", "level": "L3"}
    nc = {"label": "not_critical", "level": "L3"}
    mn = {"label": "minimum_like", "level": "L3"}

    r1 = reachability_report(False, None, nc)
    assert r1["verdict"] == "target_not_found" and "capacity" in r1["recommendations"][0]["text"]

    r2 = reachability_report(True, bar, sad)
    assert r2["verdict"] == "separated_by_barrier"
    assert any("edited point" in r["text"] for r in r2["recommendations"])
    assert any("momentum" in r["text"] for r in r2["recommendations"])
    assert r2["levels_used"] == ["L2", "L3"]

    r3 = reachability_report(True, free, nc)
    assert r3["verdict"] == "reachable_by_straight_path"
    assert any("learning rate" in r["text"] for r in r3["recommendations"])

    assert reachability_report(None)["verdict"] == "target_unknown"
    assert reachability_report(True, None, mn)["verdict"] == "target_exists_path_unknown"
    for r in (r1, r2, r3):
        assert all(x["tag"] == "heuristic" for x in r["recommendations"]) and "never guarantees" in r["caveat"]
