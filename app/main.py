#!/usr/bin/env python3
"""Main orchestration for batch-transcoding Immich library assets."""

import json
import logging
import os
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

try:
    from app.cli import parse_args, setup_logging
    from app.config import Config
    from app.immich_api import Asset, ImmichClient
    from app.interactive import QuestionaryPrompt, run_interactive
    from app.state import StateDB
    from app.transcode import (
        detect_video_codec,
        transcode,
        transcode_video,
        validate_output,
        validate_video_output,
    )
except ImportError:  # pragma: no cover
    from cli import parse_args, setup_logging  # type: ignore[no-redef]
    from config import Config  # type: ignore[no-redef]
    from immich_api import Asset, ImmichClient  # type: ignore[no-redef]
    from interactive import QuestionaryPrompt, run_interactive  # type: ignore[no-redef]
    from state import StateDB  # type: ignore[no-redef]
    from transcode import (  # type: ignore[no-redef]
        detect_video_codec,
        transcode,
        transcode_video,
        validate_output,
        validate_video_output,
    )

try:
    from tqdm import tqdm
    from tqdm.contrib.logging import logging_redirect_tqdm
except ImportError:  # pragma: no cover
    tqdm = None  # type: ignore
    logging_redirect_tqdm = None  # type: ignore

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


def _fmt_timings(timings: dict[str, float]) -> str:
    """Render per-stage timings as `dl=120ms tx=3.1s` with a total."""
    parts = []
    total = 0.0
    for stage, seconds in timings.items():
        total += seconds
        if seconds < 1:
            parts.append(f"{stage}={int(seconds * 1000)}ms")
        else:
            parts.append(f"{stage}={seconds:.1f}s")
    return " ".join(parts) + f" (total {total:.1f}s)"


def process_asset(asset: Asset, client: ImmichClient, config: Config) -> dict:
    input_path = ""
    output_path = ""
    timings: dict[str, float] = {}
    result_info: dict = {
        "status": "unknown",
        "input_bytes": 0,
        "output_bytes": 0,
        "savings_pct": 0.0,
        "timings": timings,
    }

    def stage(name: str, start: float) -> None:
        timings[name] = time.monotonic() - start

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

        t = time.monotonic()
        input_bytes, error = client.download_original(asset.id, input_path)
        stage("dl", t)
        if error:
            logger.error("%s: %s", asset.original_file_name, error)
            result_info["status"] = "failed_download"
            result_info["error"] = error
            return result_info

        if input_bytes == 0:
            logger.error("%s: Downloaded file is empty", asset.original_file_name)
            result_info["status"] = "failed_download"
            result_info["error"] = "Downloaded file is empty"
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

        t = time.monotonic()
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
        stage("tx", t)

        if not result.success:
            if result.error and result.error.startswith("Already "):
                logger.info("%s: Skipped (%s)", asset.original_file_name, result.error)
                result_info["status"] = "skipped"
                return result_info
            logger.error("%s: %s", asset.original_file_name, result.error)
            result_info["status"] = "failed_transcode"
            result_info["error"] = result.error
            return result_info

        if not is_valid:
            logger.error("%s: Output validation failed", asset.original_file_name)
            result_info["status"] = "failed_transcode"
            result_info["error"] = "Output validation failed"
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
                t = time.monotonic()
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
                stage("tx_retry", t)

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

        t = time.monotonic()
        new_asset_id, error = client.upload_asset(
            file_path=output_path,
            device_asset_id=new_device_asset_id,
            device_id=asset.device_id,
            file_created_at=asset.file_created_at,
            file_modified_at=asset.file_modified_at,
            filename=new_filename,
        )
        stage("up", t)

        if error or not new_asset_id:
            logger.error("%s: Upload failed: %s", asset.original_file_name, error)
            result_info["status"] = "failed_upload"
            result_info["error"] = error
            return result_info

        result_info["new_asset_id"] = new_asset_id

        t = time.monotonic()
        success, error = client.copy_asset_data(
            from_asset_id=asset.id, to_asset_id=new_asset_id
        )
        stage("copy", t)
        if not success:
            client.delete_assets([new_asset_id])
            logger.error("%s: Copy failed: %s", asset.original_file_name, error)
            result_info["status"] = "failed_copy"
            result_info["error"] = error
            return result_info

        t = time.monotonic()
        verified, verify_error = client.get_asset(new_asset_id)
        stage("verify", t)
        if not verified:
            client.delete_assets([new_asset_id])
            logger.error(
                "%s: Verification failed: %s", asset.original_file_name, verify_error
            )
            result_info["status"] = "failed_verification"
            result_info["error"] = verify_error
            return result_info

        t = time.monotonic()
        success, error = client.delete_assets([asset.id])
        stage("del", t)
        if not success:
            logger.warning(
                "%s: Replaced but old asset not deleted: %s",
                asset.original_file_name,
                error,
            )
            result_info["status"] = "partial_success"
            result_info["error"] = error
            return result_info

        logger.debug(
            "%s: %d kB -> %d kB (%.1f%% saved) [%s]",
            asset.original_file_name,
            input_bytes / 1024,
            output_bytes / 1024,
            result_info["savings_pct"],
            _fmt_timings(timings),
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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(
        level=args.log_level or "info",
        fmt=args.log_format or "text",
    )

    if args.interactive:
        config = run_interactive(
            prompt=QuestionaryPrompt(),
            env_defaults={
                "api_base": os.environ.get("IMMICH_API_BASE", ""),
                "api_key": os.environ.get("IMMICH_API_KEY", ""),
            },
            auto_confirm=args.yes,
        )
        if config is None:
            logger.info("Aborted by user")
            return 0

        logger.info("=" * 50)
        logger.info("Running dry-run preview...")
        logger.info("Preview shows what will be processed, not estimated savings.")
        preview_code = run_converter(config)
        if preview_code != 0:
            return preview_code

        if not args.yes:  # pragma: no cover
            import questionary

            proceed = questionary.confirm(
                "Proceed with real run?", default=False
            ).unsafe_ask()
            if not proceed:
                logger.info("Aborted by user")
                return 0

        from dataclasses import replace

        real_config = replace(config, dry_run=False)
        return run_converter(real_config)

    try:
        config = Config.from_args_and_env(args)
    except ValueError as e:
        logger.error("Configuration error: %s", e)
        return 1

    return run_converter(config, stats_json_path=args.stats_json)


def run_converter(config: Config, stats_json_path: str | None = None) -> int:
    """Run the conversion pipeline with the given config."""
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

    if config.filter_album_id:
        # Fetch assets from specific album
        logger.info("Fetching assets from album %s...", config.filter_album_id)
        try:
            album_assets = client.get_album_assets(config.filter_album_id)
            # Filter by asset type and other criteria
            for asset in album_assets:
                if asset.type not in config.asset_types:
                    continue
                # Apply date filters if set — parse to datetime for robust
                # comparison instead of relying on ISO string lexicographic order.
                if config.filter_date_after:
                    try:
                        asset_dt = datetime.fromisoformat(
                            asset.file_created_at.replace("Z", "+00:00")
                        )
                        filter_dt = datetime.fromisoformat(
                            config.filter_date_after.replace("Z", "+00:00")
                        )
                        if asset_dt < filter_dt:
                            continue
                    except (ValueError, AttributeError):
                        pass
                if config.filter_date_before:
                    try:
                        asset_dt = datetime.fromisoformat(
                            asset.file_created_at.replace("Z", "+00:00")
                        )
                        filter_dt = datetime.fromisoformat(
                            config.filter_date_before.replace("Z", "+00:00")
                        )
                        if asset_dt > filter_dt:
                            continue
                    except (ValueError, AttributeError):
                        pass
                assets.append(asset)
                if config.max_assets and len(assets) >= config.max_assets:
                    break
        except Exception as e:
            logger.error("Failed to get album: %s", e)
            return 1
    else:
        # Original search logic for all assets
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

    # State DB for resumability — only used outside dry-run.
    state: StateDB | None = None
    if config.use_state and not config.dry_run:
        state = StateDB(config.state_db_path())
        if config.reset_state:
            logger.info("Resetting state DB at %s", config.state_db_path())
            state.reset()

        if config.only_failed:
            failed = state.failed_ids()
            before = len(assets)
            assets = [a for a in assets if a.id in failed]
            logger.info(
                "--only-failed: kept %d/%d assets matching last-failure state",
                len(assets),
                before,
            )
        else:
            done = state.completed_ids()
            if done:
                before = len(assets)
                assets = [a for a in assets if a.id not in done]
                skipped = before - len(assets)
                if skipped:
                    logger.info(
                        "Resuming: skipping %d assets already recorded as done",
                        skipped,
                    )

    if config.max_assets and len(assets) > config.max_assets:
        assets = assets[: config.max_assets]

    total_count = len(assets)
    logger.info("Found %d assets (%s)", total_count, ", ".join(config.asset_types))

    if total_count == 0:
        logger.info("Nothing to process")
        if state is not None:
            _maybe_export_failures(state, config)
            state.close()
        return 0

    # Graceful SIGINT: finish in-flight, cancel the rest.
    interrupted = threading.Event()
    prev_handler = signal.getsignal(signal.SIGINT)

    def _on_sigint(signum, frame):  # type: ignore[no-untyped-def]
        if not interrupted.is_set():
            logger.warning(
                "Interrupt received — finishing in-flight work, then stopping. "
                "Press Ctrl-C again to abort immediately."
            )
            interrupted.set()
        else:
            logger.error("Second interrupt — aborting.")
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            os.kill(os.getpid(), signal.SIGINT)

    try:
        signal.signal(signal.SIGINT, _on_sigint)
    except ValueError:
        # Not on main thread — signals unavailable; skip graceful handler.
        pass

    results: list[dict] = []

    _redirect = (
        logging_redirect_tqdm()
        if logging_redirect_tqdm is not None and tqdm is not None
        else None
    )
    if _redirect is not None:
        _redirect.__enter__()

    try:
        with ThreadPoolExecutor(max_workers=config.concurrency) as executor:
            futures = {
                executor.submit(process_asset, asset, client, config): asset
                for asset in assets
            }

            if tqdm is not None:
                pbar = tqdm(
                    total=total_count,
                    desc="Converting",
                    unit="asset",
                )
            else:
                pbar = None  # type: ignore

            for future in as_completed(futures):
                asset = futures[future]
                try:
                    result = future.result()
                except Exception as e:
                    logger.error(
                        "Unexpected error: %s: %s", asset.original_file_name, e
                    )
                    result = {
                        "status": "error",
                        "input_bytes": 0,
                        "output_bytes": 0,
                        "savings_pct": 0.0,
                        "error": str(e),
                    }
                results.append(result)

                if state is not None and result.get("status") not in (
                    "dry_run_skip",
                    "unknown",
                ):
                    state.record(
                        asset_id=asset.id,
                        status=result["status"],
                        filename=asset.original_file_name,
                        error=result.get("error"),
                        new_asset_id=result.get("new_asset_id"),
                        target_format=_get_target_format(asset),
                        input_bytes=int(result.get("input_bytes", 0)),
                        output_bytes=int(result.get("output_bytes", 0)),
                    )

                if pbar is not None:
                    pbar.update(1)
                else:
                    i = len(results)
                    if i % 50 == 0 or i == total_count:
                        logger.info(
                            "Progress: %d/%d (%.0f%%)",
                            i,
                            total_count,
                            i / total_count * 100,
                        )

                if interrupted.is_set():
                    for pending in futures:
                        if not pending.done():
                            pending.cancel()
                    break

            if pbar is not None:
                pbar.close()
    finally:
        if _redirect is not None:
            _redirect.__exit__(None, None, None)
        try:
            signal.signal(signal.SIGINT, prev_handler)
        except ValueError:
            pass

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

    if stats_json_path:
        stats = {
            "total_assets": total_count,
            "status_counts": status_counts,
            "input_bytes": total_input,
            "output_bytes": total_output,
            "savings_bytes": total_savings,
            "savings_pct": (total_savings / total_input) * 100
            if total_input > 0
            else 0.0,
        }
        try:
            with open(stats_json_path, "w") as f:
                json.dump(stats, f, indent=2)
            logger.info("Stats written to %s", stats_json_path)
        except OSError as e:
            logger.error("Failed to write stats to %s: %s", stats_json_path, e)

    if state is not None:
        _maybe_export_failures(state, config)
        state.close()

    return 0


def _maybe_export_failures(state: StateDB, config: Config) -> None:
    if not config.export_failures:
        return
    try:
        count = state.export_failures_csv(config.export_failures)
        logger.info("Exported %d failure rows to %s", count, config.export_failures)
    except OSError as e:
        logger.error("Failed to export failures to %s: %s", config.export_failures, e)


if __name__ == "__main__":
    sys.exit(main())
