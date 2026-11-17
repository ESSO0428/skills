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
    """Permute the output units (dim 0) of the named tensors with one shared permutation."""
    n = state[output_names[0]].shape[0]
    perm = torch.randperm(n, generator=torch.Generator().manual_seed(seed))
    out = {k: v.detach().cpu().clone() for k, v in state.items()}
    for name in output_names:
        if out[name].shape[0] != n:
            raise ValueError(f"{name}: first dim {out[name].shape[0]} != {n}")
        out[name] = out[name][perm].clone()
    return out, perm


if __name__ == "__main__":
    import argparse

    argparse.ArgumentParser(description="Library: matched_random_direction, shuffled_copy, permute_outputs. Import it; it has no CLI.").parse_args()
