"""
Hardware Abstraction Layer Demo

Demonstration of the hardware abstraction layer with delay compensation,
clock synchronization, error recovery, and performance monitoring.
"""

import time
import logging
from datetime import datetime

from src.audio_core.hardware_interface import HardwareAbstractionLayer
from src.audio_core.hardware_devices import create_mock_devices
from src.audio_core.models import AudioFrame


def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def demonstrate_basic_hal_usage():
    """Demonstrate basic HAL usage"""
    print("\n=== Basic Hardware Abstraction Layer Usage ===")
    
    # Create HAL instance
    hal = HardwareAbstractionLayer()
    
    # Initialize HAL
    config = {
        'enable_delay_compensation': True,
        'sync_interval': 1.0,
        'monitor_interval': 1.0
    }
    
    if not hal.init(config):
        print("Failed to initialize HAL")
        return
    
    print("✓ HAL initialized successfully")
    
    # Start HAL
    if not hal.start():
        print("Failed to start HAL")
        return
    
    print("✓ HAL started successfully")
    print(f"HAL State: {hal.get_state().value}")
    
    # Get health status
    health = hal.get_health_status()
    print(f"HAL Health: {health}")
    
    # Stop and cleanup
    hal.stop()
    hal.cleanup()
    print("✓ HAL stopped and cleaned up")


def demonstrate_device_registration():
    """Demonstrate device registration and management"""
    print("\n=== Device Registration and Management ===")
    
    # Create HAL
    hal = HardwareAbstractionLayer()
    hal.init({'enable_delay_compensation': True})
    hal.start()
    
    # Create mock devices
    mock_devices = create_mock_devices()
    print(f"Created {len(mock_devices)} mock devices")
    
    # Register devices with HAL
    device_configs = {
        'sample_rate': 48000,
        'channels': 2,
        'buffer_size': 256
    }
    
    for device_id, device in mock_devices.items():
        if hal.register_device(device_id, device, device_configs):
            print(f"✓ Registered device: {device_id}")
            
            # Get device info
            device_info = device.get_device_info()
            print(f"  - Name: {device_info.name}")
            print(f"  - Type: {device_info.device_type.value}")
            print(f"  - Input: {device_info.is_input}, Output: {device_info.is_output}")
        else:
            print(f"✗ Failed to register device: {device_id}")
    
    # Set master clock device
    if hal.set_master_clock("mock_input_0"):
        print("✓ Set mock_input_0 as master clock")
    
    # Get all registered devices
    all_devices = hal.get_all_devices()
    print(f"Total registered devices: {len(all_devices)}")
    
    # Cleanup
    hal.stop()
    hal.cleanup()


def demonstrate_timing_and_synchronization():
    """Demonstrate timing and synchronization features"""
    print("\n=== Timing and Synchronization ===")
    
    # Create HAL
    hal = HardwareAbstractionLayer()
    hal.init({'enable_delay_compensation': True})
    hal.start()
    
    # Create and register devices
    mock_devices = create_mock_devices()
    device_configs = {'sample_rate': 48000, 'channels': 2, 'buffer_size': 256}
    
    for device_id, device in mock_devices.items():
        hal.register_device(device_id, device, device_configs)
    
    # Set master clock
    hal.set_master_clock("mock_input_0")
    
    # Wait for synchronization to stabilize
    print("Waiting for synchronization to stabilize...")
    time.sleep(2)
    
    # Get timing information for each device
    for device_id in mock_devices.keys():
        timing_info = hal.get_device_timing(device_id)
        if timing_info:
            print(f"\nTiming info for {device_id}:")
            print(f"  - Sample Rate: {timing_info.sample_rate}")
            print(f"  - Input Latency: {timing_info.input_latency_ms:.2f}ms")
            print(f"  - Output Latency: {timing_info.output_latency_ms:.2f}ms")
            print(f"  - Clock Drift: {timing_info.clock_drift_ppm:.2f} ppm")
            print(f"  - Sync Status: {timing_info.sync_status.value}")
            print(f"  - Jitter: {timing_info.jitter_ms:.2f}ms")
            
            # Get compensation delay
            compensation = hal.get_compensation_delay(device_id)
            print(f"  - Compensation Delay: {compensation:.2f}ms")
    
    # Demonstrate timing calibration
    print("\nCalibrating timing for mock_usb_0...")
    if hal.calibrate_device_timing("mock_usb_0"):
        print("✓ Timing calibration successful")
        
        # Get updated timing info
        timing_info = hal.get_device_timing("mock_usb_0")
        if timing_info:
            print(f"  - Updated Sync Status: {timing_info.sync_status.value}")
    
    # Cleanup
    hal.stop()
    hal.cleanup()


def demonstrate_performance_monitoring():
    """Demonstrate performance monitoring"""
    print("\n=== Performance Monitoring ===")
    
    # Create HAL
    hal = HardwareAbstractionLayer()
    hal.init({'enable_delay_compensation': True})
    hal.start()
    
    # Create and register devices
    mock_devices = create_mock_devices()
    device_configs = {'sample_rate': 48000, 'channels': 2, 'buffer_size': 256}
    
    for device_id, device in mock_devices.items():
        hal.register_device(device_id, device, device_configs)
        # Start device to generate performance data
        device.start()
    
    # Wait for performance data to be collected
    print("Collecting performance data...")
    time.sleep(3)
    
    # Get performance metrics for each device
    for device_id in mock_devices.keys():
        metrics = hal.get_device_performance(device_id)
        if metrics:
            print(f"\nPerformance metrics for {device_id}:")
            print(f"  - CPU Usage: {metrics.cpu_usage_percent:.1f}%")
            print(f"  - Memory Usage: {metrics.memory_usage_mb:.1f} MB")
            print(f"  - Signal Level: {metrics.signal_level_db:.1f} dB")
            print(f"  - Noise Floor: {metrics.noise_floor_db:.1f} dB")
            print(f"  - SNR: {metrics.snr_db:.1f} dB")
            print(f"  - THD: {metrics.thd_percent:.3f}%")
            print(f"  - Frames/sec: {metrics.frames_per_second:.1f}")
            print(f"  - Error Count: {metrics.error_count}")
            print(f"  - Last Update: {metrics.last_update.strftime('%H:%M:%S')}")
    
    # Get all metrics at once
    all_metrics = hal.get_all_performance_metrics()
    print(f"\nTotal devices being monitored: {len(all_metrics)}")
    
    # Stop devices and cleanup
    for device in mock_devices.values():
        device.stop()
    
    hal.stop()
    hal.cleanup()


def demonstrate_error_recovery():
    """Demonstrate error recovery system"""
    print("\n=== Error Recovery System ===")
    
    # Create HAL
    hal = HardwareAbstractionLayer()
    hal.init({'enable_delay_compensation': True})
    hal.start()
    
    # Create and register a device
    mock_devices = create_mock_devices()
    device_configs = {'sample_rate': 48000, 'channels': 2, 'buffer_size': 256}
    
    device_id = "mock_input_0"
    device = mock_devices[device_id]
    hal.register_device(device_id, device, device_configs)
    device.start()
    
    print(f"Registered and started device: {device_id}")
    
    # Simulate various errors
    error_scenarios = [
        ("buffer_underrun", "Simulated buffer underrun", "medium"),
        ("buffer_overrun", "Simulated buffer overrun", "medium"),
        ("sync_lost", "Clock synchronization lost", "high"),
        ("device_error", "Device communication error", "high"),
    ]
    
    for error_type, error_msg, severity in error_scenarios:
        print(f"\nSimulating error: {error_type}")
        
        # Report error to HAL
        recovery_attempted = hal.report_device_error(device_id, error_type, error_msg, severity)
        
        if recovery_attempted:
            print(f"✓ Recovery attempted for {error_type}")
        else:
            print(f"✗ No recovery attempted for {error_type}")
        
        # Wait a bit between errors
        time.sleep(0.5)
    
    # Get error history
    error_history = hal.get_error_history(device_id)
    print(f"\nError history for {device_id}:")
    for i, error in enumerate(error_history, 1):
        print(f"  {i}. {error.error_type} - {error.severity} - {error.timestamp.strftime('%H:%M:%S')}")
        if error.recovery_attempted:
            status = "successful" if error.recovery_successful else "failed"
            print(f"     Recovery: {error.recovery_action.value if error.recovery_action else 'unknown'} ({status})")
    
    # Simulate critical error (should not trigger recovery)
    print(f"\nSimulating critical error...")
    hal.report_device_error(device_id, "critical_error", "Critical system failure", "critical")
    
    # Get updated error history
    error_history = hal.get_error_history(device_id)
    critical_error = error_history[-1]
    print(f"Critical error recovery attempted: {critical_error.recovery_attempted}")
    
    # Cleanup
    device.stop()
    hal.stop()
    hal.cleanup()


def demonstrate_audio_processing():
    """Demonstrate basic audio processing through HAL"""
    print("\n=== Audio Processing Demo ===")
    
    # Create HAL
    hal = HardwareAbstractionLayer()
    hal.init({'enable_delay_compensation': True})
    hal.start()
    
    # Create and register devices
    mock_devices = create_mock_devices()
    device_configs = {'sample_rate': 48000, 'channels': 2, 'buffer_size': 256}
    
    input_device = mock_devices["mock_input_0"]
    output_device = mock_devices["mock_output_0"]
    
    hal.register_device("input", input_device, device_configs)
    hal.register_device("output", output_device, device_configs)
    
    # Start devices
    input_device.start()
    output_device.start()
    
    print("Starting audio processing loop...")
    
    # Simple audio processing loop
    frames_processed = 0
    start_time = time.time()
    
    try:
        while frames_processed < 10:  # Process 10 frames for demo
            # Read frame from input
            frame = input_device.read_frame()
            
            if frame:
                # Apply compensation delay if needed
                compensation_delay = hal.get_compensation_delay("input")
                if compensation_delay > 0:
                    # In real implementation, would apply delay here
                    pass
                
                # Process frame (simple pass-through for demo)
                processed_frame = frame
                
                # Write to output
                if output_device.write_frame(processed_frame):
                    frames_processed += 1
                    print(f"Processed frame {frames_processed}: {frame.frame_size} bytes")
                else:
                    print("Failed to write frame to output")
            
            time.sleep(0.01)  # Small delay to prevent busy loop
    
    except KeyboardInterrupt:
        print("\nProcessing interrupted by user")
    
    processing_time = time.time() - start_time
    print(f"\nProcessed {frames_processed} frames in {processing_time:.2f} seconds")
    
    if frames_processed > 0:
        avg_frame_time = processing_time / frames_processed
        print(f"Average frame processing time: {avg_frame_time*1000:.2f}ms")
    
    # Stop devices and cleanup
    input_device.stop()
    output_device.stop()
    hal.stop()
    hal.cleanup()


def main():
    """Main demonstration function"""
    setup_logging()
    
    print("Hardware Abstraction Layer Demonstration")
    print("=" * 50)
    
    try:
        # Run all demonstrations
        demonstrate_basic_hal_usage()
        demonstrate_device_registration()
        demonstrate_timing_and_synchronization()
        demonstrate_performance_monitoring()
        demonstrate_error_recovery()
        demonstrate_audio_processing()
        
        print("\n" + "=" * 50)
        print("All demonstrations completed successfully!")
        
    except Exception as e:
        print(f"\nError during demonstration: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()