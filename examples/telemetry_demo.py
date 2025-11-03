#!/usr/bin/env python3
"""
Telemetry Service Demonstration

This script demonstrates the telemetry service functionality including:
- Real-time performance monitoring
- Metrics collection from audio services
- Performance alerts
- Dashboard data generation
"""

import asyncio
import time
import numpy as np
from datetime import datetime
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audio_processing.services.telemetry import TelemetryService, QualityMetrics
from audio_processing.models import AudioFrame, AudioConfig, AudioMetrics


async def simulate_audio_service(service_name: str, telemetry: TelemetryService, duration: int = 30):
    """
    Simulate an audio processing service generating metrics.
    
    Args:
        service_name: Name of the simulated service
        telemetry: TelemetryService instance
        duration: How long to run the simulation in seconds
    """
    collector = telemetry.get_metrics_collector()
    
    print(f"Starting simulation for {service_name}")
    
    start_time = time.time()
    frame_count = 0
    
    while time.time() - start_time < duration:
        # Simulate processing latency (varies between 15-45ms)
        base_latency = 25.0
        latency_variation = np.random.normal(0, 5.0)
        processing_latency = max(10.0, base_latency + latency_variation)
        
        # Simulate CPU usage (varies between 20-60%)
        base_cpu = 40.0
        cpu_variation = np.random.normal(0, 10.0)
        cpu_usage = max(0.0, min(100.0, base_cpu + cpu_variation))
        
        # Simulate memory usage (gradually increases)
        base_memory = 100.0 + (frame_count * 0.1)  # Slight memory leak simulation
        memory_usage = base_memory + np.random.normal(0, 5.0)
        
        # Simulate audio levels
        input_level = -20.0 + np.random.normal(0, 3.0)
        output_level = input_level + np.random.normal(2.0, 1.0)  # Slight gain
        
        # Record metrics
        collector.record_latency(service_name, processing_latency)
        collector.record_cpu_usage(service_name, cpu_usage)
        collector.record_memory_usage(service_name, memory_usage)
        collector.record_audio_level(service_name, input_level, is_input=True)
        collector.record_audio_level(service_name, output_level, is_input=False)
        
        # Occasionally simulate frame drops
        if np.random.random() < 0.02:  # 2% chance
            collector.record_frame_drop(service_name)
            print(f"  {service_name}: Frame dropped!")
        
        # Simulate quality metrics every 10 frames
        if frame_count % 10 == 0:
            quality = QualityMetrics(
                erle_db=20.0 + np.random.normal(0, 3.0),
                pesq_score=3.0 + np.random.normal(0, 0.3),
                snr_db=15.0 + np.random.normal(0, 2.0),
                thd_percent=2.0 + abs(np.random.normal(0, 0.5))
            )
            collector.record_quality_metric(service_name, quality)
        
        frame_count += 1
        
        # Simulate processing time
        await asyncio.sleep(0.02)  # 50 FPS simulation
    
    print(f"Finished simulation for {service_name} ({frame_count} frames processed)")


async def performance_monitor(telemetry: TelemetryService, duration: int = 30):
    """
    Monitor and display performance metrics periodically.
    
    Args:
        telemetry: TelemetryService instance
        duration: How long to monitor in seconds
    """
    print("Starting performance monitoring...")
    
    start_time = time.time()
    
    while time.time() - start_time < duration:
        await asyncio.sleep(5.0)  # Report every 5 seconds
        
        # Get performance summary
        summary = telemetry.get_service_performance_summary()
        
        print(f"\n=== Performance Report ({datetime.now().strftime('%H:%M:%S')}) ===")
        
        for service_name, metrics in summary.items():
            status_emoji = "✅" if metrics["status"] == "healthy" else "⚠️"
            print(f"{status_emoji} {service_name}:")
            print(f"  Latency: {metrics['processing_latency_ms']:.1f}ms")
            print(f"  CPU: {metrics['cpu_usage_percent']:.1f}%")
            print(f"  Memory: {metrics['memory_usage_mb']:.1f}MB")
            print(f"  Frame drops: {metrics['frame_drop_rate_percent']:.2f}%")
            print(f"  Frames processed: {metrics['frames_processed']}")
        
        # Get system metrics
        system_metrics = telemetry.get_system_metrics(duration_minutes=1)
        if system_metrics:
            latest_system = system_metrics[-1]
            print(f"\n🖥️  System Overview:")
            print(f"  CPU: {latest_system.total_cpu_percent:.1f}%")
            print(f"  Memory: {latest_system.total_memory_mb:.1f}MB")
            print(f"  Available: {latest_system.available_memory_mb:.1f}MB")
            print(f"  Disk: {latest_system.disk_usage_percent:.1f}%")


async def alert_handler(event_data):
    """Handle performance alerts."""
    alert_type = event_data.get("alert_type", "unknown")
    message = event_data.get("message", "No message")
    
    print(f"\n🚨 ALERT [{alert_type.upper()}]: {message}")


async def main():
    """Main demonstration function."""
    print("🎵 Audio Processing System - Telemetry Service Demo")
    print("=" * 60)
    
    # Configure telemetry service
    telemetry_config = {
        "monitoring_interval": 1.0,
        "log_level": "info",
        "log_format": "console",
        "enable_system_monitoring": True,
        "enable_quality_monitoring": True,
        "max_history_size": 500,
        "cpu_threshold": 70.0,  # Lower threshold for demo
        "memory_threshold_mb": 200.0,  # Lower threshold for demo
        "latency_threshold_ms": 40.0
    }
    
    # Create and start telemetry service
    telemetry = TelemetryService("demo_telemetry", telemetry_config)
    
    # Register alert handler
    telemetry.register_event_handler("performance_alert", alert_handler)
    
    print("Starting telemetry service...")
    await telemetry.start()
    
    try:
        # Create tasks for simulated services
        services = ["ssl_service", "aec_service", "denoise_service", "beamformer_service"]
        simulation_duration = 30
        
        print(f"Starting simulation with {len(services)} services for {simulation_duration} seconds...")
        
        # Start all simulations concurrently
        tasks = []
        
        # Add service simulations
        for service in services:
            task = asyncio.create_task(
                simulate_audio_service(service, telemetry, simulation_duration)
            )
            tasks.append(task)
        
        # Add performance monitoring
        monitor_task = asyncio.create_task(
            performance_monitor(telemetry, simulation_duration)
        )
        tasks.append(monitor_task)
        
        # Wait for all tasks to complete
        await asyncio.gather(*tasks)
        
        # Final dashboard report
        print("\n" + "=" * 60)
        print("📊 Final Dashboard Data:")
        print("=" * 60)
        
        dashboard_data = telemetry.get_performance_dashboard_data()
        
        print(f"Timestamp: {dashboard_data['timestamp']}")
        
        system_overview = dashboard_data['system_overview']
        print(f"\nSystem Overview:")
        print(f"  CPU: {system_overview['cpu_percent']:.1f}%")
        print(f"  Memory: {system_overview['memory_mb']:.1f}MB")
        print(f"  Available: {system_overview['available_memory_mb']:.1f}MB")
        
        print(f"\nService Summary:")
        for service_name, metrics in dashboard_data['services'].items():
            status_emoji = "✅" if metrics["status"] == "healthy" else "⚠️"
            print(f"  {status_emoji} {service_name}: "
                  f"{metrics['processing_latency_ms']:.1f}ms latency, "
                  f"{metrics['cpu_usage_percent']:.1f}% CPU, "
                  f"{metrics['frames_processed']} frames")
        
        print(f"\nDemo completed successfully! 🎉")
        
    except KeyboardInterrupt:
        print("\nDemo interrupted by user")
    
    finally:
        print("Stopping telemetry service...")
        await telemetry.stop()
        print("Demo finished.")


if __name__ == "__main__":
    asyncio.run(main())