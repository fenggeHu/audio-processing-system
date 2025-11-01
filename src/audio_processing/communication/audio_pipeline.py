"""
High-performance audio data pipeline with backpressure control.

This module implements asyncio.Queue-based audio data pipelines with
advanced flow control, buffering, and performance optimization.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, AsyncGenerator, Callable, Union
from enum import Enum
import structlog
import numpy as np

from ..models import AudioFrame, ProcessingResult

logger = structlog.get_logger(__name__)


class PipelineState(Enum):
    """Pipeline processing states."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    ERROR = "error"


class BackpressureStrategy(Enum):
    """Backpressure handling strategies."""
    DROP_OLDEST = "drop_oldest"  # Drop oldest frames when queue is full
    DROP_NEWEST = "drop_newest"  # Drop newest frames when queue is full
    BLOCK = "block"  # Block producer until space available
    ADAPTIVE = "adaptive"  # Dynamically adjust based on conditions


@dataclass
class PipelineMetrics:
    """Pipeline performance metrics."""
    frames_processed: int = 0
    frames_dropped: int = 0
    total_processing_time: float = 0.0
    avg_processing_time: float = 0.0
    max_processing_time: float = 0.0
    queue_size: int = 0
    max_queue_size: int = 0
    backpressure_events: int = 0
    throughput_fps: float = 0.0
    last_update: float = field(default_factory=time.time)


class BackpressureController:
    """
    Advanced backpressure control for audio pipelines.
    
    Monitors queue levels and processing performance to prevent
    buffer overruns and maintain system stability.
    """
    
    def __init__(self, strategy: BackpressureStrategy = BackpressureStrategy.ADAPTIVE,
                 high_watermark: float = 0.8, low_watermark: float = 0.3,
                 max_latency_ms: float = 50.0):
        self.strategy = strategy
        self.high_watermark = high_watermark
        self.low_watermark = low_watermark
        self.max_latency_ms = max_latency_ms
        
        # State tracking
        self._backpressure_active = False
        self._last_check_time = time.time()
        self._processing_times: List[float] = []
        self._drop_count = 0
        
        # Adaptive parameters
        self._target_queue_level = 0.5
        self._adaptation_rate = 0.1
    
    def should_drop_frame(self, queue_size: int, max_queue_size: int,
                         processing_time_ms: Optional[float] = None) -> bool:
        """
        Determine if a frame should be dropped based on backpressure conditions.
        
        Args:
            queue_size: Current queue size
            max_queue_size: Maximum queue capacity
            processing_time_ms: Recent processing time in milliseconds
            
        Returns:
            True if frame should be dropped
        """
        if max_queue_size == 0:
            return False
        
        queue_level = queue_size / max_queue_size
        current_time = time.time()
        
        # Update processing time history
        if processing_time_ms is not None:
            self._processing_times.append(processing_time_ms)
            if len(self._processing_times) > 100:
                self._processing_times.pop(0)
        
        # Check different strategies
        if self.strategy == BackpressureStrategy.DROP_OLDEST:
            return queue_level > self.high_watermark
        
        elif self.strategy == BackpressureStrategy.DROP_NEWEST:
            return queue_level > self.high_watermark
        
        elif self.strategy == BackpressureStrategy.BLOCK:
            return False  # Never drop, let producer block
        
        elif self.strategy == BackpressureStrategy.ADAPTIVE:
            return self._adaptive_drop_decision(queue_level, processing_time_ms)
        
        return False
    
    def _adaptive_drop_decision(self, queue_level: float, 
                               processing_time_ms: Optional[float]) -> bool:
        """Make adaptive drop decision based on system conditions."""
        # Check queue level
        if queue_level > self.high_watermark:
            return True
        
        # Check processing latency
        if processing_time_ms and processing_time_ms > self.max_latency_ms:
            return queue_level > self.low_watermark
        
        # Check average processing time trend
        if len(self._processing_times) >= 10:
            recent_avg = np.mean(self._processing_times[-10:])
            if recent_avg > self.max_latency_ms * 0.8:
                return queue_level > self._target_queue_level
        
        return False
    
    def update_backpressure_state(self, queue_size: int, max_queue_size: int) -> None:
        """Update backpressure state based on current conditions."""
        if max_queue_size == 0:
            return
        
        queue_level = queue_size / max_queue_size
        was_active = self._backpressure_active
        
        if queue_level > self.high_watermark:
            self._backpressure_active = True
        elif queue_level < self.low_watermark:
            self._backpressure_active = False
        
        # Log state changes
        if was_active != self._backpressure_active:
            logger.info(
                "Backpressure state changed",
                active=self._backpressure_active,
                queue_level=queue_level,
                strategy=self.strategy.value
            )
    
    def get_recommended_queue_size(self, current_size: int) -> int:
        """Get recommended queue size based on current conditions."""
        if self.strategy != BackpressureStrategy.ADAPTIVE:
            return current_size
        
        # Adaptive queue size adjustment
        if self._backpressure_active:
            return max(current_size // 2, 10)
        else:
            return min(current_size * 2, 1000)
    
    @property
    def is_backpressure_active(self) -> bool:
        """Check if backpressure is currently active."""
        return self._backpressure_active


class PipelineNode(ABC):
    """
    Abstract base class for pipeline processing nodes.
    
    Each node represents a stage in the audio processing pipeline
    that can transform, filter, or route audio frames.
    """
    
    def __init__(self, node_name: str, max_queue_size: int = 100):
        self.node_name = node_name
        self.max_queue_size = max_queue_size
        self._input_queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self._output_queues: List[asyncio.Queue] = []
        self._metrics = PipelineMetrics(max_queue_size=max_queue_size)
        self._state = PipelineState.STOPPED
        self._processor_task: Optional[asyncio.Task] = None
        self._backpressure_controller = BackpressureController()
    
    @abstractmethod
    async def process_frame(self, frame: AudioFrame) -> Optional[AudioFrame]:
        """
        Process a single audio frame.
        
        Args:
            frame: Input audio frame
            
        Returns:
            Processed audio frame or None to drop frame
        """
        pass
    
    async def start(self) -> None:
        """Start the pipeline node processing."""
        if self._state != PipelineState.STOPPED:
            logger.warning("Node already running", node=self.node_name)
            return
        
        self._state = PipelineState.STARTING
        self._processor_task = asyncio.create_task(self._process_loop())
        self._state = PipelineState.RUNNING
        
        logger.info("Pipeline node started", node=self.node_name)
    
    async def stop(self) -> None:
        """Stop the pipeline node processing."""
        if self._state == PipelineState.STOPPED:
            return
        
        self._state = PipelineState.STOPPING
        
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        
        # Clear queues
        while not self._input_queue.empty():
            try:
                self._input_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        self._state = PipelineState.STOPPED
        logger.info("Pipeline node stopped", node=self.node_name)
    
    async def pause(self) -> None:
        """Pause the pipeline node processing."""
        if self._state == PipelineState.RUNNING:
            self._state = PipelineState.PAUSED
            logger.info("Pipeline node paused", node=self.node_name)
    
    async def resume(self) -> None:
        """Resume the pipeline node processing."""
        if self._state == PipelineState.PAUSED:
            self._state = PipelineState.RUNNING
            logger.info("Pipeline node resumed", node=self.node_name)
    
    def connect_output(self, output_queue: asyncio.Queue) -> None:
        """Connect an output queue to this node."""
        self._output_queues.append(output_queue)
        logger.debug("Output queue connected", node=self.node_name)
    
    def disconnect_output(self, output_queue: asyncio.Queue) -> None:
        """Disconnect an output queue from this node."""
        if output_queue in self._output_queues:
            self._output_queues.remove(output_queue)
            logger.debug("Output queue disconnected", node=self.node_name)
    
    async def put_frame(self, frame: AudioFrame) -> bool:
        """
        Put a frame into the node's input queue.
        
        Args:
            frame: Audio frame to process
            
        Returns:
            True if frame was queued, False if dropped due to backpressure
        """
        if self._state != PipelineState.RUNNING:
            return False
        
        # Check backpressure
        queue_size = self._input_queue.qsize()
        if self._backpressure_controller.should_drop_frame(queue_size, self.max_queue_size):
            self._metrics.frames_dropped += 1
            self._metrics.backpressure_events += 1
            logger.debug("Frame dropped due to backpressure", node=self.node_name)
            return False
        
        try:
            self._input_queue.put_nowait(frame)
            return True
        except asyncio.QueueFull:
            self._metrics.frames_dropped += 1
            return False
    
    async def _process_loop(self) -> None:
        """Main processing loop for the node."""
        logger.info("Processing loop started", node=self.node_name)
        
        while self._state in [PipelineState.RUNNING, PipelineState.PAUSED]:
            try:
                if self._state == PipelineState.PAUSED:
                    await asyncio.sleep(0.01)
                    continue
                
                # Get frame with timeout
                frame = await asyncio.wait_for(
                    self._input_queue.get(),
                    timeout=0.1
                )
                
                # Process frame
                start_time = time.time()
                processed_frame = await self.process_frame(frame)
                processing_time = (time.time() - start_time) * 1000  # ms
                
                # Update metrics
                self._update_metrics(processing_time)
                
                # Send to output queues if frame was not dropped
                if processed_frame is not None:
                    await self._send_to_outputs(processed_frame)
                
                # Update backpressure state
                self._backpressure_controller.update_backpressure_state(
                    self._input_queue.qsize(), self.max_queue_size
                )
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Error in processing loop", node=self.node_name, error=str(e))
                self._state = PipelineState.ERROR
                break
        
        logger.info("Processing loop ended", node=self.node_name)
    
    async def _send_to_outputs(self, frame: AudioFrame) -> None:
        """Send processed frame to all output queues."""
        for output_queue in self._output_queues:
            try:
                output_queue.put_nowait(frame)
            except asyncio.QueueFull:
                logger.warning("Output queue full, dropping frame", node=self.node_name)
    
    def _update_metrics(self, processing_time_ms: float) -> None:
        """Update node processing metrics."""
        self._metrics.frames_processed += 1
        self._metrics.total_processing_time += processing_time_ms
        self._metrics.avg_processing_time = (
            self._metrics.total_processing_time / self._metrics.frames_processed
        )
        self._metrics.max_processing_time = max(
            self._metrics.max_processing_time, processing_time_ms
        )
        self._metrics.queue_size = self._input_queue.qsize()
        
        # Calculate throughput
        current_time = time.time()
        time_diff = current_time - self._metrics.last_update
        if time_diff >= 1.0:  # Update every second
            self._metrics.throughput_fps = self._metrics.frames_processed / time_diff
            self._metrics.last_update = current_time
    
    def get_metrics(self) -> PipelineMetrics:
        """Get current node metrics."""
        return self._metrics
    
    @property
    def state(self) -> PipelineState:
        """Get current node state."""
        return self._state


class AudioPipeline:
    """
    High-performance audio processing pipeline.
    
    Manages a chain of processing nodes with advanced flow control,
    monitoring, and optimization capabilities.
    """
    
    def __init__(self, pipeline_name: str, enable_monitoring: bool = True):
        self.pipeline_name = pipeline_name
        self.enable_monitoring = enable_monitoring
        
        self._nodes: List[PipelineNode] = []
        self._connections: Dict[str, List[str]] = {}
        self._input_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._output_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        
        self._state = PipelineState.STOPPED
        self._feeder_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None
        
        # Pipeline metrics
        self._total_frames_processed = 0
        self._total_frames_dropped = 0
        self._pipeline_start_time = 0.0
        
        # Backpressure control
        self._global_backpressure = BackpressureController(
            strategy=BackpressureStrategy.ADAPTIVE
        )
    
    def add_node(self, node: PipelineNode) -> None:
        """Add a processing node to the pipeline."""
        self._nodes.append(node)
        self._connections[node.node_name] = []
        logger.info("Node added to pipeline", 
                   pipeline=self.pipeline_name, 
                   node=node.node_name)
    
    def connect_nodes(self, source_node: str, target_node: str) -> None:
        """Connect two nodes in the pipeline."""
        source = self._get_node(source_node)
        target = self._get_node(target_node)
        
        if source and target:
            source.connect_output(target._input_queue)
            self._connections[source_node].append(target_node)
            logger.info("Nodes connected", 
                       source=source_node, 
                       target=target_node)
    
    def _get_node(self, node_name: str) -> Optional[PipelineNode]:
        """Get node by name."""
        for node in self._nodes:
            if node.node_name == node_name:
                return node
        return None
    
    async def start(self) -> None:
        """Start the entire pipeline."""
        if self._state != PipelineState.STOPPED:
            logger.warning("Pipeline already running", pipeline=self.pipeline_name)
            return
        
        self._state = PipelineState.STARTING
        self._pipeline_start_time = time.time()
        
        # Start all nodes
        for node in self._nodes:
            await node.start()
        
        # Start feeder task
        self._feeder_task = asyncio.create_task(self._feed_pipeline())
        
        # Start monitoring if enabled
        if self.enable_monitoring:
            self._monitor_task = asyncio.create_task(self._monitor_pipeline())
        
        self._state = PipelineState.RUNNING
        logger.info("Pipeline started", pipeline=self.pipeline_name)
    
    async def stop(self) -> None:
        """Stop the entire pipeline."""
        if self._state == PipelineState.STOPPED:
            return
        
        self._state = PipelineState.STOPPING
        
        # Cancel tasks
        if self._feeder_task:
            self._feeder_task.cancel()
        if self._monitor_task:
            self._monitor_task.cancel()
        
        # Stop all nodes
        for node in self._nodes:
            await node.stop()
        
        # Wait for tasks to complete
        for task in [self._feeder_task, self._monitor_task]:
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self._state = PipelineState.STOPPED
        logger.info("Pipeline stopped", pipeline=self.pipeline_name)
    
    async def process_frame(self, frame: AudioFrame) -> bool:
        """
        Process a frame through the pipeline.
        
        Args:
            frame: Audio frame to process
            
        Returns:
            True if frame was accepted, False if dropped
        """
        if self._state != PipelineState.RUNNING:
            return False
        
        try:
            self._input_queue.put_nowait(frame)
            return True
        except asyncio.QueueFull:
            self._total_frames_dropped += 1
            return False
    
    async def get_output_frame(self, timeout: Optional[float] = None) -> Optional[AudioFrame]:
        """
        Get a processed frame from the pipeline output.
        
        Args:
            timeout: Maximum time to wait for frame
            
        Returns:
            Processed audio frame or None if timeout
        """
        try:
            if timeout:
                return await asyncio.wait_for(self._output_queue.get(), timeout=timeout)
            else:
                return await self._output_queue.get()
        except asyncio.TimeoutError:
            return None
    
    async def _feed_pipeline(self) -> None:
        """Feed frames from input queue to first node."""
        if not self._nodes:
            logger.warning("No nodes in pipeline", pipeline=self.pipeline_name)
            return
        
        first_node = self._nodes[0]
        
        while self._state == PipelineState.RUNNING:
            try:
                frame = await asyncio.wait_for(self._input_queue.get(), timeout=0.1)
                
                success = await first_node.put_frame(frame)
                if success:
                    self._total_frames_processed += 1
                else:
                    self._total_frames_dropped += 1
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Error in pipeline feeder", error=str(e))
    
    async def _monitor_pipeline(self) -> None:
        """Monitor pipeline performance and health."""
        while self._state == PipelineState.RUNNING:
            try:
                # Collect metrics from all nodes
                total_queue_size = 0
                total_backpressure_events = 0
                
                for node in self._nodes:
                    metrics = node.get_metrics()
                    total_queue_size += metrics.queue_size
                    total_backpressure_events += metrics.backpressure_events
                
                # Log pipeline status
                if total_backpressure_events > 0:
                    logger.warning(
                        "Pipeline backpressure detected",
                        pipeline=self.pipeline_name,
                        total_queue_size=total_queue_size,
                        backpressure_events=total_backpressure_events
                    )
                
                await asyncio.sleep(5.0)  # Monitor every 5 seconds
                
            except Exception as e:
                logger.error("Error in pipeline monitoring", error=str(e))
                await asyncio.sleep(1.0)
    
    def get_pipeline_metrics(self) -> Dict[str, Any]:
        """Get comprehensive pipeline metrics."""
        runtime = time.time() - self._pipeline_start_time if self._pipeline_start_time else 0
        
        node_metrics = {}
        for node in self._nodes:
            node_metrics[node.node_name] = {
                'frames_processed': node.get_metrics().frames_processed,
                'frames_dropped': node.get_metrics().frames_dropped,
                'avg_processing_time_ms': node.get_metrics().avg_processing_time,
                'queue_size': node.get_metrics().queue_size,
                'state': node.state.value
            }
        
        return {
            'pipeline_name': self.pipeline_name,
            'state': self._state.value,
            'runtime_seconds': runtime,
            'total_frames_processed': self._total_frames_processed,
            'total_frames_dropped': self._total_frames_dropped,
            'input_queue_size': self._input_queue.qsize(),
            'output_queue_size': self._output_queue.qsize(),
            'node_count': len(self._nodes),
            'node_metrics': node_metrics
        }


# Concrete pipeline node implementations
class PassthroughNode(PipelineNode):
    """Simple passthrough node for testing."""
    
    async def process_frame(self, frame: AudioFrame) -> Optional[AudioFrame]:
        """Pass frame through unchanged."""
        return frame


class FrameBufferNode(PipelineNode):
    """Node that buffers frames for batch processing."""
    
    def __init__(self, node_name: str, buffer_size: int = 10, max_queue_size: int = 100):
        super().__init__(node_name, max_queue_size)
        self.buffer_size = buffer_size
        self._frame_buffer: List[AudioFrame] = []
    
    async def process_frame(self, frame: AudioFrame) -> Optional[AudioFrame]:
        """Buffer frames and process in batches."""
        self._frame_buffer.append(frame)
        
        if len(self._frame_buffer) >= self.buffer_size:
            # Process batch (for now, just return the latest frame)
            result_frame = self._frame_buffer[-1]
            self._frame_buffer.clear()
            return result_frame
        
        return None  # Don't output until buffer is full