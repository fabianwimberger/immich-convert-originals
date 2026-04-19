"""Seed a test library into a real Immich instance."""

import subprocess
import uuid
from pathlib import Path
from typing import Any

import requests

from app.immich_api import ImmichClient

DEVICE_ID = "integration-test-device"
SEED_MARKER_ALBUM = "__immich-convert-seed-marker__"
IMAGE_NAMES = (
    "sample.jpg",
    "progressive.jpg",
    "sample.png",
    "sample.webp",
    "sample.heic",
    "already.jxl",
    "tiny.png",
)
VIDEO_NAMES = (
    "h264.mp4",
    "h264_portrait.mp4",
    "hevc.mov",
    "av1.mp4",
)


def _generate_media(fixtures_dir: Path, tmp_dir: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}

    # Copy shipped fixtures used for already-target and retry-path coverage.
    for name in (
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

    # Generate a photo-sized sample.jpg with mandelbrot content. The tiny
    # shipped fixture (~400 B) is too small for JXL to compress below input
    # size, so the converter would skip it and the trash/upload path wouldn't
    # be exercised.
    sample_jpg = tmp_dir / "sample.jpg"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "mandelbrot=size=1024x768:rate=1",
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(sample_jpg),
        ],
        check=True,
        capture_output=True,
    )
    files["sample.jpg"] = sample_jpg

    # Inject EXIF (GPS + DateTimeOriginal + Artist) into sample.jpg so we can
    # verify the transcode pipeline preserves metadata end-to-end.
    subprocess.run(
        [
            "exiftool",
            "-overwrite_original",
            "-GPSLatitude=48.2082",
            "-GPSLatitudeRef=N",
            "-GPSLongitude=16.3738",
            "-GPSLongitudeRef=E",
            "-DateTimeOriginal=2015:01:01 12:00:00",
            "-Artist=immich-convert-originals integration test",
            str(files["sample.jpg"]),
        ],
        check=True,
        capture_output=True,
    )

    # Generate HEIC from sample.jpg (ImageMagick 7 uses 'magick', v6 uses 'convert')
    heic_path = tmp_dir / "sample.heic"
    magick_cmd = (
        "magick"
        if subprocess.run(["which", "magick"], capture_output=True).returncode == 0
        else "convert"
    )
    subprocess.run(
        [magick_cmd, str(files["sample.jpg"]), str(heic_path)],
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


def _list_albums(api_base: str, api_key: str) -> list[dict[str, Any]]:
    resp = requests.get(
        f"{api_base}albums",
        headers={"x-api-key": api_key},
        timeout=30,
    )
    resp.raise_for_status()
    return list(resp.json())


def _existing_library(client: ImmichClient) -> dict[str, Any] | None:
    """If a previous run already seeded this Immich, rebuild the library dict
    from the marker album without re-uploading."""
    albums = _list_albums(client.api_base, client.api_key)
    marker = next((a for a in albums if a["albumName"] == SEED_MARKER_ALBUM), None)
    if marker is None:
        return None

    by_name = {a["albumName"]: a["id"] for a in albums}
    vacation_id = by_name.get("Vacation 2023")
    screenshots_id = by_name.get("Screenshots")
    if not (vacation_id and screenshots_id):
        return None

    # Pull every asset and index by original filename.
    image_ids: dict[str, str] = {}
    video_ids: dict[str, str] = {}
    for asset_type, bucket in (("IMAGE", image_ids), ("VIDEO", video_ids)):
        page = 1
        while True:
            assets = client.search_assets(
                page=page, size=500, asset_type=asset_type, with_archived=True
            )
            if not assets:
                break
            for a in assets:
                bucket.setdefault(a.original_file_name, a.id)
            page += 1

    expected_images = set(IMAGE_NAMES)
    expected_videos = set(VIDEO_NAMES)
    if not expected_images.issubset(image_ids) or not expected_videos.issubset(
        video_ids
    ):
        return None

    return {
        "assets": {**image_ids, **video_ids},
        "images": {k: image_ids[k] for k in IMAGE_NAMES},
        "videos": {k: video_ids[k] for k in VIDEO_NAMES},
        "albums": {"vacation": vacation_id, "screenshots": screenshots_id},
    }


def seed_library(client: ImmichClient, tmp_path_factory: Any) -> dict[str, Any]:
    existing = _existing_library(client)
    if existing is not None:
        return existing

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

    # Drop a marker album so future sessions can short-circuit the seed.
    _create_album(
        client.api_base,
        client.api_key,
        SEED_MARKER_ALBUM,
        [image_ids["sample.jpg"]],
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
