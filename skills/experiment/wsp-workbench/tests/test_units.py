import json

import pytest
import torch

from wsp_compare import gate, paired_counts, per_class_deltas, sign_test_p
from wsp_controls import matched_random_direction, permute_outputs, shuffled_copy
from wsp_inspect import inventory, main as inspect_main, stats, text_dump, top_cosine_pairs
from wsp_session import (
    BudgetExhausted,
    EditPolicy,
    ForbiddenCode,
    ForwardBudget,
    PolicyViolation,
    WeightSession,
    check_agent_code,
)


def make_model():
    torch.manual_seed(0)
    return torch.nn.Sequential(torch.nn.Linear(6, 8), torch.nn.ReLU(), torch.nn.Linear(8, 4))


def session(model=None, level="L1", budget=0, frac=0.5, **kw):
    policy = EditPolicy(allowed=[r"^2\.weight$", r"^2\.bias$"], forbidden=[r"^0\."], max_fraction_changed=frac)
    return WeightSession(model or make_model(), policy, level=level, budget=budget, **kw)


def test_project_out_sign_convention():
    s = session(frac=1.0)
    W0 = s.param("2.weight")
    u = torch.tensor([1.0, 2.0, 0.0, -1.0])
    un = u / u.norm()
    # alpha=1 removes the u-component
    s.project_out("2.weight", u, alpha=1.0)
    W1 = s.param("2.weight")
    assert torch.allclose(un @ W1, torch.zeros(8), atol=1e-6)
    s.undo_all()
    # alpha=0.5 halves it; alpha=2 flips it
    s.project_out("2.weight", u, alpha=0.5)
    assert torch.allclose(un @ s.param("2.weight"), 0.5 * (un @ W0), atol=1e-6)
    s.undo_all()
    s.project_out("2.weight", u, alpha=2.0)
    assert torch.allclose(un @ s.param("2.weight"), -(un @ W0), atol=1e-6)
    # exact formula: W - alpha * u (u^T W)
    s.undo_all()
    s.project_out("2.weight", u, alpha=0.3)
    assert torch.allclose(s.param("2.weight"), W0 - 0.3 * torch.outer(un, un @ W0), atol=1e-6)


def test_project_out_columns_only():
    s = session()
    W0 = s.param("2.weight")
    s.project_out("2.weight", torch.tensor([1.0, 0, 0, 0]), cols=[0, 1])
    W1 = s.param("2.weight")
    assert torch.equal(W1[:, 2:], W0[:, 2:])
    assert torch.allclose(W1[0, :2], torch.zeros(2))


def test_gate_rejects_out_of_policy_tensor():
    s = session()
    with pytest.raises(PolicyViolation):
        s.zero_units("0.weight", [0])  # forbidden
    with pytest.raises(PolicyViolation):
        s.assign("0.bias", [0], [1.0])  # forbidden by pattern
    s2 = WeightSession(make_model(), EditPolicy(allowed=[r"^2\.weight$"]))
    with pytest.raises(PolicyViolation):
        s2.assign("2.bias", [0], [1.0])  # not allowed


def test_gate_rejects_non_finite_over_cap_and_scaling():
    s = session(frac=0.1)
    with pytest.raises(PolicyViolation, match="non-finite"):
        s.assign("2.bias", [0], [float("nan")])
    with pytest.raises(PolicyViolation, match="cap"):
        s.zero_units("2.weight", [0, 1])  # 16/32 changed
    s_all = session(frac=1.0)
    with pytest.raises(PolicyViolation, match="nothing"):
        s_all.add_rank1("2.weight", torch.ones(4), torch.ones(8), scale=0.0)
    W = s_all.param("2.weight")
    with pytest.raises(PolicyViolation, match="scaling"):
        s_all._commit("assign", "2.weight", W * 1.5, "whole tensor")
    s_all.assert_baseline()  # refused edits left nothing behind


def test_undo_restores_exact_bytes_and_ledger(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    s = session(ledger_path=ledger)
    before = {k: v.clone() for k, v in s.model.state_dict().items()}
    e1 = s.add_rank1("2.weight", torch.tensor([1.0, 0, 0, 0]), torch.ones(8), scale=0.7, note="a")
    e2 = s.assign("2.bias", [1], [3.0], note="b")
    s.zero_units("2.weight", [2], dim=0)
    with pytest.raises(AssertionError):
        s.assert_baseline()
    with pytest.raises(PolicyViolation):  # e1's tensor was changed again by edit 3
        s.undo(e1)
    s.undo_all()
    s.assert_baseline()
    for k, v in s.model.state_dict().items():
        assert torch.equal(v, before[k])
    lines = [json.loads(x) for x in ledger.read_text().splitlines()]
    edits = [x for x in lines if x["event"] == "edit"]
    assert [x["edit_id"] for x in edits] == [e1, e2, 3]
    assert edits[0]["before_hash"] != edits[0]["after_hash"]
    assert {"op", "tensor", "n_changed", "note", "level"} <= edits[0].keys()
    assert sum(x["event"] == "undo" for x in lines) == 3


def test_forward_budget_and_levels():
    b = ForwardBudget(2)
    b.consume()
    b.consume()
    with pytest.raises(BudgetExhausted):
        b.consume()
    s1 = session(level="L1")
    with pytest.raises(BudgetExhausted):
        s1.forward(torch.zeros(1, 6))
    s2 = session(level="L2", budget=1)
    s2.forward(torch.zeros(3, 6))
    with pytest.raises(BudgetExhausted):
        s2.forward(torch.zeros(3, 6))
    with pytest.raises(ValueError):
        session(level="L0")


def test_check_agent_code_rejects_forbidden():
    bad = [
        "loss.backward()",
        "import torch.optim as o",
        "from torch import optim",
        "from torch.optim import SGD",
        "torch.autograd.grad(y, x)",
        "p.requires_grad_(True)",
        "p.requires_grad_()",
        "p.requires_grad = True",
        "opt = torch.optim.Adam(m.parameters())",
        "torch.func.grad(f)(x)",
    ]
    for src in bad:
        with pytest.raises(ForbiddenCode):
            check_agent_code(src)
    assert check_agent_code("p.requires_grad_(False)\nw = torch.linalg.svdvals(W)\n") == []


def test_sign_test_exact_values():
    assert sign_test_p(0, 0) == 1.0
    assert sign_test_p(5, 0) == pytest.approx(2 / 32)
    assert sign_test_p(3, 3) == 1.0
    assert sign_test_p(8, 2) == pytest.approx(2 * (1 + 10 + 45) / 1024)
    assert sign_test_p(2, 8) == sign_test_p(8, 2)


def test_gate_thresholds():
    assert gate(10, 2, 40)["verdict"] == "PASS"  # need 8, broke <= 2.5
    assert gate(7, 0, 40)["verdict"] == "FAIL"  # need ceil(8)
    assert gate(10, 3, 40)["verdict"] == "FAIL"  # 3 > 2.5
    assert gate(3, 0, 5)["verdict"] == "PASS"  # floor of 3
    assert gate(2, 0, 5)["verdict"] == "FAIL"
    assert gate(10, 0, 40, control_fixed=10)["verdict"] == "FAIL"
    assert gate(10, 0, 40, control_fixed=4)["checks"]["beats_control"]


def test_paired_counts_and_per_class():
    y = [0, 0, 1, 1, 2]
    base = [1, 0, 1, 0, 2]
    new = [0, 0, 1, 1, 0]
    assert paired_counts(y, base, new) == (2, 1)
    d = per_class_deltas(y, base, new)
    assert d[0]["delta"] == pytest.approx(0.5)
    assert d[2]["after"] == 0.0


def test_controls():
    v = torch.tensor([3.0, 4.0, 0.0])
    r = matched_random_direction(v, seed=1)
    assert r.norm().item() == pytest.approx(5.0, rel=1e-5)
    assert not torch.allclose(r, v)
    state = make_model().state_dict()
    sh = shuffled_copy(state, seed=2)
    for k in state:
        assert torch.equal(state[k].flatten().sort().values, sh[k].flatten().sort().values)
        assert sh[k].shape == state[k].shape
    assert any(not torch.equal(state[k], sh[k]) for k in state)
    perm_state, perm = permute_outputs(state, ["2.weight", "2.bias"], seed=3)
    assert torch.equal(perm_state["2.weight"], state["2.weight"][perm])
    assert torch.equal(perm_state["2.bias"], state["2.bias"][perm])


def test_inspect_functions_and_cli(tmp_path, capsys):
    state = make_model().state_dict()
    inv = inventory(state)
    assert [r["name"] for r in inv] == list(state)
    assert inv[0]["numel"] == 48 and len(inv[0]["sha256"]) == 64
    st = stats(state["2.weight"])
    assert 1 <= st["effective_rank"] <= 4
    pairs = top_cosine_pairs(state["2.weight"], k=2)
    assert len(pairs) == 2 and pairs[0]["cosine"] >= pairs[1]["cosine"]
    txt = text_dump(state["0.weight"], max_chars=120)
    assert "integer *" in txt and "truncated" in txt and len(txt) < 260
    path = tmp_path / "m.pt"
    torch.save(state, path)
    inspect_main(["inventory", str(path)])
    assert "0.weight" in capsys.readouterr().out
    inspect_main(["stats", str(path), "--pattern", "2.weight"])
    assert "effective_rank" in capsys.readouterr().out


def test_env_info_fields_and_session_start_record(tmp_path):
    from wsp_session import env_info

    env = env_info()
    for key in ("python", "platform", "torch", "torch_cuda", "cuda_available", "devices", "torch_build"):
        assert key in env
    ver = torch.__version__
    assert env["torch_build"] == (ver.split("+", 1)[1] if "+" in ver else "pypi")
    assert isinstance(env["devices"], list) and env["cuda_available"] == torch.cuda.is_available()
    ledger = tmp_path / "ledger.jsonl"
    s = session(ledger_path=ledger)
    s.assign("2.bias", [0], [1.0])
    lines = [json.loads(x) for x in ledger.read_text().splitlines()]
    assert lines[0]["event"] == "session_start" and lines[0]["env"] == s.env == env
    assert [x["event"] for x in lines] == ["session_start", "edit"]
    assert s.ledger[0]["event"] == "session_start"


def test_results_carry_env():
    from wsp_methods import localize_by_patching, patch_plan

    s = session(level="L2", budget=10)
    x = torch.randn(4, 6)
    out = patch_plan(s, ["0", "2"], x, lambda o, i: float(o.mean()))
    assert out["env"] is s.env
    assert localize_by_patching(session(level="L2", budget=10), ["0"], x, x + 1, lambda o: float(o.mean()))["env"]["torch"]


def test_recall_at_k_on_toy_gallery():
    from wsp_compare import recall_at_k

    # identities A (items 0, 1) and B (items 2, 3)
    gallery = torch.tensor([[1.0, 0.0], [0.0, -1.0], [0.8, 0.6], [0.6, 0.8]])
    g_lab = torch.tensor([0, 0, 1, 1])
    # queries predicted close to A and close to B
    pred = torch.tensor([[1.0, 0.1], [0.7, 0.7]])
    q_lab = torch.tensor([0, 1])
    assert recall_at_k(pred, gallery, q_lab, g_lab, k=1) == 1.0
    assert recall_at_k(pred, gallery, torch.tensor([1, 0]), g_lab, k=1) == 0.0  # wrong identities
    assert recall_at_k(pred, gallery, torch.tensor([1, 0]), g_lab, k=4) == 1.0  # everything fits in top 4
    # a query that IS gallery item 0: counting it against itself inflates recall
    own = gallery[:1]
    assert recall_at_k(own, gallery, torch.tensor([0]), g_lab, k=1) == 1.0
    assert recall_at_k(own, gallery, torch.tensor([0]), g_lab, k=1, exclude_self=torch.tensor([0])) == 0.0
    assert recall_at_k(own, gallery, torch.tensor([0]), g_lab, k=4, exclude_self=torch.tensor([0])) == 1.0
    # a query whose identity has no gallery positive is skipped, not counted as a miss
    assert recall_at_k(pred, gallery, torch.tensor([0, 9]), g_lab, k=1) == 1.0
    only = recall_at_k(own, gallery, torch.tensor([1]), g_lab, k=1, exclude_self=torch.tensor([2]))
    assert 0.0 <= only <= 1.0
    solo = recall_at_k(own, gallery, torch.tensor([2]), torch.tensor([0, 0, 1, 2]), k=1, exclude_self=torch.tensor([3]))
    assert solo != solo  # nan: the query's only positive was itself
