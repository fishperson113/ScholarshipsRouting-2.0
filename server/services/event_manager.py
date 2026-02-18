import logging
from typing import Dict, List, Callable, Any
import asyncio

logger = logging.getLogger(__name__)

class EventManager:
    """
    Internal Event Bus for decoupling components.
    Simulates a Webhook system within the application architecture.
    """
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_type: str, handler: Callable):
        """Register a handler for a specific event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
        logger.info(f"🔌 Validated subscription: {handler.__name__} subscribed to {event_type}")

    async def emit(self, event_type: str, payload: Any):
        """Dispatch event to all subscribers."""
        if event_type not in self._subscribers:
            logger.debug(f"Event {event_type} emitted but no subscribers found.")
            return

        logger.info(f"📢 Emitting event: {event_type}")
        
        # Execute all handlers concurrently
        handlers = self._subscribers[event_type]
        tasks = []
        
        for handler in handlers:
            try:
                # Support both async and sync handlers
                if asyncio.iscoroutinefunction(handler):
                    tasks.append(handler(payload))
                else:
                    # Run sync function in thread pool to avoid blocking
                    loop = asyncio.get_running_loop()
                    tasks.append(loop.run_in_executor(None, handler, payload))
            except Exception as e:
                logger.error(f"❌ Error preparing handler {handler.__name__}: {e}")

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

# Global Instance
event_bus = EventManager()
