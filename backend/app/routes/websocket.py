"""Live progress: clients connect here to receive run/asset events."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.websocket_manager import websocket_manager

router = APIRouter()


@router.websocket("/ws")
async def progress_socket(websocket: WebSocket):
    await websocket_manager.connect(websocket)
    try:
        while True:
            # Clients don't send anything meaningful; just keep the
            # connection open until they disconnect.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        websocket_manager.disconnect(websocket)
