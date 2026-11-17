"""Planted-fault repair: a closed-form rank-1 edit, no optimisation inside the session.

Gradient training happens only in the fixtures, to create the model under test.
"""
import pytest
import torch

from wsp_compare import gate, paired_counts, per_class_deltas
from wsp_controls import matched_random_direction
from wsp_inspect import top_cosine_pairs
from wsp_session import BudgetExhausted, EditPolicy, WeightSession, tensor_hash

N_CLASSES, DIM = 5, 64
TARGET, RIVAL = 0, 1  # the planted fault: part of class 0 was labelled 1
CANDIDATE_SCALES = (1.0, 2.0, 4.0, 8.0)  # fixed in advance (logit shift in units of margin)
OUT_W, OUT_B, HIDDEN = "net.2.weight", "net.2.bias", "net.1"


class TinyMLP(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.net = torch.nn.Sequential(torch.nn.Linear(DIM, 16), torch.nn.ReLU(), torch.nn.Linear(16, N_CLASSES))

    def forward(self, x):
        return self.net(x)


def make_data(n_per_class, seed):
    g = torch.Generator().manual_seed(1234)  # prototypes shared by every split
    protos = torch.randn(N_CLASSES, DIM, generator=g)
    protos[RIVAL] = 0.6 * protos[TARGET] + 0.8 * torch.randn(DIM, generator=g)  # confusable pair
    g2 = torch.Generator().manual_seed(seed)
    y = torch.arange(N_CLASSES).repeat_interleave(n_per_class)
    x = protos[y] + 1.5 * torch.randn(len(y), DIM, generator=g2)
    return x, y


@pytest.fixture(scope="module")
def faulty_model():
    torch.manual_seed(0)
    x, y = make_data(120, seed=1)
    y_train = y.clone()
    g = torch.Generator().manual_seed(5)
    idx = (y == TARGET).nonzero().flatten()
    flip = idx[torch.randperm(len(idx), generator=g)[: int(0.7 * len(idx))]]
    y_train[flip] = RIVAL  # plant the fault
    model = TinyMLP()
    opt = torch.optim.Adam(model.parameters(), lr=1e-2)
    for _ in range(60):
        opt.zero_grad()
        torch.nn.functional.cross_entropy(model.net(x), y_train).backward()
        opt.step()
    model.eval()
    return model


def predict(out):
    return out.argmax(1).tolist()


def test_planted_fault_repair(faulty_model, tmp_path, capsys):
    model = faulty_model
    original = {k: v.clone() for k, v in model.state_dict().items()}
    xp, yp = make_data(100, seed=2)  # practice
    xh, yh = make_data(100, seed=3)  # held-out, used once
    yp_l, yh_l = yp.tolist(), yh.tolist()

    policy = EditPolicy(allowed=[r"^net\.2\.(weight|bias)$"], forbidden=[r"^net\.0\."], max_fraction_changed=0.5)
    sess = WeightSession(model, policy, level="L2", budget=11, ledger_path=tmp_path / "ledger.jsonl")

    # 1. baseline on practice (pass 1) and held-out (pass 2)
    out, acts = sess.forward(xp, capture=[HIDDEN])
    base_p = predict(out)
    base_h = predict(sess.forward(xh))
    base_failures = sum(a != b for a, b in zip(yp_l, base_p))
    assert per_class_deltas(yh_l, base_h, base_h)[TARGET]["before"] < 0.5  # the fault is real

    # 2. find the confusion: most frequent off-diagonal (true, predicted) pair
    conf = {}
    for t, p in zip(yp_l, base_p):
        if t != p:
            conf[(t, p)] = conf.get((t, p), 0) + 1
    (a_cls, b_cls), _ = max(conf.items(), key=lambda kv: kv[1])
    assert (a_cls, b_cls) == (TARGET, RIVAL)
    cosine_pairs = top_cosine_pairs(sess.param(OUT_W), k=3)  # structural cross-check, reported only

    # 3. closed-form edit: shift logit(a) - logit(b) along the hidden direction separating the classes
    hidden = acts[HIDDEN]
    ha = hidden[torch.tensor(yp_l) == a_cls].mean(0)
    hb = hidden[torch.tensor(yp_l) == b_cls].mean(0)
    v = ha - hb
    b_vec = v / (v @ v)  # b . (ha - hb) = 1
    mid = 0.5 * (ha + hb)
    e_a = torch.zeros(N_CLASSES)
    e_a[a_cls] = 1.0
    e_a[b_cls] = -1.0
    bias = sess.param(OUT_B)

    def apply(direction, scale, tag):
        shift = scale * float(direction @ mid)
        i1 = sess.add_rank1(OUT_W, e_a, direction, scale=scale, note=f"{tag} s={scale}")
        i2 = sess.assign(
            OUT_B, [a_cls, b_cls], [float(bias[a_cls]) - shift, float(bias[b_cls]) + shift], note=f"{tag} bias"
        )
        return [i2, i1]  # undo order

    def undo(ids):
        for i in ids:
            sess.undo(i)

    # 4. fixed candidate list, each against a norm-matched random control, then the gate
    best = None
    for s in CANDIDATE_SCALES:
        ids = apply(b_vec, s, "cand")
        fixed, broke = paired_counts(yp_l, base_p, predict(sess.forward(xp)))
        undo(ids)
        ids = apply(matched_random_direction(b_vec, seed=7), s, "control")
        c_fixed, c_broke = paired_counts(yp_l, base_p, predict(sess.forward(xp)))
        undo(ids)
        sess.assert_baseline()
        verdict = gate(fixed, broke, base_failures, control_fixed=c_fixed)
        if verdict["verdict"] == "PASS" and (best is None or fixed - broke > best[1]["fixed"] - best[1]["broke"]):
            best = (s, verdict, c_fixed, c_broke)
    assert best is not None, "no candidate passed the gate"
    scale, verdict, c_fixed, c_broke = best
    assert verdict["sign_test_p"] < 0.01

    # 5. apply the winner, held-out once, per-class side effects
    apply(b_vec, scale, "final")
    after_h = predict(sess.forward(xh))
    deltas = per_class_deltas(yh_l, base_h, after_h)
    assert deltas[TARGET]["after"] - deltas[TARGET]["before"] >= 0.2
    for c, d in deltas.items():
        if c != TARGET:
            assert d["delta"] >= (-0.10 if c == RIVAL else -0.05), (c, d)

    with pytest.raises(BudgetExhausted):  # 11 passes are used
        sess.forward(xh)
    assert sess.budget.remaining == 0

    # 6. undo everything; hashes must equal the baseline bytes
    sess.undo_all()
    sess.assert_baseline()
    for k, v0 in original.items():
        assert tensor_hash(model.state_dict()[k]) == tensor_hash(v0)
        assert torch.equal(model.state_dict()[k], v0)

    with capsys.disabled():
        print(
            f"\n[e2e] pair=({a_cls},{b_cls}) cosine_pairs={[(p['rows'], round(p['cosine'], 2)) for p in cosine_pairs]}"
            f"\n[e2e] chosen scale={scale} gate={verdict['verdict']} fixed={verdict['fixed']} broke={verdict['broke']}"
            f" need={verdict['need_fixed']} p={verdict['sign_test_p']:.2e}"
            f"\n[e2e] random control (same scale): fixed={c_fixed} broke={c_broke}"
            f"\n[e2e] held-out per class (before->after): "
            + ", ".join(f"{c}: {d['before']:.2f}->{d['after']:.2f}" for c, d in deltas.items())
        )


def test_session_code_has_no_optimiser_calls():
    """The shipped scripts themselves obey the no-optimisation rule."""
    from pathlib import Path

    from wsp_session import check_agent_code

    for f in (Path(__file__).parent.parent / "scripts").glob("wsp_*.py"):
        if f.name in ("wsp_session.py", "wsp_landscape.py"):
            continue  # the checker itself, and the trusted L3 measurement code
        assert check_agent_code(f.read_text(encoding="utf-8")) == []
