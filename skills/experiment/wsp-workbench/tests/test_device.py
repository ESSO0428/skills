"""CUDA model + CPU inputs: every op and method must move inputs to the weights' device.

Skipped without a GPU. Each check compares the CUDA result with the same edit on a CPU copy.
"""
import copy

import pytest
import torch

from wsp_controls import matched_random_direction
from wsp_landscape import landscape_path
from wsp_methods import apply_eraser, apply_eraser_to_next_linear, apply_rank_one, apply_task_vector, leace_fit
from wsp_session import EditPolicy, WeightSession

pytestmark = pytest.mark.skipif(not torch.cuda.is_available(), reason="needs CUDA")

POLICY = EditPolicy(allowed=["."], max_fraction_changed=1.0)


def make_pair(seed=0):
    torch.manual_seed(seed)
    cpu = torch.nn.Sequential(torch.nn.Linear(6, 5), torch.nn.ReLU(), torch.nn.Linear(5, 3))
    return cpu, copy.deepcopy(cpu).cuda()


def both(fn):
    """Run fn(session) on a CPU and a CUDA copy; return the two resulting state dicts."""
    cpu, gpu = make_pair()
    fn(WeightSession(cpu, POLICY))
    fn(WeightSession(gpu, POLICY))
    return cpu.state_dict(), {k: v.cpu() for k, v in gpu.state_dict().items()}


def assert_same(a, b):
    for k in a:
        assert torch.allclose(a[k], b[k], atol=1e-5), k


def test_ops_accept_cpu_inputs_on_cuda_model():
    u, a, b = torch.randn(3), torch.randn(3), torch.randn(5)
    assert_same(*both(lambda s: s.project_out("2.weight", u)))
    assert_same(*both(lambda s: s.add_rank1("2.weight", a, b, scale=0.3)))
    assert_same(*both(lambda s: s.assign("2.bias", [0, 2], torch.tensor([0.5, -0.5]))))


def test_methods_accept_cpu_inputs_on_cuda_model():
    k, v = torch.randn(5), torch.randn(3)
    assert_same(*both(lambda s: apply_rank_one(s, "2.weight", k, v)))

    tau = {"2.weight": torch.randn(3, 5) * 0.1}
    assert_same(*both(lambda s: apply_task_vector(s, tau, 0.5)))

    X, Z = torch.randn(200, 5), torch.randn(200, 1)
    eraser = leace_fit(X, Z)  # fitted on CPU features
    assert_same(*both(lambda s: apply_eraser_to_next_linear(s, "2.weight", "2.bias", eraser)))
    assert apply_eraser(X.cuda(), eraser).is_cuda


def test_controls_and_path_mix_devices():
    v = torch.randn(4, device="cuda")
    r = matched_random_direction(v)
    assert r.is_cuda and torch.isclose(r.norm(), v.norm())

    _, gpu = make_pair(0)
    other_cpu, _ = make_pair(1)
    x, y = torch.randn(32, 6, device="cuda"), torch.randint(0, 3, (32,), device="cuda")
    sess = WeightSession(gpu, POLICY, access_level="L2", budget=5)
    before = sess._hashes()
    out = landscape_path(sess, gpu.state_dict(), other_cpu.state_dict(), torch.nn.functional.cross_entropy,
                         [(x, y)], n_points=5)
    assert len(out["losses"]) == 5 and sess._hashes() == before


class TwoInput(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.a = torch.nn.Sequential(torch.nn.Linear(4, 4), torch.nn.ReLU())
        self.b = torch.nn.Sequential(torch.nn.Linear(4, 4), torch.nn.ReLU())

    def forward(self, x1, x2):
        return self.a(x1) + self.b(x2)


def test_multi_input_forward_patch_plan_and_controls_on_cuda():
    from wsp_controls import make_patch, random_activation, shuffle_pairing
    from wsp_methods import patch_plan

    torch.manual_seed(0)
    sess = WeightSession(TwoInput().cuda(), POLICY, access_level="L2", budget=10)
    x1, x2 = torch.rand(8, 4), torch.rand(8, 4)  # CPU inputs on a CUDA model
    assert sess.forward(x1, x2).is_cuda
    assert sess.forward_inputs({"x1": x1, "x2": x2}).is_cuda
    res = patch_plan(sess, ["a", "b"], (x1, x2), lambda out, inputs: float(out.mean()), mode="resample")
    assert len(res["rows"]) == 4 and sess.budget.used == 2 + 4
    act = torch.randn(8, 4, device="cuda")
    for mode in ("zero", "mean", "resample"):
        assert make_patch(mode, act).is_cuda
    assert random_activation(act).is_cuda
    assert shuffle_pairing((x1.cuda(), x2.cuda()), 1)[1].is_cuda


def test_checkpoint_trajectory_with_cuda_states_and_session():
    from wsp_landscape import checkpoint_trajectory

    _, gpu = make_pair(0)
    states = [make_pair(s)[1].state_dict() for s in range(3)]  # CUDA state dicts
    x, y = torch.randn(16, 6), torch.randint(0, 3, (16,))
    sess = WeightSession(gpu, POLICY, access_level="L2", budget=20)
    res = checkpoint_trajectory(states, session=sess, loss_fn=torch.nn.functional.cross_entropy,
                                batches=[(x, y)], n_points=3)
    assert len(res["segments"]) == 2 and res["piecewise_path"]["forward_passes"] == 6
