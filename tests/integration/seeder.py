"""Seed a test library into a real Immich instance."""

import subprocess
import uuid
from pathlib import Path
from typing import Any

import requests

from app.immich_api import ImmichClient

DEVICE_ID = "integration-test-device"


def _generate_media(fixtures_dir: Path, tmp_dir: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}

    # Copy shipped fixtures
    for name in (
        "sample.jpg",
        "progressive.jpg",
        "sample.png",
        "sample.webp",
        "already.jxl",
        "tiny.png",
    ):
        src = fixtures_dir / name
        dst = tmp_dir / name
        dst.write_bytes(src.read_bytes())
        files[name] = dst

    # Generate HEIC from sample.jpg
    heic_path = tmp_dir / "sample.heic"
    subprocess.run(
        ["magick", str(files["sample.jpg"]), str(heic_path)],
        check=True,
        capture_output=True,
    )
    files["sample.heic"] = heic_path

    # Generate videos
    h264_path = tmp_dir / "h264.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=2:size=320x240:rate=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=2",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(h264_path),
        ],
        check=True,
        capture_output=True,
    )
    files["h264.mp4"] = h264_path

    # h264_portrait.mp4
    portrait_path = tmp_dir / "h264_portrait.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=2:size=240x320:rate=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=2",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(portrait_path),
        ],
        check=True,
        capture_output=True,
    )
    files["h264_portrait.mp4"] = portrait_path

    # hevc.mov
    hevc_path = tmp_dir / "hevc.mov"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=2:size=320x240:rate=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=2",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx265",
            "-c:a",
            "aac",
            str(hevc_path),
        ],
        check=True,
        capture_output=True,
    )
    files["hevc.mov"] = hevc_path

    # av1.mp4
    av1_path = tmp_dir / "av1.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=2:size=320x240:rate=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=2",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libsvtav1",
            "-c:a",
            "aac",
            str(av1_path),
        ],
        check=True,
        capture_output=True,
    )
    files["av1.mp4"] = av1_path

    return files


def _upload_asset(
    client: ImmichClient, path: Path, filename: str, created_at: str
) -> str:
    device_asset_id = f"{filename}-{uuid.uuid4()}"
    asset_id, error = client.upload_asset(
        file_path=str(path),
        device_asset_id=device_asset_id,
        device_id=DEVICE_ID,
        file_created_at=created_at,
        file_modified_at=created_at,
        filename=filename,
    )
    if error or not asset_id:
        raise RuntimeError(f"Failed to upload {filename}: {error}")
    return asset_id


def _update_assets(
    api_base: str, api_key: str, asset_ids: list[str], **kwargs: Any
) -> None:
    """Bulk-update asset metadata (favorite, archive, etc.)."""
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    body: dict[str, Any] = {"ids": asset_ids}
    body.update(kwargs)
    resp = requests.put(
        f"{api_base}assets",
        json=body,
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()


def _create_album(api_base: str, api_key: str, name: str, asset_ids: list[str]) -> str:
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    resp = requests.post(
        f"{api_base}albums",
        json={"albumName": name, "assetIds": asset_ids},
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def seed_library(client: ImmichClient, tmp_path_factory: Any) -> dict[str, Any]:
    fixtures_dir = Path(__file__).parent / "fixtures"
    tmp_dir = tmp_path_factory.mktemp("fixtures")

    files = _generate_media(fixtures_dir, tmp_dir)

    # Upload images with varied dates
    image_dates = {
        "sample.jpg": "2015-01-01T00:00:00Z",
        "progressive.jpg": "2018-06-15T00:00:00Z",
        "sample.png": "2020-03-20T00:00:00Z",
        "sample.webp": "2021-09-10T00:00:00Z",
        "sample.heic": "2022-12-01T00:00:00Z",
        "already.jxl": "2023-01-01T00:00:00Z",
        "tiny.png": "2024-04-19T00:00:00Z",
    }
    image_ids: dict[str, str] = {}
    for name, date in image_dates.items():
        image_ids[name] = _upload_asset(client, files[name], name, date)

    # Upload videos
    video_dates = {
        "h264.mp4": "2019-07-04T00:00:00Z",
        "h264_portrait.mp4": "2020-02-14T00:00:00Z",
        "hevc.mov": "2021-08-01T00:00:00Z",
        "av1.mp4": "2022-11-11T00:00:00Z",
    }
    video_ids: dict[str, str] = {}
    for name, date in video_dates.items():
        video_ids[name] = _upload_asset(client, files[name], name, date)

    all_asset_ids = {**image_ids, **video_ids}

    # Create albums
    vacation_album_id = _create_album(
        client.api_base,
        client.api_key,
        "Vacation 2023",
        [
            image_ids["sample.jpg"],
            image_ids["progressive.jpg"],
            image_ids["sample.png"],
            video_ids["h264.mp4"],
        ],
    )
    screenshots_album_id = _create_album(
        client.api_base,
        client.api_key,
        "Screenshots",
        [image_ids["sample.webp"]],
    )

    # Mark favorite and archive
    _update_assets(
        client.api_base, client.api_key, [image_ids["sample.jpg"]], isFavorite=True
    )
    _update_assets(
        client.api_base, client.api_key, [image_ids["sample.heic"]], isArchived=True
    )

    return {
        "assets": all_asset_ids,
        "images": image_ids,
        "videos": video_ids,
        "albums": {
            "vacation": vacation_album_id,
            "screenshots": screenshots_album_id,
        },
    }
