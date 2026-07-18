"""End-to-end integration tests against a real Immich instance, driven
through the GUI's HTTP API (POST /api/runs, poll GET /api/runs/{id})
instead of calling the old CLI's run_converter() directly."""

import asyncio
import json
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
import requests

pytestmark = pytest.mark.integration


async def _wait_for_run(
    gui_client, run_id: int, timeout: float = 120
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = await gui_client.get(f"/api/runs/{run_id}")
        data = resp.json()
        if data["status"] in ("completed", "failed", "cancelled"):
            return data
        await asyncio.sleep(1)
    pytest.fail(f"Run {run_id} did not finish within {timeout}s")


def _get_asset_detail(admin_client, asset_id: str) -> dict[str, Any] | None:
    url = f"{admin_client.api_base}assets/{asset_id}"
    resp = requests.get(url, headers=admin_client._default_headers, timeout=10)
    return resp.json() if resp.status_code == 200 else None


class TestEndToEnd:
    async def test_full_flow(self, gui_client, admin_client, seeded_library, tmp_path):
        lib = seeded_library

        # sample.jpg: has EXIF/GPS/Artist injected by the seeder, is
        # favorited, and belongs to the "Vacation 2023" album.
        source_id = lib["images"]["sample.jpg"]

        create_resp = await gui_client.post(
            "/api/runs", json={"asset_ids": [source_id], "dry_run": False}
        )
        assert create_resp.status_code == 200
        run = await _wait_for_run(gui_client, create_resp.json()["id"])
        assert run["status"] == "completed"
        assert run["success_count"] == 1

        outcomes = (await gui_client.get(f"/api/runs/{run['id']}/assets")).json()[
            "items"
        ]
        assert len(outcomes) == 1
        assert outcomes[0]["status"] == "success"
        new_asset_id = outcomes[0]["new_asset_id"]
        assert new_asset_id

        # New asset replaced the original.
        assert _get_asset_detail(admin_client, source_id) is None or _get_asset_detail(
            admin_client, source_id
        ).get("isTrashed")

        detail = _get_asset_detail(admin_client, new_asset_id)
        assert detail is not None
        assert detail["isFavorite"] is True
        assert detail["originalFileName"].endswith(".jxl")

        # EXIF/GPS preserved end to end.
        jxl_path = tmp_path / "converted.jxl"
        size, err = admin_client.download_original(new_asset_id, str(jxl_path))
        assert err is None and size > 0
        exif = subprocess.run(
            [
                "exiftool",
                "-json",
                "-GPSLatitude",
                "-GPSLongitude",
                "-Artist",
                str(jxl_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        tags = json.loads(exif.stdout)[0]
        assert tags.get("GPSLatitude"), "GPSLatitude missing from converted JXL"
        assert "integration test" in str(tags.get("Artist", ""))

        # Album membership preserved via the new copy-based flow.
        album_assets = admin_client.get_album_assets(lib["albums"]["vacation"])
        assert new_asset_id in {a.id for a in album_assets}

        # A video too, via the same run-creation path.
        video_source_id = lib["videos"]["h264.mp4"]
        video_run_resp = await gui_client.post(
            "/api/runs", json={"asset_ids": [video_source_id], "dry_run": False}
        )
        video_run = await _wait_for_run(gui_client, video_run_resp.json()["id"])
        assert video_run["status"] == "completed"
        assert video_run["success_count"] == 1

        video_outcomes = (
            await gui_client.get(f"/api/runs/{video_run['id']}/assets")
        ).json()["items"]
        new_video_id = video_outcomes[0]["new_asset_id"]
        assert new_video_id

        video_path = tmp_path / "converted.mp4"
        size, err = admin_client.download_original(new_video_id, str(video_path))
        assert err is None and size > 0
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        assert probe.stdout.strip() == "av1"

    async def test_skips_already_converted_asset(self, gui_client, seeded_library):
        # already.jxl is pre-converted by the seeder; a filter-based run
        # should skip it via mime-type detection without downloading.
        create_resp = await gui_client.post(
            "/api/runs",
            json={
                "asset_ids": [seeded_library["images"]["already.jxl"]],
                "dry_run": False,
            },
        )
        run = await _wait_for_run(gui_client, create_resp.json()["id"])
        assert run["status"] == "completed"
        assert run["skipped_count"] == 1
        assert run["success_count"] == 0

    async def test_upload_failure_rollback(
        self, gui_client, admin_client, upload_fault_api_base, seeded_library, tmp_path
    ):
        """POST /api/assets returns 503 via the fault proxy. The converter
        must record failed_upload, leave the original intact, and create no
        new asset."""
        _ = seeded_library  # ensures the library (and thus the marker album) exists

        fixture = Path(__file__).parent / "fixtures" / "sample.jpg"
        unique_name = f"rollback-target-{uuid.uuid4().hex[:8]}.jpg"
        target_path = tmp_path / unique_name
        target_path.write_bytes(fixture.read_bytes())

        fresh_id, err = admin_client.upload_asset(
            file_path=str(target_path),
            file_created_at="2017-05-05T00:00:00Z",
            file_modified_at="2017-05-05T00:00:00Z",
            filename=unique_name,
        )
        assert err is None and fresh_id

        # Point this run's connection at the fault proxy for the upload step.
        await gui_client.put(
            "/api/settings",
            json={"immich_api_base": upload_fault_api_base},
        )
        create_resp = await gui_client.post(
            "/api/runs", json={"asset_ids": [fresh_id], "dry_run": False}
        )
        run = await _wait_for_run(gui_client, create_resp.json()["id"])
        assert run["status"] == "completed"
        assert run["failed_count"] == 1

        outcomes = (await gui_client.get(f"/api/runs/{run['id']}/assets")).json()[
            "items"
        ]
        assert outcomes[0]["status"] == "failed_upload"
        assert outcomes[0]["new_asset_id"] is None

        # Original untouched -- verified against the real (non-faulty) base.
        detail = _get_asset_detail(admin_client, fresh_id)
        assert detail is not None
        assert not detail.get("isTrashed")
