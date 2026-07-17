"""Album listing (for the album filter in the asset browser)."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_immich_client
from app.models.schemas import AlbumItem, AlbumListResponse
from app.services.immich_client import ImmichClient

router = APIRouter()


@router.get("", response_model=AlbumListResponse)
async def list_albums(client: ImmichClient = Depends(get_immich_client)):
    try:
        albums = await asyncio.to_thread(client.list_albums)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return AlbumListResponse(
        items=[
            AlbumItem(
                id=a["id"], album_name=a["album_name"], asset_count=a["asset_count"]
            )
            for a in albums
        ]
    )
