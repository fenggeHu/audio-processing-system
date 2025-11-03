"""
Base classes for audio processing components.

This module provides abstract base classes that implement common
functionality for audio services, configurable components, and
async services.
"""

import asyncio
import time
from abc import abstractmethod
from typing import Dict, Any, Optional, List
import structlog

from .interfaces import IAudioService, IMetricsCollector, IConfigurable
from .models import AudioFrame, ProcessingResult, AudioConfig, AudioMetrics
from .exceptions import ServiceError, ConfigError, ProcessingError

logger = structlog.get_logger(__name__)


class BaseConfigurable(IConfigurable):
    """
    Base class for configurable components.
    
    Provides common configuration management functionality
    including validation, change tracking, and hot updates.
    """
    
    def __init__(self, initial_config: Optional[Dict[str, Any]] = None):
        self._config: Dict[str, Any] = initial_config or {}
        self._config_version = 0
        self._config_history: List[Dict[str, Any]] = []
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate configuration dictionary.
        
        Base implementation performs basic type checking.
        Subclasses should override for specific validation.
        """
        try:
            schema = self.get_config_schema()
            # Basic validation - check required fields exist
            required_fields = schema.get('required', [])
            for field in required_fields:
                if field not in config:
                    logger.warning("Missing required config field", field=field)
                    return False
            return True
        except Exception as e:
            logger.error("Config validation failed", error=str(e))
            return False
    
    async def apply_config(self, config: Dict[str, Any]) -> None:
        """Apply new configuration with validation and history tracking."""
        if not self.validate_config(config):
            raise ConfigError("Configuration validation failed")
        
        # Store previous config in history
        self._config_history.append(self._config.copy())
        
        # Keep only last 10 configurations
        if len(self._config_history) > 10:
            self._config_history.pop(0)
        
        # Apply new configuration
        old_config = self._config.copy()
        self._config.update(config)
        self._config_version += 1
        
        logger.info(
            "Configuration updated",
            version=self._config_version,
            changes=self._get_config_changes(old_config, self._config)
        )
        
        # Notify subclasses of config change
        await self._on_config_changed(old_config, self._config)
    
    def get_config_schema(self) -> Dict[str, Any]:
        """
        Get configuration schema.
        
        Base implementation returns empty schema.
        Subclasses should override with specific schema.
        """
        return {
            "type": "object",
            "properties": {},
            "required": []
        }
    
    def get_current_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return self._config.copy()
    
    def get_config_version(self) -> int:
        """Get current configuration version."""
        return self._config_version
    
    async def rollback_config(self, steps: int = 1) -> None:
        """
        Rollback configuration to previous version.
        
        Args:
            steps: Number of versions to rollback
        """
        if not self._config_history:
            raise ConfigError("No configuration history available")
        
        # Get target configuration
        target_config = self._config_history[-min(steps, len(self._config_history))]
        
        # Apply target configuration
        await self.apply_config(target_config)
        
        logger.info("Configuration rolled back", steps=steps)
    
    async def _on_config_changed(self, old_config: Dict[str, Any], 
                               new_config: Dict[str, Any]) -> None:
        """
        Called when configuration changes.
        
        Subclasses can override to handle configuration changes.
        """
    
    def _get_config_changes(self, old_config: Dict[str, Any], 
                          new_config: Dict[str, Any]) -> Dict[str, Any]:
        """Get dictionary of configuration changes."""
        changes = {}
        
        # Find changed values
        for key, new_value in new_config.items():
            old_value = old_config.get(key)
            if old_value != new_value:
                changes[key] = {"old": old_value, "new": new_value}
        
        # Find removed values
        for key in old_config:
            if key not in new_config:
                changes[key] = {"old": old_config[key], "new": None}
        
        return changes


class BaseAsyncService(BaseConfigurable):
    """
    Base class for asynchronous services.
    
    Provides common async service functionality including
    lifecycle management, task coordination, and graceful shutdown.
    """
    
    def __init__(self, service_name: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._service_name = service_name
        self._is_running = False
        self._tasks: List[asyncio.Task] = []
        self._shutdown_event = asyncio.Event()
        self._startup_complete = asyncio.Event()
    
    @property
    def service_name(self) -> str:
        """Get service name."""
        return self._service_name
    
    @property
    def is_running(self) -> bool:
        """Check if service is running."""
        return self._is_running
    
    async def start(self) -> None:
        """Start the async service."""
        if self._is_running:
            logger.warning("Service already running", service=self._service_name)
            return
        
        logger.info("Starting service", service=self._service_name)
        
        try:
            # Initialize service
            await self._initialize()
            
            # Start background tasks
            await self._start_background_tasks()
            
            self._is_running = True
            self._startup_complete.set()
            
            logger.info("Service started successfully", service=self._service_name)
            
        except Exception as e:
            logger.error("Failed to start service", service=self._service_name, error=str(e))
            await self._cleanup()
            raise ServiceError(f"Failed to start {self._service_name}: {e}")
    
    async def stop(self) -> None:
        """Stop the async service."""
        if not self._is_running:
            logger.warning("Service not running", service=self._service_name)
            return
        
        logger.info("Stopping service", service=self._service_name)
        
        self._is_running = False
        self._shutdown_event.set()
        
        # Cancel all background tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        # Cleanup resources
        await self._cleanup()
        
        self._tasks.clear()
        self._startup_complete.clear()
        self._shutdown_event.clear()
        
        logger.info("Service stopped", service=self._service_name)
    
    async def wait_for_startup(self, timeout: Optional[float] = None) -> None:
        """
        Wait for service to complete startup.
        
        Args:
            timeout: Maximum time to wait in seconds
        """
        await asyncio.wait_for(self._startup_complete.wait(), timeout=timeout)
    
    def add_background_task(self, coro) -> asyncio.Task:
        """
        Add a background task to the service.
        
        Args:
            coro: Coroutine to run as background task
            
        Returns:
            Created task object
        """
        task = asyncio.create_task(coro)
        self._tasks.append(task)
        return task
    
    @abstractmethod
    async def _initialize(self) -> None:
        """Initialize service resources. Subclasses must implement."""
    
    @abstractmethod
    async def _cleanup(self) -> None:
        """Cleanup service resources. Subclasses must implement."""
    
    async def _start_background_tasks(self) -> None:
        """
        Start background tasks.
        
        Base implementation does nothing.
        Subclasses can override to start specific tasks.
        """


class BaseAudioProcessor(BaseAsyncService, IAudioService):
    """
    Base class for audio processing services.
    
    Provides common audio processing functionality including
    metrics collection, error handling, and performance monitoring.
    """
    
    def __init__(self, service_name: str, config: AudioConfig, 
                 metrics_collector: Optional[IMetricsCollector] = None):
        super().__init__(service_name, config.model_dump())
        self._audio_config = config
        self._metrics_collector = metrics_collector
        self._current_metrics = AudioMetrics()
        self._frames_processed = 0
        self._frames_dropped = 0
        self._total_processing_time = 0.0
    
    def get_config(self) -> AudioConfig:
        """Get current audio configuration."""
        return self._audio_config
    
    async def update_config(self, config: AudioConfig) -> None:
        """Update audio configuration."""
        old_config = self._audio_config
        self._audio_config = config
        await self.apply_config(config.model_dump())
        
        logger.info(
            "Audio config updated",
            service=self._service_name,
            old_sample_rate=old_config.sample_rate,
            new_sample_rate=config.sample_rate
        )
    
    async def process(self, frame: AudioFrame) -> ProcessingResult:
        """
        Process audio frame with error handling and metrics collection.
        
        This method wraps the actual processing logic with common
        functionality like timing, error handling, and metrics.
        """
        if not self._is_running:
            return ProcessingResult.error_result("Service not running")
        
        start_time = time.time()
        
        try:
            # Validate input frame
            self._validate_input_frame(frame)
            
            # Record input level
            if self._metrics_collector:
                input_level = frame.get_rms_level()
                self._metrics_collector.record_audio_level(
                    self._service_name, input_level, is_input=True
                )
            
            # Process the frame
            processed_frame = await self._process_frame(frame)
            
            # Calculate processing time
            processing_time = (time.time() - start_time) * 1000  # ms
            self._total_processing_time += processing_time
            
            # Record metrics
            if self._metrics_collector:
                self._metrics_collector.record_latency(self._service_name, processing_time)
                
                if processed_frame:
                    output_level = processed_frame.get_rms_level()
                    self._metrics_collector.record_audio_level(
                        self._service_name, output_level, is_input=False
                    )
            
            # Update internal metrics
            self._frames_processed += 1
            self._update_current_metrics(processing_time)
            
            return ProcessingResult.success_result(
                data=processed_frame,
                processing_time_ms=processing_time
            )
            
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            self._frames_dropped += 1
            
            if self._metrics_collector:
                self._metrics_collector.record_frame_drop(self._service_name)
            
            # Update internal metrics
            self._update_current_metrics(processing_time)
            
            logger.error(
                "Frame processing failed",
                service=self._service_name,
                error=str(e),
                processing_time_ms=processing_time
            )
            
            return ProcessingResult.error_result(
                error=f"Processing failed: {e}",
                processing_time_ms=processing_time
            )
    
    def get_metrics(self) -> AudioMetrics:
        """Get current service metrics."""
        return self._current_metrics
    
    @abstractmethod
    async def _process_frame(self, frame: AudioFrame) -> AudioFrame:
        """
        Process a single audio frame.
        
        Subclasses must implement the actual processing logic.
        
        Args:
            frame: Input audio frame
            
        Returns:
            Processed audio frame
        """
    
    def _validate_input_frame(self, frame: AudioFrame) -> None:
        """
        Validate input audio frame.
        
        Args:
            frame: Frame to validate
            
        Raises:
            ProcessingError: If frame is invalid
        """
        if frame.sample_rate != self._audio_config.sample_rate:
            raise ProcessingError(
                f"Sample rate mismatch: expected {self._audio_config.sample_rate}, "
                f"got {frame.sample_rate}"
            )
        
        if frame.frame_size != self._audio_config.frame_size:
            raise ProcessingError(
                f"Frame size mismatch: expected {self._audio_config.frame_size}, "
                f"got {frame.frame_size}"
            )
    
    def _update_current_metrics(self, processing_time_ms: float) -> None:
        """Update current metrics with latest processing data."""
        self._current_metrics.processing_latency_ms = processing_time_ms
        self._current_metrics.frames_processed = self._frames_processed
        self._current_metrics.frames_dropped = self._frames_dropped
        
        if self._frames_processed > 0:
            avg_processing_time = self._total_processing_time / self._frames_processed
            self._current_metrics.processing_latency_ms = avg_processing_time
    
    async def _on_config_changed(self, old_config: Dict[str, Any], 
                               new_config: Dict[str, Any]) -> None:
        """Handle audio configuration changes."""
        # Update audio config object
        self._audio_config = AudioConfig(**new_config)
        
        # Reset metrics on significant config changes
        if (old_config.get('sample_rate') != new_config.get('sample_rate') or
            old_config.get('frame_size') != new_config.get('frame_size')):
            self._reset_metrics()
    
    def _reset_metrics(self) -> None:
        """Reset processing metrics."""
        self._frames_processed = 0
        self._frames_dropped = 0
        self._total_processing_time = 0.0
        self._current_metrics = AudioMetrics()