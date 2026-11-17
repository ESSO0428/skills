"""Weight reading helpers (L1): inventory, statistics, cosine pairs, limited text dump."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

try:
    import torch
except ImportError:  # torch lives in the cpu / cu126 / cu132 extras
    raise SystemExit("""torch is not installed. Set up the skill environment once (pick by the CUDA Version shown by nvidia-smi):
  uv sync --project <skill dir> --extra cu132   # CUDA Version >= 13.2
  uv sync --project <skill dir> --extra cu126   # CUDA 12.x
  uv sync --project <skill dir> --extra cpu     # no NVIDIA GPU
(add --extra dev to run the tests; see README.md)""")

sys.path.insert(0, str(Path(__file__).parent))
from wsp_session import tensor_hash  # noqa: E402


def load_state(path: str | Path) -> dict[str, torch.Tensor]:
    """Load a .pt/.pth state_dict (weights_only) or a .safetensors file."""
    path = Path(path)
    if path.suffix == ".safetensors":
        try:
            from safetensors.torch import load_file
        except ImportError:
            raise SystemExit(
                "safetensors is not installed. Install it with `uv add safetensors` "
                "or run with `uv run --extra safetensors ...`."
            )
        return load_file(str(path))
    obj = torch.load(path, map_location="cpu", weights_only=True)
    if isinstance(obj, dict) and isinstance(obj.get("state_dict"), dict):
        obj = obj["state_dict"]
    if not isinstance(obj, dict) or not all(isinstance(v, torch.Tensor) for v in obj.values()):
        raise SystemExit("expected a state_dict of tensors (full pickled models are refused)")
    return obj


def inventory(state: dict[str, torch.Tensor]) -> list[dict]:
    return [
        {
            "name": k,
            "shape": list(v.shape),
            "dtype": str(v.dtype).replace("torch.", ""),
            "numel": v.numel(),
            "sha256": tensor_hash(v),
        }
        for k, v in state.items()
    ]


def _matrix(t: torch.Tensor) -> torch.Tensor:
    return t.float().reshape(t.shape[0], -1)


def stats(t: torch.Tensor, top_sv: int = 5, near_zero: float = 1e-6) -> dict:
    f = t.float()
    out = {
        "numel": t.numel(),
        "norm": float(f.norm()),
        "mean": float(f.mean()),
        "std": float(f.std()) if t.numel() > 1 else 0.0,
        "near_zero_fraction": float((f.abs() <= near_zero).float().mean()),
    }
    if t.ndim >= 2:
        M = _matrix(t)
        s = torch.linalg.svdvals(M)
        total = float(s.sum())
        eff = 0.0
        if total > 0:
            p = s[s > 0] / total
            eff = math.exp(-float((p * p.log()).sum()))
        out["top_singular_values"] = [float(x) for x in s[:top_sv]]
        out["effective_rank"] = eff
        out["dead_rows"] = int((M.abs().max(dim=1).values <= near_zero).sum())
        out["dead_cols"] = int((M.abs().max(dim=0).values <= near_zero).sum())
    return out


def top_cosine_pairs(t: torch.Tensor, k: int = 5) -> list[dict]:
    """Most similar row pairs (e.g. confusable output classes)."""
    M = _matrix(t)
    M = M / M.norm(dim=1, keepdim=True).clamp_min(1e-12)
    C = M @ M.T
    n = C.shape[0]
    pairs = sorted(((float(C[i, j]), i, j) for i in range(n) for j in range(i + 1, n)), reverse=True)
    return [{"rows": [i, j], "cosine": c} for c, i, j in pairs[:k]]


def text_dump(t: torch.Tensor, max_chars: int = 4000) -> str:
    """Integers times one scale, one row per line, cut at max_chars (the footer says so)."""
    M = _matrix(t)
    amax = float(M.abs().max())
    scale = amax / 99 if amax > 0 else 1.0
    ints = (M / scale).round().to(torch.int64)
    header = f"shape={list(t.shape)} value = integer * {scale:.6g}\n"
    body, used, truncated = [], len(header), False
    for i, row in enumerate(ints.tolist()):
        line = f"{i}: " + " ".join(map(str, row)) + "\n"
        if used + len(line) > max_chars:
            truncated = True
            break
        body.append(line)
        used += len(line)
    footer = f"[truncated after {len(body)} of {M.shape[0]} rows]\n" if truncated else ""
    return header + "".join(body) + footer


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Inspect a state_dict (.pt/.pth/.safetensors).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("inventory", "stats", "cosine", "dump"):
        p = sub.add_parser(name)
        p.add_argument("path")
        if name != "inventory":
            p.add_argument("--pattern", default=".", help="regex over tensor names")
        if name == "cosine":
            p.add_argument("--top", type=int, default=5)
        if name == "dump":
            p.add_argument("--max-chars", type=int, default=4000)
    a = ap.parse_args(argv)
    state = load_state(a.path)
    if a.cmd == "inventory":
        print(json.dumps(inventory(state), indent=1))
        return
    for n in (n for n in state if re.search(a.pattern, n)):
        if a.cmd == "stats":
            print(n, json.dumps(stats(state[n])))
        elif a.cmd == "cosine" and state[n].ndim >= 2:
            print(n, json.dumps(top_cosine_pairs(state[n], a.top)))
        elif a.cmd == "dump" and state[n].ndim >= 1:
            print(f"== {n}\n" + text_dump(state[n], a.max_chars))


if __name__ == "__main__":
    main()
