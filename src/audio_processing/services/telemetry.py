"""
Telemetry and performance monitoring service.

This module implements the TelemetryService that provides real-time monitoring
of system performance, audio quality metrics, and structured logging capabilities
for the audio processing system.
"""

import asyncio
import time
import psutil
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable, Deque
from enum import Enum
import structlog
import json
import numpy as np

from ..interfaces import IAudioService, IMetricsCollector, IEventHandler
from ..base import BaseAsyncService
from ..models import AudioFrame, AudioConfig, AudioMetrics, ProcessingResult
from ..exceptions import ServiceError, ProcessingError


class LogLevel(Enum):
    """Logging levels for telemetry service."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class MetricType(Enum):
    """Types of metrics collected by telemetry service."""
    LATENCY = "latency"
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    AUDIO_LEVEL = "audio_level"
    FRAME_DROP = "frame_drop"
    QUALITY = "quality"
    CUSTOM = "custom"


@dataclass
class MetricPoint:
    """Single metric data point."""
    timestamp: datetime
    service_name: str
    metric_type: MetricType
    value: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QualityMetrics:
    """Audio quality metrics container."""
    erle_db: Optional[float] = None  # Echo Return Loss Enhancement
    pesq_score: Optional[float] = None  # Perceptual Evaluation of Speech Quality
    stoi_score: Optional[float] = None  # Short-Time Objective Intelligibility
    snr_db: Optional[float] = None  # Signal-to-Noise Ratio
    thd_percent: Optional[float] = None  # Total Harmonic Distortion
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'erle_db': self.erle_db,
            'pesq_score': self.pesq_score,
            'stoi_score': self.stoi_score,
            'snr_db': self.snr_db,
            'thd_percent': self.thd_percent
        }


@dataclass
class SystemMetrics:
    """System-wide performance metrics."""
    timestamp: datetime
    total_cpu_percent: float
    total_memory_mb: float
    available_memory_mb: float
    disk_usage_percent: float
    network_bytes_sent: int = 0
    network_bytes_recv: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'total_cpu_percent': self.total_cpu_percent,
            'total_memory_mb': self.total_memory_mb,
            'available_memory_mb': self.available_memory_mb,
            'disk_usage_percent': self.disk_usage_percent,
            'network_bytes_sent': self.network_bytes_sent,
            'network_bytes_recv': self.network_bytes_recv
        }


class MetricsCollector(IMetricsCollector):
    """
    Concrete implementation of metrics collector interface.
    
    Collects and aggregates performance metrics from all audio services.
    """
    
    def __init__(self, max_history_size: int = 1000):
        self.max_history_size = max_history_size
        self._metrics_history: Dict[str, Deque[MetricPoint]] = defaultdict(
            lambda: deque(maxlen=max_history_size)
        )
        self._service_metrics: Dict[str, AudioMetrics] = {}
        self._lock = threading.RLock()
        
        # Initialize logger
        self.logger = structlog.get_logger(__name__)
    
    def record_latency(self, service_name: str, latency_ms: float) -> None:
        """Record processing latency for a service."""
        with self._lock:
            metric = MetricPoint(
                timestamp=datetime.now(),
                service_name=service_name,
                metric_type=MetricType.LATENCY,
                value=latency_ms
            )
            self._metrics_history[f"{service_name}_latency"].append(metric)
            
            # Update service metrics
            if service_name not in self._service_metrics:
                self._service_metrics[service_name] = AudioMetrics()
            self._service_metrics[service_name].processing_latency_ms = latency_ms
    
    def record_cpu_usage(self, service_name: str, cpu_percent: float) -> None:
        """Record CPU usage for a service."""
        with self._lock:
            metric = MetricPoint(
                timestamp=datetime.now(),
                service_name=service_name,
                metric_type=MetricType.CPU_USAGE,
                value=cpu_percent
            )
            self._metrics_history[f"{service_name}_cpu"].append(metric)
            
            # Update service metrics
            if service_name not in self._service_metrics:
                self._service_metrics[service_name] = AudioMetrics()
            self._service_metrics[service_name].cpu_usage_percent = cpu_percent
    
    def record_memory_usage(self, service_name: str, memory_mb: float) -> None:
        """Record memory usage for a service."""
        with self._lock:
            metric = MetricPoint(
                timestamp=datetime.now(),
                service_name=service_name,
                metric_type=MetricType.MEMORY_USAGE,
                value=memory_mb
            )
            self._metrics_history[f"{service_name}_memory"].append(metric)
            
            # Update service metrics
            if service_name not in self._service_metrics:
                self._service_metrics[service_name] = AudioMetrics()
            self._service_metrics[service_name].memory_usage_mb = memory_mb
    
    def record_audio_level(self, service_name: str, level_dbfs: float, 
                          is_input: bool = True) -> None:
        """Record audio level measurement."""
        with self._lock:
            metric_key = f"{service_name}_{'input' if is_input else 'output'}_level"
            metric = MetricPoint(
                timestamp=datetime.now(),
                service_name=service_name,
                metric_type=MetricType.AUDIO_LEVEL,
                value=level_dbfs,
                metadata={'is_input': is_input}
            )
            self._metrics_history[metric_key].append(metric)
            
            # Update service metrics
            if service_name not in self._service_metrics:
                self._service_metrics[service_name] = AudioMetrics()
            
            if is_input:
                self._service_metrics[service_name].input_level_dbfs = level_dbfs
            else:
                self._service_metrics[service_name].output_level_dbfs = level_dbfs
    
    def record_frame_drop(self, service_name: str) -> None:
        """Record a dropped frame event."""
        with self._lock:
            metric = MetricPoint(
                timestamp=datetime.now(),
                service_name=service_name,
                metric_type=MetricType.FRAME_DROP,
                value=1.0
            )
            self._metrics_history[f"{service_name}_drops"].append(metric)
            
            # Update service metrics
            if service_name not in self._service_metrics:
                self._service_metrics[service_name] = AudioMetrics()
            self._service_metrics[service_name].frames_dropped += 1
    
    def record_quality_metric(self, service_name: str, quality_metrics: QualityMetrics) -> None:
        """Record audio quality metrics."""
        with self._lock:
            for metric_name, value in quality_metrics.to_dict().items():
                if value is not None:
                    metric = MetricPoint(
                        timestamp=datetime.now(),
                        service_name=service_name,
                        metric_type=MetricType.QUALITY,
                        value=value,
                        metadata={'quality_type': metric_name}
                    )
                    self._metrics_history[f"{service_name}_{metric_name}"].append(metric)
    
    def get_service_metrics(self, service_name: str) -> AudioMetrics:
        """Get aggregated metrics for a specific service."""
        with self._lock:
            return self._service_metrics.get(service_name, AudioMetrics())
    
    def get_system_metrics(self) -> Dict[str, AudioMetrics]:
        """Get metrics for all services in the system."""
        with self._lock:
            return self._service_metrics.copy()
    
    def reset_metrics(self, service_name: Optional[str] = None) -> None:
        """Reset metrics for a service or all services."""
        with self._lock:
            if service_name:
                # Reset specific service
                keys_to_remove = [k for k in self._metrics_history.keys() 
                                if k.startswith(service_name)]
                for key in keys_to_remove:
                    self._metrics_history[key].clear()
                
                if service_name in self._service_metrics:
                    self._service_metrics[service_name] = AudioMetrics()
            else:
                # Reset all metrics
                self._metrics_history.clear()
                self._service_metrics.clear()
    
    def get_metric_history(self, service_name: str, metric_type: str, 
                          duration_minutes: int = 10) -> List[MetricPoint]:
        """Get historical metrics for a service."""
        with self._lock:
            key = f"{service_name}_{metric_type}"
            if key not in self._metrics_history:
                return []
            
            cutoff_time = datetime.now() - timedelta(minutes=duration_minutes)
            return [m for m in self._metrics_history[key] if m.timestamp >= cutoff_time]


class TelemetryService(BaseAsyncService, IEventHandler):
    """
    Telemetry and performance monitoring service.
    
    Provides real-time monitoring of system performance, audio quality metrics,
    and structured logging capabilities for the audio processing system.
    """
    
    def __init__(self, service_name: str = "telemetry_service", 
                 config: Optional[Dict[str, Any]] = None):
        super().__init__(service_name, config)
        
        # Configuration
        self.monitoring_interval = self._config.get('monitoring_interval', 1.0)  # seconds
        self.log_level = LogLevel(self._config.get('log_level', 'info'))
        self.enable_system_monitoring = self._config.get('enable_system_monitoring', True)
        self.enable_quality_monitoring = self._config.get('enable_quality_monitoring', True)
        self.max_history_size = self._config.get('max_history_size', 1000)
        
        # Metrics collector
        self.metrics_collector = MetricsCollector(self.max_history_size)
        
        # System monitoring
        self.system_metrics_history: Deque[SystemMetrics] = deque(maxlen=self.max_history_size)
        self._process = psutil.Process()
        
        # Event handlers
        self._event_handlers: Dict[str, List[Callable]] = defaultdict(list)
        
        # Performance thresholds for alerts
        self.cpu_threshold = self._config.get('cpu_threshold', 80.0)
        self.memory_threshold_mb = self._config.get('memory_threshold_mb', 1024.0)
        self.latency_threshold_ms = self._config.get('latency_threshold_ms', 50.0)
        
        # Initialize structured logger
        self._setup_logging()
        
        self.logger.info("TelemetryService initialized", 
                        monitoring_interval=self.monitoring_interval,
                        log_level=self.log_level.value)
    
    def _setup_logging(self) -> None:
        """Setup structured logging configuration."""
        log_format = self._config.get('log_format', 'json')
        
        processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
        ]
        
        if log_format == 'json':
            processors.append(structlog.processors.JSONRenderer())
        else:
            processors.append(structlog.dev.ConsoleRenderer())
        
        structlog.configure(
            processors=processors,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        self.logger = structlog.get_logger(__name__)
    
    async def _initialize(self) -> None:
        """Initialize telemetry service resources."""
        self.logger.info("Initializing telemetry service")
        
        # Initialize system monitoring baseline
        if self.enable_system_monitoring:
            await self._collect_system_metrics()
    
    async def _cleanup(self) -> None:
        """Cleanup telemetry service resources."""
        self.logger.info("Cleaning up telemetry service")
        
        # Save final metrics if needed
        await self._save_metrics_snapshot()
    
    async def _start_background_tasks(self) -> None:
        """Start background monitoring tasks."""
        if self.enable_system_monitoring:
            self.add_background_task(self._system_monitoring_loop())
        
        if self.enable_quality_monitoring:
            self.add_background_task(self._quality_monitoring_loop())
        
        # Start alert monitoring
        self.add_background_task(self._alert_monitoring_loop())
    
    async def _system_monitoring_loop(self) -> None:
        """Background task for system performance monitoring."""
        self.logger.info("Starting system monitoring loop")
        
        while self._is_running:
            try:
                await self._collect_system_metrics()
                await asyncio.sleep(self.monitoring_interval)
            except Exception as e:
                self.logger.error("System monitoring error", error=str(e))
                await asyncio.sleep(self.monitoring_interval)
    
    async def _quality_monitoring_loop(self) -> None:
        """Background task for audio quality monitoring."""
        self.logger.info("Starting quality monitoring loop")
        
        while self._is_running:
            try:
                await self._collect_quality_metrics()
                await asyncio.sleep(self.monitoring_interval * 5)  # Less frequent
            except Exception as e:
                self.logger.error("Quality monitoring error", error=str(e))
                await asyncio.sleep(self.monitoring_interval * 5)
    
    async def _alert_monitoring_loop(self) -> None:
        """Background task for performance alert monitoring."""
        self.logger.info("Starting alert monitoring loop")
        
        while self._is_running:
            try:
                await self._check_performance_alerts()
                await asyncio.sleep(self.monitoring_interval * 2)
            except Exception as e:
                self.logger.error("Alert monitoring error", error=str(e))
                await asyncio.sleep(self.monitoring_interval * 2)
    
    async def _collect_system_metrics(self) -> None:
        """Collect system-wide performance metrics."""
        try:
            # CPU and memory usage
            cpu_percent = psutil.cpu_percent(interval=None)
            memory_info = psutil.virtual_memory()
            disk_info = psutil.disk_usage('/')
            
            # Network stats (optional)
            network_stats = psutil.net_io_counters()
            
            system_metrics = SystemMetrics(
                timestamp=datetime.now(),
                total_cpu_percent=cpu_percent,
                total_memory_mb=memory_info.used / (1024 * 1024),
                available_memory_mb=memory_info.available / (1024 * 1024),
                disk_usage_percent=disk_info.percent,
                network_bytes_sent=network_stats.bytes_sent if network_stats else 0,
                network_bytes_recv=network_stats.bytes_recv if network_stats else 0
            )
            
            self.system_metrics_history.append(system_metrics)
            
            # Log system metrics periodically
            if len(self.system_metrics_history) % 60 == 0:  # Every minute
                self.logger.info("System metrics", **system_metrics.to_dict())
                
        except Exception as e:
            self.logger.error("Failed to collect system metrics", error=str(e))
    
    async def _collect_quality_metrics(self) -> None:
        """Collect audio quality metrics from services."""
        # This would typically interface with audio services to get quality metrics
        # For now, we'll simulate some basic quality monitoring
        
        service_metrics = self.metrics_collector.get_system_metrics()
        
        for service_name, metrics in service_metrics.items():
            if metrics.frames_processed > 0:
                # Calculate derived quality metrics
                frame_drop_rate = metrics.get_frame_drop_rate()
                
                if frame_drop_rate > 5.0:  # More than 5% drop rate
                    self.logger.warning(
                        "High frame drop rate detected",
                        service=service_name,
                        drop_rate_percent=frame_drop_rate
                    )
    
    async def _check_performance_alerts(self) -> None:
        """Check for performance issues and generate alerts."""
        # Check system-wide metrics
        if self.system_metrics_history:
            latest_system = self.system_metrics_history[-1]
            
            if latest_system.total_cpu_percent > self.cpu_threshold:
                await self._trigger_alert(
                    "high_cpu_usage",
                    f"System CPU usage {latest_system.total_cpu_percent:.1f}% exceeds threshold {self.cpu_threshold}%",
                    {"cpu_percent": latest_system.total_cpu_percent}
                )
            
            if latest_system.total_memory_mb > self.memory_threshold_mb:
                await self._trigger_alert(
                    "high_memory_usage",
                    f"System memory usage {latest_system.total_memory_mb:.1f}MB exceeds threshold {self.memory_threshold_mb}MB",
                    {"memory_mb": latest_system.total_memory_mb}
                )
        
        # Check service-specific metrics
        service_metrics = self.metrics_collector.get_system_metrics()
        for service_name, metrics in service_metrics.items():
            if metrics.processing_latency_ms > self.latency_threshold_ms:
                await self._trigger_alert(
                    "high_latency",
                    f"Service {service_name} latency {metrics.processing_latency_ms:.1f}ms exceeds threshold {self.latency_threshold_ms}ms",
                    {"service": service_name, "latency_ms": metrics.processing_latency_ms}
                )
    
    async def _trigger_alert(self, alert_type: str, message: str, data: Dict[str, Any]) -> None:
        """Trigger a performance alert."""
        alert_data = {
            "alert_type": alert_type,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        
        self.logger.warning("Performance alert", **alert_data)
        
        # Trigger event handlers
        await self.handle_event("performance_alert", alert_data)
    
    async def _save_metrics_snapshot(self) -> None:
        """Save current metrics snapshot for persistence."""
        try:
            snapshot = {
                "timestamp": datetime.now().isoformat(),
                "system_metrics": [m.to_dict() for m in list(self.system_metrics_history)[-10:]],
                "service_metrics": {
                    name: {
                        "processing_latency_ms": metrics.processing_latency_ms,
                        "cpu_usage_percent": metrics.cpu_usage_percent,
                        "memory_usage_mb": metrics.memory_usage_mb,
                        "frames_processed": metrics.frames_processed,
                        "frames_dropped": metrics.frames_dropped
                    }
                    for name, metrics in self.metrics_collector.get_system_metrics().items()
                }
            }
            
            # In a real implementation, this would save to a file or database
            self.logger.info("Metrics snapshot saved", snapshot_size=len(str(snapshot)))
            
        except Exception as e:
            self.logger.error("Failed to save metrics snapshot", error=str(e))
    
    # Public API methods
    
    def get_metrics_collector(self) -> IMetricsCollector:
        """Get the metrics collector instance."""
        return self.metrics_collector
    
    def get_system_metrics(self, duration_minutes: int = 10) -> List[SystemMetrics]:
        """Get system metrics for the specified duration."""
        cutoff_time = datetime.now() - timedelta(minutes=duration_minutes)
        return [m for m in self.system_metrics_history if m.timestamp >= cutoff_time]
    
    def get_service_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary for all services."""
        service_metrics = self.metrics_collector.get_system_metrics()
        
        summary = {}
        for service_name, metrics in service_metrics.items():
            summary[service_name] = {
                "status": "healthy" if metrics.is_performance_acceptable(
                    AudioConfig()  # Use default config for thresholds
                ) else "degraded",
                "processing_latency_ms": metrics.processing_latency_ms,
                "cpu_usage_percent": metrics.cpu_usage_percent,
                "memory_usage_mb": metrics.memory_usage_mb,
                "frame_drop_rate_percent": metrics.get_frame_drop_rate(),
                "frames_processed": metrics.frames_processed
            }
        
        return summary
    
    def get_performance_dashboard_data(self) -> Dict[str, Any]:
        """Get data for performance visualization dashboard."""
        return {
            "timestamp": datetime.now().isoformat(),
            "system_overview": {
                "cpu_percent": self.system_metrics_history[-1].total_cpu_percent if self.system_metrics_history else 0,
                "memory_mb": self.system_metrics_history[-1].total_memory_mb if self.system_metrics_history else 0,
                "available_memory_mb": self.system_metrics_history[-1].available_memory_mb if self.system_metrics_history else 0
            },
            "services": self.get_service_performance_summary(),
            "alerts": self._get_recent_alerts()
        }
    
    def _get_recent_alerts(self, duration_minutes: int = 60) -> List[Dict[str, Any]]:
        """Get recent performance alerts."""
        # In a real implementation, this would query stored alerts
        # For now, return empty list as alerts are logged but not stored
        return []
    
    # Event handler interface implementation
    
    async def handle_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Handle system events."""
        self.logger.info("Handling event", event_type=event_type, data=event_data)
        
        # Call registered event handlers
        if event_type in self._event_handlers:
            for handler in self._event_handlers[event_type]:
                try:
                    await handler(event_data)
                except Exception as e:
                    self.logger.error("Event handler failed", 
                                    event_type=event_type, 
                                    error=str(e))
    
    def get_supported_events(self) -> List[str]:
        """Get list of supported event types."""
        return [
            "performance_alert",
            "service_started",
            "service_stopped",
            "service_error",
            "quality_degradation"
        ]
    
    def register_event_handler(self, event_type: str, handler: Callable) -> None:
        """Register an event handler for specific event type."""
        self._event_handlers[event_type].append(handler)
        self.logger.info("Event handler registered", event_type=event_type)
    
    def unregister_event_handler(self, event_type: str, handler: Callable) -> None:
        """Unregister an event handler."""
        if event_type in self._event_handlers:
            try:
                self._event_handlers[event_type].remove(handler)
                self.logger.info("Event handler unregistered", event_type=event_type)
            except ValueError:
                self.logger.warning("Event handler not found for unregistration", 
                                  event_type=event_type)
    
    def get_config_schema(self) -> Dict[str, Any]:
        """Get configuration schema for telemetry service."""
        return {
            "type": "object",
            "properties": {
                "monitoring_interval": {
                    "type": "number",
                    "minimum": 0.1,
                    "maximum": 60.0,
                    "default": 1.0,
                    "description": "Monitoring interval in seconds"
                },
                "log_level": {
                    "type": "string",
                    "enum": ["debug", "info", "warning", "error", "critical"],
                    "default": "info",
                    "description": "Logging level"
                },
                "log_format": {
                    "type": "string",
                    "enum": ["json", "console"],
                    "default": "json",
                    "description": "Log output format"
                },
                "enable_system_monitoring": {
                    "type": "boolean",
                    "default": True,
                    "description": "Enable system performance monitoring"
                },
                "enable_quality_monitoring": {
                    "type": "boolean",
                    "default": True,
                    "description": "Enable audio quality monitoring"
                },
                "max_history_size": {
                    "type": "integer",
                    "minimum": 100,
                    "maximum": 10000,
                    "default": 1000,
                    "description": "Maximum number of metric points to keep in history"
                },
                "cpu_threshold": {
                    "type": "number",
                    "minimum": 10.0,
                    "maximum": 100.0,
                    "default": 80.0,
                    "description": "CPU usage threshold for alerts (%)"
                },
                "memory_threshold_mb": {
                    "type": "number",
                    "minimum": 100.0,
                    "default": 1024.0,
                    "description": "Memory usage threshold for alerts (MB)"
                },
                "latency_threshold_ms": {
                    "type": "number",
                    "minimum": 1.0,
                    "maximum": 1000.0,
                    "default": 50.0,
                    "description": "Processing latency threshold for alerts (ms)"
                }
            },
            "required": []
        }