"""End-to-end integration tests against a real Immich instance."""

import hashlib
import json
import os
import subprocess
from typing import Any

import pytest
import requests

from app.config import Config
from app.immich_api import ImmichClient

pytestmark = pytest.mark.integration


def _count_assets(client: ImmichClient) -> int:
    total = 0
    for atype in ("IMAGE", "VIDEO"):
        page = 1
        while True:
            assets = client.search_assets(
                page=page, size=500, asset_type=atype, with_archived=True
            )
            if not assets:
                break
            total += len(assets)
            page += 1
    return total


def _get_asset_detail(client: ImmichClient, asset_id: str) -> dict[str, Any] | None:
    url = f"{client.api_base}assets/{asset_id}"
    try:
        resp = requests.get(url, headers=client._default_headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def _download_original(client: ImmichClient, asset_id: str, path: str) -> int:
    size, error = client.download_original(asset_id, path)
    if error:
        raise RuntimeError(f"Download failed: {error}")
    return size


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_converter(
    api_base: str,
    api_key: str,
    **kwargs: Any,
) -> int:
    """Run the converter with config overrides."""
    workdir = "/tmp/immich-convert-test"
    os.makedirs(f"{workdir}/in", exist_ok=True)
    os.makedirs(f"{workdir}/out", exist_ok=True)

    defaults: dict[str, Any] = {
        "dry_run": True,
        "concurrency": 1,
        "max_assets": 0,
        "asset_types": ("IMAGE", "VIDEO"),
        "include_archived": False,
        "include_deleted": False,
        "filter_date_after": None,
        "filter_date_before": None,
        "filter_album_id": None,
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
    }
    defaults.update(kwargs)

    config = Config(
        immich_api_base=api_base,
        immich_api_key=api_key,
        workdir=workdir,
        **defaults,
    )
    # Patch main to use our config directly instead of argparse
    import app.main as main_mod

    orig_from_args = main_mod.Config.from_args_and_env
    main_mod.Config.from_args_and_env = lambda args: config  # type: ignore[method-assign]
    orig_parse_args = main_mod.parse_args
    main_mod.parse_args = lambda argv=None: type(  # type: ignore[assignment, return-value, method-assign]
        "Args",
        (),
        {
            "interactive": False,
            "yes": False,
            "log_level": None,
            "log_format": None,
            "stats_json": None,
        },
    )
    try:
        return main_mod.main([])
    finally:
        main_mod.Config.from_args_and_env = orig_from_args  # type: ignore[method-assign]
        main_mod.parse_args = orig_parse_args  # type: ignore[method-assign]


class TestEndToEnd:
    def test_full_flow(self, admin_client: ImmichClient, seeded_library: Any, tmp_path: Any):
        lib = seeded_library

        # 1. Dry run: count should not change
        before_count = _count_assets(admin_client)
        code = _run_converter(
            admin_client.api_base,
            admin_client.api_key,
            dry_run=True,
            asset_types=("IMAGE", "VIDEO"),
            max_assets=0,
        )
        assert code == 0
        assert _count_assets(admin_client) == before_count

        # 2. Happy path: convert one JPEG (sample.jpg)
        sample_id = lib["images"]["sample.jpg"]
        code = _run_converter(
            admin_client.api_base,
            admin_client.api_key,
            dry_run=False,
            asset_types=("IMAGE",),
            max_assets=1,
            image_distance=1.0,
        )
        assert code == 0

        # Original should be in trash
        detail = _get_asset_detail(admin_client, sample_id)
        assert detail is None or detail.get("isTrashed") is True

        # Find new JXL asset by searching all images
        all_images = admin_client.search_assets(
            page=1, size=50, asset_type="IMAGE"
        )
        jxl_assets = [a for a in all_images if a.original_file_name.endswith(".jxl")]
        assert len(jxl_assets) >= 1, "New JXL asset not found"
        new_jxl = jxl_assets[0]

        # Download and verify format
        jxl_path = str(tmp_path / "downloaded.jxl")
        _download_original(admin_client, new_jxl.id, jxl_path)
        result = subprocess.run(
            ["magick", "identify", "-verbose", jxl_path],
            capture_output=True,
            text=True,
        )
        assert "JPEG-XL" in result.stdout or "JXL" in result.stdout

        # Verify favorite preserved
        detail = _get_asset_detail(admin_client, new_jxl.id)
        assert detail is not None
        assert detail.get("isFavorite") is True

        # Verify album membership by querying the album
        album_url = f"{admin_client.api_base}albums/{lib['albums']['vacation']}"
        album_resp = requests.get(
            album_url, headers=admin_client._default_headers, timeout=10
        )
        assert album_resp.status_code == 200
        album_data = album_resp.json()
        album_asset_ids = {a["id"] for a in album_data.get("assets", [])}
        assert new_jxl.id in album_asset_ids

        # 3. Happy path: convert one video (h264.mp4)
        code = _run_converter(
            admin_client.api_base,
            admin_client.api_key,
            dry_run=False,
            asset_types=("VIDEO",),
            max_assets=1,
            video_crf=36,
        )
        assert code == 0

        all_videos = admin_client.search_assets(
            page=1, size=50, asset_type="VIDEO"
        )
        new_mp4s = [a for a in all_videos if a.original_file_name.endswith(".mp4")]
        # Should have the original av1.mp4 plus at least one new converted mp4
        assert len(new_mp4s) >= 1

        # Find the newly converted one (not the original av1)
        converted = None
        for a in new_mp4s:
            if a.id != lib["videos"]["av1.mp4"]:
                converted = a
                break
        assert converted is not None, "New AV1 video not found"

        mp4_path = str(tmp_path / "downloaded.mp4")
        _download_original(admin_client, converted.id, mp4_path)

        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,duration",
                "-of",
                "json",
                mp4_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        info = json.loads(probe.stdout)
        streams = info.get("streams", [])
        assert len(streams) >= 1
        assert streams[0]["codec_name"] == "av1"
        duration = float(streams[0].get("duration", 0))
        assert abs(duration - 2.0) < 0.5

        # Verify audio stream present
        audio_probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "json",
                mp4_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        audio_info = json.loads(audio_probe.stdout)
        assert len(audio_info.get("streams", [])) >= 1

        # 4. Already-target skip: verify already.jxl and av1.mp4 were
        # untouched by earlier steps and would be skipped in a full run.
        jxl_id = lib["images"]["already.jxl"]
        av1_id = lib["videos"]["av1.mp4"]
        jxl_detail = _get_asset_detail(admin_client, jxl_id)
        assert jxl_detail is not None
        assert not jxl_detail.get("isTrashed")
        av1_detail = _get_asset_detail(admin_client, av1_id)
        assert av1_detail is not None
        assert not av1_detail.get("isTrashed")

        # 5. Album filter
        vacation_id = lib["albums"]["vacation"]
        code = _run_converter(
            admin_client.api_base,
            admin_client.api_key,
            dry_run=False,
            asset_types=("IMAGE", "VIDEO"),
            filter_album_id=vacation_id,
            max_assets=0,
        )
        assert code == 0
        # Screenshots album asset should still be untouched
        screenshot_asset_id = lib["images"]["sample.webp"]
        detail = _get_asset_detail(admin_client, screenshot_asset_id)
        assert detail is not None and not detail.get("isTrashed")

        # 6. Date filter
        code = _run_converter(
            admin_client.api_base,
            admin_client.api_key,
            dry_run=False,
            asset_types=("IMAGE", "VIDEO"),
            filter_date_after="2020-01-01T00:00:00Z",
            filter_date_before="2021-12-31T23:59:59Z",
            max_assets=0,
        )
        assert code == 0

        # 7. Retry path: target tiny.png via date filter
        code = _run_converter(
            admin_client.api_base,
            admin_client.api_key,
            dry_run=False,
            asset_types=("IMAGE",),
            filter_date_after="2024-01-01T00:00:00Z",
            max_assets=1,
            image_distance=0.1,
            enable_retry=True,
            image_distance_retry=3.0,
        )
        assert code == 0

        # 8. Concurrency
        # At this point the only remaining unconverted IMAGE assets are
        # sample.webp (retry-skipped earlier) and sample.heic (archived).
        # sample.webp is tiny and may still be skipped; sample.heic should convert.
        heic_id = lib["images"]["sample.heic"]

        code = _run_converter(
            admin_client.api_base,
            admin_client.api_key,
            dry_run=False,
            asset_types=("IMAGE",),
            max_assets=0,
            concurrency=4,
            include_archived=True,
        )
        assert code == 0

        # sample.heic should be trashed (it converts successfully)
        detail = _get_asset_detail(admin_client, heic_id)
        if detail is not None:
            assert detail.get("isTrashed") is True

        # 9. Idempotency: run again on IMAGE scope
        code = _run_converter(
            admin_client.api_base,
            admin_client.api_key,
            dry_run=False,
            asset_types=("IMAGE",),
            max_assets=10,
        )
        assert code == 0


@pytest.mark.skip(reason="toxiproxy sidecar not yet wired")
def test_upload_failure_rollback(admin_client: ImmichClient, seeded_library: Any):
    pass
