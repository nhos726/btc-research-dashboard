from pathlib import Path
from collect_snapshot import write_snapshot
import collect_snapshot


def test_write_snapshot_creates_latest_and_hourly_history(tmp_path, monkeypatch):
    monkeypatch.setattr(collect_snapshot, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(collect_snapshot, "HISTORY_DIR", tmp_path / "data" / "history")
    monkeypatch.setattr(collect_snapshot, "LATEST_PATH", tmp_path / "data" / "latest_snapshot.json")
    snap = {"observed_at": "2026-09-26T07:17:00+00:00", "x": 1}
    latest, history = write_snapshot(snap)
    assert latest.exists()
    assert history == tmp_path / "data" / "history" / "2026" / "09" / "26" / "07.json"
    assert '"x": 1' in latest.read_text(encoding="utf-8")
