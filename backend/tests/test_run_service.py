"""Tests for run_service: the per-asset pipeline and run orchestration."""

import json
from dataclasses import dataclass, field
from typing import Any

import pytest
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal, init_db
from app.models.asset_outcome import AssetOutcome
from app.models.run import Run
from app.services import run_service
from app.services.immich_client import Asset
from app.services.transcode import TranscodeResult


@dataclass
class FakeClient:
    download_result: tuple[int, str | None] = (1000, None)
    upload_result: tuple[str | None, str | None] = ("new-id", None)
    copy_result: tuple[bool, str | None] = (True, None)
    verify_result: tuple[bool, str | None] = (True, None)
    delete_result: tuple[bool, str | None] = (True, None)
    deleted_ids: list[str] = field(default_factory=list)
    search_pages: dict[str, list[list[Asset]]] = field(default_factory=dict)
    album_assets: list[Asset] = field(default_factory=list)
    by_id: dict[str, Asset] = field(default_factory=dict)

    def download_original(self, asset_id: str, output_path: str):
        if self.download_result[1] is None:
            with open(output_path, "wb") as f:
                f.write(b"x" * self.download_result[0])
        return self.download_result

    def upload_asset(self, **kwargs: Any):
        return self.upload_result

    def copy_asset_data(self, from_asset_id: str, to_asset_id: str):
        return self.copy_result

    def get_asset(self, asset_id: str):
        return self.verify_result

    def get_asset_full(self, asset_id: str):
        return self.by_id.get(asset_id)

    def delete_assets(self, asset_ids: list[str]):
        self.deleted_ids.extend(asset_ids)
        return self.delete_result

    def search_assets(self, page: int, size: int, asset_type: str, **kwargs: Any):
        pages = self.search_pages.get(asset_type, [])
        return pages[page - 1] if page <= len(pages) else []

    def get_album_assets(self, album_id: str):
        return self.album_assets


def _make_asset(
    asset_id: str = "a1",
    file_name: str = "photo.jpg",
    mime_type: str | None = "image/jpeg",
    asset_type: str = "IMAGE",
    created_at: str = "2023-01-01T00:00:00Z",
) -> Asset:
    return Asset(
        id=asset_id,
        original_file_name=file_name,
        original_path="/uploads/" + file_name,
        original_mime_type=mime_type,
        type=asset_type,
        file_created_at=created_at,
        file_modified_at=created_at,
    )


BASE_CFG = {
    "dry_run": False,
    "image_distance": 1.0,
    "image_distance_retry": 2.0,
    "video_crf": 36,
    "video_preset": 4,
    "video_max_dimension": 0,
    "video_audio_bitrate": "64k",
    "video_crf_retry": 40,
    "enable_retry": True,
    "accept_retry_output": False,
    "allow_larger": False,
}


class TestProcessAssetSyncImages:
    def test_already_jxl_skipped_without_download(self, tmp_path):
        asset = _make_asset(mime_type="image/jxl")
        client = FakeClient()
        result = run_service._process_asset_sync(asset, client, BASE_CFG, str(tmp_path))
        assert result["status"] == "skipped"

    def test_dry_run_image_skips_without_download(self, tmp_path):
        asset = _make_asset()
        client = FakeClient()
        cfg = {**BASE_CFG, "dry_run": True}
        result = run_service._process_asset_sync(asset, client, cfg, str(tmp_path))
        assert result["status"] == "dry_run_skip"

    def test_download_failure(self, tmp_path):
        asset = _make_asset()
        client = FakeClient(download_result=(0, "boom"))
        result = run_service._process_asset_sync(asset, client, BASE_CFG, str(tmp_path))
        assert result["status"] == "failed_download"
        assert result["error"] == "boom"

    def test_happy_path_success(self, tmp_path, monkeypatch):
        asset = _make_asset()
        client = FakeClient()

        monkeypatch.setattr(
            run_service,
            "transcode",
            lambda inp, out, distance: TranscodeResult(
                success=True,
                input_path=inp,
                output_path=out,
                input_bytes=1000,
                output_bytes=500,
                input_format="jpg",
            ),
        )
        monkeypatch.setattr(run_service, "validate_output", lambda path, fmt: True)

        result = run_service._process_asset_sync(asset, client, BASE_CFG, str(tmp_path))
        assert result["status"] == "success"
        assert result["new_asset_id"] == "new-id"
        assert client.deleted_ids == ["a1"]

    def test_output_larger_retries_then_accepts_smaller(self, tmp_path, monkeypatch):
        asset = _make_asset()
        client = FakeClient()
        calls = []

        def fake_transcode(inp, out, distance):
            calls.append(distance)
            output = 1500 if len(calls) == 1 else 400
            return TranscodeResult(
                success=True,
                input_path=inp,
                output_path=out,
                input_bytes=1000,
                output_bytes=output,
                input_format="jpg",
            )

        monkeypatch.setattr(run_service, "transcode", fake_transcode)
        monkeypatch.setattr(run_service, "validate_output", lambda path, fmt: True)

        result = run_service._process_asset_sync(asset, client, BASE_CFG, str(tmp_path))
        assert result["status"] == "success"
        assert calls == [BASE_CFG["image_distance"], BASE_CFG["image_distance_retry"]]

    def test_output_larger_retry_still_larger_is_skipped(self, tmp_path, monkeypatch):
        asset = _make_asset()
        client = FakeClient()
        monkeypatch.setattr(
            run_service,
            "transcode",
            lambda inp, out, distance: TranscodeResult(
                success=True,
                input_path=inp,
                output_path=out,
                input_bytes=1000,
                output_bytes=1500,
                input_format="jpg",
            ),
        )
        monkeypatch.setattr(run_service, "validate_output", lambda path, fmt: True)

        result = run_service._process_asset_sync(asset, client, BASE_CFG, str(tmp_path))
        assert result["status"] == "skipped"

    def test_upload_failure(self, tmp_path, monkeypatch):
        asset = _make_asset()
        client = FakeClient(upload_result=(None, "upload boom"))
        monkeypatch.setattr(
            run_service,
            "transcode",
            lambda inp, out, distance: TranscodeResult(
                success=True,
                input_path=inp,
                output_path=out,
                input_bytes=1000,
                output_bytes=500,
                input_format="jpg",
            ),
        )
        monkeypatch.setattr(run_service, "validate_output", lambda path, fmt: True)

        result = run_service._process_asset_sync(asset, client, BASE_CFG, str(tmp_path))
        assert result["status"] == "failed_upload"

    def test_copy_failure_deletes_new_asset(self, tmp_path, monkeypatch):
        asset = _make_asset()
        client = FakeClient(copy_result=(False, "copy boom"))
        monkeypatch.setattr(
            run_service,
            "transcode",
            lambda inp, out, distance: TranscodeResult(
                success=True,
                input_path=inp,
                output_path=out,
                input_bytes=1000,
                output_bytes=500,
                input_format="jpg",
            ),
        )
        monkeypatch.setattr(run_service, "validate_output", lambda path, fmt: True)

        result = run_service._process_asset_sync(asset, client, BASE_CFG, str(tmp_path))
        assert result["status"] == "failed_copy"
        assert client.deleted_ids == ["new-id"]

    def test_verification_failure_deletes_new_asset(self, tmp_path, monkeypatch):
        asset = _make_asset()
        client = FakeClient(verify_result=(False, "verify boom"))
        monkeypatch.setattr(
            run_service,
            "transcode",
            lambda inp, out, distance: TranscodeResult(
                success=True,
                input_path=inp,
                output_path=out,
                input_bytes=1000,
                output_bytes=500,
                input_format="jpg",
            ),
        )
        monkeypatch.setattr(run_service, "validate_output", lambda path, fmt: True)

        result = run_service._process_asset_sync(asset, client, BASE_CFG, str(tmp_path))
        assert result["status"] == "failed_verification"
        assert client.deleted_ids == ["new-id"]

    def test_delete_original_failure_is_partial_success(self, tmp_path, monkeypatch):
        asset = _make_asset()
        client = FakeClient(delete_result=(False, "delete boom"))
        monkeypatch.setattr(
            run_service,
            "transcode",
            lambda inp, out, distance: TranscodeResult(
                success=True,
                input_path=inp,
                output_path=out,
                input_bytes=1000,
                output_bytes=500,
                input_format="jpg",
            ),
        )
        monkeypatch.setattr(run_service, "validate_output", lambda path, fmt: True)

        result = run_service._process_asset_sync(asset, client, BASE_CFG, str(tmp_path))
        assert result["status"] == "partial_success"

    def test_transcode_failure(self, tmp_path, monkeypatch):
        asset = _make_asset()
        client = FakeClient()
        monkeypatch.setattr(
            run_service,
            "transcode",
            lambda inp, out, distance: TranscodeResult(
                success=False,
                input_path=inp,
                output_path=out,
                input_bytes=1000,
                output_bytes=0,
                input_format="jpg",
                error="bad input",
            ),
        )
        result = run_service._process_asset_sync(asset, client, BASE_CFG, str(tmp_path))
        assert result["status"] == "failed_transcode"

    def test_cleans_up_temp_files(self, tmp_path, monkeypatch):
        asset = _make_asset()
        client = FakeClient()
        monkeypatch.setattr(
            run_service,
            "transcode",
            lambda inp, out, distance: TranscodeResult(
                success=True,
                input_path=inp,
                output_path=out,
                input_bytes=1000,
                output_bytes=500,
                input_format="jpg",
            ),
        )
        monkeypatch.setattr(run_service, "validate_output", lambda path, fmt: True)
        run_service._process_asset_sync(asset, client, BASE_CFG, str(tmp_path))
        assert list(tmp_path.iterdir()) == []


class TestProcessAssetSyncVideos:
    def test_dry_run_video_downloads_for_codec_detection(self, tmp_path, monkeypatch):
        asset = _make_asset(
            asset_type="VIDEO", file_name="clip.mp4", mime_type="video/mp4"
        )
        client = FakeClient()
        monkeypatch.setattr(run_service, "detect_video_codec", lambda path: "h264")
        cfg = {**BASE_CFG, "dry_run": True}
        result = run_service._process_asset_sync(asset, client, cfg, str(tmp_path))
        assert result["status"] == "dry_run_skip"

    def test_dry_run_video_already_av1_is_skipped(self, tmp_path, monkeypatch):
        asset = _make_asset(
            asset_type="VIDEO", file_name="clip.mp4", mime_type="video/mp4"
        )
        client = FakeClient()
        monkeypatch.setattr(run_service, "detect_video_codec", lambda path: "av1")
        cfg = {**BASE_CFG, "dry_run": True}
        result = run_service._process_asset_sync(asset, client, cfg, str(tmp_path))
        assert result["status"] == "skipped"

    def test_video_happy_path(self, tmp_path, monkeypatch):
        asset = _make_asset(
            asset_type="VIDEO", file_name="clip.mp4", mime_type="video/mp4"
        )
        client = FakeClient()
        monkeypatch.setattr(
            run_service,
            "transcode_video",
            lambda inp, out, crf, preset, max_dimension, audio_bitrate: TranscodeResult(
                success=True,
                input_path=inp,
                output_path=out,
                input_bytes=1000,
                output_bytes=500,
                input_format="h264",
            ),
        )
        monkeypatch.setattr(run_service, "validate_video_output", lambda path: True)

        result = run_service._process_asset_sync(asset, client, BASE_CFG, str(tmp_path))
        assert result["status"] == "success"


@pytest.mark.asyncio
class TestResolveAssets:
    async def test_explicit_asset_ids(self):
        a1 = _make_asset("a1")
        a2 = _make_asset("a2", file_name="b.jpg")
        client = FakeClient(by_id={"a1": a1, "a2": a2})
        cfg = {**BASE_CFG, "asset_ids": ["a1", "a2", "missing"]}
        result = await run_service._resolve_assets(client, cfg)
        assert {a.id for a in result} == {"a1", "a2"}

    async def test_filter_based_search(self):
        a1 = _make_asset("a1")
        client = FakeClient(search_pages={"IMAGE": [[a1], []]})
        cfg = {
            **BASE_CFG,
            "asset_ids": None,
            "asset_types": "IMAGE",
            "album_id": None,
            "include_archived": False,
            "include_deleted": False,
            "skip_done_filter": True,
        }
        result = await run_service._resolve_assets(client, cfg)
        assert [a.id for a in result] == ["a1"]

    async def test_album_based_filters_by_type_and_date(self):
        a1 = _make_asset("a1", created_at="2023-01-01T00:00:00Z")
        a2 = _make_asset("a2", created_at="2023-06-01T00:00:00Z", file_name="b.jpg")
        video = _make_asset("v1", asset_type="VIDEO", file_name="c.mp4")
        client = FakeClient(album_assets=[a1, a2, video])
        cfg = {
            **BASE_CFG,
            "asset_ids": None,
            "asset_types": "IMAGE",
            "album_id": "album-1",
            "taken_after": "2023-03-01T00:00:00Z",
            "skip_done_filter": True,
        }
        result = await run_service._resolve_assets(client, cfg)
        assert [a.id for a in result] == ["a2"]

    async def test_skips_assets_with_final_status(self):
        await init_db()
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AssetOutcome))
            db.add(
                AssetOutcome(
                    run_id=1,
                    asset_id="a1",
                    filename="a.jpg",
                    status="success",
                )
            )
            await db.commit()

        a1 = _make_asset("a1")
        a2 = _make_asset("a2", file_name="b.jpg")
        client = FakeClient(search_pages={"IMAGE": [[a1, a2], []]})
        cfg = {
            **BASE_CFG,
            "asset_ids": None,
            "asset_types": "IMAGE",
            "album_id": None,
            "include_archived": False,
            "include_deleted": False,
        }
        result = await run_service._resolve_assets(client, cfg)
        assert [a.id for a in result] == ["a2"]


@dataclass
class FakeClientFactory:
    fake: FakeClient

    def __call__(self, api_base: str, api_key: str, **kwargs: Any):
        return self.fake


@pytest.mark.asyncio
class TestExecuteRun:
    async def test_happy_path_updates_counters_and_outcomes(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("TEMP_DIR", str(tmp_path))
        await init_db()
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AssetOutcome))
            await db.commit()

        a1 = _make_asset("run-a1", file_name="one.jpg")
        a2 = _make_asset("run-a2", file_name="two.jpg")
        client = FakeClient(search_pages={"IMAGE": [[a1, a2], []], "VIDEO": [[]]})
        monkeypatch.setattr(run_service, "ImmichClient", FakeClientFactory(client))
        monkeypatch.setattr(
            run_service,
            "transcode",
            lambda inp, out, distance: TranscodeResult(
                success=True,
                input_path=inp,
                output_path=out,
                input_bytes=1000,
                output_bytes=500,
                input_format="jpg",
            ),
        )
        monkeypatch.setattr(run_service, "validate_output", lambda path, fmt: True)

        cfg = {
            **BASE_CFG,
            "immich_api_base": "https://example.com/api/",
            "immich_api_key": "key",
            "asset_ids": None,
            "asset_types": "IMAGE",
            "album_id": None,
            "include_archived": False,
            "include_deleted": False,
            "taken_after": None,
            "taken_before": None,
            "original_filename": None,
            "max_assets": None,
            "concurrency": 2,
        }

        async with AsyncSessionLocal() as db:
            run = Run(status="queued", config_snapshot=json.dumps(cfg))
            db.add(run)
            await db.commit()
            await db.refresh(run)
            run_id = run.id

        await run_service.execute_run(run_id)

        async with AsyncSessionLocal() as db:
            run_result = await db.execute(select(Run).where(Run.id == run_id))
            refreshed = run_result.scalar_one()
            outcomes_result = await db.execute(
                select(AssetOutcome).where(AssetOutcome.run_id == run_id)
            )
            outcomes = outcomes_result.scalars().all()

        assert refreshed.status == "completed"
        assert refreshed.total_assets == 2
        assert refreshed.processed_count == 2
        assert refreshed.success_count == 2
        assert {o.asset_id for o in outcomes} == {"run-a1", "run-a2"}
        assert all(o.status == "success" for o in outcomes)
