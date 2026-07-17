"""Tests for main.process_asset orchestration with fakes and stubs."""

from dataclasses import dataclass, field
from typing import Any

from app.config import Config
from app.immich_api import Asset
from app.main import process_asset


@dataclass
class FakeImmichClient:
    download_result: tuple[int, str | None] = (100, None)
    upload_result: tuple[str | None, str | None] = ("new-id", None)
    copy_result: tuple[bool, str | None] = (True, None)
    verify_result: tuple[bool, str | None] = (True, None)
    delete_result: tuple[bool, str | None] = (True, None)
    deleted_ids: list[str] = field(default_factory=list)

    def download_original(
        self, asset_id: str, output_path: str
    ) -> tuple[int, str | None]:
        return self.download_result

    def upload_asset(self, **kwargs: Any) -> tuple[str | None, str | None]:
        return self.upload_result

    def copy_asset_data(
        self, from_asset_id: str, to_asset_id: str
    ) -> tuple[bool, str | None]:
        return self.copy_result

    def get_asset(self, asset_id: str) -> tuple[bool, str | None]:
        return self.verify_result

    def delete_assets(self, asset_ids: list[str]) -> tuple[bool, str | None]:
        self.deleted_ids.extend(asset_ids)
        return self.delete_result


def _make_asset(
    asset_id: str = "a1",
    file_name: str = "photo.jpg",
    mime_type: str | None = "image/jpeg",
    asset_type: str = "IMAGE",
) -> Asset:
    return Asset(
        id=asset_id,
        original_file_name=file_name,
        original_path="/uploads/" + file_name,
        original_mime_type=mime_type,
        type=asset_type,
        file_created_at="2023-01-01T00:00:00Z",
        file_modified_at="2023-01-01T00:00:00Z",
    )


def _make_config(**overrides: Any) -> Config:
    defaults = {
        "immich_api_base": "https://example.com/api/",
        "immich_api_key": "key",
        "dry_run": False,
        "concurrency": 1,
        "max_assets": 0,
        "asset_types": ("IMAGE", "VIDEO"),
        "image_distance": 1.0,
        "image_distance_retry": 2.0,
        "video_crf": 36,
        "video_preset": "4",
        "video_max_dimension": 0,
        "video_audio_bitrate": "64k",
        "video_crf_retry": 40,
        "enable_retry": True,
        "accept_retry_output": False,
        "allow_larger": False,
        "workdir": "/tmp/work",
    }
    defaults.update(overrides)
    return Config(**defaults)  # type: ignore[arg-type]


class TestProcessAsset:
    def test_image_already_jxl_by_mime_skipped_no_download(self, monkeypatch, tmp_path):
        asset = _make_asset(mime_type="image/jxl")
        config = _make_config(workdir=str(tmp_path))
        client = FakeImmichClient()

        result = process_asset(asset, client, config)
        assert result["status"] == "skipped"
        assert asset.id not in client.deleted_ids

    def test_image_dry_run_skip(self, monkeypatch, tmp_path):
        asset = _make_asset()
        config = _make_config(dry_run=True, workdir=str(tmp_path))
        client = FakeImmichClient()

        result = process_asset(asset, client, config)
        assert result["status"] == "dry_run_skip"

    def test_video_dry_run_av1_skipped(self, monkeypatch, tmp_path):
        asset = _make_asset(asset_type="VIDEO", file_name="video.mp4")
        config = _make_config(dry_run=True, workdir=str(tmp_path))
        client = FakeImmichClient()

        monkeypatch.setattr("app.main.detect_video_codec", lambda p: "av1")

        result = process_asset(asset, client, config)
        assert result["status"] == "skipped"

    def test_download_fails(self, monkeypatch, tmp_path):
        asset = _make_asset()
        config = _make_config(workdir=str(tmp_path))
        client = FakeImmichClient(download_result=(0, "Network error"))

        result = process_asset(asset, client, config)
        assert result["status"] == "failed_download"

    def test_transcode_failure(self, monkeypatch, tmp_path):
        asset = _make_asset()
        config = _make_config(workdir=str(tmp_path))
        client = FakeImmichClient()

        def fake_transcode(input_path, output_path, distance):
            from app.transcode import TranscodeResult

            return TranscodeResult(
                success=False,
                input_path=input_path,
                output_path=output_path,
                input_bytes=100,
                output_bytes=0,
                input_format="jpg",
                error="magick exploded",
            )

        monkeypatch.setattr("app.main.transcode", fake_transcode)

        result = process_asset(asset, client, config)
        assert result["status"] == "failed_transcode"

    def test_output_larger_allow_larger_still_succeeds(self, monkeypatch, tmp_path):
        asset = _make_asset()
        config = _make_config(allow_larger=True, workdir=str(tmp_path))
        client = FakeImmichClient()

        def fake_transcode(input_path, output_path, distance):
            from app.transcode import TranscodeResult

            return TranscodeResult(
                success=True,
                input_path=input_path,
                output_path=output_path,
                input_bytes=100,
                output_bytes=200,
                input_format="jpg",
            )

        monkeypatch.setattr("app.main.transcode", fake_transcode)
        monkeypatch.setattr("app.main.validate_output", lambda p, f: True)

        result = process_asset(asset, client, config)
        assert result["status"] == "success"
        assert result["savings_pct"] < 0

    def test_output_larger_retry_succeeds(self, monkeypatch, tmp_path):
        asset = _make_asset()
        config = _make_config(enable_retry=True, workdir=str(tmp_path))
        client = FakeImmichClient()

        call_count = 0

        def fake_transcode(input_path, output_path, distance):
            from app.transcode import TranscodeResult

            nonlocal call_count
            call_count += 1
            output_bytes = 50 if distance > 1.0 else 200
            return TranscodeResult(
                success=True,
                input_path=input_path,
                output_path=output_path,
                input_bytes=100,
                output_bytes=output_bytes,
                input_format="jpg",
            )

        monkeypatch.setattr("app.main.transcode", fake_transcode)
        monkeypatch.setattr("app.main.validate_output", lambda p, f: True)

        result = process_asset(asset, client, config)
        assert result["status"] == "success"
        assert call_count == 2
        assert result["savings_pct"] == 50.0

    def test_output_larger_retry_still_larger_skipped(self, monkeypatch, tmp_path):
        asset = _make_asset()
        config = _make_config(enable_retry=True, workdir=str(tmp_path))
        client = FakeImmichClient()

        def fake_transcode(input_path, output_path, distance):
            from app.transcode import TranscodeResult

            return TranscodeResult(
                success=True,
                input_path=input_path,
                output_path=output_path,
                input_bytes=100,
                output_bytes=200,
                input_format="jpg",
            )

        monkeypatch.setattr("app.main.transcode", fake_transcode)
        monkeypatch.setattr("app.main.validate_output", lambda p, f: True)

        result = process_asset(asset, client, config)
        assert result["status"] == "skipped"

    def test_upload_fails_no_copy_attempted(self, monkeypatch, tmp_path):
        asset = _make_asset()
        config = _make_config(workdir=str(tmp_path))
        client = FakeImmichClient(upload_result=(None, "Server busy"))

        def fake_transcode(input_path, output_path, distance):
            from app.transcode import TranscodeResult

            return TranscodeResult(
                success=True,
                input_path=input_path,
                output_path=output_path,
                input_bytes=100,
                output_bytes=50,
                input_format="jpg",
            )

        monkeypatch.setattr("app.main.transcode", fake_transcode)
        monkeypatch.setattr("app.main.validate_output", lambda p, f: True)

        result = process_asset(asset, client, config)
        assert result["status"] == "failed_upload"
        assert asset.id not in client.deleted_ids
        assert "new-id" not in client.deleted_ids

    def test_copy_fails_new_asset_deleted(self, monkeypatch, tmp_path):
        asset = _make_asset()
        config = _make_config(workdir=str(tmp_path))
        client = FakeImmichClient(copy_result=(False, "Conflict"))

        def fake_transcode(input_path, output_path, distance):
            from app.transcode import TranscodeResult

            return TranscodeResult(
                success=True,
                input_path=input_path,
                output_path=output_path,
                input_bytes=100,
                output_bytes=50,
                input_format="jpg",
            )

        monkeypatch.setattr("app.main.transcode", fake_transcode)
        monkeypatch.setattr("app.main.validate_output", lambda p, f: True)

        result = process_asset(asset, client, config)
        assert result["status"] == "failed_copy"
        assert "new-id" in client.deleted_ids

    def test_verify_fails_new_asset_deleted(self, monkeypatch, tmp_path):
        asset = _make_asset()
        config = _make_config(workdir=str(tmp_path))
        client = FakeImmichClient(verify_result=(False, "Not found"))

        def fake_transcode(input_path, output_path, distance):
            from app.transcode import TranscodeResult

            return TranscodeResult(
                success=True,
                input_path=input_path,
                output_path=output_path,
                input_bytes=100,
                output_bytes=50,
                input_format="jpg",
            )

        monkeypatch.setattr("app.main.transcode", fake_transcode)
        monkeypatch.setattr("app.main.validate_output", lambda p, f: True)

        result = process_asset(asset, client, config)
        assert result["status"] == "failed_verification"
        assert "new-id" in client.deleted_ids

    def test_delete_original_fails_partial_success(self, monkeypatch, tmp_path):
        asset = _make_asset()
        config = _make_config(workdir=str(tmp_path))
        client = FakeImmichClient(delete_result=(False, "Locked"))

        def fake_transcode(input_path, output_path, distance):
            from app.transcode import TranscodeResult

            return TranscodeResult(
                success=True,
                input_path=input_path,
                output_path=output_path,
                input_bytes=100,
                output_bytes=50,
                input_format="jpg",
            )

        monkeypatch.setattr("app.main.transcode", fake_transcode)
        monkeypatch.setattr("app.main.validate_output", lambda p, f: True)

        result = process_asset(asset, client, config)
        assert result["status"] == "partial_success"

    def test_full_happy_path(self, monkeypatch, tmp_path):
        asset = _make_asset()
        config = _make_config(workdir=str(tmp_path))
        client = FakeImmichClient()

        def fake_transcode(input_path, output_path, distance):
            from app.transcode import TranscodeResult

            return TranscodeResult(
                success=True,
                input_path=input_path,
                output_path=output_path,
                input_bytes=100,
                output_bytes=60,
                input_format="jpg",
            )

        monkeypatch.setattr("app.main.transcode", fake_transcode)
        monkeypatch.setattr("app.main.validate_output", lambda p, f: True)

        result = process_asset(asset, client, config)
        assert result["status"] == "success"
        assert result["input_bytes"] == 100
        assert result["output_bytes"] == 60
        assert result["savings_pct"] == 40.0

    def test_video_happy_path(self, monkeypatch, tmp_path):
        asset = _make_asset(asset_type="VIDEO", file_name="video.mp4")
        config = _make_config(workdir=str(tmp_path))
        client = FakeImmichClient()

        def fake_transcode_video(
            input_path, output_path, crf, preset, max_dimension, audio_bitrate
        ):
            from app.transcode import TranscodeResult

            return TranscodeResult(
                success=True,
                input_path=input_path,
                output_path=output_path,
                input_bytes=1000,
                output_bytes=50,
                input_format="h264",
            )

        monkeypatch.setattr("app.main.transcode_video", fake_transcode_video)
        monkeypatch.setattr("app.main.validate_video_output", lambda p: True)

        result = process_asset(asset, client, config)
        assert result["status"] == "success"
        assert result["savings_pct"] == 50.0

    def test_video_dry_run_non_av1(self, monkeypatch, tmp_path):
        asset = _make_asset(asset_type="VIDEO", file_name="video.mp4")
        config = _make_config(dry_run=True, workdir=str(tmp_path))
        client = FakeImmichClient()

        monkeypatch.setattr("app.main.detect_video_codec", lambda p: "h264")

        result = process_asset(asset, client, config)
        assert result["status"] == "dry_run_skip"

    def test_validation_failure(self, monkeypatch, tmp_path):
        asset = _make_asset()
        config = _make_config(workdir=str(tmp_path))
        client = FakeImmichClient()

        def fake_transcode(input_path, output_path, distance):
            from app.transcode import TranscodeResult

            return TranscodeResult(
                success=True,
                input_path=input_path,
                output_path=output_path,
                input_bytes=100,
                output_bytes=50,
                input_format="jpg",
            )

        monkeypatch.setattr("app.main.transcode", fake_transcode)
        monkeypatch.setattr("app.main.validate_output", lambda p, f: False)

        result = process_asset(asset, client, config)
        assert result["status"] == "failed_transcode"

    def test_retry_validation_failure(self, monkeypatch, tmp_path):
        asset = _make_asset()
        config = _make_config(enable_retry=True, workdir=str(tmp_path))
        client = FakeImmichClient()

        def fake_transcode(input_path, output_path, distance):
            from app.transcode import TranscodeResult

            return TranscodeResult(
                success=True,
                input_path=input_path,
                output_path=output_path,
                input_bytes=100,
                output_bytes=200,
                input_format="jpg",
            )

        validate_calls = []

        def fake_validate(path, fmt):
            validate_calls.append(1)
            # Fail on retry (second call)
            return len(validate_calls) == 1

        monkeypatch.setattr("app.main.transcode", fake_transcode)
        monkeypatch.setattr("app.main.validate_output", fake_validate)

        result = process_asset(asset, client, config)
        assert result["status"] == "skipped"

    def test_retry_still_larger_with_accept(self, monkeypatch, tmp_path):
        asset = _make_asset()
        config = _make_config(
            enable_retry=True, accept_retry_output=True, workdir=str(tmp_path)
        )
        client = FakeImmichClient()

        def fake_transcode(input_path, output_path, distance):
            from app.transcode import TranscodeResult

            return TranscodeResult(
                success=True,
                input_path=input_path,
                output_path=output_path,
                input_bytes=100,
                output_bytes=200,
                input_format="jpg",
            )

        monkeypatch.setattr("app.main.transcode", fake_transcode)
        monkeypatch.setattr("app.main.validate_output", lambda p, f: True)

        result = process_asset(asset, client, config)
        assert result["status"] == "success"

    def test_empty_download(self, monkeypatch, tmp_path):
        asset = _make_asset()
        config = _make_config(workdir=str(tmp_path))
        client = FakeImmichClient(download_result=(0, None))

        result = process_asset(asset, client, config)
        assert result["status"] == "failed_download"

    def test_already_target_format_skip(self, monkeypatch, tmp_path):
        asset = _make_asset()
        config = _make_config(workdir=str(tmp_path))
        client = FakeImmichClient()

        def fake_transcode(input_path, output_path, distance):
            from app.transcode import TranscodeResult

            return TranscodeResult(
                success=False,
                input_path=input_path,
                output_path=output_path,
                input_bytes=100,
                output_bytes=100,
                input_format="jxl",
                error="Already JXL",
            )

        monkeypatch.setattr("app.main.transcode", fake_transcode)

        result = process_asset(asset, client, config)
        assert result["status"] == "skipped"
