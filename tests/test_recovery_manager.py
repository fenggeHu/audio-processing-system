"""
Tests for Automatic Recovery Manager

Basic tests to verify the automatic recovery functionality.
"""

import pytest
import asyncio
import tempfile
import time
from pathlib import Path

from src.audio_core.recovery_manager import (
    AutomaticRecoveryManager, DeviceReconnectionStrategy, BufferAdjustmentStrategy,
    PerformanceDegradationStrategy, DeviceStatus, RecoveryStatus,
    initialize_recovery_manager, get_recovery_manager
)
from src.audio_core.error_handling import initialize_error_handling


class TestRecoveryStrategies:
    """Test individual recovery strategies"""
    
    def setup_method(self):
        self.device_callback_called = False
        self.buffer_callback_called = False
        self.performance_callback_called = False
    
    async def mock_device_callback(self, device_id: str, context: dict) -> bool:
        """Mock device manager callback"""
        self.device_callback_called = True
        return True
    
    async def mock_buffer_callback(self, component_name: str, new_size: int, context: dict) -> bool:
        """Mock buffer manager callback"""
        self.buffer_callback_called = True
        return True
    
    async def mock_performance_callback(self, params: dict) -> bool:
        """Mock performance manager callback"""
        self.performance_callback_called = True
        return True
    
    @pytest.mark.asyncio
    async def test_device_reconnection_strategy(self):
        """Test device reconnection strategy"""
        strategy = DeviceReconnectionStrategy(self.mock_device_callback)
        
        # Test can_handle
        can_handle = await strategy.can_handle("device_disconnection", {"device_id": "test_device"})
        assert can_handle
        
        # Test execute_recovery
        context = {"device_id": "test_device", "reconnect_delay": 0.1}
        success, message = await strategy.execute_recovery(context)
        
        assert success
        assert "reconnected successfully" in message
        assert self.device_callback_called
    
    @pytest.mark.asyncio
    async def test_buffer_adjustment_strategy(self):
        """Test buffer adjustment strategy"""
        strategy = BufferAdjustmentStrategy(self.mock_buffer_callback)
        
        # Test can_handle
        can_handle = await strategy.can_handle("buffer_underrun", {"component_name": "test_component"})
        assert can_handle
        
        # Test execute_recovery
        context = {
            "component_name": "test_component",
            "issue_type": "buffer_underrun",
            "current_buffer_size": 512
        }
        success, message = await strategy.execute_recovery(context)
        
        assert success
        assert "Buffer size adjusted" in message
        assert self.buffer_callback_called
    
    @pytest.mark.asyncio
    async def test_performance_degradation_strategy(self):
        """Test performance degradation strategy"""
        strategy = PerformanceDegradationStrategy(self.mock_performance_callback)
        
        # Test can_handle
        can_handle = await strategy.can_handle("performance_degradation", {"component_name": "test_component"})
        assert can_handle
        
        # Test execute_recovery - degradation
        context = {
            "component_name": "test_component",
            "action": "degrade",
            "current_degradation_level": 0
        }
        success, message = await strategy.execute_recovery(context)
        
        assert success
        assert "degradation level 1 applied" in message
        assert self.performance_callback_called


class TestAutomaticRecoveryManager:
    """Test automatic recovery manager"""
    
    def setup_method(self):
        # Initialize error handling system
        temp_dir = Path(tempfile.mkdtemp())
        self.error_system = initialize_error_handling(temp_dir)
        
        # Initialize recovery manager
        self.recovery_manager = AutomaticRecoveryManager(self.error_system)
        
        # Setup mock callbacks
        self.device_operations = []
        self.buffer_operations = []
        self.performance_operations = []
        self.alerts = []
        
        async def mock_device_callback(device_id: str, context: dict) -> bool:
            self.device_operations.append({"device_id": device_id, "context": context})
            return True
        
        async def mock_buffer_callback(component_name: str, new_size: int, context: dict) -> bool:
            self.buffer_operations.append({"component_name": component_name, "new_size": new_size, "context": context})
            return True
        
        async def mock_performance_callback(params: dict) -> bool:
            self.performance_operations.append(params)
            return True
        
        async def mock_alert_callback(alert_data: dict):
            self.alerts.append(alert_data)
        
        self.recovery_manager.set_device_manager_callback(mock_device_callback)
        self.recovery_manager.set_buffer_manager_callback(mock_buffer_callback)
        self.recovery_manager.set_performance_manager_callback(mock_performance_callback)
        self.recovery_manager.set_alert_callback(mock_alert_callback)
    
    def teardown_method(self):
        if self.recovery_manager:
            self.recovery_manager.shutdown()
    
    def test_device_registration(self):
        """Test device registration for monitoring"""
        self.recovery_manager.register_device("device_001", "Test Microphone", is_primary=True)
        
        assert "device_001" in self.recovery_manager.device_states
        device_state = self.recovery_manager.device_states["device_001"]
        assert device_state.device_name == "Test Microphone"
        assert device_state.is_primary == True
    
    def test_buffer_registration(self):
        """Test buffer registration for monitoring"""
        self.recovery_manager.register_buffer("audio_buffer", 1024)
        
        assert "audio_buffer" in self.recovery_manager.buffer_states
        buffer_state = self.recovery_manager.buffer_states["audio_buffer"]
        assert buffer_state.buffer_size == 1024
    
    def test_performance_registration(self):
        """Test performance component registration"""
        self.recovery_manager.register_performance_component("audio_processor", 10.0)
        
        assert "audio_processor" in self.recovery_manager.performance_states
        perf_state = self.recovery_manager.performance_states["audio_processor"]
        assert perf_state.target_latency_ms == 10.0
    
    def test_monitoring_lifecycle(self):
        """Test monitoring start/stop lifecycle"""
        # Initially not monitoring
        assert self.recovery_manager.recovery_status == RecoveryStatus.IDLE
        
        # Start monitoring
        self.recovery_manager.start_monitoring()
        assert self.recovery_manager.recovery_status == RecoveryStatus.MONITORING
        assert self.recovery_manager.monitoring_enabled == True
        
        # Stop monitoring
        self.recovery_manager.stop_monitoring()
        assert self.recovery_manager.recovery_status == RecoveryStatus.IDLE
        assert self.recovery_manager.monitoring_enabled == False
    
    @pytest.mark.asyncio
    async def test_device_disconnection_handling(self):
        """Test device disconnection handling"""
        # Register a device
        self.recovery_manager.register_device("device_001", "Test Device")
        device_state = self.recovery_manager.device_states["device_001"]
        
        # Simulate disconnection and recovery
        await self.recovery_manager._handle_device_disconnection("device_001", device_state)
        
        # Check that device callback was called
        assert len(self.device_operations) > 0
        assert self.device_operations[0]["device_id"] == "device_001"
        
        # Check that alert was sent
        assert len(self.alerts) > 0
        assert self.alerts[0]["type"] == "device_reconnected"
    
    @pytest.mark.asyncio
    async def test_buffer_anomaly_handling(self):
        """Test buffer anomaly handling"""
        # Register a buffer
        self.recovery_manager.register_buffer("test_buffer", 512)
        buffer_state = self.recovery_manager.buffer_states["test_buffer"]
        
        # Simulate buffer underrun
        buffer_state.underrun_count = 10  # Above threshold
        
        await self.recovery_manager._handle_buffer_anomaly("test_buffer", buffer_state)
        
        # Check that buffer callback was called
        assert len(self.buffer_operations) > 0
        assert self.buffer_operations[0]["component_name"] == "test_buffer"
        
        # Check that alert was sent
        assert len(self.alerts) > 0
        assert self.alerts[0]["type"] == "buffer_adjusted"
    
    @pytest.mark.asyncio
    async def test_performance_degradation_handling(self):
        """Test performance degradation handling"""
        # Register a performance component
        self.recovery_manager.register_performance_component("test_processor", 10.0)
        perf_state = self.recovery_manager.performance_states["test_processor"]
        
        # Simulate high latency requiring degradation
        perf_state.current_latency_ms = 25.0  # 2.5x target
        perf_state.cpu_usage_percent = 98.0  # High CPU
        
        await self.recovery_manager._handle_performance_degradation("test_processor", perf_state)
        
        # Check that performance callback was called
        assert len(self.performance_operations) > 0
        assert self.performance_operations[0]["component_name"] == "test_processor"
        assert self.performance_operations[0]["action"] == "degrade"
        
        # Check that alert was sent
        assert len(self.alerts) > 0
        assert self.alerts[0]["type"] == "performance_degraded"
    
    def test_recovery_status_reporting(self):
        """Test recovery status reporting"""
        # Register some components
        self.recovery_manager.register_device("device_001", "Test Device")
        self.recovery_manager.register_buffer("buffer_001", 1024)
        self.recovery_manager.register_performance_component("processor_001", 10.0)
        
        status = self.recovery_manager.get_recovery_status()
        
        assert status["status"] == RecoveryStatus.IDLE.value
        assert status["registered_devices"] == 1
        assert status["registered_buffers"] == 1
        assert status["registered_performance_components"] == 1
        assert len(status["strategies"]) >= 3  # Default strategies
    
    def test_health_reports(self):
        """Test health reporting functionality"""
        # Register components
        self.recovery_manager.register_device("device_001", "Test Device")
        self.recovery_manager.register_buffer("buffer_001", 1024)
        self.recovery_manager.register_performance_component("processor_001", 10.0)
        
        # Get health reports
        device_health = self.recovery_manager.get_device_health_report()
        buffer_health = self.recovery_manager.get_buffer_health_report()
        performance_health = self.recovery_manager.get_performance_health_report()
        
        # Verify device health report
        assert "device_001" in device_health
        assert device_health["device_001"]["name"] == "Test Device"
        assert "status" in device_health["device_001"]
        
        # Verify buffer health report
        assert "buffer_001" in buffer_health
        assert buffer_health["buffer_001"]["buffer_size"] == 1024
        assert "usage_percentage" in buffer_health["buffer_001"]
        
        # Verify performance health report
        assert "processor_001" in performance_health
        assert performance_health["processor_001"]["target_latency_ms"] == 10.0
        assert "performance_score" in performance_health["processor_001"]


class TestGlobalRecoveryManager:
    """Test global recovery manager functions"""
    
    def test_global_recovery_manager_initialization(self):
        """Test global recovery manager initialization"""
        # Initialize error handling first
        temp_dir = Path(tempfile.mkdtemp())
        error_system = initialize_error_handling(temp_dir)
        
        # Initialize recovery manager
        recovery_manager = initialize_recovery_manager(error_system)
        
        assert recovery_manager is not None
        assert get_recovery_manager() is recovery_manager
        
        # Cleanup
        recovery_manager.shutdown()


if __name__ == "__main__":
    pytest.main([__file__])