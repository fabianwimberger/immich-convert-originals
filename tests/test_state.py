"""Tests for the SQLite-backed state database."""

import os

from app.state import StateDB


def test_record_and_get_status(tmp_path):
    db = StateDB(str(tmp_path / "state.db"))
    try:
        db.record("a1", "success", "foo.jpg", input_bytes=100, output_bytes=50)
        assert db.get_status("a1") == "success"
        assert db.get_status("missing") is None
    finally:
        db.close()


def test_record_upserts(tmp_path):
    db = StateDB(str(tmp_path / "state.db"))
    try:
        db.record("a1", "failed_upload", "foo.jpg", error="503")
        db.record("a1", "success", "foo.jpg")
        assert db.get_status("a1") == "success"
    finally:
        db.close()


def test_completed_and_failed_ids(tmp_path):
    db = StateDB(str(tmp_path / "state.db"))
    try:
        db.record("ok", "success", "a.jpg")
        db.record("part", "partial_success", "b.jpg")
        db.record("skip", "skipped", "c.jpg")
        db.record("fail1", "failed_upload", "d.jpg", error="boom")
        db.record("fail2", "failed_transcode", "e.jpg")
        db.record("unk", "error", "f.jpg")

        assert db.completed_ids() == {"ok", "part", "skip"}
        assert db.failed_ids() == {"fail1", "fail2", "unk"}
    finally:
        db.close()


def test_export_failures_csv(tmp_path):
    db = StateDB(str(tmp_path / "state.db"))
    try:
        db.record("ok", "success", "a.jpg")
        db.record("fail1", "failed_upload", "d.jpg", error="503 Service Unavailable")
        db.record("fail2", "failed_transcode", "e.jpg", error=None)

        csv_path = tmp_path / "failures.csv"
        count = db.export_failures_csv(str(csv_path))
        assert count == 2

        content = csv_path.read_text()
        assert "asset_id,filename,status,error,updated_at" in content
        assert "fail1" in content and "503" in content
        assert "fail2" in content
        assert "ok" not in content
    finally:
        db.close()


def test_reset(tmp_path):
    db = StateDB(str(tmp_path / "state.db"))
    try:
        db.record("a", "success", "x.jpg")
        db.record("b", "failed_upload", "y.jpg")
        db.reset()
        assert db.completed_ids() == set()
        assert db.failed_ids() == set()
    finally:
        db.close()


def test_context_manager_closes(tmp_path):
    path = tmp_path / "state.db"
    with StateDB(str(path)) as db:
        db.record("a", "success", "x.jpg")
    # Re-open to confirm data persisted and no stale lock.
    with StateDB(str(path)) as db2:
        assert db2.get_status("a") == "success"


def test_creates_parent_directory(tmp_path):
    nested = tmp_path / "nested" / "dir" / "state.db"
    db = StateDB(str(nested))
    try:
        assert os.path.exists(nested)
    finally:
        db.close()
