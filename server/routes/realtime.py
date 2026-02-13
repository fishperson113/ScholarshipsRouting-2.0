"""
WebSocket endpoint for real-time updates using Redis Pub/Sub.

Provides real-time notifications to connected clients.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set
import json
import asyncio
from services.pubsub import pubsub

router = APIRouter()

# Track active WebSocket connections (Optional: for metrics)
active_connections: Set[WebSocket] = set()


@router.websocket("/ws/updates/{channel}")
async def websocket_updates(websocket: WebSocket, channel: str):
    """
    WebSocket endpoint for real-time updates.
    
    Clients connect and receive messages published to the specified channel.
    
    Example:
        ws://localhost:8000/api/v1/realtime/ws/updates/user.{uid}.notifications
    """
    await websocket.accept()
    active_connections.add(websocket)
    
    # Get the current event loop to schedule async tasks from sync callbacks
    loop = asyncio.get_running_loop()
    
    # Define the callback that Redis listener (Thread) will call
    # It must be SYNC, but it needs to trigger ASYNC websocket send
    def forward_to_websocket(message: dict):
        try:
            # Schedule the send_json coroutine on the main event loop
            if websocket.client_state.name == "CONNECTED":
                asyncio.run_coroutine_threadsafe(websocket.send_json(message), loop)
        except Exception as e:
            print(f"Error forwarding message to WS: {e}")

    # Register the callback
    pubsub.subscribe(channel, forward_to_websocket)
    print(f"✅ Client connected to channel: {channel}")

    try:
        # Keep connection alive
        while True:
            # Wait for messages from client (ping/pong or ignore)
            data = await websocket.receive_text()
            # We don't expect client to send anything, but we must await receive
            # to keep the connection open.
            
    except WebSocketDisconnect:
        print(f"❌ Client disconnected from channel: {channel}")
        active_connections.remove(websocket)
        # Note: In current PubSub implementation, unsubscribe removes ALL listeners for the channel.
        # Ideally, we should remove only THIS callback, but pubsub.py doesn't support that yet.
        # For notification channels (unique per user), this is generally fine (1 user = 1 connection usually).
        # We perform unsafe unsubscribe here if we assume 1 connection per user.
        # If we don't unsubscribe, the list of callbacks grows indefinitely in pubsub.py (Memory Leak).
        # So we MUST unsubscribe.
        pubsub.unsubscribe(channel)
        
    except Exception as e:
        print(f"WebSocket error: {e}")
        if websocket in active_connections:
            active_connections.remove(websocket)
        pubsub.unsubscribe(channel)


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
