"""Run API: start conversion runs, track progress, browse history."""

import csv
import io
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.asset_outcome import NON_FAILURE_STATUSES, AssetOutcome
from app.models.run import Run
from app.models.schemas import (
    AssetOutcomeListResponse,
    AssetOutcomeResponse,
    RunCreate,
    RunListResponse,
    RunResponse,
)
from app.routes.settings import get_settings_row
from app.services import run_service
from app.services.run_queue import run_queue

router = APIRouter()


def _pick(override: Any, default: Any) -> Any:
    return override if override is not None else default


async def _build_config_snapshot(data: RunCreate, db: AsyncSession) -> dict[str, Any]:
    settings = await get_settings_row(db)
    if not settings.immich_api_base or not settings.immich_api_key:
        raise HTTPException(
            status_code=424,
            detail="Immich connection not configured -- set it on the Settings page",
        )

    return {
        "immich_api_base": settings.immich_api_base,
        "immich_api_key": settings.immich_api_key,
        "asset_ids": data.asset_ids,
        "asset_types": _pick(data.asset_types, settings.asset_types),
        "album_id": data.album_id,
        "include_archived": _pick(data.include_archived, settings.include_archived),
        "include_deleted": _pick(data.include_deleted, settings.include_deleted),
        "taken_after": data.taken_after,
        "taken_before": data.taken_before,
        "original_filename": data.original_filename,
        "max_assets": data.max_assets,
        "dry_run": data.dry_run,
        "image_distance": _pick(data.image_distance, settings.image_distance),
        "image_distance_retry": _pick(
            data.image_distance_retry, settings.image_distance_retry
        ),
        "video_crf": _pick(data.video_crf, settings.video_crf),
        "video_preset": _pick(data.video_preset, settings.video_preset),
        "video_max_dimension": _pick(
            data.video_max_dimension, settings.video_max_dimension
        ),
        "video_audio_bitrate": _pick(
            data.video_audio_bitrate, settings.video_audio_bitrate
        ),
        "video_crf_retry": _pick(data.video_crf_retry, settings.video_crf_retry),
        "enable_retry": _pick(data.enable_retry, settings.enable_retry),
        "accept_retry_output": _pick(
            data.accept_retry_output, settings.accept_retry_output
        ),
        "allow_larger": _pick(data.allow_larger, settings.allow_larger),
        "concurrency": _pick(data.concurrency, settings.concurrency),
    }


@router.post("", response_model=RunResponse)
async def create_run(data: RunCreate, db: AsyncSession = Depends(get_db)):
    cfg = await _build_config_snapshot(data, db)

    run = Run(
        status="queued",
        config_snapshot=json.dumps(cfg),
        dry_run=cfg["dry_run"],
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    await run_queue.add_run(run.id)
    return RunResponse.from_run(run)


@router.get("", response_model=RunListResponse)
async def list_runs(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    query = select(Run).order_by(Run.created_at.desc())
    if status:
        query = query.where(Run.status == status)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    result = await db.execute(query.limit(limit).offset(offset))
    runs = result.scalars().all()
    return RunListResponse(items=[RunResponse.from_run(r) for r in runs], total=total)


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunResponse.from_run(run)


@router.get("/{run_id}/assets", response_model=AssetOutcomeListResponse)
async def get_run_assets(
    run_id: int,
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    query = select(AssetOutcome).where(AssetOutcome.run_id == run_id)
    if status:
        query = query.where(AssetOutcome.status == status)
    query = query.order_by(AssetOutcome.updated_at.desc())

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    result = await db.execute(query.limit(limit).offset(offset))
    outcomes = result.scalars().all()
    return AssetOutcomeListResponse(
        items=[AssetOutcomeResponse.from_outcome(o) for o in outcomes], total=total
    )


@router.delete("/{run_id}", response_model=RunResponse)
async def cancel_run(run_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status in ("queued", "running"):
        run_service.request_cancel(run_id)
        if run.status == "queued":
            # The worker checks status before starting; mark it directly so
            # a queued run that never gets picked up still ends up cancelled.
            run.status = "cancelled"
            await db.commit()
            await db.refresh(run)

    return RunResponse.from_run(run)


@router.post("/{run_id}/retry-failed", response_model=RunResponse)
async def retry_failed(run_id: int, db: AsyncSession = Depends(get_db)):
    """Start a new run scoped to this run's non-final-status assets, using
    the same settings the original run used."""
    result = await db.execute(select(Run).where(Run.id == run_id))
    source_run = result.scalar_one_or_none()
    if source_run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    outcomes_result = await db.execute(
        select(AssetOutcome.asset_id)
        .where(AssetOutcome.run_id == run_id)
        .where(AssetOutcome.status.not_in(NON_FAILURE_STATUSES))
        .distinct()
    )
    failed_ids = [row[0] for row in outcomes_result.all()]
    if not failed_ids:
        raise HTTPException(
            status_code=400, detail="This run has no failed assets to retry"
        )

    cfg = json.loads(source_run.config_snapshot)
    cfg["asset_ids"] = failed_ids

    run = Run(status="queued", config_snapshot=json.dumps(cfg), dry_run=cfg["dry_run"])
    db.add(run)
    await db.commit()
    await db.refresh(run)

    await run_queue.add_run(run.id)
    return RunResponse.from_run(run)


@router.get("/{run_id}/export-failures")
async def export_failures(run_id: int, db: AsyncSession = Depends(get_db)):
    """CSV of this run's non-final-status asset outcomes."""
    result = await db.execute(select(Run).where(Run.id == run_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Run not found")

    outcomes_result = await db.execute(
        select(AssetOutcome)
        .where(AssetOutcome.run_id == run_id)
        .where(AssetOutcome.status.not_in(NON_FAILURE_STATUSES))
        .order_by(AssetOutcome.updated_at.desc())
    )
    outcomes = outcomes_result.scalars().all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["asset_id", "filename", "status", "error", "updated_at"])
    for o in outcomes:
        writer.writerow([o.asset_id, o.filename, o.status, o.error, o.updated_at])
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="run-{run_id}-failures.csv"'
        },
    )
