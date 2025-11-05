"""
Hardware Abstraction Layer

Unified hardware interface abstraction with delay compensation, clock synchronization,
error handling, auto recovery, and device performance monitoring.

Implements requirements: 2.4, 4.1, 4.2, 4.3, 5.2
"""

import threading
import time
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import numpy as np

from .models import AudioDevice, AudioFrame, ProcessingMetrics
from .interfaces import IPluggableComponent, ComponentState


class ClockSyncStatus(Enum):
    """Clock synchronization status"""
    SYNCED = "synced"
    SYNCING = "syncing"
    DRIFT_DETECTED = "drift_detected"
    SYNC_LOST = "sync_lost"
    ERROR = "error"


class RecoveryAction(Enum):
    """Auto recovery actions"""
    RESTART_DEVICE = "restart_device"
    RESET_BUFFERS = "reset_buffers"
    RECALIBRATE_TIMING = "recalibrate_timing"
    SWITCH_FALLBACK = "switch_fallback"
    NOTIFY_USER = "notify_user"


@dataclass
class TimingInfo:
    """Device timing and synchronization information"""
    device_id: str
    sample_rate: int
    buffer_size: int
    
    # Latency measurements
    input_latency_ms: float = 0.0
    output_latency_ms: float = 0.0
    round_trip_latency_ms: float = 0.0
    
    # Clock synchronization
    clock_drift_ppm: float = 0.0  # parts per million
    sync_status: ClockSyncStatus = ClockSyncStatus.SYNCING
    last_sync_time: datetime = field(default_factory=datetime.now)
    
    # Timing statistics
    jitter_ms: float = 0.0
    max_jitter_ms: float = 0.0
    avg_processing_time_ms: float = 0.0
    
    # Buffer management
    buffer_underruns: int = 0
    buffer_overruns: int = 0
    dropped_frames: int = 0


@dataclass
class PerformanceMetrics:
    """Device performance monitoring metrics"""
    device_id: str
    
    # CPU and memory usage
    cpu_usage_percent: float = 0.0
    memory_usage_mb: float = 0.0
    
    # Audio quality metrics
    signal_level_db: float = -60.0
    noise_floor_db: float = -80.0
    snr_db: float = 0.0
    thd_percent: float = 0.0
    
    # Throughput metrics
    frames_per_second: float = 0.0
    bytes_per_second: float = 0.0
    
    # Error statistics
    error_count: int = 0
    warning_count: int = 0
    recovery_count: int = 0
    
    # Timestamps
    last_update: datetime = field(default_factory=datetime.now)
    measurement_duration: timedelta = field(default_factory=lambda: timedelta(seconds=1))


@dataclass
class ErrorInfo:
    """Error information for recovery system"""
    error_type: str
    error_message: str
    device_id: str
    timestamp: datetime
    severity: str  # "low", "medium", "high", "critical"
    recovery_attempted: bool = False
    recovery_successful: bool = False
    recovery_action: Optional[RecoveryAction] = None


class IHardwareDevice(ABC):
    """Abstract interface for hardware device abstraction"""
    
    @abstractmethod
    def get_device_info(self) -> AudioDevice:
        """Get device information"""
        pass
    
    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize device with configuration"""
        pass
    
    @abstractmethod
    def start(self) -> bool:
        """Start device operation"""
        pass
    
    @abstractmethod
    def stop(self) -> bool:
        """Stop device operation"""
        pass
    
    @abstractmethod
    def read_frame(self) -> Optional[AudioFrame]:
        """Read audio frame from input device"""
        pass
    
    @abstractmethod
    def write_frame(self, frame: AudioFrame) -> bool:
        """Write audio frame to output device"""
        pass
    
    @abstractmethod
    def get_timing_info(self) -> TimingInfo:
        """Get device timing information"""
        pass
    
    @abstractmethod
    def get_performance_metrics(self) -> PerformanceMetrics:
        """Get device performance metrics"""
        pass
    
    @abstractmethod
    def calibrate_timing(self) -> bool:
        """Calibrate device timing"""
        pass
    
    @abstractmethod
    def reset_buffers(self) -> bool:
        """Reset device buffers"""
        pass


class DelayCompensator:
    """Delay compensation system for multi-device synchronization"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._device_delays: Dict[str, float] = {}
        self._reference_device: Optional[str] = None
        self._compensation_enabled = True
    
    def set_reference_device(self, device_id: str):
        """Set reference device for delay compensation"""
        self._reference_device = device_id
        self.logger.info(f"Set reference device for delay compensation: {device_id}")
    
    def measure_device_delay(self, device_id: str, timing_info: TimingInfo) -> float:
        """Measure and store device delay"""
        # Calculate total device delay
        total_delay = timing_info.input_latency_ms + timing_info.output_latency_ms
        
        # Store delay measurement
        self._device_delays[device_id] = total_delay
        
        self.logger.debug(f"Measured delay for {device_id}: {total_delay:.2f}ms")
        return total_delay
    
    def calculate_compensation_delay(self, device_id: str) -> float:
        """Calculate compensation delay for device"""
        if not self._compensation_enabled or not self._reference_device:
            return 0.0
        
        device_delay = self._device_delays.get(device_id, 0.0)
        reference_delay = self._device_delays.get(self._reference_device, 0.0)
        
        # Compensation delay = reference delay - device delay
        compensation = reference_delay - device_delay
        
        # Only apply positive compensation (don't advance audio)
        return max(0.0, compensation)
    
    def get_all_delays(self) -> Dict[str, float]:
        """Get all measured device delays"""
        return self._device_delays.copy()
    
    def enable_compensation(self, enabled: bool):
        """Enable or disable delay compensation"""
        self._compensation_enabled = enabled
        self.logger.info(f"Delay compensation {'enabled' if enabled else 'disabled'}")


class ClockSynchronizer:
    """Clock synchronization system for precise timing"""
    
    def __init__(self, sync_interval: float = 1.0):
        self.sync_interval = sync_interval
        self.logger = logging.getLogger(__name__)
        self._master_clock: Optional[str] = None
        self._device_clocks: Dict[str, TimingInfo] = {}
        self._sync_active = False
        self._sync_thread: Optional[threading.Thread] = None
        self._sync_callbacks: List[Callable[[str, ClockSyncStatus], None]] = []
    
    def set_master_clock(self, device_id: str):
        """Set master clock device"""
        self._master_clock = device_id
        self.logger.info(f"Set master clock device: {device_id}")
    
    def register_device_clock(self, device_id: str, timing_info: TimingInfo):
        """Register device clock for synchronization"""
        self._device_clocks[device_id] = timing_info
        
        # Set first device as master if none set
        if not self._master_clock:
            self.set_master_clock(device_id)
    
    def start_synchronization(self):
        """Start clock synchronization"""
        if self._sync_active:
            return
        
        self._sync_active = True
        self._sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._sync_thread.start()
        
        self.logger.info("Started clock synchronization")
    
    def stop_synchronization(self):
        """Stop clock synchronization"""
        self._sync_active = False
        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_thread.join(timeout=1.0)
        
        self.logger.info("Stopped clock synchronization")
    
    def _sync_loop(self):
        """Main synchronization loop"""
        while self._sync_active:
            try:
                self._perform_sync_check()
                time.sleep(self.sync_interval)
            except Exception as e:
                self.logger.error(f"Error in sync loop: {e}")
                time.sleep(0.1)
    
    def _perform_sync_check(self):
        """Perform synchronization check for all devices"""
        if not self._master_clock or self._master_clock not in self._device_clocks:
            return
        
        master_timing = self._device_clocks[self._master_clock]
        
        for device_id, timing_info in self._device_clocks.items():
            if device_id == self._master_clock:
                continue
            
            # Calculate clock drift
            drift = self._calculate_clock_drift(master_timing, timing_info)
            timing_info.clock_drift_ppm = drift
            
            # Update sync status
            old_status = timing_info.sync_status
            if abs(drift) < 10:  # Within 10 ppm
                timing_info.sync_status = ClockSyncStatus.SYNCED
            elif abs(drift) < 50:  # Within 50 ppm
                timing_info.sync_status = ClockSyncStatus.DRIFT_DETECTED
            else:
                timing_info.sync_status = ClockSyncStatus.SYNC_LOST
            
            timing_info.last_sync_time = datetime.now()
            
            # Notify callbacks if status changed
            if old_status != timing_info.sync_status:
                self._notify_sync_callbacks(device_id, timing_info.sync_status)
    
    def _calculate_clock_drift(self, master: TimingInfo, device: TimingInfo) -> float:
        """Calculate clock drift in parts per million"""
        # Simplified drift calculation - in real implementation would use
        # actual timestamp comparisons and sample counting
        
        # Mock calculation based on sample rates
        expected_rate = master.sample_rate
        actual_rate = device.sample_rate
        
        if expected_rate == 0:
            return 0.0
        
        drift_ratio = (actual_rate - expected_rate) / expected_rate
        return drift_ratio * 1_000_000  # Convert to ppm
    
    def register_sync_callback(self, callback: Callable[[str, ClockSyncStatus], None]):
        """Register callback for sync status changes"""
        self._sync_callbacks.append(callback)
    
    def _notify_sync_callbacks(self, device_id: str, status: ClockSyncStatus):
        """Notify sync callbacks"""
        for callback in self._sync_callbacks:
            try:
                callback(device_id, status)
            except Exception as e:
                self.logger.error(f"Error in sync callback: {e}")


class ErrorRecoverySystem:
    """Automatic error recovery system"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._error_history: List[ErrorInfo] = []
        self._recovery_strategies: Dict[str, List[RecoveryAction]] = {
            "buffer_underrun": [RecoveryAction.RESET_BUFFERS, RecoveryAction.RECALIBRATE_TIMING],
            "buffer_overrun": [RecoveryAction.RESET_BUFFERS, RecoveryAction.RECALIBRATE_TIMING],
            "sync_lost": [RecoveryAction.RECALIBRATE_TIMING, RecoveryAction.RESTART_DEVICE],
            "device_error": [RecoveryAction.RESTART_DEVICE, RecoveryAction.SWITCH_FALLBACK],
            "critical_error": [RecoveryAction.NOTIFY_USER]
        }
        self._recovery_callbacks: List[Callable[[ErrorInfo, RecoveryAction], bool]] = []
        self._max_recovery_attempts = 3
    
    def report_error(self, error_type: str, error_message: str, device_id: str, severity: str = "medium") -> bool:
        """Report error and attempt recovery"""
        error_info = ErrorInfo(
            error_type=error_type,
            error_message=error_message,
            device_id=device_id,
            timestamp=datetime.now(),
            severity=severity
        )
        
        self._error_history.append(error_info)
        self.logger.warning(f"Error reported: {error_type} on {device_id}: {error_message}")
        
        # Attempt recovery if not critical
        if severity != "critical":
            return self._attempt_recovery(error_info)
        
        return False
    
    def _attempt_recovery(self, error_info: ErrorInfo) -> bool:
        """Attempt automatic recovery"""
        recovery_actions = self._recovery_strategies.get(error_info.error_type, [])
        
        for action in recovery_actions:
            if self._get_error_count(error_info.device_id, error_info.error_type) > self._max_recovery_attempts:
                self.logger.error(f"Max recovery attempts exceeded for {error_info.device_id}")
                break
            
            error_info.recovery_attempted = True
            error_info.recovery_action = action
            
            # Execute recovery action through callbacks
            success = self._execute_recovery_action(error_info, action)
            
            if success:
                error_info.recovery_successful = True
                self.logger.info(f"Recovery successful: {action.value} for {error_info.device_id}")
                return True
            else:
                self.logger.warning(f"Recovery failed: {action.value} for {error_info.device_id}")
        
        return False
    
    def _execute_recovery_action(self, error_info: ErrorInfo, action: RecoveryAction) -> bool:
        """Execute recovery action through registered callbacks"""
        for callback in self._recovery_callbacks:
            try:
                if callback(error_info, action):
                    return True
            except Exception as e:
                self.logger.error(f"Error in recovery callback: {e}")
        
        return False
    
    def _get_error_count(self, device_id: str, error_type: str) -> int:
        """Get error count for device and error type in recent history"""
        recent_time = datetime.now() - timedelta(minutes=5)
        count = 0
        
        for error in self._error_history:
            if (error.device_id == device_id and 
                error.error_type == error_type and 
                error.timestamp > recent_time):
                count += 1
        
        return count
    
    def register_recovery_callback(self, callback: Callable[[ErrorInfo, RecoveryAction], bool]):
        """Register recovery action callback"""
        self._recovery_callbacks.append(callback)
    
    def get_error_history(self, device_id: Optional[str] = None, limit: int = 100) -> List[ErrorInfo]:
        """Get error history"""
        errors = self._error_history
        
        if device_id:
            errors = [e for e in errors if e.device_id == device_id]
        
        return errors[-limit:] if limit > 0 else errors


class PerformanceMonitor:
    """Device performance monitoring system"""
    
    def __init__(self, monitor_interval: float = 1.0):
        self.monitor_interval = monitor_interval
        self.logger = logging.getLogger(__name__)
        self._metrics: Dict[str, PerformanceMetrics] = {}
        self._monitoring_active = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._performance_callbacks: List[Callable[[str, PerformanceMetrics], None]] = []
        self._devices: Dict[str, IHardwareDevice] = {}
    
    def register_device(self, device_id: str, device: IHardwareDevice):
        """Register device for performance monitoring"""
        self._devices[device_id] = device
        self._metrics[device_id] = PerformanceMetrics(device_id=device_id)
    
    def start_monitoring(self):
        """Start performance monitoring"""
        if self._monitoring_active:
            return
        
        self._monitoring_active = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        
        self.logger.info("Started performance monitoring")
    
    def stop_monitoring(self):
        """Stop performance monitoring"""
        self._monitoring_active = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)
        
        self.logger.info("Stopped performance monitoring")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self._monitoring_active:
            try:
                for device_id, device in self._devices.items():
                    self._update_device_metrics(device_id, device)
                
                time.sleep(self.monitor_interval)
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(0.1)
    
    def _update_device_metrics(self, device_id: str, device: IHardwareDevice):
        """Update metrics for a specific device"""
        try:
            # Get current metrics from device
            device_metrics = device.get_performance_metrics()
            
            # Update stored metrics
            stored_metrics = self._metrics[device_id]
            stored_metrics.cpu_usage_percent = device_metrics.cpu_usage_percent
            stored_metrics.memory_usage_mb = device_metrics.memory_usage_mb
            stored_metrics.signal_level_db = device_metrics.signal_level_db
            stored_metrics.noise_floor_db = device_metrics.noise_floor_db
            stored_metrics.snr_db = device_metrics.snr_db
            stored_metrics.thd_percent = device_metrics.thd_percent
            stored_metrics.frames_per_second = device_metrics.frames_per_second
            stored_metrics.bytes_per_second = device_metrics.bytes_per_second
            stored_metrics.last_update = datetime.now()
            
            # Notify callbacks
            for callback in self._performance_callbacks:
                try:
                    callback(device_id, stored_metrics)
                except Exception as e:
                    self.logger.error(f"Error in performance callback: {e}")
                    
        except Exception as e:
            self.logger.error(f"Error updating metrics for {device_id}: {e}")
    
    def get_device_metrics(self, device_id: str) -> Optional[PerformanceMetrics]:
        """Get performance metrics for device"""
        return self._metrics.get(device_id)
    
    def get_all_metrics(self) -> Dict[str, PerformanceMetrics]:
        """Get all device performance metrics"""
        return self._metrics.copy()
    
    def register_performance_callback(self, callback: Callable[[str, PerformanceMetrics], None]):
        """Register performance monitoring callback"""
        self._performance_callbacks.append(callback)


class HardwareAbstractionLayer(IPluggableComponent):
    """
    Unified hardware abstraction layer with delay compensation, clock synchronization,
    error handling, auto recovery, and device performance monitoring.
    
    Implements requirements: 2.4, 4.1, 4.2, 4.3, 5.2
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._state = ComponentState.UNINITIALIZED
        
        # Core systems
        self._delay_compensator = DelayCompensator()
        self._clock_synchronizer = ClockSynchronizer()
        self._error_recovery = ErrorRecoverySystem()
        self._performance_monitor = PerformanceMonitor()
        
        # Device management
        self._devices: Dict[str, IHardwareDevice] = {}
        self._device_configs: Dict[str, Dict[str, Any]] = {}
        
        # Setup internal callbacks
        self._setup_callbacks()
    
    def _setup_callbacks(self):
        """Setup internal system callbacks"""
        # Clock sync callbacks
        self._clock_synchronizer.register_sync_callback(self._on_sync_status_changed)
        
        # Error recovery callbacks
        self._error_recovery.register_recovery_callback(self._on_recovery_action)
        
        # Performance monitoring callbacks
        self._performance_monitor.register_performance_callback(self._on_performance_update)
    
    # IPluggableComponent interface
    
    def get_component_info(self):
        """Get component information"""
        from .interfaces import ComponentInfo
        return ComponentInfo(
            component_id="hardware_abstraction_layer",
            name="Hardware Abstraction Layer",
            version="1.0.0",
            description="Unified hardware interface with timing, sync, and recovery",
            author="Production Audio System",
            category="hardware_interface"
        )
    
    def get_state(self) -> ComponentState:
        """Get current component state"""
        return self._state
    
    def init(self, config: Dict[str, Any]) -> bool:
        """Initialize hardware abstraction layer"""
        try:
            self._state = ComponentState.INITIALIZING
            
            # Initialize subsystems
            self._delay_compensator.enable_compensation(config.get("enable_delay_compensation", True))
            
            self._state = ComponentState.READY
            self.logger.info("Hardware abstraction layer initialized")
            return True
            
        except Exception as e:
            self._state = ComponentState.ERROR
            self.logger.error(f"HAL initialization failed: {e}")
            return False
    
    def start(self) -> bool:
        """Start hardware abstraction layer"""
        if self._state != ComponentState.READY:
            return False
        
        try:
            # Start subsystems
            self._clock_synchronizer.start_synchronization()
            self._performance_monitor.start_monitoring()
            
            self._state = ComponentState.RUNNING
            self.logger.info("Hardware abstraction layer started")
            return True
            
        except Exception as e:
            self._state = ComponentState.ERROR
            self.logger.error(f"Failed to start HAL: {e}")
            return False
    
    def pause(self) -> bool:
        """Pause hardware abstraction layer"""
        if self._state == ComponentState.RUNNING:
            self._state = ComponentState.PAUSED
            return True
        return False
    
    def resume(self) -> bool:
        """Resume hardware abstraction layer"""
        if self._state == ComponentState.PAUSED:
            self._state = ComponentState.RUNNING
            return True
        return False
    
    def stop(self) -> bool:
        """Stop hardware abstraction layer"""
        try:
            # Stop subsystems
            self._clock_synchronizer.stop_synchronization()
            self._performance_monitor.stop_monitoring()
            
            # Stop all devices
            for device in self._devices.values():
                device.stop()
            
            self._state = ComponentState.STOPPED
            self.logger.info("Hardware abstraction layer stopped")
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping HAL: {e}")
            return False
    
    def cleanup(self) -> bool:
        """Clean up hardware abstraction layer"""
        try:
            self.stop()
            self._devices.clear()
            self._device_configs.clear()
            return True
        except Exception as e:
            self.logger.error(f"Error during HAL cleanup: {e}")
            return False
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get hardware abstraction layer health status"""
        return {
            "status": "healthy" if self._state == ComponentState.RUNNING else "degraded",
            "state": self._state.value,
            "device_count": len(self._devices),
            "active_devices": len([d for d in self._devices.values() if hasattr(d, '_active') and d._active]),
            "sync_status": "active" if self._clock_synchronizer._sync_active else "inactive",
            "monitoring_status": "active" if self._performance_monitor._monitoring_active else "inactive",
            "last_check": datetime.now().isoformat()
        }
    
    def handle_error(self, error: Exception) -> bool:
        """Handle component errors"""
        self.logger.error(f"HAL error: {error}")
        self._state = ComponentState.ERROR
        return False
    
    # Device management methods
    
    def register_device(self, device_id: str, device: IHardwareDevice, config: Dict[str, Any]) -> bool:
        """Register hardware device with HAL"""
        try:
            # Initialize device
            if not device.initialize(config):
                self.logger.error(f"Failed to initialize device: {device_id}")
                return False
            
            # Register with subsystems
            self._devices[device_id] = device
            self._device_configs[device_id] = config
            
            # Register with performance monitor
            self._performance_monitor.register_device(device_id, device)
            
            # Register timing info with clock synchronizer
            timing_info = device.get_timing_info()
            self._clock_synchronizer.register_device_clock(device_id, timing_info)
            
            # Measure delay for compensation
            self._delay_compensator.measure_device_delay(device_id, timing_info)
            
            self.logger.info(f"Registered device: {device_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error registering device {device_id}: {e}")
            return False
    
    def unregister_device(self, device_id: str) -> bool:
        """Unregister hardware device from HAL"""
        try:
            if device_id in self._devices:
                device = self._devices[device_id]
                device.stop()
                del self._devices[device_id]
                del self._device_configs[device_id]
                
                self.logger.info(f"Unregistered device: {device_id}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error unregistering device {device_id}: {e}")
            return False
    
    def get_device(self, device_id: str) -> Optional[IHardwareDevice]:
        """Get registered hardware device"""
        return self._devices.get(device_id)
    
    def get_all_devices(self) -> Dict[str, IHardwareDevice]:
        """Get all registered devices"""
        return self._devices.copy()
    
    # Timing and synchronization methods
    
    def set_master_clock(self, device_id: str) -> bool:
        """Set master clock device for synchronization"""
        if device_id in self._devices:
            self._clock_synchronizer.set_master_clock(device_id)
            self._delay_compensator.set_reference_device(device_id)
            return True
        return False
    
    def get_device_timing(self, device_id: str) -> Optional[TimingInfo]:
        """Get device timing information"""
        device = self._devices.get(device_id)
        if device:
            return device.get_timing_info()
        return None
    
    def calibrate_device_timing(self, device_id: str) -> bool:
        """Calibrate device timing"""
        device = self._devices.get(device_id)
        if device:
            return device.calibrate_timing()
        return False
    
    def get_compensation_delay(self, device_id: str) -> float:
        """Get delay compensation for device"""
        return self._delay_compensator.calculate_compensation_delay(device_id)
    
    # Performance monitoring methods
    
    def get_device_performance(self, device_id: str) -> Optional[PerformanceMetrics]:
        """Get device performance metrics"""
        return self._performance_monitor.get_device_metrics(device_id)
    
    def get_all_performance_metrics(self) -> Dict[str, PerformanceMetrics]:
        """Get all device performance metrics"""
        return self._performance_monitor.get_all_metrics()
    
    # Error handling methods
    
    def report_device_error(self, device_id: str, error_type: str, error_message: str, severity: str = "medium") -> bool:
        """Report device error for automatic recovery"""
        return self._error_recovery.report_error(error_type, error_message, device_id, severity)
    
    def get_error_history(self, device_id: Optional[str] = None) -> List[ErrorInfo]:
        """Get error history"""
        return self._error_recovery.get_error_history(device_id)
    
    # Internal callback handlers
    
    def _on_sync_status_changed(self, device_id: str, status: ClockSyncStatus):
        """Handle clock sync status changes"""
        self.logger.info(f"Clock sync status changed for {device_id}: {status.value}")
        
        if status == ClockSyncStatus.SYNC_LOST:
            self.report_device_error(device_id, "sync_lost", "Clock synchronization lost", "high")
    
    def _on_recovery_action(self, error_info: ErrorInfo, action: RecoveryAction) -> bool:
        """Handle recovery actions"""
        device_id = error_info.device_id
        device = self._devices.get(device_id)
        
        if not device:
            return False
        
        try:
            if action == RecoveryAction.RESTART_DEVICE:
                device.stop()
                time.sleep(0.1)
                return device.start()
            
            elif action == RecoveryAction.RESET_BUFFERS:
                return device.reset_buffers()
            
            elif action == RecoveryAction.RECALIBRATE_TIMING:
                return device.calibrate_timing()
            
            elif action == RecoveryAction.SWITCH_FALLBACK:
                # Implementation would switch to fallback device
                self.logger.warning(f"Fallback switching not implemented for {device_id}")
                return False
            
            elif action == RecoveryAction.NOTIFY_USER:
                self.logger.critical(f"User notification required for {device_id}: {error_info.error_message}")
                return True
            
        except Exception as e:
            self.logger.error(f"Error executing recovery action {action.value}: {e}")
            return False
        
        return False
    
    def _on_performance_update(self, device_id: str, metrics: PerformanceMetrics):
        """Handle performance metric updates"""
        # Check for performance issues
        if metrics.cpu_usage_percent > 80:
            self.report_device_error(device_id, "high_cpu", f"High CPU usage: {metrics.cpu_usage_percent}%", "medium")
        
        if metrics.error_count > 0:
            self.report_device_error(device_id, "device_error", f"Device errors detected: {metrics.error_count}", "medium")


# Factory function
def create_hardware_abstraction_layer() -> HardwareAbstractionLayer:
    """Create and return a hardware abstraction layer instance"""
    return HardwareAbstractionLayer()