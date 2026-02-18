"""
WebSocket endpoint for real-time updates using Redis Pub/Sub.

Provides real-time notifications to connected clients.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Track active WebSocket connections
active_connections: Set[WebSocket] = set()


@router.websocket("/ws/updates/{channel}")
async def websocket_updates(websocket: WebSocket, channel: str):
    """
    WebSocket endpoint for real-time updates.

    Clients connect and receive messages published to the specified channel.

    Example:
        ws://localhost:8000/api/v1/realtime/ws/updates/firestore.scholarships
    """
    await websocket.accept()
    active_connections.add(websocket)

    from services.pubsub import pubsub

    async def on_message(message):
        """Called directly on the event loop when a PubSub message arrives."""
        try:
            await websocket.send_json(message)
        except Exception:
            pass

    await pubsub.subscribe(channel, on_message)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error on channel {channel}: {e}")
    finally:
        await pubsub.unsubscribe(channel, on_message)
        active_connections.discard(websocket)
        logger.info(f"Client disconnected from channel: {channel}")


@router.get("/channels")
async def list_channels():
    """List available pub/sub channels."""
    return {
        "channels": [
            "firestore.{collection}",
            "cache.invalidate",
            "user.{user_id}.notifications"
        ],
        "active_connections": len(active_connections)
    }
