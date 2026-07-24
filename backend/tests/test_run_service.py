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
    download_calls: int = 0
    upload_calls: int = 0

    def download_original(self, asset_id: str, output_path: str):
        self.download_calls += 1
        if self.download_result[1] is None:
            with open(output_path, "wb") as f:
                f.write(b"x" * self.download_result[0])
        return self.download_result

    def upload_asset(self, **kwargs: Any):
        self.upload_calls += 1
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
    "convert_image_formats": "jpg,png,webp,heic,avif,tiff,gif,bmp",
    "image_target_format": "jxl",
    "image_distance": 1.0,
    "image_distance_retry": 2.0,
    "image_quality_heic": 80,
    "image_quality_heic_retry": 60,
    "image_quality_avif": 75,
    "image_quality_avif_retry": 55,
    "video_crf": 36,
    "video_preset": 4,
    "video_max_dimension": 0,
    "video_audio_bitrate": "64k",
    "video_crf_retry": 40,
    "enable_retry": True,
    "accept_retry_output": False,
    "allow_larger": False,
    "output_mode": "upload",
    "local_output_dir": "/app/output",
    "local_keep_originals": False,
}


class TestGetTargetFormat:
    def test_video_always_mp4(self):
        asset = _make_asset(
            asset_type="VIDEO", file_name="clip.mp4", mime_type="video/mp4"
        )
        cfg = {"image_target_format": "heic"}
        assert run_service._get_target_format(asset, cfg) == "mp4"

    def test_image_uses_configured_format(self):
        asset = _make_asset()
        assert (
            run_service._get_target_format(asset, {"image_target_format": "avif"})
            == "avif"
        )

    def test_image_falls_back_to_jxl_when_missing(self):
        """A config_snapshot persisted before this setting existed must still
        default to jxl instead of KeyError-ing."""
        asset = _make_asset()
        assert run_service._get_target_format(asset, {}) == "jxl"


class TestGetImageQuality:
    def test_jxl_uses_distance(self):
        assert run_service._get_image_quality(BASE_CFG, "jxl", retry=False) == 1.0
        assert run_service._get_image_quality(BASE_CFG, "jxl", retry=True) == 2.0

    def test_heic_uses_quality(self):
        assert run_service._get_image_quality(BASE_CFG, "heic", retry=False) == 80
        assert run_service._get_image_quality(BASE_CFG, "heic", retry=True) == 60

    def test_avif_uses_quality(self):
        assert run_service._get_image_quality(BASE_CFG, "avif", retry=False) == 75
        assert run_service._get_image_quality(BASE_CFG, "avif", retry=True) == 55

    def test_falls_back_to_defaults_for_missing_keys(self):
        assert run_service._get_image_quality({}, "jxl", retry=False) == 1.0
        assert run_service._get_image_quality({}, "heic", retry=True) == 60
        assert run_service._get_image_quality({}, "avif", retry=False) == 75


class TestLocalOutputPaths:
    def test_output_path_is_dated_by_capture_year_month(self):
        asset = _make_asset(file_name="photo.jpg", created_at="2024-03-09T12:00:00Z")
        path = run_service._local_output_path("/out", asset, "avif")
        assert path == "/out/2024/03/photo.avif"

    def test_original_path_is_dated_and_under_originals_subdir(self):
        asset = _make_asset(file_name="photo.jpg", created_at="2024-03-09T12:00:00Z")
        path = run_service._local_original_path("/out", asset)
        assert path == "/out/2024/03/originals/photo.jpg"


class TestProcessAssetSyncImages:
    def test_already_jxl_skipped_without_download(self, tmp_path):
        asset = _make_asset(mime_type="image/jxl")
        client = FakeClient()
        result = run_service._process_asset_sync(asset, client, BASE_CFG, str(tmp_path))
        assert result["status"] == "skipped"
        assert result["error"] == "Already JPEG XL"
        assert client.download_calls == 0

    def test_excluded_format_skipped_without_download(self, tmp_path):
        asset = _make_asset(file_name="photo.heic", mime_type="image/heic")
        client = FakeClient()
        cfg = {**BASE_CFG, "convert_image_formats": "jpg,png"}
        result = run_service._process_asset_sync(asset, client, cfg, str(tmp_path))
        assert result["status"] == "skipped"
        assert result["error"] == "Format excluded by settings"
        assert client.download_calls == 0

    def test_allowed_format_not_skipped(self, tmp_path, monkeypatch):
        asset = _make_asset(file_name="photo.heic", mime_type="image/heic")
        client = FakeClient()
        cfg = {**BASE_CFG, "convert_image_formats": "jpg,heic", "dry_run": True}
        monkeypatch.setattr(
            run_service,
            "transcode",
            lambda inp, out, fmt, distance: TranscodeResult(
                success=True,
                input_path=inp,
                output_path=out,
                input_bytes=1000,
                output_bytes=500,
                input_format="heic",
            ),
        )
        monkeypatch.setattr(run_service, "validate_output", lambda path, fmt: True)
        result = run_service._process_asset_sync(asset, client, cfg, str(tmp_path))
        assert result["status"] == "dry_run_preview"
        assert client.download_calls == 1

    def test_uses_configured_target_format_and_quality(self, tmp_path, monkeypatch):
        asset = _make_asset()
        client = FakeClient()
        cfg = {**BASE_CFG, "image_target_format": "avif", "dry_run": True}
        captured = {}

        def fake_transcode(inp, out, fmt, quality):
            captured["fmt"] = fmt
            captured["quality"] = quality
            captured["out"] = out
            return TranscodeResult(
                success=True,
                input_path=inp,
                output_path=out,
                input_bytes=1000,
                output_bytes=500,
                input_format="jpg",
            )

        monkeypatch.setattr(run_service, "transcode", fake_transcode)
        monkeypatch.setattr(run_service, "validate_output", lambda path, fmt: True)

        result = run_service._process_asset_sync(asset, client, cfg, str(tmp_path))
        assert result["status"] == "dry_run_preview"
        assert result["target_format"] == "avif"
        assert captured["fmt"] == "avif"
        assert captured["quality"] == BASE_CFG["image_quality_avif"]
        assert captured["out"].endswith(".avif")

    def test_missing_convert_image_formats_key_defaults_to_all(self, tmp_path):
        """A config_snapshot persisted before this setting existed (e.g. a
        retry-failed run started from an old run row) has no
        convert_image_formats key at all -- it must still convert everything
        instead of KeyError-ing or skipping every asset."""
        asset = _make_asset(file_name="photo.heic", mime_type="image/heic")
        cfg = {k: v for k, v in BASE_CFG.items() if k != "convert_image_formats"}
        assert "convert_image_formats" not in cfg
        reason = run_service._should_skip_by_mime_type(asset, cfg)
        assert reason is None

    def test_dry_run_image_previews_real_size_without_upload(
        self, tmp_path, monkeypatch
    ):
        asset = _make_asset()
        client = FakeClient()
        cfg = {**BASE_CFG, "dry_run": True}

        monkeypatch.setattr(
            run_service,
            "transcode",
            lambda inp, out, fmt, distance: TranscodeResult(
                success=True,
                input_path=inp,
                output_path=out,
                input_bytes=1000,
                output_bytes=500,
                input_format="jpg",
            ),
        )
        monkeypatch.setattr(run_service, "validate_output", lambda path, fmt: True)

        result = run_service._process_asset_sync(asset, client, cfg, str(tmp_path))
        assert result["status"] == "dry_run_preview"
        assert result["input_bytes"] == 1000
        assert result["output_bytes"] == 500
        assert client.deleted_ids == []

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
            lambda inp, out, fmt, distance: TranscodeResult(
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

        def fake_transcode(inp, out, fmt, distance):
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
            lambda inp, out, fmt, distance: TranscodeResult(
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
            lambda inp, out, fmt, distance: TranscodeResult(
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
            lambda inp, out, fmt, distance: TranscodeResult(
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
            lambda inp, out, fmt, distance: TranscodeResult(
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
            lambda inp, out, fmt, distance: TranscodeResult(
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
            lambda inp, out, fmt, distance: TranscodeResult(
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
        assert result["input_bytes"] == 0

    def test_cleans_up_temp_files(self, tmp_path, monkeypatch):
        asset = _make_asset()
        client = FakeClient()
        monkeypatch.setattr(
            run_service,
            "transcode",
            lambda inp, out, fmt, distance: TranscodeResult(
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


class TestProcessAssetSyncLocalMode:
    def _patch_transcode(self, monkeypatch, input_format="jpg"):
        def fake_transcode(inp, out, fmt, quality):
            # shutil.move/copy2 in the local-save path need a real file --
            # unlike upload_asset (which just reads kwargs), this is the
            # first path that actually touches output_path on disk.
            with open(out, "wb") as f:
                f.write(b"x" * 500)
            return TranscodeResult(
                success=True,
                input_path=inp,
                output_path=out,
                input_bytes=1000,
                output_bytes=500,
                input_format=input_format,
            )

        monkeypatch.setattr(run_service, "transcode", fake_transcode)
        monkeypatch.setattr(run_service, "validate_output", lambda path, fmt: True)

    def test_saves_to_dated_local_path_without_touching_immich(
        self, tmp_path, monkeypatch
    ):
        local_dir = tmp_path / "output"
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        asset = _make_asset(file_name="photo.jpg", created_at="2023-06-15T00:00:00Z")
        client = FakeClient()
        cfg = {**BASE_CFG, "output_mode": "local", "local_output_dir": str(local_dir)}
        self._patch_transcode(monkeypatch)

        result = run_service._process_asset_sync(asset, client, cfg, str(work_dir))

        assert result["status"] == "saved_local"
        assert result.get("new_asset_id") is None
        assert client.upload_calls == 0
        assert client.deleted_ids == []

        dest = local_dir / "2023" / "06" / "photo.jxl"
        assert dest.exists()
        assert dest.read_bytes() == b"x" * 500

    def test_keep_originals_copies_source_alongside(self, tmp_path, monkeypatch):
        local_dir = tmp_path / "output"
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        asset = _make_asset(file_name="photo.jpg", created_at="2023-06-15T00:00:00Z")
        client = FakeClient()
        cfg = {
            **BASE_CFG,
            "output_mode": "local",
            "local_output_dir": str(local_dir),
            "local_keep_originals": True,
        }
        self._patch_transcode(monkeypatch)

        result = run_service._process_asset_sync(asset, client, cfg, str(work_dir))

        assert result["status"] == "saved_local"
        original_dest = local_dir / "2023" / "06" / "originals" / "photo.jpg"
        assert original_dest.exists()

    def test_keep_originals_off_does_not_copy_source(self, tmp_path, monkeypatch):
        local_dir = tmp_path / "output"
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        asset = _make_asset(file_name="photo.jpg", created_at="2023-06-15T00:00:00Z")
        client = FakeClient()
        cfg = {**BASE_CFG, "output_mode": "local", "local_output_dir": str(local_dir)}
        self._patch_transcode(monkeypatch)

        run_service._process_asset_sync(asset, client, cfg, str(work_dir))

        assert not (local_dir / "2023" / "06" / "originals").exists()

    def test_dry_run_previews_without_writing_local_files(self, tmp_path, monkeypatch):
        local_dir = tmp_path / "output"
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        asset = _make_asset()
        client = FakeClient()
        cfg = {
            **BASE_CFG,
            "output_mode": "local",
            "local_output_dir": str(local_dir),
            "dry_run": True,
        }
        self._patch_transcode(monkeypatch)

        result = run_service._process_asset_sync(asset, client, cfg, str(work_dir))

        assert result["status"] == "dry_run_preview"
        assert not local_dir.exists()


class TestProcessAssetSyncVideos:
    def test_dry_run_video_previews_real_size_without_upload(
        self, tmp_path, monkeypatch
    ):
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
                output_bytes=600,
                input_format="h264",
            ),
        )
        monkeypatch.setattr(run_service, "validate_video_output", lambda path: True)
        cfg = {**BASE_CFG, "dry_run": True}
        result = run_service._process_asset_sync(asset, client, cfg, str(tmp_path))
        assert result["status"] == "dry_run_preview"
        assert result["input_bytes"] == 1000
        assert result["output_bytes"] == 600
        assert client.deleted_ids == []

    def test_dry_run_video_already_av1_is_skipped(self, tmp_path, monkeypatch):
        asset = _make_asset(
            asset_type="VIDEO", file_name="clip.mp4", mime_type="video/mp4"
        )
        client = FakeClient()
        monkeypatch.setattr(
            run_service,
            "transcode_video",
            lambda inp, out, crf, preset, max_dimension, audio_bitrate: TranscodeResult(
                success=False,
                input_path=inp,
                output_path=out,
                input_bytes=1000,
                output_bytes=1000,
                input_format="av1",
                error="Already AV1",
            ),
        )
        cfg = {**BASE_CFG, "dry_run": True}
        result = run_service._process_asset_sync(asset, client, cfg, str(tmp_path))
        assert result["status"] == "skipped"
        assert result["input_bytes"] == 0

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
            lambda inp, out, fmt, distance: TranscodeResult(
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

    async def test_one_asset_exception_does_not_abort_run(self, tmp_path, monkeypatch):
        """An unexpected error in one asset's pipeline must not blow up the
        whole gather() -- it should be recorded as a failed outcome and let
        the rest of the run continue instead of aborting to execute_run's
        except/finally (which deletes work_dir out from under any sibling
        assets still using it)."""
        monkeypatch.setenv("TEMP_DIR", str(tmp_path))
        await init_db()
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AssetOutcome))
            await db.commit()

        a1 = _make_asset("boom-a1", file_name="one.jpg")
        a2 = _make_asset("boom-a2", file_name="two.jpg")
        client = FakeClient(search_pages={"IMAGE": [[a1, a2], []], "VIDEO": [[]]})
        monkeypatch.setattr(run_service, "ImmichClient", FakeClientFactory(client))
        monkeypatch.setattr(run_service, "validate_output", lambda path, fmt: True)

        def flaky_transcode(inp, out, fmt, distance):
            if "boom-a1" in inp:
                raise RuntimeError("disk exploded")
            return TranscodeResult(
                success=True,
                input_path=inp,
                output_path=out,
                input_bytes=1000,
                output_bytes=500,
                input_format="jpg",
            )

        monkeypatch.setattr(run_service, "transcode", flaky_transcode)

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
            "concurrency": 1,
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
            outcomes = {o.asset_id: o for o in outcomes_result.scalars().all()}

        assert refreshed.status == "completed"
        assert refreshed.processed_count == 2
        assert refreshed.failed_count == 1
        assert refreshed.success_count == 1
        assert outcomes["boom-a1"].status == "failed_error"
        assert "disk exploded" in outcomes["boom-a1"].error
        assert outcomes["boom-a2"].status == "success"

    async def test_cancel_during_run_marks_run_cancelled(self, tmp_path, monkeypatch):
        """A run cancelled while assets are still processing must end up
        status == "cancelled" -- the flag used to be discarded before it was
        read, so every cancelled run silently reported "completed" instead."""
        monkeypatch.setenv("TEMP_DIR", str(tmp_path))
        await init_db()
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AssetOutcome))
            await db.commit()

        a1 = _make_asset("cancel-a1", file_name="one.jpg")
        a2 = _make_asset("cancel-a2", file_name="two.jpg")
        a3 = _make_asset("cancel-a3", file_name="three.jpg")
        client = FakeClient(search_pages={"IMAGE": [[a1, a2, a3], []], "VIDEO": [[]]})
        monkeypatch.setattr(run_service, "ImmichClient", FakeClientFactory(client))
        monkeypatch.setattr(run_service, "validate_output", lambda path, fmt: True)

        run_id_holder: dict[str, int] = {}

        def cancel_on_first_asset(inp, out, fmt, distance):
            if "cancel-a1" in inp:
                run_service.request_cancel(run_id_holder["id"])
            return TranscodeResult(
                success=True,
                input_path=inp,
                output_path=out,
                input_bytes=1000,
                output_bytes=500,
                input_format="jpg",
            )

        monkeypatch.setattr(run_service, "transcode", cancel_on_first_asset)

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
            "concurrency": 1,
        }

        async with AsyncSessionLocal() as db:
            run = Run(status="queued", config_snapshot=json.dumps(cfg))
            db.add(run)
            await db.commit()
            await db.refresh(run)
            run_id_holder["id"] = run.id

        await run_service.execute_run(run_id_holder["id"])

        async with AsyncSessionLocal() as db:
            run_result = await db.execute(
                select(Run).where(Run.id == run_id_holder["id"])
            )
            refreshed = run_result.scalar_one()
            outcomes_result = await db.execute(
                select(AssetOutcome).where(AssetOutcome.run_id == run_id_holder["id"])
            )
            outcomes = outcomes_result.scalars().all()

        assert refreshed.status == "cancelled"
        assert refreshed.processed_count == 1
        assert {o.asset_id for o in outcomes} == {"cancel-a1"}
