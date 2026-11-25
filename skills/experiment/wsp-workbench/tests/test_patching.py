import itertools

import pytest
import torch

from wsp_controls import derangement, make_patch, random_activation, shuffle_pairing
from wsp_methods import localize_by_patching, patch_plan
from wsp_session import AccessDenied, BudgetExhausted, EditPolicy, WeightSession

POLICY = EditPolicy(allowed=["."], max_fraction_changed=1.0)
D = 6


class TwoBranch(torch.nn.Module):
    """Two non-negative branches (a, b) feeding a parameter-free head: sum, max or product."""

    def __init__(self, head="sum", n_nodes=2):
        super().__init__()
        self.head = head
        self.a = torch.nn.Sequential(torch.nn.Linear(D, D), torch.nn.ReLU())
        self.b = torch.nn.Sequential(torch.nn.Linear(D, D), torch.nn.ReLU())
        self.c = torch.nn.Sequential(torch.nn.Linear(D, D), torch.nn.ReLU())
        self.n_nodes = n_nodes

    def forward(self, x1, x2, x3=None):
        outs = [self.a(x1), self.b(x2)] + ([self.c(x3)] if x3 is not None else [])
        if self.head == "sum":
            return sum(outs)
        if self.head == "max":
            return torch.stack(outs).max(0).values
        return outs[0] * outs[1]


def mean_output(out, inputs):
    return float(out.mean())


def make(head="sum", same_branches=False, level="L2", budget=20):
    torch.manual_seed(0)
    m = TwoBranch(head)
    if same_branches:
        m.b.load_state_dict(m.a.state_dict())
    return WeightSession(m, POLICY, access_level=level, budget=budget)


X = torch.rand(16, D) + 0.5


def test_forward_accepts_tuple_dict_and_keeps_single_tensor_form():
    s = make(budget=10)
    ref = s.model(X, X + 1)
    assert torch.allclose(s.forward(X, X + 1), ref)
    assert torch.allclose(s.forward_inputs((X, X + 1)), ref)
    assert torch.allclose(s.forward_inputs([X, X + 1]), ref)
    assert torch.allclose(s.forward(x1=X, x2=X + 1), ref)
    assert torch.allclose(s.forward_inputs({"x1": X, "x2": X + 1}), ref)
    out, acts = s.forward(X, X + 1, capture=["a"])
    assert torch.allclose(out, ref) and acts["a"].shape == (16, D)
    assert s.budget.used == 6  # one pass per call, whatever the inputs
    seq = WeightSession(torch.nn.Linear(D, 2), POLICY, access_level="L2", budget=2)
    assert seq.forward(X).shape == (16, 2) and seq.forward_inputs(X).shape == (16, 2)


def test_patch_plan_additive_design_has_zero_interaction(capsys):
    s = make("sum")
    res = patch_plan(s, ["a", "b"], (X, X + 1), mean_output)
    rows = {tuple(r["nodes"]): r for r in res["rows"]}
    assert set(rows) == {(), ("a",), ("b",), ("a", "b")}
    assert rows[("a",)]["delta"] < 0 and rows[("b",)]["delta"] < 0
    assert rows[("a", "b")]["interaction"] == pytest.approx(0.0, abs=1e-6)
    assert rows[("a", "b")]["delta"] == pytest.approx(rows[("a",)]["delta"] + rows[("b",)]["delta"], abs=1e-6)
    assert s.budget.used == res["forward_passes"] == 4
    with capsys.disabled():
        print(f"\n[patch_plan] additive: single deltas={rows[('a',)]['delta']:.4f}, {rows[('b',)]['delta']:.4f}, "
              f"joint={rows[('a', 'b')]['delta']:.4f}, interaction={rows[('a', 'b')]['interaction']:.2e}")


def test_patch_plan_redundant_design_has_negative_interaction(capsys):
    # identical branches, max head: removing one hides nothing, removing both loses everything
    s = make("max", same_branches=True)
    res = patch_plan(s, ["a", "b"], (X, X), mean_output)
    rows = {tuple(r["nodes"]): r for r in res["rows"]}
    assert rows[("a",)]["delta"] == pytest.approx(0.0, abs=1e-6)
    assert rows[("b",)]["delta"] == pytest.approx(0.0, abs=1e-6)
    joint = rows[("a", "b")]
    assert joint["delta"] < -0.1 and joint["interaction"] == pytest.approx(joint["delta"], abs=1e-6)
    assert joint["interaction"] < 0  # sign convention: joint harm exceeds the sum of single harms
    with capsys.disabled():
        print(f"[patch_plan] redundant (max): singles=0, joint={joint['delta']:.4f}, interaction={joint['interaction']:.4f}")


def test_patch_plan_conjunctive_design_has_positive_interaction(capsys):
    s = make("prod")
    res = patch_plan(s, ["a", "b"], (X, X + 1), mean_output)
    rows = {tuple(r["nodes"]): r for r in res["rows"]}
    m = rows[("a", "b")]
    assert rows[("a",)]["delta"] == pytest.approx(rows[("b",)]["delta"], abs=1e-6)  # each kills the product
    assert m["interaction"] > 0  # joint harm is smaller than the sum: the loss does not stack
    with capsys.disabled():
        print(f"[patch_plan] conjunctive (product): single={rows[('a',)]['delta']:.4f}, joint={m['delta']:.4f}, "
              f"interaction={m['interaction']:.4f}")


def test_patch_plan_budget_accounting_and_modes():
    inputs = {"x1": X, "x2": X + 1, "x3": X + 2}
    s = make("sum", budget=7)  # three nodes need 1 + 3 + 3 + 1 = 8
    with pytest.raises(BudgetExhausted):
        patch_plan(s, ["a", "b", "c"], inputs, mean_output)
    assert s.budget.used == 0  # refused before spending
    s = make("sum", budget=8)
    res = patch_plan(s, ["a", "b", "c"], inputs, mean_output)
    assert s.budget.used == 8 == res["forward_passes"] and s.budget.remaining == 0
    orders = sorted(r["order"] for r in res["rows"])
    assert orders == [0, 1, 1, 1, 2, 2, 2, 3]
    assert all("interaction" in r for r in res["rows"] if r["order"] >= 2)
    s = make("sum", budget=3)
    assert patch_plan(s, ["a", "b"], (X, X), mean_output, max_order=1)["forward_passes"] == 3
    for mode in ("mean", "resample", torch.zeros(16, D)):
        s = make("sum")
        assert len(patch_plan(s, ["a", "b"], (X, X + 1), mean_output, mode=mode)["rows"]) == 4
    with pytest.raises(AccessDenied):
        patch_plan(make("sum", level="L1"), ["a"], (X, X), mean_output)
    with pytest.raises(ValueError):
        patch_plan(make("sum"), ["a"], (X, X), mean_output, max_order=3)


def test_localize_accepts_multi_input_and_two_arg_metric():
    s = make("sum", budget=10)
    clean, corrupt = (X, X + 1), (X + 3, X + 5)
    res = localize_by_patching(s, ["a", "b"], clean, corrupt, mean_output)
    assert s.budget.used == 4
    assert set(res["effects"]) == {"a", "b"}
    one_arg = localize_by_patching(make("sum"), ["a"], clean, corrupt, lambda out: float(out.mean()))
    assert one_arg["effects"]["a"] == pytest.approx(res["effects"]["a"], abs=1e-6)


def test_patch_modes_properties():
    a = torch.randn(10, 4)
    z = make_patch("zero", a)
    assert torch.equal(z, torch.zeros_like(a))
    m = make_patch("mean", a)
    assert m.shape == a.shape and torch.allclose(m.mean(0), a.mean(0), atol=1e-6)
    assert torch.allclose(m, a.mean(0, keepdim=True).expand_as(a))
    r = make_patch("resample", a, seed=3)
    assert not any(torch.equal(r[i], a[i]) for i in range(10))  # no sample keeps its own activation
    assert torch.equal(r.sort(0).values, a.sort(0).values)  # same multiset of samples
    assert torch.equal(r, make_patch("resample", a, seed=3))  # seeded
    for n in range(2, 12):
        for seed in range(5):
            assert (derangement(n, seed) != torch.arange(n)).all()
            assert sorted(derangement(n, seed).tolist()) == list(range(n))
    one = torch.randn(1, 4)
    assert torch.equal(make_patch("resample", one), one)  # a batch of one cannot be resampled
    t = torch.ones(10, 4)
    assert torch.equal(make_patch(t, a), t)
    with pytest.raises(ValueError):
        make_patch("nonsense", a)


def test_shuffle_pairing_and_random_activation():
    s = make("sum")
    x2 = X + torch.arange(16.0)[:, None]
    base = s.model(X, x2)
    for inputs, which in (((X, x2), 1), ([X, x2], 1), ({"x1": X, "x2": x2}, "x2")):
        shuffled = shuffle_pairing(inputs, which, seed=1)
        assert type(shuffled) is type(inputs)
        out = s.forward_inputs(shuffled)
        assert not torch.allclose(out, base)
        other = shuffled[which]
        assert torch.equal(other.sort(0).values, x2.sort(0).values)
    with pytest.raises(ValueError):
        shuffle_pairing(X, 0)
    act = torch.randn(8, 3, 5) * torch.arange(1, 9.0)[:, None, None]
    r = random_activation(act, seed=2)
    assert r.shape == act.shape
    assert torch.allclose(r.reshape(8, -1).norm(dim=1), act.reshape(8, -1).norm(dim=1), rtol=1e-5)
    assert not torch.allclose(r, act)
    assert torch.equal(r, random_activation(act, seed=2))
