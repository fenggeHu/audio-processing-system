"""
Tests for the communication framework components.
"""

import pytest
import asyncio
import time
import numpy as np
from datetime import datetime
from typing import Set, Optional

from audio_processing.models import AudioConfig, AudioFrame
from audio_processing.communication import (
    EventBus, Event, EventHandler, EventPriority,
    AudioPipeline, PipelineNode, BackpressureController, BackpressureStrategy,
    MessageRouter, Message, MessageHandler, MessageType, RoutingStrategy,
    SharedMemoryManager, AudioFrameBuffer
)


class TestEventHandler(EventHandler):
    """Test event handler for testing."""
    
    def __init__(self, handler_name: str, supported_events: Set[str]):
        self.handler_name = handler_name
        self.supported_events = supported_events
        self.received_events = []
        self.processing_delay = 0.0
    
    async def handle_event(self, event: Event) -> None:
        """Handle an event."""
        if self.processing_delay > 0:
            await asyncio.sleep(self.processing_delay)
        self.received_events.append(event)
    
    def get_supported_events(self) -> Set[str]:
        """Get supported event types."""
        return self.supported_events


class TestEventBus:
    """Test event bus functionality."""
    
    async def test_event_bus_lifecycle(self):
        """Test event bus start/stop lifecycle."""
        event_bus = EventBus()
        
        assert not event_bus._running
        
        await event_bus.start()
        assert event_bus._running
        
        await event_bus.stop()
        assert not event_bus._running
    
    async def test_event_subscription_and_publishing(self):
        """Test event subscription and publishing."""
        event_bus = EventBus()
        handler = TestEventHandler("test_handler", {"test.event"})
        
        # Subscribe handler
        event_bus.subscribe(handler)
        
        await event_bus.start()
        
        try:
            # Publish event
            event = Event(
                event_type="test.event",
                source="test_source",
                data={"message": "hello"}
            )
            
            success = await event_bus.publish(event)
            assert success
            
            # Wait for processing
            await event_bus.wait_for_processing(timeout=1.0)
            
            # Check handler received event
            assert len(handler.received_events) == 1
            assert handler.received_events[0].event_type == "test.event"
            assert handler.received_events[0].data["message"] == "hello"
        
        finally:
            await event_bus.stop()
    
    async def test_event_priority_handling(self):
        """Test event priority processing."""
        event_bus = EventBus()
        handler = TestEventHandler("test_handler", {"test.high", "test.low"})
        
        event_bus.subscribe(handler)
        await event_bus.start()
        
        try:
            # Publish low priority event first
            low_event = Event(
                event_type="test.low",
                source="test",
                priority=EventPriority.LOW
            )
            
            # Publish high priority event second
            high_event = Event(
                event_type="test.high",
                source="test",
                priority=EventPriority.HIGH
            )
            
            await event_bus.publish(low_event)
            await event_bus.publish(high_event)
            
            await event_bus.wait_for_processing(timeout=1.0)
            
            # High priority event should be processed first
            assert len(handler.received_events) == 2
            assert handler.received_events[0].event_type == "test.high"
            assert handler.received_events[1].event_type == "test.low"
        
        finally:
            await event_bus.stop()
    
    async def test_event_filtering(self):
        """Test event filtering functionality."""
        event_bus = EventBus()
        handler = TestEventHandler("test_handler", {"test.event"})
        
        # Subscribe with filter
        def filter_func(event: Event) -> bool:
            return event.data.get("allowed", False)
        
        event_bus.subscribe(handler, filter_func=filter_func)
        await event_bus.start()
        
        try:
            # Publish filtered event
            filtered_event = Event(
                event_type="test.event",
                source="test",
                data={"allowed": False}
            )
            
            # Publish allowed event
            allowed_event = Event(
                event_type="test.event",
                source="test",
                data={"allowed": True}
            )
            
            await event_bus.publish(filtered_event)
            await event_bus.publish(allowed_event)
            
            await event_bus.wait_for_processing(timeout=1.0)
            
            # Only allowed event should be received
            assert len(handler.received_events) == 1
            assert handler.received_events[0].data["allowed"] is True
        
        finally:
            await event_bus.stop()
    
    async def test_event_metrics(self):
        """Test event bus metrics collection."""
        event_bus = EventBus()
        handler = TestEventHandler("test_handler", {"test.event"})
        
        event_bus.subscribe(handler)
        await event_bus.start()
        
        try:
            # Publish some events
            for i in range(5):
                event = Event(
                    event_type="test.event",
                    source="test",
                    data={"index": i}
                )
                await event_bus.publish(event)
            
            await event_bus.wait_for_processing(timeout=1.0)
            
            # Check metrics
            metrics = event_bus.get_metrics()
            assert metrics["events_published"] == 5
            assert metrics["events_processed"] == 5
            assert metrics["events_dropped"] == 0
            assert metrics["is_running"] is True
        
        finally:
            await event_bus.stop()


class TestPipelineNode(PipelineNode):
    """Test pipeline node implementation."""
    
    def __init__(self, node_name: str, processing_delay: float = 0.0):
        super().__init__(node_name)
        self.processing_delay = processing_delay
        self.processed_frames = []
    
    async def process_frame(self, frame: AudioFrame) -> Optional[AudioFrame]:
        """Process frame with optional delay."""
        if self.processing_delay > 0:
            await asyncio.sleep(self.processing_delay)
        
        self.processed_frames.append(frame)
        
        # Add processing metadata
        frame.metadata = frame.metadata or {}
        frame.metadata[f"processed_by_{self.node_name}"] = True
        
        return frame


class TestAudioPipeline:
    """Test audio pipeline functionality."""
    
    async def test_pipeline_node_lifecycle(self):
        """Test pipeline node start/stop lifecycle."""
        node = TestPipelineNode("test_node")
        
        assert node.state.name == "STOPPED"
        
        await node.start()
        assert node.state.name == "RUNNING"
        
        await node.stop()
        assert node.state.name == "STOPPED"
    
    async def test_single_node_processing(self):
        """Test single node frame processing."""
        node = TestPipelineNode("test_node")
        await node.start()
        
        try:
            # Create test frame
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=2,
                frame_size=480,
                data=np.random.randn(2, 480).astype(np.float32)
            )
            
            # Process frame
            success = await node.put_frame(frame)
            assert success
            
            # Wait for processing
            await asyncio.sleep(0.1)
            
            # Check frame was processed
            assert len(node.processed_frames) == 1
            assert node.processed_frames[0].sample_rate == 48000
        
        finally:
            await node.stop()
    
    async def test_backpressure_control(self):
        """Test backpressure control mechanism."""
        controller = BackpressureController(
            strategy=BackpressureStrategy.DROP_OLDEST,
            high_watermark=0.8
        )
        
        # Test normal conditions
        should_drop = controller.should_drop_frame(50, 100)  # 50% full
        assert not should_drop
        
        # Test high watermark
        should_drop = controller.should_drop_frame(85, 100)  # 85% full
        assert should_drop
        
        # Test adaptive strategy
        adaptive_controller = BackpressureController(
            strategy=BackpressureStrategy.ADAPTIVE,
            max_latency_ms=20.0
        )
        
        # High processing time should trigger drops at lower queue levels
        should_drop = adaptive_controller.should_drop_frame(60, 100, processing_time_ms=25.0)
        assert should_drop
    
    async def test_pipeline_with_multiple_nodes(self):
        """Test pipeline with connected nodes."""
        pipeline = AudioPipeline("test_pipeline")
        
        # Create nodes
        node1 = TestPipelineNode("node1")
        node2 = TestPipelineNode("node2")
        
        # Add nodes to pipeline
        pipeline.add_node(node1)
        pipeline.add_node(node2)
        
        # Connect nodes
        pipeline.connect_nodes("node1", "node2")
        
        await pipeline.start()
        
        try:
            # Create test frame
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=2,
                frame_size=480,
                data=np.random.randn(2, 480).astype(np.float32)
            )
            
            # Process frame through pipeline
            success = await pipeline.process_frame(frame)
            assert success
            
            # Wait for processing
            await asyncio.sleep(0.2)
            
            # Check both nodes processed the frame
            assert len(node1.processed_frames) == 1
            assert len(node2.processed_frames) == 1
            
            # Check metadata was added by both nodes
            final_frame = node2.processed_frames[0]
            assert final_frame.metadata["processed_by_node1"] is True
            assert final_frame.metadata["processed_by_node2"] is True
        
        finally:
            await pipeline.stop()


class TestMessageHandler(MessageHandler):
    """Test message handler implementation."""
    
    def __init__(self, handler_id: str, supported_types: Set[MessageType]):
        self.handler_id = handler_id
        self.supported_types = supported_types
        self.received_messages = []
        self.response_data = None
    
    async def handle_message(self, message: Message) -> Optional[Message]:
        """Handle a message."""
        self.received_messages.append(message)
        
        if self.response_data and message.reply_to:
            return Message(
                message_id=f"reply_{message.message_id}",
                message_type=MessageType.CONTROL,
                source=self.handler_id,
                destination=message.source,
                payload=self.response_data
            )
        
        return None
    
    def get_supported_message_types(self) -> Set[MessageType]:
        """Get supported message types."""
        return self.supported_types


class TestMessageRouter:
    """Test message router functionality."""
    
    async def test_message_router_lifecycle(self):
        """Test message router start/stop lifecycle."""
        router = MessageRouter("test_router")
        
        assert not router._running
        
        await router.start()
        assert router._running
        
        await router.stop()
        assert not router._running
    
    async def test_message_routing(self):
        """Test basic message routing."""
        router = MessageRouter("test_router")
        handler = TestMessageHandler("test_handler", {MessageType.CONTROL})
        
        # Register handler
        router.register_handler("test_destination", handler)
        
        await router.start()
        
        try:
            # Send message
            message = Message(
                message_id="test_msg_1",
                message_type=MessageType.CONTROL,
                source="test_source",
                destination="test_destination",
                payload={"command": "test"}
            )
            
            success = await router.send_message(message)
            assert success
            
            # Wait for processing
            await asyncio.sleep(0.1)
            
            # Check handler received message
            assert len(handler.received_messages) == 1
            assert handler.received_messages[0].message_id == "test_msg_1"
        
        finally:
            await router.stop()
    
    async def test_request_response_pattern(self):
        """Test request-response messaging pattern."""
        router = MessageRouter("test_router")
        handler = TestMessageHandler("test_handler", {MessageType.CONTROL})
        handler.response_data = {"status": "success"}
        
        router.register_handler("test_service", handler)
        await router.start()
        
        try:
            # Send request
            request = Message(
                message_id="request_1",
                message_type=MessageType.CONTROL,
                source="client",
                destination="test_service",
                payload={"command": "get_status"}
            )
            
            response = await router.send_request(request, timeout=1.0)
            
            assert response is not None
            assert response.payload["status"] == "success"
        
        finally:
            await router.stop()
    
    async def test_routing_strategies(self):
        """Test different routing strategies."""
        router = MessageRouter("test_router")
        
        # Create multiple handlers for same destination
        handler1 = TestMessageHandler("handler1", {MessageType.CONTROL})
        handler2 = TestMessageHandler("handler2", {MessageType.CONTROL})
        
        # Register with round-robin strategy
        router.register_handler("service", handler1, strategy=RoutingStrategy.ROUND_ROBIN)
        router.register_handler("service", handler2, strategy=RoutingStrategy.ROUND_ROBIN)
        
        await router.start()
        
        try:
            # Send multiple messages
            for i in range(4):
                message = Message(
                    message_id=f"msg_{i}",
                    message_type=MessageType.CONTROL,
                    source="client",
                    destination="service",
                    payload={"index": i}
                )
                await router.send_message(message)
            
            await asyncio.sleep(0.2)
            
            # Check round-robin distribution
            total_messages = len(handler1.received_messages) + len(handler2.received_messages)
            assert total_messages == 4
            
            # Both handlers should have received messages
            assert len(handler1.received_messages) > 0
            assert len(handler2.received_messages) > 0
        
        finally:
            await router.stop()


class TestSharedMemory:
    """Test shared memory functionality."""
    
    def test_buffer_header_serialization(self):
        """Test buffer header pack/unpack."""
        from audio_processing.communication.shared_memory import BufferHeader
        
        # Create header
        header = BufferHeader(
            state=1,
            timestamp_ns=1234567890,
            sample_rate=48000,
            channels=8,
            frame_size=480,
            data_size=15360,
            sequence_number=42,
            producer_id=12345,
            consumer_count=2,
            checksum=0xABCDEF
        )
        
        # Pack and unpack
        packed = header.pack()
        unpacked = BufferHeader.unpack(packed)
        
        # Verify all fields
        assert unpacked.state == header.state
        assert unpacked.timestamp_ns == header.timestamp_ns
        assert unpacked.sample_rate == header.sample_rate
        assert unpacked.channels == header.channels
        assert unpacked.frame_size == header.frame_size
        assert unpacked.data_size == header.data_size
        assert unpacked.sequence_number == header.sequence_number
        assert unpacked.producer_id == header.producer_id
        assert unpacked.consumer_count == header.consumer_count
        assert unpacked.checksum == header.checksum
    
    def test_audio_frame_buffer_creation(self):
        """Test audio frame buffer creation."""
        buffer = AudioFrameBuffer("test_buffer", max_frame_size=1024, max_channels=8)
        
        success = buffer.create()
        assert success
        
        try:
            # Check buffer properties
            assert buffer.buffer_id == "test_buffer"
            assert buffer.max_frame_size == 1024
            assert buffer.max_channels == 8
            
            # Get statistics
            stats = buffer.get_statistics()
            assert stats["buffer_id"] == "test_buffer"
            assert stats["frames_written"] == 0
            assert stats["frames_read"] == 0
        
        finally:
            buffer.detach()
    
    def test_frame_write_read_cycle(self):
        """Test writing and reading frames from shared buffer."""
        buffer = AudioFrameBuffer("test_buffer", max_frame_size=480, max_channels=2)
        
        success = buffer.create()
        assert success
        
        try:
            # Create test frame
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=2,
                frame_size=480,
                data=np.random.randn(2, 480).astype(np.float32)
            )
            
            # Write frame
            write_success = buffer.write_frame(frame)
            assert write_success
            
            # Read frame back
            read_frame = buffer.read_frame(timeout_ms=100.0)
            assert read_frame is not None
            
            # Verify frame data
            assert read_frame.sample_rate == frame.sample_rate
            assert read_frame.channels == frame.channels
            assert read_frame.frame_size == frame.frame_size
            
            # Check audio data (should be very close due to float precision)
            np.testing.assert_array_almost_equal(read_frame.data, frame.data, decimal=6)
        
        finally:
            buffer.detach()
    
    def test_shared_memory_manager(self):
        """Test shared memory manager functionality."""
        manager = SharedMemoryManager("test_manager")
        
        # Create buffer
        success = manager.create_buffer("buffer1", max_frame_size=480, max_channels=2)
        assert success
        
        # Get buffer
        buffer = manager.get_buffer("buffer1")
        assert buffer is not None
        assert buffer.buffer_id == "buffer1"
        
        # Test frame operations
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=2,
            frame_size=480,
            data=np.random.randn(2, 480).astype(np.float32)
        )
        
        write_success = buffer.write_frame(frame)
        assert write_success
        
        read_frame = buffer.read_frame(timeout_ms=100.0)
        assert read_frame is not None
        
        # Get manager statistics
        stats = manager.get_manager_statistics()
        assert stats["manager_name"] == "test_manager"
        assert stats["buffer_count"] == 1
        assert stats["total_frames_written"] == 1
        assert stats["total_frames_read"] == 1
        
        # Cleanup
        manager.cleanup()


# Integration test
class TestCommunicationIntegration:
    """Integration tests for communication framework components."""
    
    async def test_event_bus_pipeline_integration(self):
        """Test integration between event bus and audio pipeline."""
        event_bus = EventBus()
        pipeline = AudioPipeline("integration_test")
        
        # Create event handler that monitors pipeline
        class PipelineMonitor(EventHandler):
            def __init__(self):
                self.pipeline_events = []
            
            async def handle_event(self, event: Event) -> None:
                self.pipeline_events.append(event)
            
            def get_supported_events(self) -> Set[str]:
                return {"pipeline.frame_processed", "pipeline.error"}
        
        monitor = PipelineMonitor()
        event_bus.subscribe(monitor)
        
        # Create pipeline node that publishes events
        class EventPublishingNode(PipelineNode):
            def __init__(self, node_name: str, event_bus: EventBus):
                super().__init__(node_name)
                self.event_bus = event_bus
            
            async def process_frame(self, frame: AudioFrame) -> Optional[AudioFrame]:
                # Publish event when frame is processed
                event = Event(
                    event_type="pipeline.frame_processed",
                    source=self.node_name,
                    data={"frame_id": id(frame)}
                )
                self.event_bus.publish_sync(event)
                return frame
        
        node = EventPublishingNode("event_node", event_bus)
        pipeline.add_node(node)
        
        # Start both systems
        await event_bus.start()
        await pipeline.start()
        
        try:
            # Process a frame
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=2,
                frame_size=480,
                data=np.random.randn(2, 480).astype(np.float32)
            )
            
            await pipeline.process_frame(frame)
            
            # Wait for processing and event handling
            await asyncio.sleep(0.2)
            await event_bus.wait_for_processing(timeout=1.0)
            
            # Check that event was received
            assert len(monitor.pipeline_events) == 1
            assert monitor.pipeline_events[0].event_type == "pipeline.frame_processed"
            assert monitor.pipeline_events[0].source == "event_node"
        
        finally:
            await pipeline.stop()
            await event_bus.stop()