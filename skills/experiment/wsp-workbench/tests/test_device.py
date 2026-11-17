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
