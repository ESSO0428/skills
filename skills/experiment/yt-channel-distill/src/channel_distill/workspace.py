"""Workspace layout and external-binary lookup shared by the CLI and skill scripts."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import os
from pathlib import Path
import shutil
import sys

COLLECTION_ROOT = Path(__file__).resolve().parents[2]
_INSTALL_HINTS = {
    "ffmpeg": "install ffmpeg (https://ffmpeg.org/download.html), add it to PATH, or set $YTD_FFMPEG_DIR / pass the flag",
    "ffprobe": "install ffmpeg (ships ffprobe), add it to PATH, or set $YTD_FFMPEG_DIR / pass the flag",
}


@dataclass(frozen=True)
class Workspace:
    root: Path

    @property
    def data(self) -> Path:
        return self.root / "data"

    manifest = property(lambda self: self.data / "manifest")
    videos = property(lambda self: self.data / "videos")
    transcripts = property(lambda self: self.data / "transcripts")
    processing = property(lambda self: self.data / "processing")
    models = property(lambda self: self.data / "models")
    knowledge = property(lambda self: self.root / "knowledge")
    evaluation = property(lambda self: self.root / "evaluation")
    config = property(lambda self: self.root / "config")


def resolve_workspace(arg: str | Path | None = None) -> Workspace:
    """Resolve the workspace: ``--workspace`` > ``$YTD_WORKSPACE`` > current directory."""
    chosen = arg or os.environ.get("YTD_WORKSPACE") or Path.cwd()
    return Workspace(Path(chosen).expanduser().resolve())


def find_binary(name: str, flag: str | Path | None = None, env: str = "YTD_FFMPEG_DIR") -> Path:
    """Locate an executable: explicit flag > ``$YTD_FFMPEG_DIR`` > PATH."""
    if flag:
        flagged = Path(flag)
        if flagged.is_file():
            return flagged
        found = shutil.which(str(flag))
        if found:
            return Path(found)
        raise FileNotFoundError(f"{name} not found at {flag}; {_INSTALL_HINTS.get(name, 'install it')}")
    directory = os.environ.get(env)
    if directory:
        found = shutil.which(name, path=directory)
        if found:
            return Path(found)
    found = shutil.which(name)
    if found:
        return Path(found)
    raise FileNotFoundError(f"{name} not found; {_INSTALL_HINTS.get(name, 'install it and add it to PATH')}")


def load_llm_wiki_module(name: str):
    """Import a module from the sibling llm-wiki skill's scripts directory."""
    scripts = COLLECTION_ROOT / "skills" / "llm-wiki" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    path = scripts / f"{name}.py"
    if not path.is_file():
        raise FileNotFoundError(f"llm-wiki script missing: {path}")
    spec = importlib.util.find_spec(name)
    if spec is None:
        raise ImportError(f"cannot import {name} from {scripts}")
    return importlib.import_module(name)
