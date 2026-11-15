import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "distilling-youtube-channel" / "scripts" / "build_semantic_review.py"


def test_stage123_audit_groups_gap_types_with_recommendations(tmp_path):
    manifest = tmp_path / "data" / "manifest" / "videos.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"videos": {
        "dl1": {"video_id": "dl1", "title": "A", "status": "DOWNLOAD_FAILED"},
        "asr1": {"video_id": "asr1", "title": "B", "verified": True, "transcript_status": "ASR_FAILED"},
    }}), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--workspace", str(tmp_path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    audit = json.loads(
        (tmp_path / "evaluation" / "semantic-review-audit-latest.json").read_text(encoding="utf-8")
    )
    assert audit["blocked_by_gap_kind"] == {"DOWNLOAD_FAILED": 1, "VERIFIED_MEDIA_TEXT_FAILURE": 1}
    grouped = audit["gap_type_recommendations"]
    assert set(grouped) == set(audit["blocked_by_gap_kind"])
    for kind, count in audit["blocked_by_gap_kind"].items():
        assert grouped[kind]["count"] == count
        assert len(grouped[kind]["video_ids"]) == count
        assert len(grouped[kind]["items"]) == count
        assert all(item["url"].startswith("https://www.youtube.com/watch?v=") for item in grouped[kind]["items"])
        assert "放棄" in grouped[kind]["recommendation"]
    assert audit["gap_set_consistency"]["status"] == "PASS"
    assert audit["gap_set_consistency"]["unclassified_gap_ids"] == []
    assert audit["gap_set_consistency"]["orphan_grouped_ids"] == []
    assert audit["gap_set_consistency"]["duplicate_grouped_ids"] == []
    assert (tmp_path / "evaluation" / "stage123-review-audit-latest.json").is_file()
