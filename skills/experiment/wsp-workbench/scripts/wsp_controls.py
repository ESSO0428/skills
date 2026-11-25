"""Controls for weight reading and intervention."""
from __future__ import annotations

try:
    import torch
except ImportError:  # torch lives in the cpu / cu126 / cu132 extras
    raise SystemExit("""torch is not installed. Set up the skill environment once (pick by the CUDA Version shown by nvidia-smi):
  uv sync --project <skill dir> --extra cu132   # CUDA Version >= 13.2
  uv sync --project <skill dir> --extra cu126   # CUDA 12.x
  uv sync --project <skill dir> --extra cpu     # no NVIDIA GPU
(add --extra dev to run the tests; see README.md)""")


def matched_random_direction(v: torch.Tensor, seed: int = 0) -> torch.Tensor:
    """Random direction with the same shape and L2 norm as v."""
    g = torch.Generator().manual_seed(seed)
    r = torch.randn(v.shape, generator=g, dtype=torch.float32).to(v.device)  # CPU generator, then v's device
    return r / r.norm() * v.float().norm()


def shuffled_copy(state: dict[str, torch.Tensor], seed: int = 0) -> dict[str, torch.Tensor]:
    """Shuffle values within each tensor (keeps each tensor's multiset of values)."""
    g = torch.Generator().manual_seed(seed)
    out = {}
    for k, v in state.items():
        flat = v.detach().cpu().reshape(-1)
        out[k] = flat[torch.randperm(flat.numel(), generator=g)].reshape(v.shape).clone()
    return out


def permute_outputs(
    state: dict[str, torch.Tensor], output_names: list[str], seed: int = 0
) -> tuple[dict[str, torch.Tensor], torch.Tensor]:
    """Permute the output units (dim 0) of the named tensors with one shared permutation.

    Only meaningful when the outputs are class labels. For dense / embedding outputs use
    shuffle_pairing or random_activation instead.
    """
    n = state[output_names[0]].shape[0]
    perm = torch.randperm(n, generator=torch.Generator().manual_seed(seed))
    out = {k: v.detach().cpu().clone() for k, v in state.items()}
    for name in output_names:
        if out[name].shape[0] != n:
            raise ValueError(f"{name}: first dim {out[name].shape[0]} != {n}")
        out[name] = out[name][perm].clone()
    return out, perm


def derangement(n: int, seed: int = 0) -> torch.Tensor:
    """Seeded permutation of range(n) with no fixed points (one random n-cycle); identity for n < 2."""
    if n < 2:
        return torch.arange(n)
    order = torch.randperm(n, generator=torch.Generator().manual_seed(seed))
    perm = torch.empty(n, dtype=torch.long)
    perm[order] = order.roll(-1)
    return perm


def make_patch(mode, activation: torch.Tensor, seed: int = 0) -> torch.Tensor:
    """Replacement for an activation of shape (batch, ...), on the activation's device.

    zero:     remove the signal (tests whether the node carries anything the output needs).
    mean:     batch mean broadcast to every sample (removes sample-specific information, keeps the average).
    resample: another sample's activation via a seeded derangement (keeps the distribution, breaks the
              pairing with this sample's other inputs). A batch of 1 cannot be resampled and is returned as is.
    A tensor is used as given (moved to the activation's device and dtype).
    """
    a = activation.detach()
    if isinstance(mode, torch.Tensor):
        return mode.to(device=a.device, dtype=a.dtype)
    if mode == "zero":
        return torch.zeros_like(a)
    if mode == "mean":
        return a.mean(0, keepdim=True).expand_as(a).clone()
    if mode == "resample":
        return a[derangement(a.shape[0], seed).to(a.device)].clone()
    raise ValueError(f"unknown patch mode {mode!r}; use zero, mean, resample or a tensor")


def random_activation(activation: torch.Tensor, seed: int = 0) -> torch.Tensor:
    """Random replacement with each sample's norm (over all dims but the first) matched to the original."""
    a = activation.detach()
    r = torch.randn(a.shape, generator=torch.Generator().manual_seed(seed), dtype=torch.float32).to(a.device)
    flat_r, flat_a = r.reshape(len(a), -1), a.float().reshape(len(a), -1)
    scale = flat_a.norm(dim=1, keepdim=True) / flat_r.norm(dim=1, keepdim=True).clamp_min(1e-12)
    return (flat_r * scale).reshape(a.shape).to(a.dtype)


def shuffle_pairing(inputs, which, seed: int = 0):
    """Permute ONE input across the batch (a derangement) so it no longer pairs with the others.

    `inputs` is a tuple/list (which = index) or a dict (which = key). Returns the same container type.
    """
    if isinstance(inputs, dict):
        out = dict(inputs)
        out[which] = inputs[which][derangement(len(inputs[which]), seed).to(inputs[which].device)]
        return out
    if isinstance(inputs, (tuple, list)):
        items = list(inputs)
        items[which] = items[which][derangement(len(items[which]), seed).to(items[which].device)]
        return tuple(items) if isinstance(inputs, tuple) else items
    raise ValueError("shuffle_pairing needs several inputs (tuple, list or dict)")


if __name__ == "__main__":
    import argparse

    argparse.ArgumentParser(description="Library: matched_random_direction, shuffled_copy, permute_outputs, make_patch, random_activation, shuffle_pairing. Import it; it has no CLI.").parse_args()
