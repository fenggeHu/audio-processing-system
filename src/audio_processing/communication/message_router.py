"""
Message routing system for point-to-point and publish-subscribe communication.

This module implements flexible message routing with support for different
communication patterns, load balancing, and message filtering.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set, Callable
from enum import Enum
import structlog
import weakref
import hashlib

logger = structlog.get_logger(__name__)


class MessageType(Enum):
    """Message types for routing decisions."""
    CONTROL = "control"
    AUDIO_DATA = "audio_data"
    METRICS = "metrics"
    CONFIG = "config"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


class RoutingStrategy(Enum):
    """Message routing strategies."""
    ROUND_ROBIN = "round_robin"
    LOAD_BALANCED = "load_balanced"
    BROADCAST = "broadcast"
    HASH_BASED = "hash_based"
    PRIORITY_BASED = "priority_based"


@dataclass
class Message:
    """
    Generic message structure for the routing system.
    
    Contains message metadata, payload, and routing information.
    """
    message_id: str
    message_type: MessageType
    source: str
    destination: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    priority: int = 0  # Higher values = higher priority
    ttl_seconds: Optional[float] = None
    correlation_id: Optional[str] = None
    reply_to: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate message after creation."""
        if not self.message_id:
            raise ValueError("Message ID cannot be empty")
        if not self.source:
            raise ValueError("Message source cannot be empty")
    
    def is_expired(self) -> bool:
        """Check if message has expired based on TTL."""
        if self.ttl_seconds is None:
            return False
        return (time.time() - self.timestamp) > self.ttl_seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary for serialization."""
        return {
            'message_id': self.message_id,
            'message_type': self.message_type.value,
            'source': self.source,
            'destination': self.destination,
            'payload': self.payload,
            'timestamp': self.timestamp,
            'priority': self.priority,
            'ttl_seconds': self.ttl_seconds,
            'correlation_id': self.correlation_id,
            'reply_to': self.reply_to,
            'headers': self.headers
        }


class MessageHandler(ABC):
    """Abstract base class for message handlers."""
    
    @abstractmethod
    async def handle_message(self, message: Message) -> Optional[Message]:
        """
        Handle a message.
        
        Args:
            message: Message to handle
            
        Returns:
            Optional response message
        """
    
    @abstractmethod
    def get_supported_message_types(self) -> Set[MessageType]:
        """Get set of message types this handler supports."""
    
    def get_handler_id(self) -> str:
        """Get unique identifier for this handler."""
        return f"{type(self).__name__}_{id(self)}"


@dataclass
class RouteEntry:
    """Routing table entry."""
    destination: str
    handler: MessageHandler
    message_types: Set[MessageType]
    strategy: RoutingStrategy
    priority: int = 0
    load_factor: float = 1.0  # For load balancing
    filter_func: Optional[Callable[[Message], bool]] = None
    
    # Statistics
    messages_routed: int = 0
    last_message_time: float = 0.0
    avg_processing_time: float = 0.0


class MessageRouter:
    """
    Advanced message routing system.
    
    Supports multiple routing strategies, load balancing, and
    flexible message filtering and transformation.
    """
    
    def __init__(self, router_name: str, max_queue_size: int = 10000):
        self.router_name = router_name
        self.max_queue_size = max_queue_size
        
        # Routing tables
        self._routes: Dict[str, List[RouteEntry]] = {}  # destination -> routes
        self._type_routes: Dict[MessageType, List[RouteEntry]] = {}  # type -> routes
        self._wildcard_routes: List[RouteEntry] = []  # catch-all routes
        
        # Message queues
        self._message_queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_queue_size)
        self._reply_queues: Dict[str, asyncio.Queue] = {}
        
        # Processing state
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None
        
        # Round-robin state
        self._round_robin_counters: Dict[str, int] = {}
        
        # Statistics
        self._messages_routed = 0
        self._messages_dropped = 0
        self._routing_errors = 0
        
        # Handler references
        self._handler_refs: Set[weakref.ReferenceType] = set()
    
    async def start(self) -> None:
        """Start the message router."""
        if self._running:
            logger.warning("Message router already running", router=self.router_name)
            return
        
        self._running = True
        self._processor_task = asyncio.create_task(self._process_messages())
        logger.info("Message router started", router=self.router_name)
    
    async def stop(self) -> None:
        """Stop the message router."""
        if not self._running:
            return
        
        self._running = False
        
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        
        # Clear queues
        while not self._message_queue.empty():
            try:
                self._message_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        logger.info("Message router stopped", router=self.router_name)
    
    def register_handler(self, destination: str, handler: MessageHandler,
                        message_types: Optional[Set[MessageType]] = None,
                        strategy: RoutingStrategy = RoutingStrategy.ROUND_ROBIN,
                        priority: int = 0,
                        filter_func: Optional[Callable[[Message], bool]] = None) -> None:
        """
        Register a message handler for a destination.
        
        Args:
            destination: Destination identifier
            handler: Message handler instance
            message_types: Set of message types to handle (None for all supported)
            strategy: Routing strategy to use
            priority: Handler priority (higher = preferred)
            filter_func: Optional message filter function
        """
        if message_types is None:
            message_types = handler.get_supported_message_types()
        
        route_entry = RouteEntry(
            destination=destination,
            handler=handler,
            message_types=message_types,
            strategy=strategy,
            priority=priority,
            filter_func=filter_func
        )
        
        # Add to destination routes
        if destination not in self._routes:
            self._routes[destination] = []
        self._routes[destination].append(route_entry)
        
        # Sort by priority (higher first)
        self._routes[destination].sort(key=lambda r: r.priority, reverse=True)
        
        # Add to type-based routes
        for msg_type in message_types:
            if msg_type not in self._type_routes:
                self._type_routes[msg_type] = []
            self._type_routes[msg_type].append(route_entry)
        
        # Keep weak reference
        self._handler_refs.add(weakref.ref(handler))
        
        logger.info(
            "Handler registered",
            router=self.router_name,
            destination=destination,
            message_types=[t.value for t in message_types],
            strategy=strategy.value
        )
    
    def unregister_handler(self, destination: str, handler: MessageHandler) -> None:
        """
        Unregister a message handler.
        
        Args:
            destination: Destination identifier
            handler: Handler to unregister
        """
        # Remove from destination routes
        if destination in self._routes:
            self._routes[destination] = [
                r for r in self._routes[destination] if r.handler is not handler
            ]
            if not self._routes[destination]:
                del self._routes[destination]
        
        # Remove from type routes
        for msg_type in list(self._type_routes.keys()):
            self._type_routes[msg_type] = [
                r for r in self._type_routes[msg_type] if r.handler is not handler
            ]
            if not self._type_routes[msg_type]:
                del self._type_routes[msg_type]
        
        logger.info("Handler unregistered", destination=destination)
    
    async def send_message(self, message: Message) -> bool:
        """
        Send a message through the router.
        
        Args:
            message: Message to send
            
        Returns:
            True if message was queued, False if dropped
        """
        if not self._running:
            logger.warning("Cannot send message: router not running")
            return False
        
        if message.is_expired():
            logger.debug("Message expired, not sending", message_id=message.message_id)
            self._messages_dropped += 1
            return False
        
        try:
            # Use negative priority for priority queue (higher priority = lower number)
            priority_value = -message.priority
            await self._message_queue.put((priority_value, time.time(), message))
            return True
        except asyncio.QueueFull:
            logger.warning("Message queue full, dropping message", message_id=message.message_id)
            self._messages_dropped += 1
            return False
    
    def send_message_sync(self, message: Message) -> bool:
        """
        Synchronously send a message (non-blocking).
        
        Args:
            message: Message to send
            
        Returns:
            True if message was queued, False if dropped
        """
        if not self._running or message.is_expired():
            self._messages_dropped += 1
            return False
        
        try:
            priority_value = -message.priority
            self._message_queue.put_nowait((priority_value, time.time(), message))
            return True
        except asyncio.QueueFull:
            self._messages_dropped += 1
            return False
    
    async def send_request(self, message: Message, timeout: float = 5.0) -> Optional[Message]:
        """
        Send a request message and wait for reply.
        
        Args:
            message: Request message
            timeout: Maximum time to wait for reply
            
        Returns:
            Reply message or None if timeout
        """
        if not message.reply_to:
            message.reply_to = f"reply_{message.message_id}"
        
        # Create reply queue
        reply_queue = asyncio.Queue(maxsize=1)
        self._reply_queues[message.reply_to] = reply_queue
        
        try:
            # Send message
            if not await self.send_message(message):
                return None
            
            # Wait for reply
            reply = await asyncio.wait_for(reply_queue.get(), timeout=timeout)
            return reply
            
        except asyncio.TimeoutError:
            logger.warning("Request timeout", message_id=message.message_id)
            return None
        finally:
            # Clean up reply queue
            if message.reply_to in self._reply_queues:
                del self._reply_queues[message.reply_to]
    
    async def _process_messages(self) -> None:
        """Main message processing loop."""
        logger.info("Message processing started", router=self.router_name)
        
        while self._running:
            try:
                # Get message with timeout
                priority, timestamp, message = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=0.1
                )
                
                # Check if message expired while in queue
                if message.is_expired():
                    logger.debug("Message expired in queue", message_id=message.message_id)
                    self._messages_dropped += 1
                    continue
                
                # Route message
                await self._route_message(message)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Error in message processing loop", error=str(e))
                await asyncio.sleep(0.001)
    
    async def _route_message(self, message: Message) -> None:
        """
        Route a message to appropriate handlers.
        
        Args:
            message: Message to route
        """
        start_time = time.time()
        routed_count = 0
        
        try:
            # Find routes for this message
            routes = self._find_routes(message)
            
            if not routes:
                logger.debug("No routes found for message", 
                           message_id=message.message_id,
                           destination=message.destination,
                           message_type=message.message_type.value)
                return
            
            # Apply routing strategy
            selected_routes = self._apply_routing_strategy(message, routes)
            
            # Process selected routes
            for route in selected_routes:
                try:
                    # Apply filter if present
                    if route.filter_func and not route.filter_func(message):
                        continue
                    
                    # Handle message
                    response = await route.handler.handle_message(message)
                    routed_count += 1
                    
                    # Update route statistics
                    route.messages_routed += 1
                    route.last_message_time = time.time()
                    
                    # Handle response
                    if response and message.reply_to:
                        await self._handle_reply(message.reply_to, response)
                    
                except Exception as e:
                    logger.error(
                        "Error handling message",
                        message_id=message.message_id,
                        handler=type(route.handler).__name__,
                        error=str(e)
                    )
                    self._routing_errors += 1
            
            # Update statistics
            processing_time = time.time() - start_time
            self._messages_routed += 1
            
            logger.debug(
                "Message routed",
                message_id=message.message_id,
                routes_used=routed_count,
                processing_time_ms=processing_time * 1000
            )
            
        except Exception as e:
            logger.error("Error routing message", message_id=message.message_id, error=str(e))
            self._routing_errors += 1
    
    def _find_routes(self, message: Message) -> List[RouteEntry]:
        """Find all possible routes for a message."""
        routes = []
        
        # Direct destination routes
        if message.destination and message.destination in self._routes:
            routes.extend(self._routes[message.destination])
        
        # Type-based routes
        if message.message_type in self._type_routes:
            routes.extend(self._type_routes[message.message_type])
        
        # Wildcard routes
        routes.extend(self._wildcard_routes)
        
        # Filter by message type support
        filtered_routes = []
        for route in routes:
            if message.message_type in route.message_types:
                filtered_routes.append(route)
        
        return filtered_routes
    
    def _apply_routing_strategy(self, message: Message, routes: List[RouteEntry]) -> List[RouteEntry]:
        """Apply routing strategy to select routes."""
        if not routes:
            return []
        
        # Group routes by strategy
        strategy_groups = {}
        for route in routes:
            strategy = route.strategy
            if strategy not in strategy_groups:
                strategy_groups[strategy] = []
            strategy_groups[strategy].append(route)
        
        selected_routes = []
        
        for strategy, route_group in strategy_groups.items():
            if strategy == RoutingStrategy.BROADCAST:
                selected_routes.extend(route_group)
            
            elif strategy == RoutingStrategy.ROUND_ROBIN:
                selected_routes.append(self._round_robin_select(route_group))
            
            elif strategy == RoutingStrategy.LOAD_BALANCED:
                selected_routes.append(self._load_balanced_select(route_group))
            
            elif strategy == RoutingStrategy.HASH_BASED:
                selected_routes.append(self._hash_based_select(message, route_group))
            
            elif strategy == RoutingStrategy.PRIORITY_BASED:
                # Already sorted by priority, take the first one
                selected_routes.append(route_group[0])
        
        return selected_routes
    
    def _round_robin_select(self, routes: List[RouteEntry]) -> RouteEntry:
        """Select route using round-robin strategy."""
        if not routes:
            return routes[0]
        
        # Use destination as key for round-robin counter
        key = routes[0].destination
        if key not in self._round_robin_counters:
            self._round_robin_counters[key] = 0
        
        selected_route = routes[self._round_robin_counters[key] % len(routes)]
        self._round_robin_counters[key] += 1
        
        return selected_route
    
    def _load_balanced_select(self, routes: List[RouteEntry]) -> RouteEntry:
        """Select route using load balancing."""
        if not routes:
            return routes[0]
        
        # Select route with lowest load factor
        return min(routes, key=lambda r: r.load_factor * r.messages_routed)
    
    def _hash_based_select(self, message: Message, routes: List[RouteEntry]) -> RouteEntry:
        """Select route using hash-based strategy."""
        if not routes:
            return routes[0]
        
        # Hash message ID to select route
        hash_value = int(hashlib.md5(message.message_id.encode()).hexdigest(), 16)
        return routes[hash_value % len(routes)]
    
    async def _handle_reply(self, reply_to: str, response: Message) -> None:
        """Handle reply message."""
        if reply_to in self._reply_queues:
            try:
                self._reply_queues[reply_to].put_nowait(response)
            except asyncio.QueueFull:
                logger.warning("Reply queue full", reply_to=reply_to)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get router metrics."""
        route_stats = {}
        for destination, routes in self._routes.items():
            route_stats[destination] = [
                {
                    'handler': type(r.handler).__name__,
                    'messages_routed': r.messages_routed,
                    'strategy': r.strategy.value,
                    'priority': r.priority
                }
                for r in routes
            ]
        
        return {
            'router_name': self.router_name,
            'messages_routed': self._messages_routed,
            'messages_dropped': self._messages_dropped,
            'routing_errors': self._routing_errors,
            'queue_size': self._message_queue.qsize(),
            'active_destinations': len(self._routes),
            'route_statistics': route_stats,
            'is_running': self._running
        }


# Utility functions for creating common message types
def create_control_message(source: str, destination: str, 
                          command: str, params: Dict[str, Any]) -> Message:
    """Create a control message."""
    return Message(
        message_id=f"ctrl_{int(time.time() * 1000000)}",
        message_type=MessageType.CONTROL,
        source=source,
        destination=destination,
        payload={'command': command, 'params': params}
    )


def create_audio_data_message(source: str, frame_data: Dict[str, Any]) -> Message:
    """Create an audio data message."""
    return Message(
        message_id=f"audio_{int(time.time() * 1000000)}",
        message_type=MessageType.AUDIO_DATA,
        source=source,
        payload=frame_data,
        priority=10  # High priority for audio data
    )


def create_metrics_message(source: str, metrics_data: Dict[str, Any]) -> Message:
    """Create a metrics message."""
    return Message(
        message_id=f"metrics_{int(time.time() * 1000000)}",
        message_type=MessageType.METRICS,
        source=source,
        payload=metrics_data,
        priority=1  # Low priority for metrics
    )