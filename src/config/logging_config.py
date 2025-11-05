"""
Lightweight Logging System

Optimized logging for embedded systems with local file logging,
performance logging, and debug logging capabilities.
"""

import os
import sys
import logging
import logging.handlers
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import structlog
import time
import threading
from contextlib import contextmanager


class LogLevel(Enum):
    """Logging levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogType(Enum):
    """Types of logs."""
    SYSTEM = "system"
    PERFORMANCE = "performance"
    AUDIO = "audio"
    DEBUG = "debug"
    ERROR = "error"


@dataclass
class LoggingConfig:
    """Configuration for the logging system."""
    
    # General settings
    log_level: LogLevel = LogLevel.INFO
    log_dir: Path = Path("logs")
    max_file_size_mb: int = 10
    backup_count: int = 5
    
    # Performance logging
    enable_performance_logging: bool = True
    performance_log_interval_sec: float = 1.0
    
    # Debug logging
    enable_debug_logging: bool = False
    debug_log_modules: list = None
    
    # Embedded optimizations
    enable_async_logging: bool = True
    log_buffer_size: int = 8192
    flush_interval_sec: float = 5.0
    
    # Console output
    enable_console_output: bool = True
    console_log_level: LogLevel = LogLevel.INFO
    
    def __post_init__(self):
        if self.debug_log_modules is None:
            self.debug_log_modules = []


class PerformanceLogger:
    """High-performance logger for audio processing metrics."""
    
    def __init__(self, config: LoggingConfig):
        self.config = config
        self.metrics_buffer = []
        self.buffer_lock = threading.Lock()
        self.last_flush = time.time()
        
        # Create performance log file
        self.perf_log_path = config.log_dir / "performance.log"
        self.perf_logger = self._create_performance_logger()
    
    def _create_performance_logger(self) -> logging.Logger:
        """Create dedicated performance logger."""
        logger = logging.getLogger("performance")
        logger.setLevel(logging.INFO)
        
        # Rotating file handler for performance logs
        handler = logging.handlers.RotatingFileHandler(
            self.perf_log_path,
            maxBytes=self.config.max_file_size_mb * 1024 * 1024,
            backupCount=self.config.backup_count
        )
        
        # Performance log format (CSV-like for easy parsing)
        formatter = logging.Formatter(
            '%(asctime)s,%(message)s',
            datefmt='%Y-%m-%d %H:%M:%S.%f'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        return logger
    
    def log_audio_metrics(self, metrics: Dict[str, float]) -> None:
        """Log audio processing metrics."""
        timestamp = time.time()
        
        # Format metrics as CSV
        metric_values = [
            str(timestamp),
            str(metrics.get('latency_ms', 0)),
            str(metrics.get('cpu_usage', 0)),
            str(metrics.get('memory_mb', 0)),
            str(metrics.get('buffer_underruns', 0)),
            str(metrics.get('buffer_overruns', 0)),
            str(metrics.get('sample_rate', 0)),
            str(metrics.get('channels', 0)),
        ]
        
        metric_line = ','.join(metric_values)
        
        with self.buffer_lock:
            self.metrics_buffer.append(metric_line)
            
            # Flush buffer if needed
            if (time.time() - self.last_flush) > self.config.flush_interval_sec:
                self._flush_metrics()
    
    def _flush_metrics(self) -> None:
        """Flush metrics buffer to file."""
        if not self.metrics_buffer:
            return
        
        try:
            for metric_line in self.metrics_buffer:
                self.perf_logger.info(metric_line)
            
            self.metrics_buffer.clear()
            self.last_flush = time.time()
        except Exception as e:
            # Don't let logging errors crash the system
            print(f"Performance logging error: {e}", file=sys.stderr)
    
    @contextmanager
    def measure_operation(self, operation_name: str):
        """Context manager to measure operation performance."""
        start_time = time.perf_counter()
        start_memory = self._get_memory_usage()
        
        try:
            yield
        finally:
            end_time = time.perf_counter()
            end_memory = self._get_memory_usage()
            
            duration_ms = (end_time - start_time) * 1000
            memory_delta_mb = (end_memory - start_memory) / (1024 * 1024)
            
            self.log_audio_metrics({
                'operation': operation_name,
                'duration_ms': duration_ms,
                'memory_delta_mb': memory_delta_mb,
            })
    
    def _get_memory_usage(self) -> int:
        """Get current memory usage in bytes."""
        try:
            import psutil
            process = psutil.Process()
            return process.memory_info().rss
        except ImportError:
            return 0


class AudioSystemLogger:
    """Main logging system for the audio processing system."""
    
    def __init__(self, config: Optional[LoggingConfig] = None):
        self.config = config or LoggingConfig()
        self.performance_logger = None
        
        # Create log directory
        self.config.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize logging
        self._setup_structured_logging()
        self._setup_standard_logging()
        
        if self.config.enable_performance_logging:
            self.performance_logger = PerformanceLogger(self.config)
        
        # Create logger instances
        self.system_logger = structlog.get_logger("system")
        self.audio_logger = structlog.get_logger("audio")
        self.debug_logger = structlog.get_logger("debug")
        self.error_logger = structlog.get_logger("error")
    
    def _setup_structured_logging(self) -> None:
        """Setup structured logging with structlog."""
        # Configure structlog
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer() if not self.config.enable_console_output
                else structlog.dev.ConsoleRenderer(),
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    
    def _setup_standard_logging(self) -> None:
        """Setup standard Python logging."""
        # Root logger configuration
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, self.config.log_level.value))
        
        # Clear existing handlers
        root_logger.handlers.clear()
        
        # File handlers for different log types
        self._create_file_handlers()
        
        # Console handler
        if self.config.enable_console_output:
            self._create_console_handler()
    
    def _create_file_handlers(self) -> None:
        """Create rotating file handlers for different log types."""
        log_types = [
            ("system", LogLevel.INFO),
            ("audio", LogLevel.DEBUG),
            ("error", LogLevel.ERROR),
        ]
        
        if self.config.enable_debug_logging:
            log_types.append(("debug", LogLevel.DEBUG))
        
        for log_type, min_level in log_types:
            log_file = self.config.log_dir / f"{log_type}.log"
            
            handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=self.config.max_file_size_mb * 1024 * 1024,
                backupCount=self.config.backup_count
            )
            
            handler.setLevel(getattr(logging, min_level.value))
            
            # Detailed format for file logs
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            
            # Add filter for specific log type
            handler.addFilter(self._create_log_type_filter(log_type))
            
            logging.getLogger().addHandler(handler)
    
    def _create_console_handler(self) -> None:
        """Create console handler for real-time monitoring."""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, self.config.console_log_level.value))
        
        # Simplified format for console
        formatter = logging.Formatter(
            '%(levelname)s - %(name)s - %(message)s'
        )
        console_handler.setFormatter(formatter)
        
        logging.getLogger().addHandler(console_handler)
    
    def _create_log_type_filter(self, log_type: str):
        """Create filter for specific log types."""
        class LogTypeFilter(logging.Filter):
            def __init__(self, log_type: str):
                super().__init__()
                self.log_type = log_type
            
            def filter(self, record):
                # Allow all records for system log
                if self.log_type == "system":
                    return True
                
                # Filter by logger name
                logger_name = record.name.lower()
                return self.log_type in logger_name or record.levelno >= logging.ERROR
        
        return LogTypeFilter(log_type)
    
    def log_system_event(self, message: str, **kwargs) -> None:
        """Log system events."""
        self.system_logger.info(message, **kwargs)
    
    def log_audio_event(self, message: str, **kwargs) -> None:
        """Log audio processing events."""
        self.audio_logger.info(message, **kwargs)
    
    def log_performance_metrics(self, metrics: Dict[str, float]) -> None:
        """Log performance metrics."""
        if self.performance_logger:
            self.performance_logger.log_audio_metrics(metrics)
    
    def log_error(self, message: str, exception: Optional[Exception] = None, **kwargs) -> None:
        """Log errors with optional exception details."""
        if exception:
            self.error_logger.error(message, exc_info=exception, **kwargs)
        else:
            self.error_logger.error(message, **kwargs)
    
    def log_debug(self, message: str, module: str = "", **kwargs) -> None:
        """Log debug information."""
        if self.config.enable_debug_logging:
            if not self.config.debug_log_modules or module in self.config.debug_log_modules:
                self.debug_logger.debug(message, module=module, **kwargs)
    
    @contextmanager
    def measure_performance(self, operation_name: str):
        """Context manager for performance measurement."""
        if self.performance_logger:
            with self.performance_logger.measure_operation(operation_name):
                yield
        else:
            yield
    
    def shutdown(self) -> None:
        """Shutdown logging system gracefully."""
        if self.performance_logger:
            self.performance_logger._flush_metrics()
        
        # Flush all handlers
        for handler in logging.getLogger().handlers:
            handler.flush()
            handler.close()


# Global logger instance
audio_logger = AudioSystemLogger()


# Convenience functions
def log_system(message: str, **kwargs) -> None:
    """Log system event."""
    audio_logger.log_system_event(message, **kwargs)


def log_audio(message: str, **kwargs) -> None:
    """Log audio event."""
    audio_logger.log_audio_event(message, **kwargs)


def log_performance(metrics: Dict[str, float]) -> None:
    """Log performance metrics."""
    audio_logger.log_performance_metrics(metrics)


def log_error(message: str, exception: Optional[Exception] = None, **kwargs) -> None:
    """Log error."""
    audio_logger.log_error(message, exception, **kwargs)


def log_debug(message: str, module: str = "", **kwargs) -> None:
    """Log debug information."""
    audio_logger.log_debug(message, module, **kwargs)


def measure_performance(operation_name: str):
    """Performance measurement context manager."""
    return audio_logger.measure_performance(operation_name)