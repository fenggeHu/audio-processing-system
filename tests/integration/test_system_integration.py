"""
System Integration Tests

Tests for the complete integrated production audio system to verify
all components work together correctly.

Tests requirements: 1.1, 2.1, 5.1, 7.1
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch
import numpy as np

from src.audio_core.integrated_audio_system import IntegratedProductionAudioSystem, SystemIntegrationState
from src.audio_core.models import AudioFrame, AudioDevice


class TestSystemIntegration:
    """Test complete system integration"""
    
    @pytest.fixture
    async def integrated_system(self):
        """Create integrated system for testing"""
        system = IntegratedProductionAudioSystem("test_system")
        
        # Mock configuration for testing
        config = {
            "sample_rate": 48000,
            "channels": 2,
            "bit_depth": 24,
            "buffer_size": 256,
            "auto_detect_devices": False,  # Disable for testing
            "enable_all_devices": True,
            "enable_quality_monitoring": True,
            "enable_hot_plug": False,  # Disable for testing
            "capture_service": {
                "device_manager": {
                    "scan_interval": 1.0,
                    "enable_hot_plug": False
                }
            },
            "recovery": {
                "enable_auto_recovery": True,
                "max_retry_attempts": 2,
                "retry_delay_seconds": 0.5
            },
            "dashboard": {
                "max_history_points": 100
            }
        }
        
        # Initialize system
        success = await system.initialize_system(config)
        assert success, "System initialization should succeed"
        
        yield system
        
        # Cleanup
        await system.stop_system()
    
    @pytest.mark.asyncio
    async def test_system_initialization(self, integrated_system):
        """Test system initialization"""
        system = integrated_system
        
        # Check system state
        assert system.state == SystemIntegrationState.READY
        
        # Check components are initialized
        assert system.capture_service is not None
        assert system.multi_input_system is not None
        assert system.component_registry is not None
        assert system.recovery_manager is not None
        assert system.visual_pipeline is not None
        assert system.dashboard is not None
        assert system.config_manager is not None
        
        # Check system configuration
        assert system.system_config is not None
        assert system.system_config.sample_rate == 48000
        assert system.system_config.channels == 2
    
    @pytest.mark.asyncio
    async def test_system_start_stop_cycle(self, integrated_system):
        """Test complete system start/stop cycle"""
        system = integrated_system
        
        # Start system
        success = await system.start_system()
        assert success, "System start should succeed"
        assert system.state == SystemIntegrationState.RUNNING
        
        # Check system status
        status = system.get_system_status()
        assert status["state"] == "running"
        assert "components" in status
        
        # Stop system
        success = await system.stop_system()
        assert success, "System stop should succeed"
        assert system.state == SystemIntegrationState.STOPPED
    
    @pytest.mark.asyncio
    async def test_system_pause_resume(self, integrated_system):
        """Test system pause and resume functionality"""
        system = integrated_system
        
        # Start system first
        await system.start_system()
        assert system.state == SystemIntegrationState.RUNNING
        
        # Pause system
        success = await system.pause_system()
        assert success, "System pause should succeed"
        assert system.state == SystemIntegrationState.PAUSED
        
        # Resume system
        success = await system.resume_system()
        assert success, "System resume should succeed"
        assert system.state == SystemIntegrationState.RUNNING
        
        # Stop system
        await system.stop_system()
    
    @pytest.mark.asyncio
    async def test_component_health_monitoring(self, integrated_system):
        """Test component health monitoring"""
        system = integrated_system
        
        # Start system
        await system.start_system()
        
        # Wait for health monitoring to run
        await asyncio.sleep(0.5)
        
        # Check health status
        health_status = system.get_health_status()
        assert health_status.overall_health in ["healthy", "degraded", "unhealthy"]
        assert health_status.total_components > 0
        assert health_status.performance_score >= 0.0
        assert health_status.performance_score <= 1.0
        
        # Check component health tracking
        assert len(system.component_health) > 0
        
        await system.stop_system()
    
    @pytest.mark.asyncio
    async def test_audio_data_flow(self, integrated_system):
        """Test audio data flow through the system"""
        system = integrated_system
        
        # Mock audio devices
        mock_device = AudioDevice(
            device_id="test_device_1",
            name="Test Audio Device",
            device_type="microphone",
            sample_rates=[48000],
            channels=2,
            is_default=True
        )
        
        # Start system
        await system.start_system()
        
        # Create test audio frame
        test_audio_data = np.random.random(1024).astype(np.float32)
        test_frame = AudioFrame(
            data=test_audio_data,
            sample_rate=48000,
            channels=2,
            timestamp=time.time()
        )
        
        # Test audio input processing
        system._on_audio_input("test_device_1", test_frame)
        
        # Test synchronized audio processing
        sync_frames = {"test_device_1": test_frame}
        system._on_synchronized_audio(sync_frames)
        
        # Verify no exceptions were raised
        await system.stop_system()
    
    @pytest.mark.asyncio
    async def test_system_callbacks(self, integrated_system):
        """Test system callback functionality"""
        system = integrated_system
        
        # Setup callback mocks
        state_callback = Mock()
        health_callback = Mock()
        
        system.register_state_change_callback(state_callback)
        system.register_health_change_callback(health_callback)
        
        # Start system (should trigger state change)
        await system.start_system()
        
        # Verify state callback was called
        assert state_callback.called
        
        # Wait for health monitoring
        await asyncio.sleep(0.5)
        
        await system.stop_system()
    
    @pytest.mark.asyncio
    async def test_error_handling(self, integrated_system):
        """Test system error handling"""
        system = integrated_system
        
        # Test error in audio processing
        with patch.object(system, '_on_audio_input', side_effect=Exception("Test error")):
            # Create test frame
            test_frame = AudioFrame(
                data=np.random.random(1024).astype(np.float32),
                sample_rate=48000,
                channels=2,
                timestamp=time.time()
            )
            
            # This should not crash the system
            system._on_audio_input("test_device", test_frame)
        
        # System should still be functional
        assert system.state == SystemIntegrationState.READY
    
    @pytest.mark.asyncio
    async def test_configuration_integration(self, integrated_system):
        """Test configuration management integration"""
        system = integrated_system
        
        # Check configuration manager is available
        assert system.config_manager is not None
        
        # Test configuration save/load
        test_config = {
            "audio": {"sample_rate": 48000},
            "processing": {"buffer_size": 256},
            "system": {"max_cpu_usage": 80}
        }
        
        # Save configuration
        success = system.config_manager.save_configuration(test_config, "Test config")
        assert success, "Configuration save should succeed"
        
        # Load configuration
        loaded_config = system.config_manager.load_configuration()
        assert loaded_config is not None
        assert loaded_config["audio"]["sample_rate"] == 48000
    
    @pytest.mark.asyncio
    async def test_component_registry_integration(self, integrated_system):
        """Test component registry integration"""
        system = integrated_system
        
        # Check component registry is available
        assert system.component_registry is not None
        
        # List available components
        components = system.component_registry.list_components()
        assert len(components) > 0, "Should have registered components"
        
        # Check for standard components
        component_ids = [comp.component_id for comp in components]
        assert any("webrtc" in comp_id for comp_id in component_ids), "Should have WebRTC components"
    
    @pytest.mark.asyncio
    async def test_visual_pipeline_integration(self, integrated_system):
        """Test visual pipeline integration"""
        system = integrated_system
        
        # Check visual pipeline is available
        assert system.visual_pipeline is not None
        
        # Start system to activate pipeline
        await system.start_system()
        
        # Check pipeline status
        assert system.visual_pipeline.running
        
        # Get topology graph
        topology = system.visual_pipeline.get_topology_graph()
        assert "nodes" in topology
        assert "connections" in topology
        assert "metadata" in topology
        
        await system.stop_system()
    
    @pytest.mark.asyncio
    async def test_dashboard_integration(self, integrated_system):
        """Test dashboard integration"""
        system = integrated_system
        
        # Check dashboard is available
        assert system.dashboard is not None
        
        # Start system to activate dashboard
        await system.start_system()
        
        # Get dashboard status
        dashboard_status = system.dashboard.get_full_chain_status()
        assert "dashboard_id" in dashboard_status
        assert "state" in dashboard_status
        
        await system.stop_system()
    
    @pytest.mark.asyncio
    async def test_recovery_manager_integration(self, integrated_system):
        """Test recovery manager integration"""
        system = integrated_system
        
        # Check recovery manager is available
        assert system.recovery_manager is not None
        
        # Start system
        await system.start_system()
        
        # Get recovery manager status
        recovery_status = system.recovery_manager.get_recovery_status()
        assert "status" in recovery_status
        
        await system.stop_system()


class TestSystemPerformance:
    """Test system performance characteristics"""
    
    @pytest.mark.asyncio
    async def test_system_startup_time(self):
        """Test system startup performance"""
        system = IntegratedProductionAudioSystem("perf_test")
        
        config = {
            "sample_rate": 48000,
            "channels": 2,
            "auto_detect_devices": False,
            "enable_hot_plug": False
        }
        
        # Measure initialization time
        start_time = time.time()
        success = await system.initialize_system(config)
        init_time = time.time() - start_time
        
        assert success
        assert init_time < 5.0, f"Initialization took too long: {init_time}s"
        
        # Measure startup time
        start_time = time.time()
        success = await system.start_system()
        startup_time = time.time() - start_time
        
        assert success
        assert startup_time < 3.0, f"Startup took too long: {startup_time}s"
        
        await system.stop_system()
    
    @pytest.mark.asyncio
    async def test_system_memory_usage(self):
        """Test system memory usage"""
        system = IntegratedProductionAudioSystem("memory_test")
        
        config = {
            "sample_rate": 48000,
            "channels": 2,
            "auto_detect_devices": False,
            "enable_hot_plug": False,
            "dashboard": {"max_history_points": 100}  # Limit for testing
        }
        
        # Initialize and start system
        await system.initialize_system(config)
        await system.start_system()
        
        # Get system status (includes memory info)
        status = system.get_system_status()
        assert "components" in status
        
        # System should be running efficiently
        health_status = system.get_health_status()
        assert health_status.performance_score > 0.5
        
        await system.stop_system()


if __name__ == "__main__":
    # Run basic integration test
    async def run_basic_test():
        system = IntegratedProductionAudioSystem("basic_test")
        
        config = {
            "sample_rate": 48000,
            "channels": 2,
            "auto_detect_devices": False,
            "enable_hot_plug": False
        }
        
        print("Initializing system...")
        success = await system.initialize_system(config)
        print(f"Initialization: {'SUCCESS' if success else 'FAILED'}")
        
        if success:
            print("Starting system...")
            success = await system.start_system()
            print(f"Start: {'SUCCESS' if success else 'FAILED'}")
            
            if success:
                print("System running, getting status...")
                status = system.get_system_status()
                print(f"System state: {status['state']}")
                print(f"Components: {len(status['components'])}")
                
                await asyncio.sleep(1.0)
                
                print("Stopping system...")
                await system.stop_system()
                print("System stopped")
    
    asyncio.run(run_basic_test())