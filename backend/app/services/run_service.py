"""Run execution: resolves an asset list and processes it through the
download -> transcode -> upload -> copy-metadata -> delete pipeline,
persisting per-asset outcomes and broadcasting live progress.

_process_asset_sync is a direct port of the old CLI's app/main.py
process_asset() (git history has the original). The async layer around it
is new: asyncio.to_thread for the blocking client/transcode calls, a
semaphore for concurrency, AssetOutcome rows instead of a flat state.db,
and WebSocket broadcasts instead of tqdm/logging.
"""

import asyncio
import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update

from app.database import AsyncSessionLocal
from app.models.asset_outcome import FINAL_STATUSES, AssetOutcome
from app.models.run import Run
from app.services.immich_client import Asset, ImmichClient
from app.services.transcode import (
    transcode,
    transcode_video,
    validate_output,
    validate_video_output,
)
from app.services.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)

_cancelled_runs: set[int] = set()


def request_cancel(run_id: int) -> None:
    _cancelled_runs.add(run_id)


def _is_cancelled(run_id: int) -> bool:
    return run_id in _cancelled_runs


def _get_target_format(asset: Asset) -> str:
    return "mp4" if asset.type == "VIDEO" else "jxl"


def _should_skip_by_mime_type(asset: Asset) -> bool:
    if asset.type != "IMAGE":
        return False
    mime_type = asset.original_mime_type.lower() if asset.original_mime_type else None
    if mime_type == "image/jxl":
        return True
    return asset.original_file_name.lower().endswith(".jxl")


def _process_asset_sync(
    asset: Asset, client: ImmichClient, cfg: dict[str, Any], work_dir: str
) -> dict[str, Any]:
    """Blocking pipeline for a single asset. Runs on a worker thread."""
    input_path = ""
    output_path = ""
    result: dict[str, Any] = {
        "status": "unknown",
        "input_bytes": 0,
        "output_bytes": 0,
    }

    is_video = asset.type == "VIDEO"
    target_format = _get_target_format(asset)
    dry_run = cfg["dry_run"]

    if not is_video and _should_skip_by_mime_type(asset):
        result["status"] = "skipped"
        return result

    try:
        input_path = os.path.join(work_dir, f"{asset.id}.bin")
        output_path = os.path.join(work_dir, f"{asset.id}.{target_format}")

        input_bytes, error = client.download_original(asset.id, input_path)
        if error:
            result["status"] = "failed_download"
            result["error"] = error
            return result
        if input_bytes == 0:
            result["status"] = "failed_download"
            result["error"] = "Downloaded file is empty"
            return result
        result["input_bytes"] = input_bytes

        if is_video:
            tx = transcode_video(
                input_path,
                output_path,
                crf=cfg["video_crf"],
                preset=str(cfg["video_preset"]),
                max_dimension=cfg["video_max_dimension"],
                audio_bitrate=cfg["video_audio_bitrate"],
            )
            is_valid = validate_video_output(output_path)
        else:
            tx = transcode(input_path, output_path, cfg["image_distance"])
            is_valid = validate_output(output_path, "jxl")

        if not tx.success:
            if tx.error and tx.error.startswith("Already "):
                result["status"] = "skipped"
                return result
            result["status"] = "failed_transcode"
            result["error"] = tx.error
            return result
        if not is_valid:
            result["status"] = "failed_transcode"
            result["error"] = "Output validation failed"
            return result

        output_bytes = tx.output_bytes
        result["output_bytes"] = output_bytes

        if output_bytes > input_bytes:
            if cfg["allow_larger"]:
                pass
            elif cfg["enable_retry"]:
                if is_video:
                    tx = transcode_video(
                        input_path,
                        output_path,
                        crf=cfg["video_crf_retry"],
                        preset=str(cfg["video_preset"]),
                        max_dimension=cfg["video_max_dimension"],
                        audio_bitrate=cfg["video_audio_bitrate"],
                    )
                    is_valid = validate_video_output(output_path)
                else:
                    tx = transcode(input_path, output_path, cfg["image_distance_retry"])
                    is_valid = validate_output(output_path, "jxl")

                if not tx.success or not is_valid:
                    result["status"] = "skipped"
                    return result

                output_bytes = tx.output_bytes
                result["output_bytes"] = output_bytes

                if output_bytes > input_bytes and not cfg["accept_retry_output"]:
                    result["status"] = "skipped"
                    return result
            else:
                result["status"] = "skipped"
                return result

        if dry_run:
            # Real download + transcode already ran above, so this reflects
            # the actual size a real run would produce -- just stop short of
            # touching the user's Immich library.
            result["status"] = "dry_run_preview"
            return result

        base_name = os.path.splitext(asset.original_file_name)[0]
        new_filename = f"{base_name}.{target_format}"

        new_asset_id, error = client.upload_asset(
            file_path=output_path,
            file_created_at=asset.file_created_at,
            file_modified_at=asset.file_modified_at,
            filename=new_filename,
        )
        if error or not new_asset_id:
            result["status"] = "failed_upload"
            result["error"] = error
            return result
        result["new_asset_id"] = new_asset_id

        success, error = client.copy_asset_data(
            from_asset_id=asset.id, to_asset_id=new_asset_id
        )
        if not success:
            client.delete_assets([new_asset_id])
            result["status"] = "failed_copy"
            result["error"] = error
            return result

        verified, verify_error = client.get_asset(new_asset_id)
        if not verified:
            client.delete_assets([new_asset_id])
            result["status"] = "failed_verification"
            result["error"] = verify_error
            return result

        success, error = client.delete_assets([asset.id])
        if not success:
            result["status"] = "partial_success"
            result["error"] = error
            return result

        result["status"] = "success"
        return result

    finally:
        for path in (input_path, output_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError as e:
                    logger.warning("Failed to clean up %s: %s", path, e)


async def _resolve_assets(client: ImmichClient, cfg: dict[str, Any]) -> list[Asset]:
    if cfg.get("asset_ids"):
        fetched = await asyncio.gather(
            *[
                asyncio.to_thread(client.get_asset_full, asset_id)
                for asset_id in cfg["asset_ids"]
            ]
        )
        return [a for a in fetched if a is not None]

    assets = []
    if cfg.get("album_id"):
        album_assets = await asyncio.to_thread(client.get_album_assets, cfg["album_id"])
        asset_types = cfg["asset_types"].split(",")
        assets = [a for a in album_assets if a.type in asset_types]
        if cfg.get("taken_after"):
            assets = [a for a in assets if a.file_created_at >= cfg["taken_after"]]
        if cfg.get("taken_before"):
            assets = [a for a in assets if a.file_created_at <= cfg["taken_before"]]
    else:
        for atype in cfg["asset_types"].split(","):
            page = 1
            while True:
                page_assets = await asyncio.to_thread(
                    client.search_assets,
                    page=page,
                    size=500,
                    asset_type=atype,
                    with_archived=cfg["include_archived"],
                    with_deleted=cfg["include_deleted"],
                    original_filename=cfg.get("original_filename"),
                    taken_after=cfg.get("taken_after"),
                    taken_before=cfg.get("taken_before"),
                )
                if not page_assets:
                    break
                assets.extend(page_assets)
                page += 1

    if not cfg.get("skip_done_filter"):
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AssetOutcome.asset_id, AssetOutcome.status).order_by(
                    AssetOutcome.updated_at.desc()
                )
            )
            latest_status: dict[str, str] = {}
            for asset_id, status in result.all():
                latest_status.setdefault(asset_id, status)
        done_ids = {aid for aid, s in latest_status.items() if s in FINAL_STATUSES}
        assets = [a for a in assets if a.id not in done_ids]

    max_assets = cfg.get("max_assets")
    if max_assets:
        assets = assets[:max_assets]

    return assets


async def _record_outcome(run_id: int, asset: Asset, result: dict[str, Any]) -> None:
    async with AsyncSessionLocal() as db:
        outcome = AssetOutcome(
            run_id=run_id,
            asset_id=asset.id,
            filename=asset.original_file_name,
            status=result["status"],
            error=result.get("error"),
            new_asset_id=result.get("new_asset_id"),
            target_format=_get_target_format(asset),
            input_bytes=result.get("input_bytes", 0),
            output_bytes=result.get("output_bytes", 0),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(outcome)
        await db.commit()


async def _bump_run_counters(run_id: int, status: str) -> dict[str, int]:
    increments: dict[str, Any] = {"processed_count": Run.processed_count + 1}
    if status in ("success", "partial_success", "dry_run_preview"):
        increments["success_count"] = Run.success_count + 1
    elif status == "skipped":
        increments["skipped_count"] = Run.skipped_count + 1
    else:
        increments["failed_count"] = Run.failed_count + 1

    async with AsyncSessionLocal() as db:
        await db.execute(update(Run).where(Run.id == run_id).values(**increments))
        await db.commit()
        result = await db.execute(select(Run).where(Run.id == run_id))
        run = result.scalar_one()
        return {
            "processed_count": run.processed_count,
            "success_count": run.success_count,
            "skipped_count": run.skipped_count,
            "failed_count": run.failed_count,
            "total_assets": run.total_assets,
        }


async def _add_run_bytes(run_id: int, input_bytes: int, output_bytes: int) -> None:
    if not input_bytes and not output_bytes:
        return
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(
                input_bytes=Run.input_bytes + input_bytes,
                output_bytes=Run.output_bytes + output_bytes,
            )
        )
        await db.commit()


async def _run_one_asset(
    run_id: int,
    asset: Asset,
    client: ImmichClient,
    cfg: dict[str, Any],
    work_dir: str,
    semaphore: asyncio.Semaphore,
) -> None:
    async with semaphore:
        if _is_cancelled(run_id):
            return

        await websocket_manager.broadcast(
            {
                "type": "asset_progress",
                "run_id": run_id,
                "asset_id": asset.id,
                "filename": asset.original_file_name,
                "stage": "processing",
            }
        )

        result = await asyncio.to_thread(
            _process_asset_sync, asset, client, cfg, work_dir
        )

        await _record_outcome(run_id, asset, result)
        await _add_run_bytes(
            run_id, result.get("input_bytes", 0), result.get("output_bytes", 0)
        )
        counters = await _bump_run_counters(run_id, result["status"])

        await websocket_manager.broadcast(
            {
                "type": "asset_progress",
                "run_id": run_id,
                "asset_id": asset.id,
                "filename": asset.original_file_name,
                "stage": "done",
                "status": result["status"],
                "error": result.get("error"),
            }
        )
        await websocket_manager.broadcast(
            {"type": "run_progress", "run_id": run_id, **counters}
        )


async def execute_run(run_id: int) -> None:
    """Main entry point, called by run_queue's worker."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Run).where(Run.id == run_id))
        run = result.scalar_one_or_none()
        if run is None or run.status == "cancelled":
            # Already cancelled while still queued (see routes/runs.py).
            # Must still discard here, or a cancelled-while-queued id that
            # never reaches the try/finally below leaks in _cancelled_runs
            # forever and can collide with a future run reusing that id.
            _cancelled_runs.discard(run_id)
            return
        cfg = json.loads(run.config_snapshot)

    api_base = cfg["immich_api_base"]
    if not api_base.endswith("/"):
        api_base += "/"
    client = ImmichClient(api_base=api_base, api_key=cfg["immich_api_key"])

    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(status="running", started_at=datetime.now(timezone.utc))
        )
        await db.commit()
    await websocket_manager.broadcast({"type": "run_started", "run_id": run_id})

    work_dir = os.path.join(
        os.environ.get("TEMP_DIR", "/app/temp"), f"run_{run_id}_{uuid.uuid4().hex[:8]}"
    )
    os.makedirs(work_dir, exist_ok=True)

    error_message = None
    try:
        assets = await _resolve_assets(client, cfg)

        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Run).where(Run.id == run_id).values(total_assets=len(assets))
            )
            await db.commit()

        if assets:
            semaphore = asyncio.Semaphore(max(1, cfg.get("concurrency", 2)))
            await asyncio.gather(
                *[
                    _run_one_asset(run_id, asset, client, cfg, work_dir, semaphore)
                    for asset in assets
                ]
            )
    except Exception as e:
        logger.exception("Run %s failed", run_id)
        error_message = str(e)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        _cancelled_runs.discard(run_id)

    final_status = (
        "cancelled"
        if _is_cancelled(run_id)
        else ("failed" if error_message else "completed")
    )
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(
                status=final_status,
                completed_at=datetime.now(timezone.utc),
                error_message=error_message,
            )
        )
        await db.commit()
    await websocket_manager.broadcast(
        {"type": "run_completed", "run_id": run_id, "status": final_status}
    )
