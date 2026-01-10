"""
WebSocket endpoint for real-time updates using Redis Pub/Sub.

Provides real-time notifications to connected clients.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set
import json

router = APIRouter()

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
    
    try:
        from services.pubsub import pubsub
        
        # Subscribe to channel and forward messages to WebSocket
        async def forward_to_websocket(message):
            try:
                await websocket.send_json(message)
            except:
                pass
        
        # Subscribe to Redis channel
        pubsub.subscribe(channel, lambda msg: forward_to_websocket(msg))
        
        # Keep connection alive and handle client messages
        while True:
            data = await websocket.receive_text()
            # Echo back or handle client messages if needed
            
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        print(f"Client disconnected from channel: {channel}")
    except Exception as e:
        print(f"WebSocket error: {e}")
        if websocket in active_connections:
            active_connections.remove(websocket)


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
