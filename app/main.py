#!/usr/bin/env python3
"""Main orchestration for batch-transcoding Immich library assets."""

import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import Config
from immich_api import Asset, ImmichClient
from transcode import (
    detect_video_codec,
    transcode,
    transcode_video,
    validate_output,
    validate_video_output,
)

logger = logging.getLogger(__name__)


def _get_target_format(asset: Asset) -> str:
    return "mp4" if asset.type == "VIDEO" else "jxl"


def _should_skip_by_mime_type(asset: Asset) -> bool:
    """Check if asset should be skipped based on MIME type from Immich metadata.

    Images: Skip if already JXL (image/jxl)
    Videos: Cannot reliably detect AV1 by MIME type (AV1 in MP4 = video/mp4 same as H.264)
          Still need ffprobe after download for codec detection
    """
    if asset.type != "IMAGE":
        return False

    # Skip images already in JXL format
    mime_type = asset.original_mime_type.lower() if asset.original_mime_type else None
    if mime_type == "image/jxl":
        return True

    # Fallback: check extension if MIME type not available
    ext = os.path.splitext(asset.original_file_name)[1].lower()
    return ext == ".jxl"


def process_asset(asset: Asset, client: ImmichClient, config: Config) -> dict:
    input_path = ""
    output_path = ""
    result_info = {
        "status": "unknown",
        "input_bytes": 0,
        "output_bytes": 0,
        "savings_pct": 0.0,
    }

    is_video = asset.type == "VIDEO"
    target_format = _get_target_format(asset)

    # Pre-filter: Skip images already in JXL format (by MIME type from API)
    if not is_video and _should_skip_by_mime_type(asset):
        logger.info("%s: Skipped (already JXL)", asset.original_file_name)
        result_info["status"] = "skipped"
        return result_info

    try:
        input_path = os.path.join(config.input_dir(), f"{asset.id}.bin")
        output_path = os.path.join(config.output_dir(), f"{asset.id}.{target_format}")

        # Images can skip download in dry_run (JXL already filtered by MIME type above).
        # Videos must be downloaded so ffprobe can detect the codec (AV1 vs H.264
        # both have MIME type video/mp4).
        if config.dry_run and not is_video:
            logger.info(
                "%s: [would transcode to %s] [DRY RUN]",
                asset.original_file_name,
                target_format,
            )
            result_info["status"] = "dry_run_skip"
            return result_info

        input_bytes, error = client.download_original(asset.id, input_path)
        if error:
            logger.error("%s: %s", asset.original_file_name, error)
            result_info["status"] = "failed_download"
            return result_info

        result_info["input_bytes"] = input_bytes

        # Video dry_run: download was needed for codec detection, report and stop
        if config.dry_run and is_video:
            codec = detect_video_codec(input_path)
            if codec == "av1":
                logger.info(
                    "%s: Skipped (already AV1) [DRY RUN]", asset.original_file_name
                )
                result_info["status"] = "skipped"
            else:
                logger.info(
                    "%s: %d kB, codec=%s -> [would transcode to AV1] [DRY RUN]",
                    asset.original_file_name,
                    input_bytes / 1024,
                    codec or "unknown",
                )
                result_info["status"] = "dry_run_skip"
            return result_info

        if is_video:
            result = transcode_video(
                input_path,
                output_path,
                crf=config.video_crf,
                preset=config.video_preset,
                max_dimension=config.video_max_dimension,
                audio_bitrate=config.video_audio_bitrate,
            )
            is_valid = validate_video_output(output_path)
        else:
            result = transcode(input_path, output_path, config.image_distance)
            is_valid = validate_output(output_path, "jxl")

        if not result.success:
            if result.error and result.error.startswith("Already "):
                logger.info("%s: Skipped (%s)", asset.original_file_name, result.error)
                result_info["status"] = "skipped"
                return result_info
            logger.error("%s: %s", asset.original_file_name, result.error)
            result_info["status"] = "failed_transcode"
            return result_info

        if not is_valid:
            logger.error("%s: Output validation failed", asset.original_file_name)
            result_info["status"] = "failed_transcode"
            return result_info

        output_bytes = result.output_bytes
        result_info["output_bytes"] = output_bytes

        # Handle larger output with retry logic
        if output_bytes > input_bytes:
            if config.allow_larger:
                # Accept larger output without retry
                pass
            elif config.enable_retry:
                # Retry with lower quality settings
                if is_video:
                    logger.info(
                        "%s: Output larger, retrying with CRF %d...",
                        asset.original_file_name,
                        config.video_crf_retry,
                    )
                    result = transcode_video(
                        input_path,
                        output_path,
                        crf=config.video_crf_retry,
                        preset=config.video_preset,
                        max_dimension=config.video_max_dimension,
                        audio_bitrate=config.video_audio_bitrate,
                    )
                    is_valid = validate_video_output(output_path)
                else:
                    logger.info(
                        "%s: Output larger, retrying with distance %.1f...",
                        asset.original_file_name,
                        config.image_distance_retry,
                    )
                    result = transcode(
                        input_path, output_path, config.image_distance_retry
                    )
                    is_valid = validate_output(output_path, "jxl")

                if not result.success or not is_valid:
                    logger.info(
                        "%s: Skipped (retry failed or validation failed)",
                        asset.original_file_name,
                    )
                    result_info["status"] = "skipped"
                    return result_info

                output_bytes = result.output_bytes
                result_info["output_bytes"] = output_bytes

                # After retry, check if still larger
                if output_bytes > input_bytes and not config.accept_retry_output:
                    logger.info(
                        "%s: Skipped (retry output still larger)",
                        asset.original_file_name,
                    )
                    result_info["status"] = "skipped"
                    return result_info
            else:
                logger.info("%s: Skipped (output larger)", asset.original_file_name)
                result_info["status"] = "skipped"
                return result_info

        if input_bytes > 0:
            savings = input_bytes - output_bytes
            savings_pct = (savings / input_bytes) * 100
            result_info["savings_pct"] = savings_pct

        # Replace: upload -> copy metadata -> verify -> delete original
        base_name = os.path.splitext(asset.original_file_name)[0]
        new_filename = f"{base_name}.{target_format}"
        new_device_asset_id = f"{asset.id}-{target_format}"

        new_asset_id, error = client.upload_asset(
            file_path=output_path,
            device_asset_id=new_device_asset_id,
            device_id=asset.device_id,
            file_created_at=asset.file_created_at,
            file_modified_at=asset.file_modified_at,
            filename=new_filename,
        )

        if error or not new_asset_id:
            logger.error("%s: Upload failed: %s", asset.original_file_name, error)
            result_info["status"] = "failed_upload"
            return result_info

        success, error = client.copy_asset_data(
            from_asset_id=asset.id, to_asset_id=new_asset_id
        )
        if not success:
            client.delete_assets([new_asset_id])
            logger.error("%s: Copy failed: %s", asset.original_file_name, error)
            result_info["status"] = "failed_copy"
            return result_info

        verified, verify_error = client.get_asset(new_asset_id)
        if not verified:
            client.delete_assets([new_asset_id])
            logger.error(
                "%s: Verification failed: %s", asset.original_file_name, verify_error
            )
            result_info["status"] = "failed_verification"
            return result_info

        success, error = client.delete_assets([asset.id])
        if not success:
            logger.warning(
                "%s: Replaced but old asset not deleted: %s",
                asset.original_file_name,
                error,
            )
            result_info["status"] = "partial_success"
            return result_info

        logger.info(
            "%s: %d kB -> %d kB (%.1f%% saved)",
            asset.original_file_name,
            input_bytes / 1024,
            output_bytes / 1024,
            result_info["savings_pct"],
        )
        result_info["status"] = "success"
        return result_info

    finally:
        for path in (input_path, output_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError as e:
                    logger.warning("Failed to clean up %s: %s", path, e)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        config = Config.from_env()
    except ValueError as e:
        logger.error("Configuration error: %s", e)
        return 1

    type_labels = ", ".join(config.asset_types)
    target_formats = []
    if "IMAGE" in config.asset_types:
        target_formats.append("JXL")
    if "VIDEO" in config.asset_types:
        target_formats.append("AV1")

    logger.info(
        "Immich Library Converter (%s -> %s)", type_labels, ", ".join(target_formats)
    )
    logger.info("=" * 50)

    dry_run_suffix = " [DRY RUN]" if config.dry_run else ""
    if "VIDEO" in config.asset_types:
        logger.info("Video: crf=%d, preset=%s", config.video_crf, config.video_preset)
        if config.enable_retry:
            logger.info("  Retry with CRF %d if larger", config.video_crf_retry)
    if "IMAGE" in config.asset_types:
        logger.info("Image: distance=%.1f", config.image_distance)
        if config.enable_retry:
            logger.info(
                "  Retry with distance %.1f if larger", config.image_distance_retry
            )
    if config.enable_retry and config.accept_retry_output:
        logger.info("Allow larger output after retry: yes")
    logger.info("Workers: %d%s", config.concurrency, dry_run_suffix)

    os.makedirs(config.input_dir(), exist_ok=True)
    os.makedirs(config.output_dir(), exist_ok=True)

    client = ImmichClient(
        api_base=config.immich_api_base,
        api_key=config.immich_api_key,
        retry_max=3,
        retry_backoff=2,
    )

    logger.info("Connecting to API...")
    ok, error = client.test_connection()
    if not ok:
        logger.error("Connection failed: %s", error)
        return 1
    logger.info("API connection OK")

    assets: list[Asset] = []
    logger.info("Scanning assets...")

    for atype in config.asset_types:
        page = 1
        while True:
            try:
                page_assets = client.search_assets(
                    page=page,
                    size=500,
                    asset_type=atype,
                    with_archived=config.include_archived,
                    with_deleted=config.include_deleted,
                    taken_after=config.filter_date_after,
                    taken_before=config.filter_date_before,
                )
            except Exception as e:
                logger.error("Failed to fetch %s page %d: %s", atype, page, e)
                break
            if not page_assets:
                break
            assets.extend(page_assets)
            page += 1
            if config.max_assets and len(assets) >= config.max_assets:
                break

    if config.max_assets and len(assets) > config.max_assets:
        assets = assets[: config.max_assets]

    total_count = len(assets)
    logger.info("Found %d assets (%s)", total_count, ", ".join(config.asset_types))

    if total_count == 0:
        logger.info("Nothing to process")
        return 0

    results = []

    with ThreadPoolExecutor(max_workers=config.concurrency) as executor:
        futures = {
            executor.submit(process_asset, asset, client, config): asset
            for asset in assets
        }

        for i, future in enumerate(as_completed(futures), 1):
            asset = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error("Unexpected error: %s: %s", asset.original_file_name, e)
                results.append(
                    {
                        "status": "error",
                        "input_bytes": 0,
                        "output_bytes": 0,
                        "savings_pct": 0.0,
                    }
                )

            if i % 50 == 0 or i == total_count:
                logger.info(
                    "Progress: %d/%d (%.0f%%)", i, total_count, i / total_count * 100
                )

    total_input = sum(r["input_bytes"] for r in results)
    total_output = sum(r["output_bytes"] for r in results)
    total_savings = total_input - total_output

    status_counts: dict[str, int] = {}
    for r in results:
        status = r["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    logger.info("=" * 50)
    logger.info("Summary:")
    for status, count in sorted(status_counts.items()):
        logger.info("  %s: %d", status, count)

    if total_input > 0:
        logger.info("Input: %s bytes", f"{total_input:,}")
        logger.info("Output: %s bytes", f"{total_output:,}")
        logger.info(
            "Savings: %s bytes (%.1f%%)",
            f"{total_savings:+,}",
            (total_savings / total_input) * 100,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
