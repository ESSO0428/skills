"""Import and merge YouTube metadata; live helpers fetch metadata only."""

from __future__ import annotations

from copy import deepcopy
import json
import subprocess
from urllib.parse import parse_qs, urlparse


CHANNEL_BASE = "https://www.youtube.com/channel"
UNAVAILABLE_STATES = {"private", "deleted", "unavailable"}


def _playlist_id(payload: dict, origin: str) -> str | None:
    value = payload.get("id")
    if value:
        return str(value)
    return parse_qs(urlparse(origin).query).get("list", [None])[0]


def parse_flat_entries(payload: dict, origin: str) -> dict[str, dict]:
    """Index flat metadata by ID, recording only actual playlist membership."""
    is_playlist = origin == "playlist" or "/playlist?" in origin
    membership = []
    if is_playlist:
        playlist_id = _playlist_id(payload, origin)
        if playlist_id:
            membership = [{
                "id": playlist_id,
                "title": payload.get("title"),
                "url": f"https://www.youtube.com/playlist?list={playlist_id}",
            }]

    videos: dict[str, dict] = {}
    for entry in payload.get("entries") or []:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        video_id = str(entry["id"])
        source_url = entry.get("url") or entry.get("webpage_url") or ""
        unavailable = (
            entry.get("availability") in UNAVAILABLE_STATES
            or entry.get("title") in {"[Private video]", "[Deleted video]"}
        )
        record = {
            "video_id": video_id,
            "title": entry.get("title"),
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "duration": entry.get("duration"),
            "upload_date": entry.get("upload_date"),
            "playlist": deepcopy(membership),
            "series": None,
            "topics": [],
            "topic_priority": "unknown",
            "media_type": "short" if entry.get("is_short") or "/shorts/" in source_url else "video",
            "status": "UNAVAILABLE" if unavailable else "DISCOVERED",
            "retryable": not unavailable,
            "inventory_sources": [origin],
        }
        videos = merge_inventory(videos, {video_id: record})
    return videos


def merge_inventory(existing: dict[str, dict], incoming: dict[str, dict]) -> dict[str, dict]:
    """Merge by video ID, retaining downloaded state and all real playlists."""
    merged = deepcopy(existing)
    for video_id, update in incoming.items():
        if video_id not in merged:
            merged[video_id] = deepcopy(update)
            continue
        current = merged[video_id]
        for key, value in update.items():
            if key == "playlist":
                playlists = current.setdefault("playlist", [])
                seen = {p.get("id") for p in playlists if isinstance(p, dict)}
                for item in value or []:
                    if item.get("id") not in seen:
                        playlists.append(deepcopy(item))
                        seen.add(item.get("id"))
            elif key == "inventory_sources":
                sources = current.setdefault("inventory_sources", [])
                for source in value or []:
                    if source not in sources:
                        sources.append(source)
            elif key in {"topics", "topic_priority"} and (not value or value == "unknown"):
                continue
            elif key == "status" and value == "DISCOVERED" and (
                current.get("status") not in (None, "DISCOVERED") or current.get("verified")
            ):
                continue
            elif key == "retryable" and update.get("status") == "DISCOVERED" and (
                current.get("status") not in (None, "DISCOVERED") or current.get("verified")
            ):
                continue
            elif value is not None:
                current[key] = deepcopy(value)
    return merged


def parse_upstream_snapshot(payload: dict) -> dict[str, dict]:
    """Import upstream video IDs/titles without trusting inferred series/topics."""
    entries = []
    for video in payload.get("videos") or []:
        if isinstance(video, dict):
            entries.append({
                "id": video.get("video_id"),
                "title": video.get("title"),
                "duration": video.get("duration"),
                "upload_date": video.get("upload_date"),
            })
    return parse_flat_entries({"entries": entries}, origin="upstream_snapshot")


def _yt_dlp_json(url: str, *, flat: bool) -> dict:
    command = ["yt-dlp", "--skip-download"]
    command.append("--flat-playlist" if flat else "--no-playlist")
    command.extend(["-J", url])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"yt-dlp failed for {url}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"yt-dlp returned invalid JSON for {url}") from exc


def fetch_channel_inventory(channel_id: str, *, include_playlists: bool = True) -> dict[str, dict]:
    """Scan `/videos` and each public playlist without downloading media."""
    base = f"{CHANNEL_BASE}/{channel_id}"
    videos_url = f"{base}/videos"
    videos = parse_flat_entries(_yt_dlp_json(videos_url, flat=True), videos_url)
    if not include_playlists:
        return videos
    playlist_index = _yt_dlp_json(f"{base}/playlists", flat=True)
    for listed in playlist_index.get("entries") or []:
        if not isinstance(listed, dict) or not listed.get("id"):
            continue
        playlist_id = str(listed["id"])
        playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
        playlist = _yt_dlp_json(playlist_url, flat=True)
        playlist.setdefault("id", playlist_id)
        if not playlist.get("title"):
            playlist["title"] = listed.get("title")
        videos = merge_inventory(videos, parse_flat_entries(playlist, playlist_url))
    return videos


def fetch_video_details(video_id: str) -> dict:
    """Hydrate one video with fields a flat listing may omit, without downloading."""
    payload = _yt_dlp_json(f"https://www.youtube.com/watch?v={video_id}", flat=False)
    if payload.get("id") != video_id:
        raise RuntimeError(f"yt-dlp returned a different video ID for {video_id}")
    return {
        "video_id": video_id,
        "title": payload.get("title"),
        "duration": payload.get("duration"),
        "upload_date": payload.get("upload_date"),
        "channel_id": payload.get("channel_id"),
    }


def hydrate_priority_metadata(videos: dict[str, dict], priority: str = "P0") -> dict[str, dict]:
    """Fetch missing duration/date for selected videos, leaving input untouched."""
    hydrated = deepcopy(videos)
    for video_id, record in hydrated.items():
        if record.get("topic_priority") != priority:
            continue
        if record.get("duration") is not None and record.get("upload_date") is not None:
            continue
        details = fetch_video_details(video_id)
        for field in ("title", "duration", "upload_date", "channel_id"):
            if details.get(field) is not None:
                record[field] = details[field]
    return hydrated
