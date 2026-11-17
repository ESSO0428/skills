"""Stop early with setup instructions when torch is missing (it is not a default dependency)."""
import importlib.util

import pytest

if importlib.util.find_spec("torch") is None:
    pytest.exit("""torch is not installed. Set up the skill environment once (pick by the CUDA Version shown by nvidia-smi):
  uv sync --project <skill dir> --extra cu132   # CUDA Version >= 13.2
  uv sync --project <skill dir> --extra cu126   # CUDA 12.x
  uv sync --project <skill dir> --extra cpu     # no NVIDIA GPU
(add --extra dev to run the tests; see README.md)""", returncode=2)
