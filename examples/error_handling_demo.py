#!/usr/bin/env python3
"""
Error Handling and Recovery System Demo

This example demonstrates the comprehensive error handling and automatic recovery
capabilities of the production audio processing system.
"""

import asyncio
import time
import random
from pathlib import Path

from src.audio_core.error_handling import (
    initialize_error_handling, handle_error, ErrorContext,
    ErrorType, ErrorSeverity, RecoveryAction
)
from src.audio_core.recovery_manager import (
    initialize_recovery_manager, DeviceStatus
)


class MockAudioSystem:
    """Mock audio system for demonstration"""
    
    def __init__(self):
        self.devices = {
            'mic_001': {'name': 'Primary Microphone', 'connected': True},
            'mic_002': {'name': 'Backup Microphone', 'connected': True},
            'speaker_001': {'name': 'Main Speaker', 'connected': True}
        }
        self.buffers = {
            'input_buffer': {'size': 1024, 'usage': 0},
            'output_buffer': {'size': 512, 'usage': 0}
        }
        self.components = {
            'audio_processor': {'latency_ms': 8.0, 'cpu_usage': 45.0, 'memory_mb': 256.0}
        }
    
    async def device_manager_callback(self, device_id: str, context: dict) -> bool:
        """Mock device manager callback"""
        print(f"🔧 Device Manager: Reconnecting {device_id}")
        await asyncio.sleep(0.5)  # Simulate reconnection time
        
        if device_id in self.devices:
            self.devices[device_id]['connected'] = True
            print(f"✅ Device {device_id} reconnected successfully")
            return True
        
        print(f"❌ Failed to reconnect device {device_id}")
        return False
    
    async def buffer_manager_callback(self, component_name: str, new_size: int, context: dict) -> bool:
        """Mock buffer manager callback"""
        print(f"🔧 Buffer Manager: Adjusting {component_name} buffer size to {new_size}")
        await asyncio.sleep(0.2)  # Simulate adjustment time
        
        if component_name in self.buffers:
            old_size = self.buffers[component_name]['size']
            self.buffers[component_name]['size'] = new_size
            print(f"✅ Buffer {component_name} adjusted: {old_size} -> {new_size}")
            return True
        
        print(f"❌ Failed to adjust buffer {component_name}")
        return False
    
    async def performance_manager_callback(self, params: dict) -> bool:
        """Mock performance manager callback"""
        component_name = params['component_name']
        action = params['action']
        level = params['level']
        
        print(f"🔧 Performance Manager: {action} {component_name} to level {level}")
        await asyncio.sleep(0.3)  # Simulate adjustment time
        
        if component_name in self.components:
            if action == 'degrade':
                # Simulate performance degradation
                self.components[component_name]['latency_ms'] *= (1.0 + level * 0.1)
                self.components[component_name]['cpu_usage'] *= (1.0 - level * 0.1)
                print(f"✅ Performance degraded for {component_name} (level {level})")
            else:  # restore
                # Simulate performance restoration
                self.components[component_name]['latency_ms'] /= (1.0 + level * 0.1)
                self.components[component_name]['cpu_usage'] /= (1.0 - level * 0.1)
                print(f"✅ Performance restored for {component_name} (level {level})")
            return True
        
        print(f"❌ Failed to adjust performance for {component_name}")
        return False
    
    async def alert_callback(self, alert_data: dict):
        """Mock alert callback"""
        alert_type = alert_data['type']
        data = alert_data['data']
        
        print(f"🚨 ALERT: {alert_type}")
        if 'device_id' in data:
            print(f"   Device: {data['device_id']}")
        if 'component_name' in data:
            print(f"   Component: {data['component_name']}")
        if 'message' in data:
            print(f"   Message: {data['message']}")


async def demonstrate_error_handling():
    """Demonstrate comprehensive error handling and recovery"""
    
    print("🎵 Audio Processing System - Error Handling Demo")
    print("=" * 60)
    
    # Initialize systems
    print("\n📋 Initializing Error Handling and Recovery Systems...")
    log_dir = Path("logs")
    error_system = initialize_error_handling(log_dir)
    recovery_manager = initialize_recovery_manager(error_system)
    
    # Setup mock audio system
    mock_system = MockAudioSystem()
    recovery_manager.set_device_manager_callback(mock_system.device_manager_callback)
    recovery_manager.set_buffer_manager_callback(mock_system.buffer_manager_callback)
    recovery_manager.set_performance_manager_callback(mock_system.performance_manager_callback)
    recovery_manager.set_alert_callback(mock_system.alert_callback)
    
    # Register components for monitoring
    print("\n📝 Registering Components for Monitoring...")
    recovery_manager.register_device('mic_001', 'Primary Microphone', is_primary=True, backup_devices=['mic_002'])
    recovery_manager.register_device('mic_002', 'Backup Microphone')
    recovery_manager.register_device('speaker_001', 'Main Speaker')
    
    recovery_manager.register_buffer('input_buffer', 1024)
    recovery_manager.register_buffer('output_buffer', 512)
    
    recovery_manager.register_performance_component('audio_processor', 10.0)
    
    print("✅ All components registered for monitoring")
    
    # Start monitoring
    print("\n🔍 Starting Automatic Monitoring...")
    recovery_manager.start_monitoring()
    
    # Demonstrate different types of errors and recovery
    print("\n" + "=" * 60)
    print("🧪 DEMONSTRATION SCENARIOS")
    print("=" * 60)
    
    # Scenario 1: Hardware Error - Device Disconnection
    print("\n1️⃣  SCENARIO: Device Disconnection")
    print("-" * 40)
    
    try:
        # Simulate device disconnection
        mock_system.devices['mic_001']['connected'] = False
        raise OSError("Primary microphone disconnected unexpectedly")
    except OSError as e:
        error_id = handle_error(e, 'device_manager', 'monitor_devices', device_id='mic_001')
        print(f"📝 Error logged with ID: {error_id}")
        
        # Trigger recovery
        device_state = recovery_manager.device_states['mic_001']
        device_state.status = DeviceStatus.DISCONNECTED
        await recovery_manager._handle_device_disconnection('mic_001', device_state)
    
    await asyncio.sleep(1)
    
    # Scenario 2: Processing Error - Buffer Issues
    print("\n2️⃣  SCENARIO: Buffer Underrun")
    print("-" * 40)
    
    try:
        # Simulate buffer underrun
        raise RuntimeError("Audio buffer underrun detected - frames dropped")
    except RuntimeError as e:
        error_id = handle_error(e, 'buffer_manager', 'process_audio', buffer_name='input_buffer')
        print(f"📝 Error logged with ID: {error_id}")
        
        # Trigger buffer adjustment
        buffer_state = recovery_manager.buffer_states['input_buffer']
        buffer_state.underrun_count = 10  # Above threshold
        await recovery_manager._handle_buffer_anomaly('input_buffer', buffer_state)
    
    await asyncio.sleep(1)
    
    # Scenario 3: Performance Degradation
    print("\n3️⃣  SCENARIO: Performance Degradation")
    print("-" * 40)
    
    try:
        # Simulate high latency
        raise PerformanceWarning("Audio processing latency exceeded threshold")
    except Exception as e:
        error_id = handle_error(e, 'audio_processor', 'process_frame', latency_ms=25.0)
        print(f"📝 Error logged with ID: {error_id}")
        
        # Trigger performance degradation
        perf_state = recovery_manager.performance_states['audio_processor']
        perf_state.current_latency_ms = 25.0  # 2.5x target
        perf_state.cpu_usage_percent = 95.0  # High CPU
        await recovery_manager._handle_performance_degradation('audio_processor', perf_state)
    
    await asyncio.sleep(1)
    
    # Scenario 4: Performance Restoration
    print("\n4️⃣  SCENARIO: Performance Restoration")
    print("-" * 40)
    
    # Simulate improved conditions
    perf_state = recovery_manager.performance_states['audio_processor']
    perf_state.current_latency_ms = 8.0  # Back to normal
    perf_state.cpu_usage_percent = 60.0  # Reduced CPU
    await recovery_manager._handle_performance_restoration('audio_processor', perf_state)
    
    await asyncio.sleep(1)
    
    # Show system status and statistics
    print("\n" + "=" * 60)
    print("📊 SYSTEM STATUS AND STATISTICS")
    print("=" * 60)
    
    # Error handling statistics
    health_report = error_system.get_system_health_report()
    print(f"\n🔧 Error Handling System:")
    print(f"   Total Errors Handled: {health_report['total_errors_handled']}")
    print(f"   Successful Recoveries: {health_report['successful_recoveries']}")
    print(f"   Recovery Success Rate: {health_report['recovery_success_rate']:.1%}")
    print(f"   System Availability: {health_report['system_availability']:.1%}")
    
    # Recovery manager statistics
    recovery_status = recovery_manager.get_recovery_status()
    print(f"\n🔄 Recovery Manager:")
    print(f"   Status: {recovery_status['status']}")
    print(f"   Successful Recoveries: {recovery_status['successful_recoveries']}")
    print(f"   Failed Recoveries: {recovery_status['failed_recoveries']}")
    print(f"   Success Rate: {recovery_status['success_rate']:.1%}")
    
    # Component health reports
    print(f"\n🖥️  Device Health:")
    device_health = recovery_manager.get_device_health_report()
    for device_id, health in device_health.items():
        status_icon = "✅" if health['is_healthy'] else "⚠️"
        print(f"   {status_icon} {health['name']}: {health['status']} (stability: {health['connection_stability']:.1%})")
    
    print(f"\n💾 Buffer Health:")
    buffer_health = recovery_manager.get_buffer_health_report()
    for buffer_name, health in buffer_health.items():
        usage_pct = health['usage_percentage']
        usage_icon = "✅" if usage_pct < 0.8 else "⚠️" if usage_pct < 0.95 else "🔴"
        print(f"   {usage_icon} {buffer_name}: {health['buffer_size']} bytes ({usage_pct:.1%} usage)")
    
    print(f"\n⚡ Performance Health:")
    performance_health = recovery_manager.get_performance_health_report()
    for component_name, health in performance_health.items():
        score = health['performance_score']
        perf_icon = "✅" if score > 0.8 else "⚠️" if score > 0.6 else "🔴"
        print(f"   {perf_icon} {component_name}: {health['current_latency_ms']:.1f}ms latency (score: {score:.1%})")
    
    # Stop monitoring
    print(f"\n🛑 Stopping Monitoring...")
    recovery_manager.stop_monitoring()
    
    # Cleanup
    print(f"\n🧹 Cleaning Up...")
    recovery_manager.shutdown()
    error_system.shutdown()
    
    print(f"\n✅ Demo completed successfully!")
    print(f"📁 Check the 'logs' directory for detailed error logs and recovery records.")


if __name__ == "__main__":
    print("Starting Error Handling and Recovery Demo...")
    asyncio.run(demonstrate_error_handling())