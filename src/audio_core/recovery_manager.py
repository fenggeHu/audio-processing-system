"""
Automatic Recovery Manager

This module implements an automatic recovery management system that handles
device disconnections, buffer anomalies, performance degradation, and integrates
with alerting and notification systems for the production audio processing system.
"""

import asyncio
import threading
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging

from .models import AudioDevice, DeviceType, SystemState, ProcessingMetrics
from .error_handling import (
    ErrorHandlingSystem, ErrorType, ErrorSeverity, RecoveryAction,
    ErrorContext, handle_error, get_error_system
)
from ..config.logging_config import log_system, log_error, log_debug


class RecoveryStatus(Enum):
    """Recovery operation status"""
    IDLE = "idle"
    MONITORING = "monitoring"
    DETECTING = "detecting"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    FAILED = "failed"


class DeviceStatus(Enum):
    """Device connection status"""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass
class DeviceMonitoringState:
    """State information for device monitoring"""
    device_id: str
    device_name: str
    status: DeviceStatus = DeviceStatus.UNKNOWN
    last_seen: datetime = field(default_factory=datetime.now)
    reconnect_attempts: int = 0
    max_reconnect_attempts: int = 5
    reconnect_delay_seconds: float = 2.0
    is_primary: bool = False
    backup_devices: List[str] = field(default_factory=list)
    
    # Health metrics
    connection_stability: float = 1.0  # 0.0 to 1.0
    error_count: int = 0
    last_error: Optional[datetime] = None
    
    def is_healthy(self) -> bool:
        """Check if device is considered healthy"""
        return (self.status == DeviceStatus.CONNECTED and 
                self.connection_stability > 0.7 and
                self.error_count < 5)
    
    def should_attempt_reconnect(self) -> bool:
        """Check if reconnection should be attempted"""
        return (self.status == DeviceStatus.DISCONNECTED and
                self.reconnect_attempts < self.max_reconnect_attempts)


@dataclass
class BufferMonitoringState:
    """State information for buffer monitoring"""
    component_name: str
    buffer_size: int
    current_usage: int = 0
    peak_usage: int = 0
    underrun_count: int = 0
    overrun_count: int = 0
    last_adjustment: Optional[datetime] = None
    
    # Thresholds
    underrun_threshold: int = 5
    overrun_threshold: int = 3
    usage_warning_threshold: float = 0.8
    usage_critical_threshold: float = 0.95
    
    def get_usage_percentage(self) -> float:
        """Get current buffer usage as percentage"""
        if self.buffer_size == 0:
            return 0.0
        return self.current_usage / self.buffer_size
    
    def needs_adjustment(self) -> bool:
        """Check if buffer needs size adjustment"""
        usage_pct = self.get_usage_percentage()
        return (self.underrun_count >= self.underrun_threshold or
                self.overrun_count >= self.overrun_threshold or
                usage_pct >= self.usage_critical_threshold)


@dataclass
class PerformanceMonitoringState:
    """State information for performance monitoring"""
    component_name: str
    target_latency_ms: float
    current_latency_ms: float = 0.0
    cpu_usage_percent: float = 0.0
    memory_usage_mb: float = 0.0
    
    # Performance thresholds
    latency_warning_threshold: float = 1.5  # 1.5x target
    latency_critical_threshold: float = 2.0  # 2x target
    cpu_warning_threshold: float = 80.0
    cpu_critical_threshold: float = 95.0
    memory_warning_threshold: float = 1024.0  # 1GB
    memory_critical_threshold: float = 2048.0  # 2GB
    
    # Degradation levels
    degradation_level: int = 0  # 0 = normal, 1-3 = increasing degradation
    max_degradation_level: int = 3
    
    def get_performance_score(self) -> float:
        """Calculate overall performance score (0.0 to 1.0)"""
        latency_score = min(1.0, self.target_latency_ms / max(self.current_latency_ms, 0.1))
        cpu_score = max(0.0, (100.0 - self.cpu_usage_percent) / 100.0)
        memory_score = max(0.0, 1.0 - (self.memory_usage_mb / self.memory_critical_threshold))
        
        return (latency_score + cpu_score + memory_score) / 3.0
    
    def needs_degradation(self) -> bool:
        """Check if performance degradation is needed"""
        return (self.current_latency_ms > self.target_latency_ms * self.latency_critical_threshold or
                self.cpu_usage_percent > self.cpu_critical_threshold or
                self.memory_usage_mb > self.memory_critical_threshold)
    
    def can_restore_performance(self) -> bool:
        """Check if performance can be restored to higher level"""
        return (self.degradation_level > 0 and
                self.current_latency_ms < self.target_latency_ms * self.latency_warning_threshold and
                self.cpu_usage_percent < self.cpu_warning_threshold and
                self.memory_usage_mb < self.memory_warning_threshold)


class IRecoveryStrategy(ABC):
    """Interface for recovery strategies"""
    
    @abstractmethod
    async def can_handle(self, issue_type: str, context: Dict[str, Any]) -> bool:
        """Check if this strategy can handle the issue"""
        pass
    
    @abstractmethod
    async def execute_recovery(self, context: Dict[str, Any]) -> Tuple[bool, str]:
        """Execute recovery action, return (success, message)"""
        pass
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """Get strategy name"""
        pass


class DeviceReconnectionStrategy(IRecoveryStrategy):
    """Strategy for automatic device reconnection"""
    
    def __init__(self, device_manager_callback: Optional[Callable] = None):
        self.device_manager_callback = device_manager_callback
        self.reconnection_lock = asyncio.Lock()
    
    async def can_handle(self, issue_type: str, context: Dict[str, Any]) -> bool:
        """Check if this strategy handles device disconnection"""
        return issue_type == "device_disconnection"
    
    async def execute_recovery(self, context: Dict[str, Any]) -> Tuple[bool, str]:
        """Execute device reconnection"""
        device_id = context.get('device_id')
        if not device_id:
            return False, "No device ID provided"
        
        async with self.reconnection_lock:
            try:
                log_system(f"Attempting to reconnect device {device_id}")
                
                # Wait before reconnection attempt
                await asyncio.sleep(context.get('reconnect_delay', 2.0))
                
                # Call device manager to reconnect
                if self.device_manager_callback:
                    success = await self._call_device_manager(device_id, context)
                    if success:
                        return True, f"Device {device_id} reconnected successfully"
                    else:
                        return False, f"Device manager failed to reconnect {device_id}"
                else:
                    # Simulate reconnection for testing
                    return True, f"Simulated reconnection of device {device_id}"
            
            except Exception as e:
                error_msg = f"Reconnection failed for device {device_id}: {str(e)}"
                log_error(error_msg, e)
                return False, error_msg
    
    async def _call_device_manager(self, device_id: str, context: Dict[str, Any]) -> bool:
        """Call device manager to perform reconnection"""
        try:
            if self.device_manager_callback:
                if asyncio.iscoroutinefunction(self.device_manager_callback):
                    return await self.device_manager_callback(device_id, context)
                else:
                    return self.device_manager_callback(device_id, context)
            return False
        except Exception as e:
            log_error(f"Device manager callback failed", e)
            return False
    
    def get_strategy_name(self) -> str:
        return "DeviceReconnectionStrategy"


class BufferAdjustmentStrategy(IRecoveryStrategy):
    """Strategy for dynamic buffer size adjustment"""
    
    def __init__(self, buffer_manager_callback: Optional[Callable] = None):
        self.buffer_manager_callback = buffer_manager_callback
        self.adjustment_lock = asyncio.Lock()
        self.min_buffer_size = 128
        self.max_buffer_size = 4096
    
    async def can_handle(self, issue_type: str, context: Dict[str, Any]) -> bool:
        """Check if this strategy handles buffer issues"""
        return issue_type in ["buffer_underrun", "buffer_overrun", "buffer_anomaly"]
    
    async def execute_recovery(self, context: Dict[str, Any]) -> Tuple[bool, str]:
        """Execute buffer adjustment"""
        component_name = context.get('component_name')
        issue_type = context.get('issue_type')
        current_size = context.get('current_buffer_size', 512)
        
        if not component_name or not issue_type:
            return False, "Missing component name or issue type"
        
        async with self.adjustment_lock:
            try:
                new_size = self._calculate_new_buffer_size(issue_type, current_size, context)
                
                log_system(f"Adjusting buffer size for {component_name}: {current_size} -> {new_size}")
                
                # Call buffer manager to adjust size
                if self.buffer_manager_callback:
                    success = await self._call_buffer_manager(component_name, new_size, context)
                    if success:
                        return True, f"Buffer size adjusted to {new_size} for {component_name}"
                    else:
                        return False, f"Buffer manager failed to adjust size for {component_name}"
                else:
                    # Simulate adjustment for testing
                    return True, f"Simulated buffer adjustment to {new_size} for {component_name}"
            
            except Exception as e:
                error_msg = f"Buffer adjustment failed for {component_name}: {str(e)}"
                log_error(error_msg, e)
                return False, error_msg
    
    def _calculate_new_buffer_size(self, issue_type: str, current_size: int, 
                                 context: Dict[str, Any]) -> int:
        """Calculate new buffer size based on issue type"""
        if issue_type == "buffer_underrun":
            # Increase buffer size for underruns
            new_size = int(current_size * 1.5)
        elif issue_type == "buffer_overrun":
            # Decrease buffer size for overruns
            new_size = int(current_size * 0.75)
        else:  # buffer_anomaly
            # Adaptive adjustment based on usage pattern
            usage_pct = context.get('usage_percentage', 0.5)
            if usage_pct > 0.9:
                new_size = int(current_size * 1.25)
            elif usage_pct < 0.3:
                new_size = int(current_size * 0.9)
            else:
                new_size = current_size
        
        # Clamp to valid range
        return max(self.min_buffer_size, min(self.max_buffer_size, new_size))
    
    async def _call_buffer_manager(self, component_name: str, new_size: int, 
                                 context: Dict[str, Any]) -> bool:
        """Call buffer manager to adjust buffer size"""
        try:
            if self.buffer_manager_callback:
                if asyncio.iscoroutinefunction(self.buffer_manager_callback):
                    return await self.buffer_manager_callback(component_name, new_size, context)
                else:
                    return self.buffer_manager_callback(component_name, new_size, context)
            return False
        except Exception as e:
            log_error(f"Buffer manager callback failed", e)
            return False
    
    def get_strategy_name(self) -> str:
        return "BufferAdjustmentStrategy"


class PerformanceDegradationStrategy(IRecoveryStrategy):
    """Strategy for adaptive performance degradation"""
    
    def __init__(self, performance_manager_callback: Optional[Callable] = None):
        self.performance_manager_callback = performance_manager_callback
        self.degradation_lock = asyncio.Lock()
        
        # Degradation configurations
        self.degradation_configs = {
            1: {  # Level 1: Mild degradation
                'sample_rate_factor': 0.9,
                'quality_factor': 0.95,
                'processing_threads': -1,
                'description': 'Mild performance optimization'
            },
            2: {  # Level 2: Moderate degradation
                'sample_rate_factor': 0.8,
                'quality_factor': 0.85,
                'processing_threads': -2,
                'description': 'Moderate performance reduction'
            },
            3: {  # Level 3: Aggressive degradation
                'sample_rate_factor': 0.7,
                'quality_factor': 0.7,
                'processing_threads': -3,
                'description': 'Aggressive performance reduction'
            }
        }
    
    async def can_handle(self, issue_type: str, context: Dict[str, Any]) -> bool:
        """Check if this strategy handles performance issues"""
        return issue_type in ["performance_degradation", "high_latency", "high_cpu_usage", "high_memory_usage"]
    
    async def execute_recovery(self, context: Dict[str, Any]) -> Tuple[bool, str]:
        """Execute performance degradation or restoration"""
        component_name = context.get('component_name')
        action = context.get('action', 'degrade')  # 'degrade' or 'restore'
        current_level = context.get('current_degradation_level', 0)
        
        if not component_name:
            return False, "Missing component name"
        
        async with self.degradation_lock:
            try:
                if action == 'degrade':
                    new_level = min(current_level + 1, 3)
                    success, message = await self._apply_degradation(component_name, new_level, context)
                else:  # restore
                    new_level = max(current_level - 1, 0)
                    success, message = await self._restore_performance(component_name, new_level, context)
                
                return success, message
            
            except Exception as e:
                error_msg = f"Performance adjustment failed for {component_name}: {str(e)}"
                log_error(error_msg, e)
                return False, error_msg
    
    async def _apply_degradation(self, component_name: str, level: int, 
                               context: Dict[str, Any]) -> Tuple[bool, str]:
        """Apply performance degradation"""
        if level == 0:
            return True, "No degradation needed"
        
        if level not in self.degradation_configs:
            return False, f"Invalid degradation level: {level}"
        
        config = self.degradation_configs[level]
        
        log_system(f"Applying performance degradation level {level} to {component_name}: {config['description']}")
        
        # Call performance manager to apply degradation
        if self.performance_manager_callback:
            success = await self._call_performance_manager(component_name, 'degrade', level, config, context)
            if success:
                return True, f"Performance degradation level {level} applied to {component_name}"
            else:
                return False, f"Performance manager failed to apply degradation to {component_name}"
        else:
            # Simulate degradation for testing
            return True, f"Simulated performance degradation level {level} for {component_name}"
    
    async def _restore_performance(self, component_name: str, level: int, 
                                 context: Dict[str, Any]) -> Tuple[bool, str]:
        """Restore performance to specified level"""
        log_system(f"Restoring performance to level {level} for {component_name}")
        
        # Call performance manager to restore performance
        if self.performance_manager_callback:
            config = self.degradation_configs.get(level, {}) if level > 0 else {}
            success = await self._call_performance_manager(component_name, 'restore', level, config, context)
            if success:
                return True, f"Performance restored to level {level} for {component_name}"
            else:
                return False, f"Performance manager failed to restore performance for {component_name}"
        else:
            # Simulate restoration for testing
            return True, f"Simulated performance restoration to level {level} for {component_name}"
    
    async def _call_performance_manager(self, component_name: str, action: str, level: int,
                                      config: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Call performance manager to adjust performance"""
        try:
            if self.performance_manager_callback:
                params = {
                    'component_name': component_name,
                    'action': action,
                    'level': level,
                    'config': config,
                    'context': context
                }
                
                if asyncio.iscoroutinefunction(self.performance_manager_callback):
                    return await self.performance_manager_callback(params)
                else:
                    return self.performance_manager_callback(params)
            return False
        except Exception as e:
            log_error(f"Performance manager callback failed", e)
            return False
    
    def get_strategy_name(self) -> str:
        return "PerformanceDegradationStrategy"


class AutomaticRecoveryManager:
    """
    Main automatic recovery manager that coordinates all recovery strategies
    and integrates with alerting and notification systems
    """
    
    def __init__(self, error_system: Optional[ErrorHandlingSystem] = None):
        self.error_system = error_system or get_error_system()
        
        # Recovery strategies
        self.strategies: List[IRecoveryStrategy] = []
        
        # Monitoring states
        self.device_states: Dict[str, DeviceMonitoringState] = {}
        self.buffer_states: Dict[str, BufferMonitoringState] = {}
        self.performance_states: Dict[str, PerformanceMonitoringState] = {}
        
        # Recovery status
        self.recovery_status = RecoveryStatus.IDLE
        self.active_recoveries: Dict[str, Dict[str, Any]] = {}
        
        # Configuration
        self.monitoring_enabled = True
        self.monitoring_interval_seconds = 1.0
        self.recovery_timeout_seconds = 30.0
        
        # Threading
        self.monitoring_thread: Optional[threading.Thread] = None
        self.shutdown_event = threading.Event()
        
        # Callbacks for external integration
        self.device_manager_callback: Optional[Callable] = None
        self.buffer_manager_callback: Optional[Callable] = None
        self.performance_manager_callback: Optional[Callable] = None
        self.alert_callback: Optional[Callable] = None
        
        # Statistics
        self.recovery_attempts = 0
        self.successful_recoveries = 0
        self.failed_recoveries = 0
        
        # Initialize default strategies
        self._initialize_default_strategies()
    
    def _initialize_default_strategies(self):
        """Initialize default recovery strategies"""
        self.strategies = [
            DeviceReconnectionStrategy(self.device_manager_callback),
            BufferAdjustmentStrategy(self.buffer_manager_callback),
            PerformanceDegradationStrategy(self.performance_manager_callback)
        ]
    
    def set_device_manager_callback(self, callback: Callable):
        """Set device manager callback for device operations"""
        self.device_manager_callback = callback
        # Update strategy callback
        for strategy in self.strategies:
            if isinstance(strategy, DeviceReconnectionStrategy):
                strategy.device_manager_callback = callback
    
    def set_buffer_manager_callback(self, callback: Callable):
        """Set buffer manager callback for buffer operations"""
        self.buffer_manager_callback = callback
        # Update strategy callback
        for strategy in self.strategies:
            if isinstance(strategy, BufferAdjustmentStrategy):
                strategy.buffer_manager_callback = callback
    
    def set_performance_manager_callback(self, callback: Callable):
        """Set performance manager callback for performance operations"""
        self.performance_manager_callback = callback
        # Update strategy callback
        for strategy in self.strategies:
            if isinstance(strategy, PerformanceDegradationStrategy):
                strategy.performance_manager_callback = callback
    
    def set_alert_callback(self, callback: Callable):
        """Set alert callback for notifications"""
        self.alert_callback = callback
    
    def add_recovery_strategy(self, strategy: IRecoveryStrategy):
        """Add custom recovery strategy"""
        self.strategies.append(strategy)
    
    def register_device(self, device_id: str, device_name: str, is_primary: bool = False,
                       backup_devices: List[str] = None):
        """Register device for monitoring"""
        self.device_states[device_id] = DeviceMonitoringState(
            device_id=device_id,
            device_name=device_name,
            is_primary=is_primary,
            backup_devices=backup_devices or []
        )
        log_system(f"Registered device for monitoring: {device_name} ({device_id})")
    
    def register_buffer(self, component_name: str, buffer_size: int):
        """Register buffer for monitoring"""
        self.buffer_states[component_name] = BufferMonitoringState(
            component_name=component_name,
            buffer_size=buffer_size
        )
        log_system(f"Registered buffer for monitoring: {component_name} (size: {buffer_size})")
    
    def register_performance_component(self, component_name: str, target_latency_ms: float):
        """Register component for performance monitoring"""
        self.performance_states[component_name] = PerformanceMonitoringState(
            component_name=component_name,
            target_latency_ms=target_latency_ms
        )
        log_system(f"Registered performance component: {component_name} (target latency: {target_latency_ms}ms)")
    
    def start_monitoring(self):
        """Start automatic monitoring and recovery"""
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            log_system("Monitoring already running")
            return
        
        self.monitoring_enabled = True
        self.shutdown_event.clear()
        self.recovery_status = RecoveryStatus.MONITORING
        
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        
        log_system("Automatic recovery monitoring started")
    
    def stop_monitoring(self):
        """Stop automatic monitoring"""
        self.monitoring_enabled = False
        self.shutdown_event.set()
        
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=5.0)
        
        self.recovery_status = RecoveryStatus.IDLE
        log_system("Automatic recovery monitoring stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        log_system("Recovery monitoring loop started")
        
        while self.monitoring_enabled and not self.shutdown_event.is_set():
            try:
                # Monitor devices
                self._monitor_devices()
                
                # Monitor buffers
                self._monitor_buffers()
                
                # Monitor performance
                self._monitor_performance()
                
                # Sleep until next monitoring cycle
                self.shutdown_event.wait(self.monitoring_interval_seconds)
            
            except Exception as e:
                log_error("Error in monitoring loop", e)
                time.sleep(1.0)  # Brief pause before continuing
        
        log_system("Recovery monitoring loop stopped")
    
    def _monitor_devices(self):
        """Monitor device connections and trigger recovery if needed"""
        for device_id, state in self.device_states.items():
            try:
                # Check device status (this would normally query actual device manager)
                current_status = self._check_device_status(device_id)
                
                if current_status != state.status:
                    log_debug(f"Device status changed: {device_id} {state.status} -> {current_status}")
                    state.status = current_status
                    state.last_seen = datetime.now()
                
                # Handle disconnected devices
                if state.status == DeviceStatus.DISCONNECTED and state.should_attempt_reconnect():
                    asyncio.create_task(self._handle_device_disconnection(device_id, state))
            
            except Exception as e:
                log_error(f"Error monitoring device {device_id}", e)
    
    def _monitor_buffers(self):
        """Monitor buffer states and trigger adjustments if needed"""
        for component_name, state in self.buffer_states.items():
            try:
                # Update buffer metrics (this would normally query actual buffer manager)
                self._update_buffer_metrics(component_name, state)
                
                # Check if adjustment is needed
                if state.needs_adjustment():
                    asyncio.create_task(self._handle_buffer_anomaly(component_name, state))
            
            except Exception as e:
                log_error(f"Error monitoring buffer {component_name}", e)
    
    def _monitor_performance(self):
        """Monitor performance and trigger degradation/restoration if needed"""
        for component_name, state in self.performance_states.items():
            try:
                # Update performance metrics (this would normally query actual performance monitor)
                self._update_performance_metrics(component_name, state)
                
                # Check if degradation is needed
                if state.needs_degradation() and state.degradation_level < state.max_degradation_level:
                    asyncio.create_task(self._handle_performance_degradation(component_name, state))
                
                # Check if performance can be restored
                elif state.can_restore_performance():
                    asyncio.create_task(self._handle_performance_restoration(component_name, state))
            
            except Exception as e:
                log_error(f"Error monitoring performance {component_name}", e)
    
    def _check_device_status(self, device_id: str) -> DeviceStatus:
        """Check actual device status (placeholder implementation)"""
        # This would normally query the actual device manager
        # For now, simulate occasional disconnections for testing
        import random
        if random.random() < 0.01:  # 1% chance of disconnection
            return DeviceStatus.DISCONNECTED
        return DeviceStatus.CONNECTED
    
    def _update_buffer_metrics(self, component_name: str, state: BufferMonitoringState):
        """Update buffer metrics (placeholder implementation)"""
        # This would normally query the actual buffer manager
        # For now, simulate some buffer usage patterns
        import random
        state.current_usage = int(state.buffer_size * random.uniform(0.3, 0.9))
        state.peak_usage = max(state.peak_usage, state.current_usage)
        
        # Simulate occasional buffer issues
        if random.random() < 0.005:  # 0.5% chance
            if random.random() < 0.5:
                state.underrun_count += 1
            else:
                state.overrun_count += 1
    
    def _update_performance_metrics(self, component_name: str, state: PerformanceMonitoringState):
        """Update performance metrics (placeholder implementation)"""
        # This would normally query the actual performance monitor
        # For now, simulate some performance variations
        import random
        base_latency = state.target_latency_ms
        state.current_latency_ms = base_latency * random.uniform(0.8, 2.5)
        state.cpu_usage_percent = random.uniform(30.0, 95.0)
        state.memory_usage_mb = random.uniform(200.0, 1500.0)
    
    async def _handle_device_disconnection(self, device_id: str, state: DeviceMonitoringState):
        """Handle device disconnection with automatic reconnection"""
        recovery_id = f"device_reconnect_{device_id}_{int(time.time())}"
        
        try:
            self.recovery_status = RecoveryStatus.RECOVERING
            self.active_recoveries[recovery_id] = {
                'type': 'device_reconnection',
                'device_id': device_id,
                'start_time': datetime.now()
            }
            
            # Find appropriate strategy
            strategy = None
            for s in self.strategies:
                if await s.can_handle("device_disconnection", {'device_id': device_id}):
                    strategy = s
                    break
            
            if not strategy:
                log_error(f"No strategy found for device disconnection: {device_id}")
                return
            
            # Attempt recovery
            state.reconnect_attempts += 1
            state.status = DeviceStatus.RECONNECTING
            
            context = {
                'device_id': device_id,
                'reconnect_delay': state.reconnect_delay_seconds,
                'attempt': state.reconnect_attempts
            }
            
            success, message = await strategy.execute_recovery(context)
            
            if success:
                state.status = DeviceStatus.CONNECTED
                state.reconnect_attempts = 0
                state.connection_stability = min(1.0, state.connection_stability + 0.1)
                self.successful_recoveries += 1
                
                log_system(f"Device reconnection successful: {device_id}")
                await self._send_alert("device_reconnected", {
                    'device_id': device_id,
                    'message': message,
                    'attempts': state.reconnect_attempts
                })
            else:
                state.status = DeviceStatus.FAILED if state.reconnect_attempts >= state.max_reconnect_attempts else DeviceStatus.DISCONNECTED
                state.connection_stability = max(0.0, state.connection_stability - 0.2)
                self.failed_recoveries += 1
                
                log_error(f"Device reconnection failed: {device_id} - {message}")
                await self._send_alert("device_reconnection_failed", {
                    'device_id': device_id,
                    'message': message,
                    'attempts': state.reconnect_attempts
                })
        
        except Exception as e:
            log_error(f"Error handling device disconnection for {device_id}", e)
            state.status = DeviceStatus.FAILED
        
        finally:
            if recovery_id in self.active_recoveries:
                del self.active_recoveries[recovery_id]
            
            if not self.active_recoveries:
                self.recovery_status = RecoveryStatus.MONITORING
    
    async def _handle_buffer_anomaly(self, component_name: str, state: BufferMonitoringState):
        """Handle buffer anomalies with dynamic adjustment"""
        recovery_id = f"buffer_adjust_{component_name}_{int(time.time())}"
        
        try:
            self.recovery_status = RecoveryStatus.RECOVERING
            self.active_recoveries[recovery_id] = {
                'type': 'buffer_adjustment',
                'component_name': component_name,
                'start_time': datetime.now()
            }
            
            # Determine issue type
            issue_type = "buffer_anomaly"
            if state.underrun_count >= state.underrun_threshold:
                issue_type = "buffer_underrun"
            elif state.overrun_count >= state.overrun_threshold:
                issue_type = "buffer_overrun"
            
            # Find appropriate strategy
            strategy = None
            for s in self.strategies:
                if await s.can_handle(issue_type, {'component_name': component_name}):
                    strategy = s
                    break
            
            if not strategy:
                log_error(f"No strategy found for buffer issue: {component_name}")
                return
            
            # Attempt recovery
            context = {
                'component_name': component_name,
                'issue_type': issue_type,
                'current_buffer_size': state.buffer_size,
                'usage_percentage': state.get_usage_percentage(),
                'underrun_count': state.underrun_count,
                'overrun_count': state.overrun_count
            }
            
            success, message = await strategy.execute_recovery(context)
            
            if success:
                # Reset counters on successful adjustment
                state.underrun_count = 0
                state.overrun_count = 0
                state.last_adjustment = datetime.now()
                self.successful_recoveries += 1
                
                log_system(f"Buffer adjustment successful: {component_name}")
                await self._send_alert("buffer_adjusted", {
                    'component_name': component_name,
                    'message': message,
                    'issue_type': issue_type
                })
            else:
                self.failed_recoveries += 1
                log_error(f"Buffer adjustment failed: {component_name} - {message}")
                await self._send_alert("buffer_adjustment_failed", {
                    'component_name': component_name,
                    'message': message,
                    'issue_type': issue_type
                })
        
        except Exception as e:
            log_error(f"Error handling buffer anomaly for {component_name}", e)
        
        finally:
            if recovery_id in self.active_recoveries:
                del self.active_recoveries[recovery_id]
            
            if not self.active_recoveries:
                self.recovery_status = RecoveryStatus.MONITORING
    
    async def _handle_performance_degradation(self, component_name: str, state: PerformanceMonitoringState):
        """Handle performance degradation"""
        recovery_id = f"perf_degrade_{component_name}_{int(time.time())}"
        
        try:
            self.recovery_status = RecoveryStatus.RECOVERING
            self.active_recoveries[recovery_id] = {
                'type': 'performance_degradation',
                'component_name': component_name,
                'start_time': datetime.now()
            }
            
            # Find appropriate strategy
            strategy = None
            for s in self.strategies:
                if await s.can_handle("performance_degradation", {'component_name': component_name}):
                    strategy = s
                    break
            
            if not strategy:
                log_error(f"No strategy found for performance degradation: {component_name}")
                return
            
            # Attempt degradation
            context = {
                'component_name': component_name,
                'action': 'degrade',
                'current_degradation_level': state.degradation_level,
                'current_latency_ms': state.current_latency_ms,
                'target_latency_ms': state.target_latency_ms,
                'cpu_usage_percent': state.cpu_usage_percent,
                'memory_usage_mb': state.memory_usage_mb
            }
            
            success, message = await strategy.execute_recovery(context)
            
            if success:
                state.degradation_level = min(state.degradation_level + 1, state.max_degradation_level)
                self.successful_recoveries += 1
                
                log_system(f"Performance degradation applied: {component_name} (level {state.degradation_level})")
                await self._send_alert("performance_degraded", {
                    'component_name': component_name,
                    'message': message,
                    'degradation_level': state.degradation_level
                })
            else:
                self.failed_recoveries += 1
                log_error(f"Performance degradation failed: {component_name} - {message}")
        
        except Exception as e:
            log_error(f"Error handling performance degradation for {component_name}", e)
        
        finally:
            if recovery_id in self.active_recoveries:
                del self.active_recoveries[recovery_id]
            
            if not self.active_recoveries:
                self.recovery_status = RecoveryStatus.MONITORING
    
    async def _handle_performance_restoration(self, component_name: str, state: PerformanceMonitoringState):
        """Handle performance restoration"""
        recovery_id = f"perf_restore_{component_name}_{int(time.time())}"
        
        try:
            self.recovery_status = RecoveryStatus.RECOVERING
            self.active_recoveries[recovery_id] = {
                'type': 'performance_restoration',
                'component_name': component_name,
                'start_time': datetime.now()
            }
            
            # Find appropriate strategy
            strategy = None
            for s in self.strategies:
                if await s.can_handle("performance_degradation", {'component_name': component_name}):
                    strategy = s
                    break
            
            if not strategy:
                log_error(f"No strategy found for performance restoration: {component_name}")
                return
            
            # Attempt restoration
            context = {
                'component_name': component_name,
                'action': 'restore',
                'current_degradation_level': state.degradation_level,
                'current_latency_ms': state.current_latency_ms,
                'target_latency_ms': state.target_latency_ms,
                'cpu_usage_percent': state.cpu_usage_percent,
                'memory_usage_mb': state.memory_usage_mb
            }
            
            success, message = await strategy.execute_recovery(context)
            
            if success:
                state.degradation_level = max(state.degradation_level - 1, 0)
                self.successful_recoveries += 1
                
                log_system(f"Performance restored: {component_name} (level {state.degradation_level})")
                await self._send_alert("performance_restored", {
                    'component_name': component_name,
                    'message': message,
                    'degradation_level': state.degradation_level
                })
            else:
                self.failed_recoveries += 1
                log_error(f"Performance restoration failed: {component_name} - {message}")
        
        except Exception as e:
            log_error(f"Error handling performance restoration for {component_name}", e)
        
        finally:
            if recovery_id in self.active_recoveries:
                del self.active_recoveries[recovery_id]
            
            if not self.active_recoveries:
                self.recovery_status = RecoveryStatus.MONITORING
    
    async def _send_alert(self, alert_type: str, data: Dict[str, Any]):
        """Send alert through configured callback"""
        if self.alert_callback:
            try:
                alert_data = {
                    'type': alert_type,
                    'timestamp': datetime.now().isoformat(),
                    'data': data
                }
                
                if asyncio.iscoroutinefunction(self.alert_callback):
                    await self.alert_callback(alert_data)
                else:
                    self.alert_callback(alert_data)
            
            except Exception as e:
                log_error("Alert callback failed", e)
    
    def get_recovery_status(self) -> Dict[str, Any]:
        """Get current recovery system status"""
        return {
            'status': self.recovery_status.value,
            'monitoring_enabled': self.monitoring_enabled,
            'active_recoveries': len(self.active_recoveries),
            'recovery_attempts': self.recovery_attempts,
            'successful_recoveries': self.successful_recoveries,
            'failed_recoveries': self.failed_recoveries,
            'success_rate': self.successful_recoveries / max(1, self.recovery_attempts),
            'registered_devices': len(self.device_states),
            'registered_buffers': len(self.buffer_states),
            'registered_performance_components': len(self.performance_states),
            'strategies': [s.get_strategy_name() for s in self.strategies]
        }
    
    def get_device_health_report(self) -> Dict[str, Any]:
        """Get device health report"""
        device_health = {}
        
        for device_id, state in self.device_states.items():
            device_health[device_id] = {
                'name': state.device_name,
                'status': state.status.value,
                'is_healthy': state.is_healthy(),
                'connection_stability': state.connection_stability,
                'error_count': state.error_count,
                'reconnect_attempts': state.reconnect_attempts,
                'last_seen': state.last_seen.isoformat(),
                'is_primary': state.is_primary
            }
        
        return device_health
    
    def get_buffer_health_report(self) -> Dict[str, Any]:
        """Get buffer health report"""
        buffer_health = {}
        
        for component_name, state in self.buffer_states.items():
            buffer_health[component_name] = {
                'buffer_size': state.buffer_size,
                'current_usage': state.current_usage,
                'usage_percentage': state.get_usage_percentage(),
                'peak_usage': state.peak_usage,
                'underrun_count': state.underrun_count,
                'overrun_count': state.overrun_count,
                'needs_adjustment': state.needs_adjustment(),
                'last_adjustment': state.last_adjustment.isoformat() if state.last_adjustment else None
            }
        
        return buffer_health
    
    def get_performance_health_report(self) -> Dict[str, Any]:
        """Get performance health report"""
        performance_health = {}
        
        for component_name, state in self.performance_states.items():
            performance_health[component_name] = {
                'target_latency_ms': state.target_latency_ms,
                'current_latency_ms': state.current_latency_ms,
                'cpu_usage_percent': state.cpu_usage_percent,
                'memory_usage_mb': state.memory_usage_mb,
                'performance_score': state.get_performance_score(),
                'degradation_level': state.degradation_level,
                'needs_degradation': state.needs_degradation(),
                'can_restore_performance': state.can_restore_performance()
            }
        
        return performance_health
    
    def shutdown(self):
        """Shutdown recovery manager"""
        log_system("Shutting down automatic recovery manager")
        self.stop_monitoring()
        
        # Clear all states
        self.device_states.clear()
        self.buffer_states.clear()
        self.performance_states.clear()
        self.active_recoveries.clear()


# Global recovery manager instance
_global_recovery_manager: Optional[AutomaticRecoveryManager] = None


def initialize_recovery_manager(error_system: Optional[ErrorHandlingSystem] = None) -> AutomaticRecoveryManager:
    """Initialize global recovery manager"""
    global _global_recovery_manager
    _global_recovery_manager = AutomaticRecoveryManager(error_system)
    return _global_recovery_manager


def get_recovery_manager() -> Optional[AutomaticRecoveryManager]:
    """Get global recovery manager"""
    return _global_recovery_manager