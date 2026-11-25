import pytest
import torch

from wsp_landscape import checkpoint_trajectory
from wsp_session import BudgetExhausted, EditPolicy, WeightSession

POLICY = EditPolicy(allowed=["."], max_fraction_changed=1.0)


def orthonormal(n, k, seed):
    q, _ = torch.linalg.qr(torch.randn(n, k, generator=torch.Generator().manual_seed(seed), dtype=torch.float64))
    return q


def rank1(u, v, scale=1.0):
    return (scale * torch.outer(u, v)).float()


def states_from(*deltas, w0=None):
    w = torch.randn(8, 6, generator=torch.Generator().manual_seed(9)) if w0 is None else w0
    out = [{"w": w.clone(), "b": torch.zeros(8)}]
    for d in deltas:
        out.append({"w": out[-1]["w"] + d, "b": out[-1]["b"].clone()})
    return out


Q8, Q6 = orthonormal(8, 2, 1), orthonormal(6, 2, 2)
A = rank1(Q8[:, 0], Q6[:, 0])
B = rank1(Q8[:, 1], Q6[:, 1])  # orthogonal to A in both spaces


def test_orthogonal_segments_have_zero_cosine_and_overlap(capsys):
    res = checkpoint_trajectory(states_from(A, B), pattern="w", top_k=1)
    c = res["consecutive"][0]
    assert c["tensors"]["w"]["cosine"] == pytest.approx(0.0, abs=1e-6)
    assert c["tensors"]["w"]["subspace_overlap"] == pytest.approx(0.0, abs=1e-6)
    assert c["global_cosine"] == pytest.approx(0.0, abs=1e-6)
    with capsys.disabled():
        print(f"\n[trajectory] orthogonal segments: cosine={c['tensors']['w']['cosine']:.2e} "
              f"overlap={c['tensors']['w']['subspace_overlap']:.2e}")


def test_consistent_segments_have_unit_cosine_and_overlap(capsys):
    res = checkpoint_trajectory(states_from(A, 2 * A, 0.5 * A), pattern="w", top_k=3)
    for c in res["consecutive"]:
        assert c["tensors"]["w"]["cosine"] == pytest.approx(1.0, abs=1e-6)
        assert c["tensors"]["w"]["subspace_overlap"] == pytest.approx(1.0, abs=1e-6)
    assert res["net"]["net_over_path_length"] == pytest.approx(1.0, abs=1e-6)
    with capsys.disabled():
        c = res["consecutive"][0]["tensors"]["w"]
        print(f"[trajectory] consistent segments: cosine={c['cosine']:.6f} overlap={c['subspace_overlap']:.6f}")


def test_rank_one_delta_has_unit_energy_share_and_norms():
    res = checkpoint_trajectory(states_from(3 * A), pattern="w", top_k=3)
    t = res["segments"][0]["tensors"]["w"]
    assert t["top_k_energy_share"] == pytest.approx(1.0, abs=1e-9)
    assert t["fro"] == pytest.approx(3.0, abs=1e-5)
    w0 = res["net"]["tensors"]["w"]
    assert w0["relative"] == pytest.approx(t["fro"] / float(states_from()[0]["w"].norm()), rel=1e-5)
    # a full-rank delta spreads its energy
    full = torch.randn(8, 6, generator=torch.Generator().manual_seed(4))
    share = checkpoint_trajectory(states_from(full), pattern="w", top_k=1)["segments"][0]["tensors"]["w"]
    assert share["top_k_energy_share"] < 0.7


def test_two_checkpoints_note_and_wording():
    res = checkpoint_trajectory(states_from(A), pattern="w")
    assert len(res["segments"]) == 1 and res["consecutive"] == []
    text = " ".join(res["notes"])
    assert "at least 3 checkpoints" in text and "net displacement" in text
    assert "not the direction training moved along" in text
    with pytest.raises(ValueError):
        checkpoint_trajectory(states_from(A)[:1])
    with pytest.raises(ValueError):
        checkpoint_trajectory(states_from(A), pattern="nothing_matches")


def test_pattern_selects_floating_tensors_and_1d_has_no_subspace():
    res = checkpoint_trajectory(states_from(A), pattern=".")
    assert set(res["tensors"]) == {"w", "b"}
    assert "top_k_energy_share" not in res["segments"][0]["tensors"]["b"]


def test_piecewise_path_counts_passes_and_restores_hashes():
    torch.manual_seed(0)
    model = torch.nn.Linear(4, 2)
    ckpts = []
    for seed in range(3):
        torch.manual_seed(seed)
        ckpts.append({k: v.clone() for k, v in torch.nn.Linear(4, 2).state_dict().items()})
    x, y = torch.randn(32, 4), torch.randn(32, 2)
    mse = torch.nn.functional.mse_loss
    sess = WeightSession(model, POLICY, access_level="L2", budget=100)
    before = sess._hashes()
    res = checkpoint_trajectory(ckpts, session=sess, loss_fn=mse, batches=[(x, y)], n_points=5)
    assert sess._hashes() == before
    assert sess.budget.used == 2 * 5 * 1 == res["piecewise_path"]["forward_passes"]
    assert len(res["piecewise_path"]["paths"]) == 2 and res["level"] == "L2"
    small = WeightSession(model, POLICY, access_level="L2", budget=9)
    with pytest.raises(BudgetExhausted):
        checkpoint_trajectory(ckpts, session=small, loss_fn=mse, batches=[(x, y)], n_points=5)
    assert small.budget.used == 0
    with pytest.raises(ValueError):
        checkpoint_trajectory(ckpts, session=sess)
