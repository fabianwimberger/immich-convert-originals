"""Live and motion photos against a real Immich instance: the converted
still has to keep its video, and the video has to survive the original
being purged."""

import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
import requests

from .test_end_to_end import _get_asset_detail, _wait_for_run

pytestmark = pytest.mark.integration

CREATED_AT = "2024-05-01T12:00:00.000Z"


def _run(*args: str) -> None:
    subprocess.run(args, check=True, capture_output=True)


def _make_still_and_video(tmp_path: Path) -> tuple[Path, Path]:
    """A photo-sized JPEG and a short clip, both unique per call so Immich's
    checksum deduplication never returns an asset from an earlier test."""
    marker = uuid.uuid4().hex
    still = tmp_path / f"{marker}.jpg"
    video = tmp_path / f"{marker}.mp4"
    _run(
        "ffmpeg", "-y", "-f", "lavfi", "-i", "mandelbrot=size=1024x768:rate=1",
        "-frames:v", "1", "-q:v", "3", str(still),
    )  # fmt: skip
    _run(
        "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x480:rate=30",
        "-t", "2", "-c:v", "libx264", "-b:v", "4M", "-pix_fmt", "yuv420p",
        "-metadata", f"comment={marker}",
        str(video),
    )  # fmt: skip
    _run("exiftool", "-overwrite_original", f"-XMP-dc:Description={marker}", str(still))
    return still, video


def _embed_video(still: Path, video: Path, layout: str) -> None:
    """Turn the still into a motion photo: video appended after the image,
    announced by the XMP tags of the given layout."""
    size = video.stat().st_size
    if layout == "microvideo":
        tags = [
            "-XMP-GCamera:MicroVideo=1",
            "-XMP-GCamera:MicroVideoVersion=1",
            f"-XMP-GCamera:MicroVideoOffset={size}",
            "-XMP-GCamera:MicroVideoPresentationTimestampUs=0",
        ]
    else:
        tags = [
            "-XMP-GCamera:MotionPhoto=1",
            "-XMP-GCamera:MotionPhotoVersion=1",
            "-XMP-GCamera:MotionPhotoPresentationTimestampUs=0",
            "-XMP-GContainer:ContainerDirectory=["
            "{Item={Mime=image/jpeg,Semantic=Primary,Length=0,Padding=0}},"
            f"{{Item={{Mime=video/mp4,Semantic=MotionPhoto,Length={size},Padding=0}}}}]",
        ]
    _run("exiftool", "-overwrite_original", *tags, str(still))
    with still.open("ab") as f:
        f.write(video.read_bytes())


def _api(admin_client, method: str, path: str, **kwargs: Any) -> requests.Response:
    return requests.request(
        method,
        f"{admin_client.api_base}{path}",
        headers=admin_client._default_headers,
        timeout=30,
        **kwargs,
    )


def _wait_for(admin_client, asset_id: str, ready, timeout: float = 90) -> dict:
    deadline = time.monotonic() + timeout
    detail = None
    while time.monotonic() < deadline:
        detail = _get_asset_detail(admin_client, asset_id)
        if detail and ready(detail):
            return detail
        time.sleep(1)
    pytest.fail(f"Asset {asset_id} never reached the expected state: {detail}")


def _upload(admin_client, path: Path, name: str) -> str:
    asset_id, error = admin_client.upload_asset(
        file_path=str(path),
        file_created_at=CREATED_AT,
        file_modified_at=CREATED_AT,
        filename=name,
    )
    assert asset_id, error
    return asset_id


def _seed_live_photo(admin_client, tmp_path: Path, layout: str) -> tuple[str, str]:
    """Upload a live photo and return (still id, video id) once Immich has
    linked the two."""
    still, video = _make_still_and_video(tmp_path)
    if layout == "separate":
        # What an iPhone upload ends up as: two assets, the still pointing
        # at a hidden video.
        video_id = _upload(admin_client, video, "live.mov")
        still_id = _upload(admin_client, still, "live.jpg")
        resp = _api(
            admin_client,
            "PUT",
            f"assets/{still_id}",
            json={"livePhotoVideoId": video_id},
        )
        assert resp.status_code == 200, resp.text
    else:
        _embed_video(still, video, layout)
        still_id = _upload(admin_client, still, "motion.jpg")
    detail = _wait_for(admin_client, still_id, lambda d: d.get("livePhotoVideoId"))
    return still_id, detail["livePhotoVideoId"]


@pytest.mark.parametrize(
    ("layout", "target"),
    [
        ("microvideo", "jxl"),
        ("motionphoto", "jxl"),
        ("separate", "jxl"),
        ("motionphoto", "heic"),
        ("microvideo", "avif"),
    ],
)
async def test_converted_live_photo_keeps_its_video(
    gui_client, admin_client, tmp_path, layout, target
):
    still_id, video_id = _seed_live_photo(admin_client, tmp_path, layout)
    video_bytes = _api(admin_client, "GET", f"assets/{video_id}/original").content
    assert video_bytes

    create_resp = await gui_client.post(
        "/api/runs",
        json={
            "asset_ids": [still_id],
            "dry_run": False,
            "image_target_format": target,
        },
    )
    assert create_resp.status_code == 200
    run = await _wait_for_run(gui_client, create_resp.json()["id"])
    outcomes = (await gui_client.get(f"/api/runs/{run['id']}/assets")).json()["items"]
    assert [o["status"] for o in outcomes] == ["success"], outcomes
    new_id = outcomes[0]["new_asset_id"]

    # Immich's own metadata extraction of the converted file runs after the
    # upload and is what used to swap in a bogus video.
    _wait_for(
        admin_client, new_id, lambda d: (d.get("exifInfo") or {}).get("exifImageWidth")
    )

    # Purge the original for good, as an emptied trash would.
    resp = _api(
        admin_client, "DELETE", "assets", json={"ids": [still_id], "force": True}
    )
    assert resp.status_code == 204
    deadline = time.monotonic() + 60
    while _get_asset_detail(admin_client, still_id) and time.monotonic() < deadline:
        time.sleep(1)
    assert _get_asset_detail(admin_client, still_id) is None
    time.sleep(5)

    converted = _get_asset_detail(admin_client, new_id)
    assert converted is not None
    assert converted["originalFileName"].endswith(f".{target}")
    assert converted["livePhotoVideoId"] == video_id
    video = _get_asset_detail(admin_client, video_id)
    assert video is not None
    assert video["visibility"] == "hidden"
    assert not video["isTrashed"]
    assert (
        _api(admin_client, "GET", f"assets/{video_id}/original").content == video_bytes
    )


@pytest.mark.parametrize("layout", ["motionphoto", "separate"])
async def test_live_photo_video_is_converted_when_enabled(
    gui_client, admin_client, tmp_path, layout
):
    still_id, video_id = _seed_live_photo(admin_client, tmp_path, layout)
    old_size = len(_api(admin_client, "GET", f"assets/{video_id}/original").content)

    create_resp = await gui_client.post(
        "/api/runs",
        json={
            "asset_ids": [still_id],
            "dry_run": False,
            "convert_live_photo_videos": True,
        },
    )
    assert create_resp.status_code == 200
    run = await _wait_for_run(gui_client, create_resp.json()["id"], timeout=300)
    outcomes = (await gui_client.get(f"/api/runs/{run['id']}/assets")).json()["items"]
    assert [o["status"] for o in outcomes] == ["success"], outcomes
    new_id = outcomes[0]["new_asset_id"]

    _wait_for(
        admin_client, new_id, lambda d: (d.get("exifInfo") or {}).get("exifImageWidth")
    )
    converted = _get_asset_detail(admin_client, new_id)
    new_video_id = converted["livePhotoVideoId"]
    assert new_video_id and new_video_id != video_id

    # Until the original is purged, both videos exist and it can be restored.
    assert _get_asset_detail(admin_client, video_id) is not None
    resp = _api(
        admin_client, "DELETE", "assets", json={"ids": [still_id], "force": True}
    )
    assert resp.status_code == 204
    deadline = time.monotonic() + 60
    while _get_asset_detail(admin_client, video_id) and time.monotonic() < deadline:
        time.sleep(1)
    assert _get_asset_detail(admin_client, video_id) is None
    time.sleep(5)

    assert _get_asset_detail(admin_client, new_id)["livePhotoVideoId"] == new_video_id
    new_video = _get_asset_detail(admin_client, new_video_id)
    assert new_video["visibility"] == "hidden"
    assert not new_video["isTrashed"]
    new_bytes = _api(admin_client, "GET", f"assets/{new_video_id}/original").content
    assert 0 < len(new_bytes) < old_size
    clip = tmp_path / "converted.mp4"
    clip.write_bytes(new_bytes)
    codec = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=codec_name", "-of", "csv=p=0", str(clip)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    assert codec.stdout.strip() == "av1"


async def test_live_photo_video_is_not_offered_for_conversion(
    gui_client, admin_client, tmp_path
):
    _, video_id = _seed_live_photo(admin_client, tmp_path, "microvideo")

    resp = await gui_client.get(
        "/api/assets",
        params={"asset_type": "VIDEO", "include_archived": True, "size": 500},
    )
    assert resp.status_code == 200
    assert video_id not in [item["id"] for item in resp.json()["items"]]

    create_resp = await gui_client.post(
        "/api/runs", json={"asset_ids": [video_id], "dry_run": False}
    )
    assert create_resp.status_code == 200
    run = await _wait_for_run(gui_client, create_resp.json()["id"])
    assert run["success_count"] == 0
    assert _get_asset_detail(admin_client, video_id) is not None


def test_upload_of_a_trashed_duplicate_restores_it(admin_client, tmp_path):
    """What a retry after a rolled-back attempt runs into: the same bytes
    are already in Immich, in the trash."""
    still, _ = _make_still_and_video(tmp_path)
    first = _upload(admin_client, still, "dup.jpg")
    assert admin_client.delete_assets([first]) == (True, None)
    assert _get_asset_detail(admin_client, first)["isTrashed"]

    again = _upload(admin_client, still, "dup.jpg")

    assert again == first
    assert not _get_asset_detail(admin_client, first)["isTrashed"]


def test_video_with_two_streams_encodes_the_first(tmp_path):
    """A Pixel motion photo clip carries a second, larger video stream that
    ffmpeg would pick by default and the encoder rejects."""
    from app.services.transcode import transcode_video

    clip = tmp_path / "two-streams.mp4"
    _run(
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30",
        "-f", "lavfi", "-i", "testsrc2=size=640x480:rate=30",
        "-map", "0:v", "-map", "1:v", "-t", "1", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", str(clip),
    )  # fmt: skip
    out = tmp_path / "out.mp4"

    result = transcode_video(str(clip), str(out), 36, "8", 0, "64k")

    assert result.success, result.error
    size = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
         "stream=width,height", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    assert size.stdout.split() == ["320,240"]
