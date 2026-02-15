"""
Redis Pub/Sub implementation for real-time updates.

Provides publish/subscribe pattern for:
- Real-time notifications
- Event broadcasting
- Cache invalidation coordination
- WebSocket message distribution

Uses sync redis.Redis for publish (fast, used by Celery/sync code).
Uses redis.asyncio for subscribe/listen (runs on the FastAPI event loop, no threads).
"""
import json
import asyncio
import logging
from typing import Callable, Dict, Any, Optional, List
from services.redis_manager import redis_manager
import redis

logger = logging.getLogger(__name__)


class RedisPubSub:
    """
    Redis Pub/Sub manager for real-time messaging.

    Publish path: sync (redis_manager.client) — safe from both async and sync callers.
    Subscribe/listen path: async (redis.asyncio) — runs on the event loop, no threads.
    """

    def __init__(self):
        # Async resources are created lazily (no event loop at module import time)
        self._async_client = None
        self._async_pubsub = None
        self._listener_task: Optional[asyncio.Task] = None
        self._running = False

        # channel -> list of async callback functions
        self._subscribers: Dict[str, List[Callable]] = {}

    # ==================== Lazy Async Initialization ====================

    async def _ensure_async(self):
        """
        Lazily create the async Redis client and PubSub object.
        Must be called from a running event loop (e.g. FastAPI route).
        """
        if self._async_client is None:
            self._async_client = redis_manager.create_async_pubsub_client()
            await self._async_client.ping()
            logger.info("Async Redis PubSub client connected")

        if self._async_pubsub is None:
            self._async_pubsub = self._async_client.pubsub()

    # ==================== Publisher Methods (SYNC) ====================

    def publish(self, channel: str, message: Dict[str, Any]) -> int:
        """
        Publish message to a channel.

        Uses the sync redis_manager.client — fast and safe to call from
        both async (FastAPI) and sync (Celery) contexts.
        """
        try:
            serialized = json.dumps(message)
            return redis_manager.client.publish(channel, serialized)
        except Exception as e:
            logger.error(f"Publish error: {e}")
            return 0

    def publish_document_update(self, collection: str, doc_id: str, action: str = "update"):
        """Publish document update event."""
        self.publish(f"firestore.{collection}", {
            "collection": collection,
            "doc_id": doc_id,
            "action": action,
            "timestamp": None
        })

    def publish_cache_invalidation(self, pattern: str):
        """Publish cache invalidation event."""
        self.publish("cache.invalidate", {
            "pattern": pattern
        })

    # ==================== Subscriber Methods (ASYNC) ====================

    async def subscribe(self, channel: str, callback: Callable):
        """
        Subscribe to a channel with an async callback.

        Args:
            channel: Channel name to subscribe to
            callback: Async function called with (message_dict) when a
                      message arrives on this channel.
        """
        await self._ensure_async()

        if channel not in self._subscribers:
            self._subscribers[channel] = []
            await self._async_pubsub.subscribe(channel)
            logger.info(f"Subscribed to Redis channel: {channel}")

        self._subscribers[channel].append(callback)

        # Start the listener task if not already running
        if not self._running:
            self._start_listening()

    async def unsubscribe(self, channel: str, callback=None):
        """
        Unsubscribe from a channel.

        If callback is provided, only that specific callback is removed.
        The Redis subscription is torn down when zero callbacks remain.
        If callback is None, all callbacks for the channel are removed.
        """
        if channel not in self._subscribers:
            return

        if callback is not None:
            try:
                self._subscribers[channel].remove(callback)
            except ValueError:
                pass

            if not self._subscribers[channel]:
                if self._async_pubsub:
                    await self._async_pubsub.unsubscribe(channel)
                del self._subscribers[channel]
                logger.info(f"Unsubscribed from Redis channel: {channel}")
        else:
            if self._async_pubsub:
                await self._async_pubsub.unsubscribe(channel)
            del self._subscribers[channel]
            logger.info(f"Unsubscribed all callbacks from channel: {channel}")

    # ==================== Listener (ASYNC TASK) ====================

    def _start_listening(self):
        """Start the async listener task if not already running."""
        if self._running:
            return

        self._running = True
        self._listener_task = asyncio.create_task(self._listen())
        logger.info("PubSub async listener task started")

    async def _listen(self):
        """
        Async listener loop using get_message(timeout=1.0).

        - Returns None if no message within 1 second (yields to event loop)
        - Cancellable via asyncio.Task.cancel() at any await point
        - Checks self._running each iteration for graceful shutdown
        """
        reconnect_attempts = 0

        while self._running:
            try:
                message = await self._async_pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0
                )

                if message is None:
                    continue

                if message['type'] == 'message':
                    channel = message['channel']
                    if isinstance(channel, bytes):
                        channel = channel.decode('utf-8')

                    # Deserialize message data
                    try:
                        data = json.loads(message['data'])
                    except (json.JSONDecodeError, TypeError):
                        data = message['data']

                    # Call all subscribers for this channel
                    if channel in self._subscribers:
                        for callback in list(self._subscribers[channel]):
                            try:
                                await callback(data)
                            except Exception as e:
                                logger.error(f"Subscriber callback error on {channel}: {e}")

                reconnect_attempts = 0

            except asyncio.CancelledError:
                logger.info("PubSub listener task cancelled")
                return

            except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError, OSError) as e:
                if not self._running:
                    return

                backoff = min(2 ** reconnect_attempts, 60)
                reconnect_attempts += 1
                logger.warning(
                    f"PubSub connection lost ({e}), reconnecting in {backoff}s... "
                    f"(attempt {reconnect_attempts})"
                )
                await asyncio.sleep(backoff)

                try:
                    # Close old resources to prevent socket leaks
                    await self._close_async_resources()

                    # Recreate async client and PubSub
                    self._async_client = redis_manager.create_async_pubsub_client()
                    await self._async_client.ping()
                    self._async_pubsub = self._async_client.pubsub()

                    # Re-subscribe to all active channels
                    for channel in self._subscribers:
                        await self._async_pubsub.subscribe(channel)

                    reconnect_attempts = 0
                    logger.info("PubSub reconnected successfully")
                except Exception as reconnect_err:
                    logger.error(f"PubSub reconnect failed: {reconnect_err}")

            except Exception as e:
                if not self._running:
                    return
                logger.error(f"PubSub unexpected error: {e}, retrying in 5s...")
                await asyncio.sleep(5)

    # ==================== Shutdown ====================

    async def _close_async_resources(self):
        """Close async PubSub and client, suppressing errors."""
        try:
            if self._async_pubsub:
                await self._async_pubsub.close()
        except Exception:
            pass
        self._async_pubsub = None

        try:
            if self._async_client:
                await self._async_client.close()
        except Exception:
            pass
        self._async_client = None

    async def shutdown(self):
        """
        Gracefully shut down the PubSub listener and close connections.
        Called from app.py shutdown event handler.
        """
        logger.info("Shutting down PubSub...")
        self._running = False

        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        await self._close_async_resources()
        self._subscribers.clear()
        logger.info("PubSub shutdown complete")

    def stop_listening(self):
        """Backwards-compatible sync stop (best-effort)."""
        self._running = False

    # ==================== Predefined Channels ====================

    @staticmethod
    def channel_document_updates(collection: str) -> str:
        """Get channel name for document updates."""
        return f"firestore.{collection}"

    @staticmethod
    def channel_cache_invalidation() -> str:
        """Get channel name for cache invalidation."""
        return "cache.invalidate"

    @staticmethod
    def channel_user_notifications(user_id: str) -> str:
        """Get channel name for user notifications."""
        return f"user.{user_id}.notifications"


# ==================== Global Instance ====================

pubsub = RedisPubSub()


# ==================== Helper Functions ====================

def notify_document_change(collection: str, doc_id: str, action: str = "update"):
    """Notify subscribers about document changes."""
    pubsub.publish_document_update(collection, doc_id, action)


def invalidate_cache_globally(pattern: str):
    """Invalidate cache across all servers."""
    pubsub.publish_cache_invalidation(pattern)
