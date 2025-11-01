"""
Event bus system for loose coupling communication between modules.

This module implements a publish-subscribe event system that allows
audio processing services to communicate without direct dependencies.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Callable, Optional, Set, Union
from enum import Enum
import structlog
import weakref

logger = structlog.get_logger(__name__)


class EventPriority(Enum):
    """Event priority levels for processing order."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class Event:
    """
    Event data structure for the event bus system.
    
    Contains event metadata, payload, and routing information.
    """
    event_type: str
    source: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    priority: EventPriority = EventPriority.NORMAL
    correlation_id: Optional[str] = None
    target: Optional[str] = None  # For targeted events
    ttl_seconds: Optional[float] = None  # Time to live
    
    def __post_init__(self):
        """Validate event after creation."""
        if not self.event_type:
            raise ValueError("Event type cannot be empty")
        if not self.source:
            raise ValueError("Event source cannot be empty")
    
    def is_expired(self) -> bool:
        """Check if event has expired based on TTL."""
        if self.ttl_seconds is None:
            return False
        
        elapsed = (datetime.now() - self.timestamp).total_seconds()
        return elapsed > self.ttl_seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            'event_type': self.event_type,
            'source': self.source,
            'data': self.data,
            'timestamp': self.timestamp.isoformat(),
            'priority': self.priority.value,
            'correlation_id': self.correlation_id,
            'target': self.target,
            'ttl_seconds': self.ttl_seconds
        }


class EventHandler(ABC):
    """
    Abstract base class for event handlers.
    
    Services implement this interface to handle specific event types.
    """
    
    @abstractmethod
    async def handle_event(self, event: Event) -> None:
        """
        Handle an event.
        
        Args:
            event: Event to handle
        """
        pass
    
    @abstractmethod
    def get_supported_events(self) -> Set[str]:
        """
        Get set of event types this handler supports.
        
        Returns:
            Set of supported event type strings
        """
        pass
    
    def get_handler_priority(self) -> int:
        """
        Get handler priority for event processing order.
        
        Returns:
            Priority value (higher = processed first)
        """
        return 0


@dataclass
class EventSubscription:
    """Event subscription information."""
    handler: EventHandler
    event_types: Set[str]
    priority: int
    filter_func: Optional[Callable[[Event], bool]] = None
    max_events_per_second: Optional[float] = None
    last_event_time: float = field(default_factory=time.time)
    event_count: int = 0


class EventBus:
    """
    Event bus system for publish-subscribe communication.
    
    Provides loose coupling between audio processing services through
    asynchronous event-driven communication.
    """
    
    def __init__(self, max_queue_size: int = 1000, 
                 enable_metrics: bool = True):
        self._subscriptions: Dict[str, List[EventSubscription]] = {}
        self._event_queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_queue_size)
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None
        self._enable_metrics = enable_metrics
        
        # Metrics
        self._events_published = 0
        self._events_processed = 0
        self._events_dropped = 0
        self._processing_times: List[float] = []
        self._subscription_count = 0
        
        # Rate limiting
        self._rate_limit_window = 1.0  # seconds
        
        # Weak references to prevent memory leaks
        self._handler_refs: Set[weakref.ReferenceType] = set()
    
    async def start(self) -> None:
        """Start the event bus processing."""
        if self._running:
            logger.warning("Event bus already running")
            return
        
        self._running = True
        self._processor_task = asyncio.create_task(self._process_events())
        logger.info("Event bus started")
    
    async def stop(self) -> None:
        """Stop the event bus processing."""
        if not self._running:
            logger.warning("Event bus not running")
            return
        
        self._running = False
        
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        
        # Clear remaining events
        while not self._event_queue.empty():
            try:
                self._event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        logger.info("Event bus stopped")
    
    def subscribe(self, handler: EventHandler, 
                  event_types: Optional[Set[str]] = None,
                  filter_func: Optional[Callable[[Event], bool]] = None,
                  max_events_per_second: Optional[float] = None) -> None:
        """
        Subscribe a handler to events.
        
        Args:
            handler: Event handler to subscribe
            event_types: Set of event types to subscribe to (None for all supported)
            filter_func: Optional filter function for events
            max_events_per_second: Rate limit for this subscription
        """
        if event_types is None:
            event_types = handler.get_supported_events()
        
        if not event_types:
            logger.warning("Handler has no supported event types", handler=type(handler).__name__)
            return
        
        subscription = EventSubscription(
            handler=handler,
            event_types=event_types,
            priority=handler.get_handler_priority(),
            filter_func=filter_func,
            max_events_per_second=max_events_per_second
        )
        
        # Add subscription for each event type
        for event_type in event_types:
            if event_type not in self._subscriptions:
                self._subscriptions[event_type] = []
            
            self._subscriptions[event_type].append(subscription)
            
            # Sort by priority (higher priority first)
            self._subscriptions[event_type].sort(
                key=lambda s: s.priority, reverse=True
            )
        
        # Keep weak reference to handler
        self._handler_refs.add(weakref.ref(handler, self._cleanup_handler))
        self._subscription_count += 1
        
        logger.info(
            "Handler subscribed to events",
            handler=type(handler).__name__,
            event_types=list(event_types),
            priority=subscription.priority
        )
    
    def unsubscribe(self, handler: EventHandler, 
                    event_types: Optional[Set[str]] = None) -> None:
        """
        Unsubscribe a handler from events.
        
        Args:
            handler: Event handler to unsubscribe
            event_types: Set of event types to unsubscribe from (None for all)
        """
        if event_types is None:
            # Unsubscribe from all event types
            event_types = set(self._subscriptions.keys())
        
        removed_count = 0
        for event_type in event_types:
            if event_type in self._subscriptions:
                # Remove subscriptions for this handler
                original_count = len(self._subscriptions[event_type])
                self._subscriptions[event_type] = [
                    sub for sub in self._subscriptions[event_type]
                    if sub.handler is not handler
                ]
                removed_count += original_count - len(self._subscriptions[event_type])
                
                # Clean up empty event type lists
                if not self._subscriptions[event_type]:
                    del self._subscriptions[event_type]
        
        if removed_count > 0:
            self._subscription_count -= removed_count
            logger.info(
                "Handler unsubscribed from events",
                handler=type(handler).__name__,
                event_types=list(event_types),
                removed_subscriptions=removed_count
            )
    
    async def publish(self, event: Event) -> bool:
        """
        Publish an event to the bus.
        
        Args:
            event: Event to publish
            
        Returns:
            True if event was queued successfully, False otherwise
        """
        if not self._running:
            logger.warning("Cannot publish event: event bus not running")
            return False
        
        # Check if event has expired
        if event.is_expired():
            logger.debug("Event expired, not publishing", event_type=event.event_type)
            self._events_dropped += 1
            return False
        
        # Check if there are any subscribers
        if event.event_type not in self._subscriptions:
            logger.debug("No subscribers for event type", event_type=event.event_type)
            return True  # Not an error, just no subscribers
        
        try:
            # Use negative priority for priority queue (higher priority = lower number)
            priority_value = -event.priority.value
            await self._event_queue.put((priority_value, time.time(), event))
            
            self._events_published += 1
            
            if self._enable_metrics:
                logger.debug(
                    "Event published",
                    event_type=event.event_type,
                    source=event.source,
                    priority=event.priority.name,
                    queue_size=self._event_queue.qsize()
                )
            
            return True
            
        except asyncio.QueueFull:
            logger.warning(
                "Event queue full, dropping event",
                event_type=event.event_type,
                source=event.source
            )
            self._events_dropped += 1
            return False
    
    def publish_sync(self, event: Event) -> bool:
        """
        Synchronously publish an event (non-blocking).
        
        Args:
            event: Event to publish
            
        Returns:
            True if event was queued successfully, False otherwise
        """
        if not self._running:
            return False
        
        if event.is_expired():
            self._events_dropped += 1
            return False
        
        if event.event_type not in self._subscriptions:
            return True
        
        try:
            priority_value = -event.priority.value
            self._event_queue.put_nowait((priority_value, time.time(), event))
            self._events_published += 1
            return True
        except asyncio.QueueFull:
            self._events_dropped += 1
            return False
    
    async def _process_events(self) -> None:
        """Main event processing loop."""
        logger.info("Event processing started")
        
        while self._running:
            try:
                # Wait for event with timeout
                priority, timestamp, event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=0.1
                )
                
                # Check if event has expired while in queue
                if event.is_expired():
                    logger.debug("Event expired in queue", event_type=event.event_type)
                    self._events_dropped += 1
                    continue
                
                # Process event
                await self._handle_event(event)
                
            except asyncio.TimeoutError:
                # No events to process, continue
                continue
            except Exception as e:
                logger.error("Error in event processing loop", error=str(e))
                await asyncio.sleep(0.001)  # Brief pause before retry
    
    async def _handle_event(self, event: Event) -> None:
        """
        Handle a single event by dispatching to subscribers.
        
        Args:
            event: Event to handle
        """
        start_time = time.time()
        
        # Get subscribers for this event type
        subscriptions = self._subscriptions.get(event.event_type, [])
        
        if not subscriptions:
            return
        
        # Filter subscriptions based on target
        if event.target:
            subscriptions = [
                sub for sub in subscriptions
                if hasattr(sub.handler, 'service_name') and 
                sub.handler.service_name == event.target
            ]
        
        handled_count = 0
        error_count = 0
        
        # Process subscriptions in priority order
        for subscription in subscriptions:
            try:
                # Check rate limiting
                if not self._check_rate_limit(subscription):
                    continue
                
                # Apply filter if present
                if subscription.filter_func and not subscription.filter_func(event):
                    continue
                
                # Handle event
                await subscription.handler.handle_event(event)
                handled_count += 1
                
            except Exception as e:
                error_count += 1
                logger.error(
                    "Error handling event",
                    event_type=event.event_type,
                    handler=type(subscription.handler).__name__,
                    error=str(e)
                )
        
        # Update metrics
        processing_time = time.time() - start_time
        self._events_processed += 1
        
        if self._enable_metrics:
            self._processing_times.append(processing_time)
            
            # Keep only recent processing times
            if len(self._processing_times) > 1000:
                self._processing_times = self._processing_times[-500:]
            
            logger.debug(
                "Event processed",
                event_type=event.event_type,
                handlers=handled_count,
                errors=error_count,
                processing_time_ms=processing_time * 1000
            )
    
    def _check_rate_limit(self, subscription: EventSubscription) -> bool:
        """
        Check if subscription is within rate limit.
        
        Args:
            subscription: Subscription to check
            
        Returns:
            True if within rate limit, False otherwise
        """
        if subscription.max_events_per_second is None:
            return True
        
        current_time = time.time()
        time_since_last = current_time - subscription.last_event_time
        
        if time_since_last >= self._rate_limit_window:
            # Reset counter for new window
            subscription.event_count = 0
            subscription.last_event_time = current_time
        
        # Check if within rate limit
        events_per_second = subscription.event_count / max(time_since_last, 0.001)
        
        if events_per_second >= subscription.max_events_per_second:
            return False
        
        subscription.event_count += 1
        return True
    
    def _cleanup_handler(self, handler_ref: weakref.ReferenceType) -> None:
        """Clean up subscriptions for garbage collected handler."""
        self._handler_refs.discard(handler_ref)
        
        # Note: We don't automatically remove subscriptions here as it would
        # require iterating through all subscriptions. The unsubscribe method
        # should be called explicitly when handlers are no longer needed.
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get event bus metrics.
        
        Returns:
            Dictionary with event bus statistics
        """
        avg_processing_time = 0.0
        if self._processing_times:
            avg_processing_time = sum(self._processing_times) / len(self._processing_times)
        
        return {
            'events_published': self._events_published,
            'events_processed': self._events_processed,
            'events_dropped': self._events_dropped,
            'queue_size': self._event_queue.qsize(),
            'subscription_count': self._subscription_count,
            'event_types': list(self._subscriptions.keys()),
            'avg_processing_time_ms': avg_processing_time * 1000,
            'is_running': self._running
        }
    
    def get_subscribers(self, event_type: str) -> List[str]:
        """
        Get list of subscribers for an event type.
        
        Args:
            event_type: Event type to query
            
        Returns:
            List of subscriber names
        """
        subscriptions = self._subscriptions.get(event_type, [])
        return [type(sub.handler).__name__ for sub in subscriptions]
    
    async def wait_for_processing(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for all queued events to be processed.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if queue is empty, False if timeout occurred
        """
        start_time = time.time()
        
        while not self._event_queue.empty():
            if timeout and (time.time() - start_time) > timeout:
                return False
            await asyncio.sleep(0.001)
        
        return True


# Convenience functions for common event types
def create_service_event(event_type: str, service_name: str, 
                        data: Optional[Dict[str, Any]] = None) -> Event:
    """Create a service-related event."""
    return Event(
        event_type=f"service.{event_type}",
        source=service_name,
        data=data or {}
    )


def create_audio_event(event_type: str, source: str,
                      frame_data: Optional[Dict[str, Any]] = None) -> Event:
    """Create an audio processing event."""
    return Event(
        event_type=f"audio.{event_type}",
        source=source,
        data=frame_data or {},
        priority=EventPriority.HIGH
    )


def create_error_event(error_type: str, source: str, 
                      error_info: Dict[str, Any]) -> Event:
    """Create an error event."""
    return Event(
        event_type=f"error.{error_type}",
        source=source,
        data=error_info,
        priority=EventPriority.CRITICAL
    )