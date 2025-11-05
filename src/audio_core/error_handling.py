"""
Error Classification and Handling System

This module implements a comprehensive error classification and handling system
for the production audio processing system, providing automatic error detection,
classification, recovery, and monitoring capabilities.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Any, Optional, Callable, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import threading
import time
import traceback
import json
import logging
from pathlib import Path

from .models import AudioDevice, ProcessingMetrics, SystemState
from ..config.logging_config import log_error, log_system, log_debug


class ErrorType(Enum):
    """Error type classification"""
    HARDWARE_ERROR = "hardware_error"
    PROCESSING_ERROR = "processing_error"
    SYSTEM_ERROR = "system_error"
    NETWORK_ERROR = "network_error"
    CONFIGURATION_ERROR = "configuration_error"
    UNKNOWN_ERROR = "unknown_error"


class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecoveryAction(Enum):
    """Recovery action types"""
    RETRY = "retry"
    RESTART_COMPONENT = "restart_component"
    SWITCH_DEVICE = "switch_device"
    DEGRADE_PERFORMANCE = "degrade_performance"
    SKIP_FRAME = "skip_frame"
    RESET_BUFFER = "reset_buffer"
    FALLBACK_CONFIG = "fallback_config"
    MANUAL_INTERVENTION = "manual_intervention"
    SYSTEM_SHUTDOWN = "system_shutdown"


@dataclass
class ErrorContext:
    """Context information for error occurrence"""
    component_name: str
    operation: str
    timestamp: datetime = field(default_factory=datetime.now)
    system_state: Optional[SystemState] = None
    audio_metrics: Optional[ProcessingMetrics] = None
    device_info: Optional[AudioDevice] = None
    additional_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'component_name': self.component_name,
            'operation': self.operation,
            'timestamp': self.timestamp.isoformat(),
            'system_state': self.system_state.value if self.system_state else None,
            'audio_metrics': self.audio_metrics.__dict__ if self.audio_metrics else None,
            'device_info': self.device_info.to_dict() if self.device_info else None,
            'additional_data': self.additional_data
        }


@dataclass
class ErrorRecord:
    """Complete error record with classification and recovery information"""
    error_id: str
    error_type: ErrorType
    severity: ErrorSeverity
    exception: Exception
    context: ErrorContext
    
    # Classification details
    error_message: str
    error_code: Optional[str] = None
    root_cause: Optional[str] = None
    
    # Recovery information
    recovery_actions: List[RecoveryAction] = field(default_factory=list)
    recovery_attempted: List[RecoveryAction] = field(default_factory=list)
    recovery_successful: bool = False
    recovery_time_ms: Optional[float] = None
    
    # Impact assessment
    affected_components: List[str] = field(default_factory=list)
    impact_scope: str = "local"  # local, component, system, global
    downtime_ms: Optional[float] = None
    
    # Metadata
    first_occurrence: datetime = field(default_factory=datetime.now)
    last_occurrence: datetime = field(default_factory=datetime.now)
    occurrence_count: int = 1
    resolved: bool = False
    resolution_time: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'error_id': self.error_id,
            'error_type': self.error_type.value,
            'severity': self.severity.value,
            'exception': {
                'type': type(self.exception).__name__,
                'message': str(self.exception),
                'traceback': traceback.format_exception(type(self.exception), self.exception, self.exception.__traceback__)
            },
            'context': self.context.to_dict(),
            'error_message': self.error_message,
            'error_code': self.error_code,
            'root_cause': self.root_cause,
            'recovery_actions': [action.value for action in self.recovery_actions],
            'recovery_attempted': [action.value for action in self.recovery_attempted],
            'recovery_successful': self.recovery_successful,
            'recovery_time_ms': self.recovery_time_ms,
            'affected_components': self.affected_components,
            'impact_scope': self.impact_scope,
            'downtime_ms': self.downtime_ms,
            'first_occurrence': self.first_occurrence.isoformat(),
            'last_occurrence': self.last_occurrence.isoformat(),
            'occurrence_count': self.occurrence_count,
            'resolved': self.resolved,
            'resolution_time': self.resolution_time.isoformat() if self.resolution_time else None
        }


class ErrorClassifier:
    """
    Error classifier that categorizes errors into hardware, processing, system, and network errors
    """
    
    def __init__(self):
        self.classification_rules = self._initialize_classification_rules()
        self.severity_rules = self._initialize_severity_rules()
    
    def _initialize_classification_rules(self) -> Dict[str, ErrorType]:
        """Initialize error classification rules based on exception types and messages"""
        return {
            # Hardware errors
            'OSError': ErrorType.HARDWARE_ERROR,
            'IOError': ErrorType.HARDWARE_ERROR,
            'device': ErrorType.HARDWARE_ERROR,
            'audio': ErrorType.HARDWARE_ERROR,
            'portaudio': ErrorType.HARDWARE_ERROR,
            'alsa': ErrorType.HARDWARE_ERROR,
            'wasapi': ErrorType.HARDWARE_ERROR,
            'coreaudio': ErrorType.HARDWARE_ERROR,
            'buffer overflow': ErrorType.HARDWARE_ERROR,
            'buffer underrun': ErrorType.HARDWARE_ERROR,
            'driver': ErrorType.HARDWARE_ERROR,
            
            # Processing errors
            'ValueError': ErrorType.PROCESSING_ERROR,
            'TypeError': ErrorType.PROCESSING_ERROR,
            'IndexError': ErrorType.PROCESSING_ERROR,
            'algorithm': ErrorType.PROCESSING_ERROR,
            'processing': ErrorType.PROCESSING_ERROR,
            'frame': ErrorType.PROCESSING_ERROR,
            'sample rate': ErrorType.PROCESSING_ERROR,
            'channels': ErrorType.PROCESSING_ERROR,
            
            # System errors
            'MemoryError': ErrorType.SYSTEM_ERROR,
            'SystemError': ErrorType.SYSTEM_ERROR,
            'PermissionError': ErrorType.SYSTEM_ERROR,
            'FileNotFoundError': ErrorType.SYSTEM_ERROR,
            'memory': ErrorType.SYSTEM_ERROR,
            'permission': ErrorType.SYSTEM_ERROR,
            'access denied': ErrorType.SYSTEM_ERROR,
            'insufficient': ErrorType.SYSTEM_ERROR,
            
            # Network errors
            'ConnectionError': ErrorType.NETWORK_ERROR,
            'TimeoutError': ErrorType.NETWORK_ERROR,
            'socket': ErrorType.NETWORK_ERROR,
            'network': ErrorType.NETWORK_ERROR,
            'connection': ErrorType.NETWORK_ERROR,
            'timeout': ErrorType.NETWORK_ERROR,
            
            # Configuration errors
            'ConfigurationError': ErrorType.CONFIGURATION_ERROR,
            'config': ErrorType.CONFIGURATION_ERROR,
            'configuration': ErrorType.CONFIGURATION_ERROR,
            'invalid parameter': ErrorType.CONFIGURATION_ERROR,
            'missing parameter': ErrorType.CONFIGURATION_ERROR,
        }
    
    def _initialize_severity_rules(self) -> Dict[str, ErrorSeverity]:
        """Initialize severity classification rules"""
        return {
            # Critical errors
            'MemoryError': ErrorSeverity.CRITICAL,
            'SystemError': ErrorSeverity.CRITICAL,
            'system shutdown': ErrorSeverity.CRITICAL,
            'critical failure': ErrorSeverity.CRITICAL,
            'total failure': ErrorSeverity.CRITICAL,
            
            # High severity
            'device disconnected': ErrorSeverity.HIGH,
            'driver failure': ErrorSeverity.HIGH,
            'buffer overflow': ErrorSeverity.HIGH,
            'processing failure': ErrorSeverity.HIGH,
            'component crash': ErrorSeverity.HIGH,
            
            # Medium severity
            'buffer underrun': ErrorSeverity.MEDIUM,
            'frame drop': ErrorSeverity.MEDIUM,
            'quality degradation': ErrorSeverity.MEDIUM,
            'parameter error': ErrorSeverity.MEDIUM,
            
            # Low severity
            'warning': ErrorSeverity.LOW,
            'minor': ErrorSeverity.LOW,
            'temporary': ErrorSeverity.LOW,
        }
    
    def classify_error(self, exception: Exception, context: ErrorContext) -> Tuple[ErrorType, ErrorSeverity]:
        """
        Classify error type and severity based on exception and context
        """
        error_type = self._classify_error_type(exception, context)
        severity = self._classify_severity(exception, context, error_type)
        
        return error_type, severity
    
    def _classify_error_type(self, exception: Exception, context: ErrorContext) -> ErrorType:
        """Classify error type based on exception and context"""
        exception_name = type(exception).__name__
        error_message = str(exception).lower()
        
        # Check exception type first
        if exception_name in self.classification_rules:
            return self.classification_rules[exception_name]
        
        # Check error message content
        for keyword, error_type in self.classification_rules.items():
            if keyword.lower() in error_message:
                return error_type
        
        # Check context for additional clues
        if context.component_name:
            component_name = context.component_name.lower()
            if 'device' in component_name or 'hardware' in component_name:
                return ErrorType.HARDWARE_ERROR
            elif 'process' in component_name or 'algorithm' in component_name:
                return ErrorType.PROCESSING_ERROR
            elif 'network' in component_name or 'web' in component_name:
                return ErrorType.NETWORK_ERROR
        
        return ErrorType.UNKNOWN_ERROR
    
    def _classify_severity(self, exception: Exception, context: ErrorContext, error_type: ErrorType) -> ErrorSeverity:
        """Classify error severity"""
        exception_name = type(exception).__name__
        error_message = str(exception).lower()
        
        # Check exception type first
        if exception_name in self.severity_rules:
            return self.severity_rules[exception_name]
        
        # Check error message content
        for keyword, severity in self.severity_rules.items():
            if keyword.lower() in error_message:
                return severity
        
        # Default severity based on error type
        severity_defaults = {
            ErrorType.HARDWARE_ERROR: ErrorSeverity.HIGH,
            ErrorType.PROCESSING_ERROR: ErrorSeverity.MEDIUM,
            ErrorType.SYSTEM_ERROR: ErrorSeverity.HIGH,
            ErrorType.NETWORK_ERROR: ErrorSeverity.MEDIUM,
            ErrorType.CONFIGURATION_ERROR: ErrorSeverity.LOW,
            ErrorType.UNKNOWN_ERROR: ErrorSeverity.MEDIUM
        }
        
        return severity_defaults.get(error_type, ErrorSeverity.MEDIUM)
    
    def suggest_recovery_actions(self, error_type: ErrorType, severity: ErrorSeverity, 
                               context: ErrorContext) -> List[RecoveryAction]:
        """Suggest appropriate recovery actions based on error classification"""
        actions = []
        
        if error_type == ErrorType.HARDWARE_ERROR:
            if severity == ErrorSeverity.CRITICAL:
                actions.extend([RecoveryAction.SWITCH_DEVICE, RecoveryAction.SYSTEM_SHUTDOWN])
            elif severity == ErrorSeverity.HIGH:
                actions.extend([RecoveryAction.RESTART_COMPONENT, RecoveryAction.SWITCH_DEVICE])
            else:
                actions.extend([RecoveryAction.RETRY, RecoveryAction.RESET_BUFFER])
        
        elif error_type == ErrorType.PROCESSING_ERROR:
            if severity == ErrorSeverity.CRITICAL:
                actions.extend([RecoveryAction.RESTART_COMPONENT, RecoveryAction.FALLBACK_CONFIG])
            elif severity == ErrorSeverity.HIGH:
                actions.extend([RecoveryAction.DEGRADE_PERFORMANCE, RecoveryAction.RESTART_COMPONENT])
            else:
                actions.extend([RecoveryAction.SKIP_FRAME, RecoveryAction.RETRY])
        
        elif error_type == ErrorType.SYSTEM_ERROR:
            if severity == ErrorSeverity.CRITICAL:
                actions.extend([RecoveryAction.SYSTEM_SHUTDOWN, RecoveryAction.MANUAL_INTERVENTION])
            else:
                actions.extend([RecoveryAction.FALLBACK_CONFIG, RecoveryAction.RESTART_COMPONENT])
        
        elif error_type == ErrorType.NETWORK_ERROR:
            actions.extend([RecoveryAction.RETRY, RecoveryAction.FALLBACK_CONFIG])
        
        elif error_type == ErrorType.CONFIGURATION_ERROR:
            actions.extend([RecoveryAction.FALLBACK_CONFIG, RecoveryAction.MANUAL_INTERVENTION])
        
        else:  # UNKNOWN_ERROR
            actions.extend([RecoveryAction.RETRY, RecoveryAction.RESTART_COMPONENT])
        
        return actions


class BaseErrorHandler(ABC):
    """Base class for error handlers"""
    
    def __init__(self, name: str):
        self.name = name
        self.enabled = True
        self.handled_errors = []
        self.recovery_callbacks: Dict[RecoveryAction, List[Callable]] = {}
    
    @abstractmethod
    def can_handle(self, error_record: ErrorRecord) -> bool:
        """Check if this handler can handle the given error"""
        pass
    
    @abstractmethod
    def handle_error(self, error_record: ErrorRecord) -> bool:
        """Handle the error and return success status"""
        pass
    
    def register_recovery_callback(self, action: RecoveryAction, callback: Callable):
        """Register callback for recovery action"""
        if action not in self.recovery_callbacks:
            self.recovery_callbacks[action] = []
        self.recovery_callbacks[action].append(callback)
    
    def execute_recovery_action(self, action: RecoveryAction, context: Dict[str, Any] = None) -> bool:
        """Execute recovery action with registered callbacks"""
        if action in self.recovery_callbacks:
            for callback in self.recovery_callbacks[action]:
                try:
                    result = callback(context or {})
                    if result:
                        return True
                except Exception as e:
                    log_error(f"Recovery callback failed for {action.value}", e)
        return False


class HardwareErrorHandler(BaseErrorHandler):
    """
    Handler for hardware errors including device disconnection, driver failures, and buffer issues
    """
    
    def __init__(self):
        super().__init__("HardwareErrorHandler")
        self.device_reconnect_attempts = {}
        self.max_reconnect_attempts = 3
        self.reconnect_delay_seconds = 2.0
        self.backup_devices = []
    
    def can_handle(self, error_record: ErrorRecord) -> bool:
        """Check if this is a hardware error"""
        return error_record.error_type == ErrorType.HARDWARE_ERROR
    
    def handle_error(self, error_record: ErrorRecord) -> bool:
        """Handle hardware errors with device management and recovery"""
        log_system(f"Handling hardware error: {error_record.error_message}")
        
        recovery_success = False
        
        for action in error_record.recovery_actions:
            if action in error_record.recovery_attempted:
                continue
            
            error_record.recovery_attempted.append(action)
            
            if action == RecoveryAction.RETRY:
                recovery_success = self._retry_operation(error_record)
            elif action == RecoveryAction.RESTART_COMPONENT:
                recovery_success = self._restart_component(error_record)
            elif action == RecoveryAction.SWITCH_DEVICE:
                recovery_success = self._switch_device(error_record)
            elif action == RecoveryAction.RESET_BUFFER:
                recovery_success = self._reset_buffer(error_record)
            
            if recovery_success:
                break
        
        error_record.recovery_successful = recovery_success
        return recovery_success
    
    def _retry_operation(self, error_record: ErrorRecord) -> bool:
        """Retry the failed operation"""
        device_id = error_record.context.device_info.device_id if error_record.context.device_info else "unknown"
        
        # Track reconnection attempts
        if device_id not in self.device_reconnect_attempts:
            self.device_reconnect_attempts[device_id] = 0
        
        if self.device_reconnect_attempts[device_id] >= self.max_reconnect_attempts:
            log_system(f"Max reconnection attempts reached for device {device_id}")
            return False
        
        self.device_reconnect_attempts[device_id] += 1
        
        # Wait before retry
        time.sleep(self.reconnect_delay_seconds)
        
        # Execute retry callback
        return self.execute_recovery_action(RecoveryAction.RETRY, {
            'device_id': device_id,
            'attempt': self.device_reconnect_attempts[device_id]
        })
    
    def _restart_component(self, error_record: ErrorRecord) -> bool:
        """Restart the affected component"""
        return self.execute_recovery_action(RecoveryAction.RESTART_COMPONENT, {
            'component_name': error_record.context.component_name
        })
    
    def _switch_device(self, error_record: ErrorRecord) -> bool:
        """Switch to backup device"""
        if not self.backup_devices:
            log_system("No backup devices available for switching")
            return False
        
        return self.execute_recovery_action(RecoveryAction.SWITCH_DEVICE, {
            'failed_device': error_record.context.device_info.device_id if error_record.context.device_info else None,
            'backup_devices': self.backup_devices
        })
    
    def _reset_buffer(self, error_record: ErrorRecord) -> bool:
        """Reset audio buffers"""
        return self.execute_recovery_action(RecoveryAction.RESET_BUFFER, {
            'component_name': error_record.context.component_name
        })
    
    def set_backup_devices(self, devices: List[str]):
        """Set list of backup devices for switching"""
        self.backup_devices = devices
    
    def reset_reconnect_attempts(self, device_id: str):
        """Reset reconnection attempts for a device"""
        if device_id in self.device_reconnect_attempts:
            del self.device_reconnect_attempts[device_id]


class ProcessingErrorHandler(BaseErrorHandler):
    """
    Handler for processing errors including algorithm exceptions and performance degradation
    """
    
    def __init__(self):
        super().__init__("ProcessingErrorHandler")
        self.frame_skip_count = {}
        self.max_consecutive_skips = 10
        self.performance_degradation_active = False
    
    def can_handle(self, error_record: ErrorRecord) -> bool:
        """Check if this is a processing error"""
        return error_record.error_type == ErrorType.PROCESSING_ERROR
    
    def handle_error(self, error_record: ErrorRecord) -> bool:
        """Handle processing errors with frame skipping and parameter degradation"""
        log_system(f"Handling processing error: {error_record.error_message}")
        
        recovery_success = False
        
        for action in error_record.recovery_actions:
            if action in error_record.recovery_attempted:
                continue
            
            error_record.recovery_attempted.append(action)
            
            if action == RecoveryAction.SKIP_FRAME:
                recovery_success = self._skip_frame(error_record)
            elif action == RecoveryAction.DEGRADE_PERFORMANCE:
                recovery_success = self._degrade_performance(error_record)
            elif action == RecoveryAction.RESTART_COMPONENT:
                recovery_success = self._restart_component(error_record)
            elif action == RecoveryAction.RETRY:
                recovery_success = self._retry_processing(error_record)
            
            if recovery_success:
                break
        
        error_record.recovery_successful = recovery_success
        return recovery_success
    
    def _skip_frame(self, error_record: ErrorRecord) -> bool:
        """Skip the problematic frame"""
        component_name = error_record.context.component_name
        
        if component_name not in self.frame_skip_count:
            self.frame_skip_count[component_name] = 0
        
        self.frame_skip_count[component_name] += 1
        
        if self.frame_skip_count[component_name] > self.max_consecutive_skips:
            log_system(f"Too many consecutive frame skips in {component_name}")
            return False
        
        return self.execute_recovery_action(RecoveryAction.SKIP_FRAME, {
            'component_name': component_name,
            'skip_count': self.frame_skip_count[component_name]
        })
    
    def _degrade_performance(self, error_record: ErrorRecord) -> bool:
        """Degrade performance parameters to reduce processing load"""
        if self.performance_degradation_active:
            return False  # Already degraded
        
        self.performance_degradation_active = True
        
        return self.execute_recovery_action(RecoveryAction.DEGRADE_PERFORMANCE, {
            'component_name': error_record.context.component_name,
            'degradation_level': 1
        })
    
    def _restart_component(self, error_record: ErrorRecord) -> bool:
        """Restart the processing component"""
        # Reset frame skip count on restart
        component_name = error_record.context.component_name
        if component_name in self.frame_skip_count:
            del self.frame_skip_count[component_name]
        
        return self.execute_recovery_action(RecoveryAction.RESTART_COMPONENT, {
            'component_name': component_name
        })
    
    def _retry_processing(self, error_record: ErrorRecord) -> bool:
        """Retry the processing operation"""
        return self.execute_recovery_action(RecoveryAction.RETRY, {
            'component_name': error_record.context.component_name,
            'operation': error_record.context.operation
        })
    
    def reset_frame_skip_count(self, component_name: str):
        """Reset frame skip count for a component"""
        if component_name in self.frame_skip_count:
            del self.frame_skip_count[component_name]
    
    def restore_performance(self):
        """Restore normal performance parameters"""
        if self.performance_degradation_active:
            self.performance_degradation_active = False
            self.execute_recovery_action(RecoveryAction.DEGRADE_PERFORMANCE, {
                'restore': True
            })


class SystemErrorHandler(BaseErrorHandler):
    """
    Handler for system errors including memory issues, permissions, and configuration problems
    """
    
    def __init__(self):
        super().__init__("SystemErrorHandler")
        self.fallback_configs = {}
        self.memory_cleanup_callbacks = []
    
    def can_handle(self, error_record: ErrorRecord) -> bool:
        """Check if this is a system error"""
        return error_record.error_type in [ErrorType.SYSTEM_ERROR, ErrorType.CONFIGURATION_ERROR]
    
    def handle_error(self, error_record: ErrorRecord) -> bool:
        """Handle system errors with fallback configurations and resource management"""
        log_system(f"Handling system error: {error_record.error_message}")
        
        recovery_success = False
        
        for action in error_record.recovery_actions:
            if action in error_record.recovery_attempted:
                continue
            
            error_record.recovery_attempted.append(action)
            
            if action == RecoveryAction.FALLBACK_CONFIG:
                recovery_success = self._apply_fallback_config(error_record)
            elif action == RecoveryAction.RESTART_COMPONENT:
                recovery_success = self._restart_component(error_record)
            elif action == RecoveryAction.MANUAL_INTERVENTION:
                recovery_success = self._request_manual_intervention(error_record)
            
            if recovery_success:
                break
        
        error_record.recovery_successful = recovery_success
        return recovery_success
    
    def _apply_fallback_config(self, error_record: ErrorRecord) -> bool:
        """Apply fallback configuration"""
        component_name = error_record.context.component_name
        
        if component_name not in self.fallback_configs:
            log_system(f"No fallback configuration available for {component_name}")
            return False
        
        return self.execute_recovery_action(RecoveryAction.FALLBACK_CONFIG, {
            'component_name': component_name,
            'fallback_config': self.fallback_configs[component_name]
        })
    
    def _restart_component(self, error_record: ErrorRecord) -> bool:
        """Restart component with memory cleanup"""
        # Perform memory cleanup before restart
        self._cleanup_memory()
        
        return self.execute_recovery_action(RecoveryAction.RESTART_COMPONENT, {
            'component_name': error_record.context.component_name,
            'cleanup_memory': True
        })
    
    def _request_manual_intervention(self, error_record: ErrorRecord) -> bool:
        """Request manual intervention for critical errors"""
        return self.execute_recovery_action(RecoveryAction.MANUAL_INTERVENTION, {
            'error_record': error_record,
            'intervention_required': True
        })
    
    def _cleanup_memory(self):
        """Perform memory cleanup"""
        for callback in self.memory_cleanup_callbacks:
            try:
                callback()
            except Exception as e:
                log_error("Memory cleanup callback failed", e)
    
    def set_fallback_config(self, component_name: str, config: Dict[str, Any]):
        """Set fallback configuration for a component"""
        self.fallback_configs[component_name] = config
    
    def register_memory_cleanup_callback(self, callback: Callable):
        """Register memory cleanup callback"""
        self.memory_cleanup_callbacks.append(callback)


class ErrorLogger:
    """
    Comprehensive error logging system with detailed error information,
    timestamps, context, recovery operations, and impact analysis
    """
    
    def __init__(self, log_dir: Path = Path("logs")):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Error log files
        self.error_log_file = self.log_dir / "errors.json"
        self.recovery_log_file = self.log_dir / "recovery.json"
        
        # In-memory error storage for quick access
        self.error_records: Dict[str, ErrorRecord] = {}
        self.error_history: List[ErrorRecord] = []
        
        # Thread safety
        self.lock = threading.Lock()
        
        # Initialize log files
        self._initialize_log_files()
    
    def _initialize_log_files(self):
        """Initialize log files if they don't exist"""
        if not self.error_log_file.exists():
            with open(self.error_log_file, 'w') as f:
                json.dump([], f)
        
        if not self.recovery_log_file.exists():
            with open(self.recovery_log_file, 'w') as f:
                json.dump([], f)
    
    def log_error(self, error_record: ErrorRecord) -> str:
        """
        Log error with detailed information including timestamp, error type,
        context, recovery operations, and impact range
        """
        with self.lock:
            # Store in memory
            self.error_records[error_record.error_id] = error_record
            self.error_history.append(error_record)
            
            # Limit history size
            if len(self.error_history) > 10000:
                self.error_history = self.error_history[-5000:]
            
            # Log to file
            self._append_to_error_log(error_record)
            
            # Log to system logger
            log_error(
                f"Error logged: {error_record.error_type.value} - {error_record.error_message}",
                error_record.exception,
                error_id=error_record.error_id,
                severity=error_record.severity.value,
                component=error_record.context.component_name
            )
            
            return error_record.error_id
    
    def _append_to_error_log(self, error_record: ErrorRecord):
        """Append error record to log file"""
        try:
            # Read existing logs
            with open(self.error_log_file, 'r') as f:
                logs = json.load(f)
            
            # Append new record
            logs.append(error_record.to_dict())
            
            # Keep only recent logs (last 1000)
            if len(logs) > 1000:
                logs = logs[-500:]
            
            # Write back to file
            with open(self.error_log_file, 'w') as f:
                json.dump(logs, f, indent=2)
        
        except Exception as e:
            log_error("Failed to write error log", e)
    
    def log_recovery_attempt(self, error_id: str, action: RecoveryAction, 
                           success: bool, duration_ms: float, details: Dict[str, Any] = None):
        """Log recovery attempt with results"""
        recovery_log = {
            'error_id': error_id,
            'action': action.value,
            'success': success,
            'duration_ms': duration_ms,
            'timestamp': datetime.now().isoformat(),
            'details': details or {}
        }
        
        with self.lock:
            # Update error record
            if error_id in self.error_records:
                error_record = self.error_records[error_id]
                if success:
                    error_record.recovery_successful = True
                    error_record.recovery_time_ms = duration_ms
                    error_record.resolved = True
                    error_record.resolution_time = datetime.now()
            
            # Log to recovery file
            self._append_to_recovery_log(recovery_log)
    
    def _append_to_recovery_log(self, recovery_log: Dict[str, Any]):
        """Append recovery log to file"""
        try:
            # Read existing logs
            with open(self.recovery_log_file, 'r') as f:
                logs = json.load(f)
            
            # Append new record
            logs.append(recovery_log)
            
            # Keep only recent logs
            if len(logs) > 1000:
                logs = logs[-500:]
            
            # Write back to file
            with open(self.recovery_log_file, 'w') as f:
                json.dump(logs, f, indent=2)
        
        except Exception as e:
            log_error("Failed to write recovery log", e)
    
    def get_error_record(self, error_id: str) -> Optional[ErrorRecord]:
        """Get error record by ID"""
        with self.lock:
            return self.error_records.get(error_id)
    
    def get_recent_errors(self, hours: int = 24) -> List[ErrorRecord]:
        """Get errors from the last N hours"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with self.lock:
            return [
                error for error in self.error_history
                if error.last_occurrence >= cutoff_time
            ]
    
    def get_errors_by_type(self, error_type: ErrorType) -> List[ErrorRecord]:
        """Get all errors of a specific type"""
        with self.lock:
            return [
                error for error in self.error_history
                if error.error_type == error_type
            ]
    
    def get_errors_by_component(self, component_name: str) -> List[ErrorRecord]:
        """Get all errors for a specific component"""
        with self.lock:
            return [
                error for error in self.error_history
                if error.context.component_name == component_name
            ]
    
    def mark_error_resolved(self, error_id: str, resolution_details: str = ""):
        """Mark error as resolved"""
        with self.lock:
            if error_id in self.error_records:
                error_record = self.error_records[error_id]
                error_record.resolved = True
                error_record.resolution_time = datetime.now()
                if resolution_details:
                    error_record.context.additional_data['resolution_details'] = resolution_details
    
    def cleanup_old_logs(self, days: int = 30):
        """Clean up old log entries"""
        cutoff_time = datetime.now() - timedelta(days=days)
        
        with self.lock:
            # Clean memory storage
            self.error_history = [
                error for error in self.error_history
                if error.last_occurrence >= cutoff_time
            ]
            
            # Update error_records dict
            old_error_ids = [
                error_id for error_id, error_record in self.error_records.items()
                if error_record.last_occurrence < cutoff_time
            ]
            
            for error_id in old_error_ids:
                del self.error_records[error_id]


class ErrorStatistics:
    """
    Error statistics collector for monitoring error frequency,
    recovery success rates, and system availability metrics
    """
    
    def __init__(self, error_logger: ErrorLogger):
        self.error_logger = error_logger
        self.stats_cache = {}
        self.cache_expiry = {}
        self.cache_duration_seconds = 300  # 5 minutes
    
    def get_error_frequency(self, time_window_hours: int = 24) -> Dict[ErrorType, int]:
        """Get error frequency by type in the specified time window"""
        cache_key = f"error_frequency_{time_window_hours}"
        
        if self._is_cache_valid(cache_key):
            return self.stats_cache[cache_key]
        
        recent_errors = self.error_logger.get_recent_errors(time_window_hours)
        frequency = {}
        
        for error_type in ErrorType:
            frequency[error_type] = sum(
                1 for error in recent_errors if error.error_type == error_type
            )
        
        self._cache_result(cache_key, frequency)
        return frequency
    
    def get_recovery_success_rate(self, time_window_hours: int = 24) -> Dict[ErrorType, float]:
        """Get recovery success rate by error type"""
        cache_key = f"recovery_success_{time_window_hours}"
        
        if self._is_cache_valid(cache_key):
            return self.stats_cache[cache_key]
        
        recent_errors = self.error_logger.get_recent_errors(time_window_hours)
        success_rates = {}
        
        for error_type in ErrorType:
            type_errors = [error for error in recent_errors if error.error_type == error_type]
            
            if not type_errors:
                success_rates[error_type] = 0.0
                continue
            
            successful_recoveries = sum(1 for error in type_errors if error.recovery_successful)
            success_rates[error_type] = successful_recoveries / len(type_errors)
        
        self._cache_result(cache_key, success_rates)
        return success_rates
    
    def get_system_availability(self, time_window_hours: int = 24) -> float:
        """Calculate system availability percentage"""
        cache_key = f"system_availability_{time_window_hours}"
        
        if self._is_cache_valid(cache_key):
            return self.stats_cache[cache_key]
        
        recent_errors = self.error_logger.get_recent_errors(time_window_hours)
        
        # Calculate total downtime
        total_downtime_ms = sum(
            error.downtime_ms or 0 for error in recent_errors
            if error.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]
        )
        
        # Total time window in milliseconds
        total_time_ms = time_window_hours * 60 * 60 * 1000
        
        # Calculate availability
        uptime_ms = total_time_ms - total_downtime_ms
        availability = max(0.0, uptime_ms / total_time_ms)
        
        self._cache_result(cache_key, availability)
        return availability
    
    def get_component_error_stats(self, time_window_hours: int = 24) -> Dict[str, Dict[str, Any]]:
        """Get error statistics by component"""
        cache_key = f"component_stats_{time_window_hours}"
        
        if self._is_cache_valid(cache_key):
            return self.stats_cache[cache_key]
        
        recent_errors = self.error_logger.get_recent_errors(time_window_hours)
        component_stats = {}
        
        for error in recent_errors:
            component = error.context.component_name
            
            if component not in component_stats:
                component_stats[component] = {
                    'total_errors': 0,
                    'error_types': {},
                    'recovery_success_rate': 0.0,
                    'average_recovery_time_ms': 0.0,
                    'last_error': None
                }
            
            stats = component_stats[component]
            stats['total_errors'] += 1
            
            # Count by error type
            error_type = error.error_type.value
            if error_type not in stats['error_types']:
                stats['error_types'][error_type] = 0
            stats['error_types'][error_type] += 1
            
            # Update last error time
            if not stats['last_error'] or error.last_occurrence > stats['last_error']:
                stats['last_error'] = error.last_occurrence.isoformat()
        
        # Calculate recovery rates and average times
        for component, stats in component_stats.items():
            component_errors = [
                error for error in recent_errors
                if error.context.component_name == component
            ]
            
            successful_recoveries = [error for error in component_errors if error.recovery_successful]
            stats['recovery_success_rate'] = len(successful_recoveries) / len(component_errors)
            
            recovery_times = [
                error.recovery_time_ms for error in successful_recoveries
                if error.recovery_time_ms is not None
            ]
            
            if recovery_times:
                stats['average_recovery_time_ms'] = sum(recovery_times) / len(recovery_times)
        
        self._cache_result(cache_key, component_stats)
        return component_stats
    
    def get_error_trends(self, days: int = 7) -> Dict[str, List[Tuple[str, int]]]:
        """Get error trends over time"""
        cache_key = f"error_trends_{days}"
        
        if self._is_cache_valid(cache_key):
            return self.stats_cache[cache_key]
        
        # Get errors for the specified period
        all_errors = self.error_logger.get_recent_errors(days * 24)
        
        # Group by day and error type
        trends = {}
        for error_type in ErrorType:
            trends[error_type.value] = []
        
        # Create daily buckets
        for day_offset in range(days):
            day_start = datetime.now() - timedelta(days=day_offset+1)
            day_end = datetime.now() - timedelta(days=day_offset)
            day_label = day_start.strftime('%Y-%m-%d')
            
            day_errors = [
                error for error in all_errors
                if day_start <= error.last_occurrence < day_end
            ]
            
            for error_type in ErrorType:
                count = sum(1 for error in day_errors if error.error_type == error_type)
                trends[error_type.value].append((day_label, count))
        
        # Reverse to get chronological order
        for error_type in trends:
            trends[error_type].reverse()
        
        self._cache_result(cache_key, trends)
        return trends
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached result is still valid"""
        if cache_key not in self.stats_cache:
            return False
        
        if cache_key not in self.cache_expiry:
            return False
        
        return datetime.now() < self.cache_expiry[cache_key]
    
    def _cache_result(self, cache_key: str, result: Any):
        """Cache result with expiry time"""
        self.stats_cache[cache_key] = result
        self.cache_expiry[cache_key] = datetime.now() + timedelta(seconds=self.cache_duration_seconds)
    
    def clear_cache(self):
        """Clear statistics cache"""
        self.stats_cache.clear()
        self.cache_expiry.clear()


class ErrorNotifier:
    """
    Error notification system that sends alerts based on error severity
    through various channels (logs, email, webhook)
    """
    
    def __init__(self):
        self.notification_channels = {}
        self.notification_rules = {}
        self.rate_limits = {}
        self.last_notifications = {}
    
    def register_notification_channel(self, channel_name: str, handler: Callable[[Dict[str, Any]], bool]):
        """Register a notification channel handler"""
        self.notification_channels[channel_name] = handler
    
    def set_notification_rule(self, severity: ErrorSeverity, channels: List[str], 
                            rate_limit_minutes: int = 5):
        """Set notification rule for error severity"""
        self.notification_rules[severity] = {
            'channels': channels,
            'rate_limit_minutes': rate_limit_minutes
        }
    
    def notify_error(self, error_record: ErrorRecord) -> Dict[str, bool]:
        """Send notifications for error based on severity and rules"""
        severity = error_record.severity
        
        if severity not in self.notification_rules:
            return {}
        
        rule = self.notification_rules[severity]
        
        # Check rate limiting
        if self._is_rate_limited(error_record):
            log_debug(f"Notification rate limited for error {error_record.error_id}")
            return {}
        
        # Prepare notification data
        notification_data = self._prepare_notification_data(error_record)
        
        # Send notifications to configured channels
        results = {}
        for channel_name in rule['channels']:
            if channel_name in self.notification_channels:
                try:
                    handler = self.notification_channels[channel_name]
                    success = handler(notification_data)
                    results[channel_name] = success
                    
                    if success:
                        log_system(f"Notification sent via {channel_name} for error {error_record.error_id}")
                    else:
                        log_error(f"Failed to send notification via {channel_name}")
                
                except Exception as e:
                    log_error(f"Notification handler {channel_name} failed", e)
                    results[channel_name] = False
        
        # Update rate limiting
        self._update_rate_limit(error_record)
        
        return results
    
    def _prepare_notification_data(self, error_record: ErrorRecord) -> Dict[str, Any]:
        """Prepare notification data from error record"""
        return {
            'error_id': error_record.error_id,
            'error_type': error_record.error_type.value,
            'severity': error_record.severity.value,
            'message': error_record.error_message,
            'component': error_record.context.component_name,
            'operation': error_record.context.operation,
            'timestamp': error_record.first_occurrence.isoformat(),
            'recovery_attempted': [action.value for action in error_record.recovery_attempted],
            'recovery_successful': error_record.recovery_successful,
            'affected_components': error_record.affected_components,
            'impact_scope': error_record.impact_scope,
            'occurrence_count': error_record.occurrence_count
        }
    
    def _is_rate_limited(self, error_record: ErrorRecord) -> bool:
        """Check if notification is rate limited"""
        severity = error_record.severity
        
        if severity not in self.notification_rules:
            return True
        
        rate_limit_key = f"{severity.value}_{error_record.context.component_name}"
        
        if rate_limit_key not in self.last_notifications:
            return False
        
        last_notification = self.last_notifications[rate_limit_key]
        rate_limit_minutes = self.notification_rules[severity]['rate_limit_minutes']
        
        time_since_last = datetime.now() - last_notification
        return time_since_last < timedelta(minutes=rate_limit_minutes)
    
    def _update_rate_limit(self, error_record: ErrorRecord):
        """Update rate limiting timestamp"""
        severity = error_record.severity
        rate_limit_key = f"{severity.value}_{error_record.context.component_name}"
        self.last_notifications[rate_limit_key] = datetime.now()
    
    def create_log_notification_handler(self) -> Callable[[Dict[str, Any]], bool]:
        """Create a log-based notification handler"""
        def log_handler(notification_data: Dict[str, Any]) -> bool:
            try:
                severity = notification_data['severity']
                message = f"ALERT [{severity}]: {notification_data['message']}"
                
                log_system(
                    message,
                    error_id=notification_data['error_id'],
                    component=notification_data['component'],
                    impact_scope=notification_data['impact_scope']
                )
                return True
            except Exception:
                return False
        
        return log_handler
    
    def create_webhook_notification_handler(self, webhook_url: str) -> Callable[[Dict[str, Any]], bool]:
        """Create a webhook notification handler"""
        def webhook_handler(notification_data: Dict[str, Any]) -> bool:
            try:
                import requests
                
                payload = {
                    'alert_type': 'audio_system_error',
                    'timestamp': datetime.now().isoformat(),
                    'data': notification_data
                }
                
                response = requests.post(
                    webhook_url,
                    json=payload,
                    timeout=10,
                    headers={'Content-Type': 'application/json'}
                )
                
                return response.status_code == 200
            
            except Exception as e:
                log_error(f"Webhook notification failed: {webhook_url}", e)
                return False
        
        return webhook_handler


# Error recovery strategy configuration and dynamic adjustment
class ErrorRecoveryStrategyManager:
    """
    Manager for error recovery strategies with dynamic adjustment capabilities
    """
    
    def __init__(self):
        self.strategies: Dict[Tuple[ErrorType, ErrorSeverity], List[RecoveryAction]] = {}
        self.strategy_effectiveness: Dict[Tuple[ErrorType, RecoveryAction], float] = {}
        self.adaptive_learning_enabled = True
        self.min_samples_for_learning = 10
    
    def set_recovery_strategy(self, error_type: ErrorType, severity: ErrorSeverity, 
                            actions: List[RecoveryAction]):
        """Set recovery strategy for specific error type and severity"""
        self.strategies[(error_type, severity)] = actions.copy()
    
    def get_recovery_strategy(self, error_type: ErrorType, severity: ErrorSeverity) -> List[RecoveryAction]:
        """Get recovery strategy, potentially adjusted based on effectiveness"""
        strategy_key = (error_type, severity)
        
        if strategy_key not in self.strategies:
            # Return default strategy
            return self._get_default_strategy(error_type, severity)
        
        base_strategy = self.strategies[strategy_key].copy()
        
        if self.adaptive_learning_enabled:
            return self._adjust_strategy_by_effectiveness(error_type, base_strategy)
        
        return base_strategy
    
    def record_recovery_result(self, error_type: ErrorType, action: RecoveryAction, 
                             success: bool, duration_ms: float):
        """Record recovery attempt result for learning"""
        effectiveness_key = (error_type, action)
        
        if effectiveness_key not in self.strategy_effectiveness:
            self.strategy_effectiveness[effectiveness_key] = 0.5  # Start with neutral
        
        # Update effectiveness using exponential moving average
        current_effectiveness = self.strategy_effectiveness[effectiveness_key]
        success_value = 1.0 if success else 0.0
        
        # Weight recent results more heavily
        alpha = 0.3
        new_effectiveness = alpha * success_value + (1 - alpha) * current_effectiveness
        
        self.strategy_effectiveness[effectiveness_key] = new_effectiveness
    
    def _get_default_strategy(self, error_type: ErrorType, severity: ErrorSeverity) -> List[RecoveryAction]:
        """Get default recovery strategy"""
        if error_type == ErrorType.HARDWARE_ERROR:
            if severity == ErrorSeverity.CRITICAL:
                return [RecoveryAction.SWITCH_DEVICE, RecoveryAction.SYSTEM_SHUTDOWN]
            elif severity == ErrorSeverity.HIGH:
                return [RecoveryAction.RESTART_COMPONENT, RecoveryAction.SWITCH_DEVICE]
            else:
                return [RecoveryAction.RETRY, RecoveryAction.RESET_BUFFER]
        
        elif error_type == ErrorType.PROCESSING_ERROR:
            if severity == ErrorSeverity.CRITICAL:
                return [RecoveryAction.RESTART_COMPONENT, RecoveryAction.FALLBACK_CONFIG]
            else:
                return [RecoveryAction.SKIP_FRAME, RecoveryAction.DEGRADE_PERFORMANCE]
        
        elif error_type == ErrorType.SYSTEM_ERROR:
            return [RecoveryAction.FALLBACK_CONFIG, RecoveryAction.RESTART_COMPONENT]
        
        else:
            return [RecoveryAction.RETRY, RecoveryAction.RESTART_COMPONENT]
    
    def _adjust_strategy_by_effectiveness(self, error_type: ErrorType, 
                                        base_strategy: List[RecoveryAction]) -> List[RecoveryAction]:
        """Adjust strategy based on recorded effectiveness"""
        # Sort actions by effectiveness
        action_effectiveness = []
        
        for action in base_strategy:
            effectiveness_key = (error_type, action)
            effectiveness = self.strategy_effectiveness.get(effectiveness_key, 0.5)
            action_effectiveness.append((action, effectiveness))
        
        # Sort by effectiveness (descending)
        action_effectiveness.sort(key=lambda x: x[1], reverse=True)
        
        # Return sorted actions
        return [action for action, _ in action_effectiveness]
    
    def get_strategy_effectiveness_report(self) -> Dict[str, Any]:
        """Get report on strategy effectiveness"""
        report = {
            'total_strategies': len(self.strategies),
            'effectiveness_data': {},
            'recommendations': []
        }
        
        for (error_type, action), effectiveness in self.strategy_effectiveness.items():
            key = f"{error_type.value}_{action.value}"
            report['effectiveness_data'][key] = effectiveness
            
            if effectiveness < 0.3:
                report['recommendations'].append(
                    f"Consider replacing {action.value} for {error_type.value} errors (low effectiveness: {effectiveness:.2f})"
                )
        
        return report


class ErrorHandlingSystem:
    """
    Main error handling system coordinator that integrates all error handling components
    """
    
    def __init__(self, log_dir: Path = Path("logs")):
        # Initialize core components
        self.classifier = ErrorClassifier()
        self.logger = ErrorLogger(log_dir)
        self.statistics = ErrorStatistics(self.logger)
        self.notifier = ErrorNotifier()
        self.strategy_manager = ErrorRecoveryStrategyManager()
        
        # Initialize error handlers
        self.hardware_handler = HardwareErrorHandler()
        self.processing_handler = ProcessingErrorHandler()
        self.system_handler = SystemErrorHandler()
        
        self.error_handlers = [
            self.hardware_handler,
            self.processing_handler,
            self.system_handler
        ]
        
        # System state
        self.enabled = True
        self.error_count = 0
        self.recovery_count = 0
        
        # Setup default notification channels
        self._setup_default_notifications()
        
        # Setup default recovery strategies
        self._setup_default_recovery_strategies()
    
    def _setup_default_notifications(self):
        """Setup default notification channels and rules"""
        # Register log notification handler
        log_handler = self.notifier.create_log_notification_handler()
        self.notifier.register_notification_channel('log', log_handler)
        
        # Set notification rules
        self.notifier.set_notification_rule(ErrorSeverity.LOW, ['log'], rate_limit_minutes=30)
        self.notifier.set_notification_rule(ErrorSeverity.MEDIUM, ['log'], rate_limit_minutes=15)
        self.notifier.set_notification_rule(ErrorSeverity.HIGH, ['log'], rate_limit_minutes=5)
        self.notifier.set_notification_rule(ErrorSeverity.CRITICAL, ['log'], rate_limit_minutes=1)
    
    def _setup_default_recovery_strategies(self):
        """Setup default recovery strategies"""
        # Hardware error strategies
        self.strategy_manager.set_recovery_strategy(
            ErrorType.HARDWARE_ERROR, ErrorSeverity.LOW,
            [RecoveryAction.RETRY, RecoveryAction.RESET_BUFFER]
        )
        self.strategy_manager.set_recovery_strategy(
            ErrorType.HARDWARE_ERROR, ErrorSeverity.MEDIUM,
            [RecoveryAction.RESTART_COMPONENT, RecoveryAction.RETRY]
        )
        self.strategy_manager.set_recovery_strategy(
            ErrorType.HARDWARE_ERROR, ErrorSeverity.HIGH,
            [RecoveryAction.SWITCH_DEVICE, RecoveryAction.RESTART_COMPONENT]
        )
        self.strategy_manager.set_recovery_strategy(
            ErrorType.HARDWARE_ERROR, ErrorSeverity.CRITICAL,
            [RecoveryAction.SWITCH_DEVICE, RecoveryAction.SYSTEM_SHUTDOWN]
        )
        
        # Processing error strategies
        self.strategy_manager.set_recovery_strategy(
            ErrorType.PROCESSING_ERROR, ErrorSeverity.LOW,
            [RecoveryAction.SKIP_FRAME, RecoveryAction.RETRY]
        )
        self.strategy_manager.set_recovery_strategy(
            ErrorType.PROCESSING_ERROR, ErrorSeverity.MEDIUM,
            [RecoveryAction.DEGRADE_PERFORMANCE, RecoveryAction.SKIP_FRAME]
        )
        self.strategy_manager.set_recovery_strategy(
            ErrorType.PROCESSING_ERROR, ErrorSeverity.HIGH,
            [RecoveryAction.RESTART_COMPONENT, RecoveryAction.DEGRADE_PERFORMANCE]
        )
        self.strategy_manager.set_recovery_strategy(
            ErrorType.PROCESSING_ERROR, ErrorSeverity.CRITICAL,
            [RecoveryAction.RESTART_COMPONENT, RecoveryAction.FALLBACK_CONFIG]
        )
        
        # System error strategies
        self.strategy_manager.set_recovery_strategy(
            ErrorType.SYSTEM_ERROR, ErrorSeverity.LOW,
            [RecoveryAction.FALLBACK_CONFIG, RecoveryAction.RETRY]
        )
        self.strategy_manager.set_recovery_strategy(
            ErrorType.SYSTEM_ERROR, ErrorSeverity.MEDIUM,
            [RecoveryAction.RESTART_COMPONENT, RecoveryAction.FALLBACK_CONFIG]
        )
        self.strategy_manager.set_recovery_strategy(
            ErrorType.SYSTEM_ERROR, ErrorSeverity.HIGH,
            [RecoveryAction.RESTART_COMPONENT, RecoveryAction.MANUAL_INTERVENTION]
        )
        self.strategy_manager.set_recovery_strategy(
            ErrorType.SYSTEM_ERROR, ErrorSeverity.CRITICAL,
            [RecoveryAction.MANUAL_INTERVENTION, RecoveryAction.SYSTEM_SHUTDOWN]
        )
    
    def handle_error(self, exception: Exception, context: ErrorContext) -> str:
        """
        Main error handling entry point - classifies, logs, and attempts recovery
        """
        if not self.enabled:
            return ""
        
        start_time = time.perf_counter()
        
        try:
            # Generate unique error ID
            error_id = f"ERR_{int(time.time() * 1000)}_{self.error_count}"
            self.error_count += 1
            
            # Classify error
            error_type, severity = self.classifier.classify_error(exception, context)
            
            # Get recovery strategy
            recovery_actions = self.strategy_manager.get_recovery_strategy(error_type, severity)
            
            # Create error record
            error_record = ErrorRecord(
                error_id=error_id,
                error_type=error_type,
                severity=severity,
                exception=exception,
                context=context,
                error_message=str(exception),
                recovery_actions=recovery_actions
            )
            
            # Determine affected components and impact scope
            self._assess_error_impact(error_record)
            
            # Log error
            self.logger.log_error(error_record)
            
            # Send notifications
            self.notifier.notify_error(error_record)
            
            # Attempt recovery
            recovery_success = self._attempt_recovery(error_record)
            
            # Record recovery result for learning
            if error_record.recovery_attempted:
                for action in error_record.recovery_attempted:
                    self.strategy_manager.record_recovery_result(
                        error_type, action, recovery_success, 
                        error_record.recovery_time_ms or 0
                    )
            
            # Calculate processing time
            processing_time = (time.perf_counter() - start_time) * 1000
            
            log_system(
                f"Error handling completed for {error_id}",
                error_type=error_type.value,
                severity=severity.value,
                recovery_success=recovery_success,
                processing_time_ms=processing_time
            )
            
            return error_id
        
        except Exception as handling_error:
            log_error("Error in error handling system", handling_error)
            return ""
    
    def _assess_error_impact(self, error_record: ErrorRecord):
        """Assess error impact on system components"""
        component_name = error_record.context.component_name
        error_type = error_record.error_type
        severity = error_record.severity
        
        # Determine affected components
        affected_components = [component_name]
        
        # Expand based on error type and severity
        if error_type == ErrorType.HARDWARE_ERROR and severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            # Hardware errors can affect multiple components
            affected_components.extend(['device_manager', 'audio_capture', 'buffer_management'])
        
        elif error_type == ErrorType.SYSTEM_ERROR and severity == ErrorSeverity.CRITICAL:
            # Critical system errors affect everything
            affected_components.extend(['all_components'])
        
        error_record.affected_components = list(set(affected_components))
        
        # Determine impact scope
        if severity == ErrorSeverity.CRITICAL or 'all_components' in affected_components:
            error_record.impact_scope = 'global'
        elif len(affected_components) > 2:
            error_record.impact_scope = 'system'
        elif len(affected_components) > 1:
            error_record.impact_scope = 'component'
        else:
            error_record.impact_scope = 'local'
    
    def _attempt_recovery(self, error_record: ErrorRecord) -> bool:
        """Attempt error recovery using appropriate handler"""
        recovery_start_time = time.perf_counter()
        
        # Find appropriate handler
        handler = None
        for h in self.error_handlers:
            if h.can_handle(error_record):
                handler = h
                break
        
        if not handler:
            log_system(f"No handler found for error type {error_record.error_type.value}")
            return False
        
        # Attempt recovery
        try:
            recovery_success = handler.handle_error(error_record)
            
            # Calculate recovery time
            recovery_time = (time.perf_counter() - recovery_start_time) * 1000
            error_record.recovery_time_ms = recovery_time
            
            # Log recovery attempt
            for action in error_record.recovery_attempted:
                self.logger.log_recovery_attempt(
                    error_record.error_id, action, recovery_success, recovery_time
                )
            
            if recovery_success:
                self.recovery_count += 1
                log_system(f"Recovery successful for error {error_record.error_id}")
            else:
                log_system(f"Recovery failed for error {error_record.error_id}")
            
            return recovery_success
        
        except Exception as recovery_error:
            log_error(f"Recovery attempt failed for error {error_record.error_id}", recovery_error)
            return False
    
    def register_recovery_callback(self, error_type: ErrorType, action: RecoveryAction, 
                                 callback: Callable):
        """Register recovery callback for specific error type and action"""
        for handler in self.error_handlers:
            if ((error_type == ErrorType.HARDWARE_ERROR and isinstance(handler, HardwareErrorHandler)) or
                (error_type == ErrorType.PROCESSING_ERROR and isinstance(handler, ProcessingErrorHandler)) or
                (error_type == ErrorType.SYSTEM_ERROR and isinstance(handler, SystemErrorHandler))):
                handler.register_recovery_callback(action, callback)
    
    def add_notification_channel(self, channel_name: str, handler: Callable[[Dict[str, Any]], bool]):
        """Add custom notification channel"""
        self.notifier.register_notification_channel(channel_name, handler)
    
    def set_notification_webhook(self, webhook_url: str, severities: List[ErrorSeverity] = None):
        """Setup webhook notifications"""
        webhook_handler = self.notifier.create_webhook_notification_handler(webhook_url)
        self.notifier.register_notification_channel('webhook', webhook_handler)
        
        # Add webhook to notification rules
        if severities is None:
            severities = [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]
        
        for severity in severities:
            if severity in self.notifier.notification_rules:
                self.notifier.notification_rules[severity]['channels'].append('webhook')
            else:
                self.notifier.set_notification_rule(severity, ['webhook'])
    
    def get_system_health_report(self) -> Dict[str, Any]:
        """Get comprehensive system health report"""
        return {
            'error_handling_enabled': self.enabled,
            'total_errors_handled': self.error_count,
            'successful_recoveries': self.recovery_count,
            'recovery_success_rate': self.recovery_count / max(1, self.error_count),
            'error_frequency': self.statistics.get_error_frequency(),
            'recovery_success_rates': self.statistics.get_recovery_success_rate(),
            'system_availability': self.statistics.get_system_availability(),
            'component_stats': self.statistics.get_component_error_stats(),
            'strategy_effectiveness': self.strategy_manager.get_strategy_effectiveness_report(),
            'recent_errors': len(self.logger.get_recent_errors(1)),  # Last hour
            'timestamp': datetime.now().isoformat()
        }
    
    def enable_adaptive_learning(self, enabled: bool = True):
        """Enable or disable adaptive learning for recovery strategies"""
        self.strategy_manager.adaptive_learning_enabled = enabled
    
    def cleanup_old_data(self, days: int = 30):
        """Clean up old error logs and statistics"""
        self.logger.cleanup_old_logs(days)
        self.statistics.clear_cache()
    
    def shutdown(self):
        """Shutdown error handling system gracefully"""
        log_system("Shutting down error handling system")
        
        # Disable new error handling
        self.enabled = False
        
        # Clean up handlers
        for handler in self.error_handlers:
            if hasattr(handler, 'cleanup'):
                handler.cleanup()
        
        # Final statistics
        final_report = self.get_system_health_report()
        log_system("Final error handling report", **final_report)


# Convenience functions for easy integration
_global_error_system: Optional[ErrorHandlingSystem] = None


def initialize_error_handling(log_dir: Path = Path("logs")) -> ErrorHandlingSystem:
    """Initialize global error handling system"""
    global _global_error_system
    _global_error_system = ErrorHandlingSystem(log_dir)
    return _global_error_system


def get_error_system() -> Optional[ErrorHandlingSystem]:
    """Get global error handling system"""
    return _global_error_system


def handle_error(exception: Exception, component_name: str, operation: str = "", 
                **context_data) -> str:
    """Convenience function to handle errors"""
    if _global_error_system is None:
        log_error(f"Error handling system not initialized: {exception}")
        return ""
    
    context = ErrorContext(
        component_name=component_name,
        operation=operation,
        additional_data=context_data
    )
    
    return _global_error_system.handle_error(exception, context)


def register_recovery_callback(error_type: ErrorType, action: RecoveryAction, 
                             callback: Callable):
    """Register recovery callback with global error system"""
    if _global_error_system:
        _global_error_system.register_recovery_callback(error_type, action, callback)


def get_error_statistics() -> Dict[str, Any]:
    """Get error statistics from global system"""
    if _global_error_system:
        return _global_error_system.get_system_health_report()
    return {}


# Context manager for error handling
class ErrorHandlingContext:
    """Context manager for automatic error handling"""
    
    def __init__(self, component_name: str, operation: str = "", **context_data):
        self.component_name = component_name
        self.operation = operation
        self.context_data = context_data
        self.error_id = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.error_id = handle_error(exc_val, self.component_name, self.operation, **self.context_data)
            # Return False to re-raise the exception
            return False
        return True


# Decorator for automatic error handling
def with_error_handling(component_name: str, operation: str = ""):
    """Decorator for automatic error handling"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                handle_error(e, component_name, operation or func.__name__)
                raise
        return wrapper
    return decorator