"""Asset browsing: search/filter/paginate the Immich library, thumbnail proxy."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.dependencies import get_immich_client
from app.models.schemas import AssetItem, AssetListResponse
from app.services.immich_client import Asset, ImmichClient

router = APIRouter()


def _already_jxl(asset: Asset) -> bool:
    if asset.type != "IMAGE":
        return False
    mime = (asset.original_mime_type or "").lower()
    if mime == "image/jxl":
        return True
    return asset.original_file_name.lower().endswith(".jxl")


def _to_item(asset: Asset) -> AssetItem:
    return AssetItem(
        id=asset.id,
        original_file_name=asset.original_file_name,
        original_path=asset.original_path,
        original_mime_type=asset.original_mime_type,
        type=asset.type,
        file_created_at=asset.file_created_at,
        file_modified_at=asset.file_modified_at,
        already_jxl=_already_jxl(asset),
    )


@router.get("", response_model=AssetListResponse)
async def list_assets(
    asset_type: str = Query("IMAGE", pattern="^(IMAGE|VIDEO)$"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    include_archived: bool = False,
    include_deleted: bool = False,
    album_id: str | None = None,
    original_filename: str | None = None,
    taken_after: str | None = None,
    taken_before: str | None = None,
    client: ImmichClient = Depends(get_immich_client),
):
    try:
        if album_id:
            all_assets = await asyncio.to_thread(client.get_album_assets, album_id)
            filtered = [a for a in all_assets if a.type == asset_type]
            if taken_after:
                filtered = [a for a in filtered if a.file_created_at >= taken_after]
            if taken_before:
                filtered = [a for a in filtered if a.file_created_at <= taken_before]
            start = (page - 1) * size
            page_assets = filtered[start : start + size]
            has_more = start + size < len(filtered)
        else:
            page_assets = await asyncio.to_thread(
                client.search_assets,
                page=page,
                size=size,
                asset_type=asset_type,
                with_archived=include_archived,
                with_deleted=include_deleted,
                original_filename=original_filename,
                taken_after=taken_after,
                taken_before=taken_before,
            )
            has_more = len(page_assets) == size
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return AssetListResponse(
        items=[_to_item(a) for a in page_assets],
        page=page,
        size=size,
        has_more=has_more,
    )


@router.get("/{asset_id}/thumbnail")
async def get_thumbnail(
    asset_id: str, client: ImmichClient = Depends(get_immich_client)
):
    content, content_type, error = await asyncio.to_thread(
        client.get_thumbnail, asset_id
    )
    if error or content is None:
        raise HTTPException(status_code=502, detail=error or "Thumbnail unavailable")
    return Response(
        content=content,
        media_type=content_type or "image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )
