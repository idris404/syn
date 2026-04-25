import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

router = APIRouter(prefix="/ws", tags=["websocket"])

_connections: list[WebSocket] = []


async def broadcast(message: dict) -> None:
    dead: list[WebSocket] = []
    for ws in _connections:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)

    for ws in dead:
        if ws in _connections:
            _connections.remove(ws)


@router.websocket("/alerts")
async def alerts_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    _connections.append(websocket)
    logger.info(f"WebSocket connected - {len(_connections)} active clients")
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        if websocket in _connections:
            _connections.remove(websocket)
        logger.info("WebSocket disconnected")