#!/usr/bin/env python3
"""
Classroom Calibration and Optimization Example.

This example demonstrates how to use the classroom calibration services
to set up and optimize audio processing for a classroom environment.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.audio_processing.services.classroom_calibration import (
    ClassroomCalibrationService,
    TeachingScenarioManager,
    ClassroomPerformanceOptimizer,
    RoomDimensions,
    TeachingScenario
)
from src.audio_processing.models import AudioFrame, AudioConfig
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Main example function."""
    print("🎓 Classroom Audio Processing Calibration Example")
    print("=" * 50)
    
    # Define classroom dimensions (typical university classroom)
    room_dimensions = RoomDimensions(
        length=12.0,  # 12 meters
        width=8.0,    # 8 meters  
        height=3.0    # 3 meters
    )
    
    # Define microphone array positions (8-mic circular array)
    mic_positions = [
        (6.0, 4.0, 2.5),  # Center of room, 50cm from ceiling
        (6.15, 4.0, 2.5), # 15cm radius circular array
        (6.0, 4.15, 2.5),
        (5.85, 4.0, 2.5),
        (6.0, 3.85, 2.5),
        (6.11, 4.11, 2.5),
        (5.89, 4.11, 2.5),
        (5.89, 3.89, 2.5)
    ]
    
    print(f"📐 Room: {room_dimensions.length}m × {room_dimensions.width}m × {room_dimensions.height}m")
    print(f"🎤 Microphones: {len(mic_positions)} in circular array")
    print()
    
    # Initialize services
    calibration_service = ClassroomCalibrationService(
        room_dimensions=room_dimensions,
        microphone_positions=mic_positions
    )
    
    scenario_manager = TeachingScenarioManager()
    performance_optimizer = ClassroomPerformanceOptimizer()
    
    try:
        # Start all services
        print("🚀 Starting calibration services...")
        await calibration_service.start()
        await scenario_manager.start()
        await performance_optimizer.start()
        
        # Perform classroom calibration
        print("\n🔧 Performing classroom calibration...")
        print("This may take 30-60 seconds...")
        
        calibration_result = await calibration_service.perform_full_calibration()
        
        print(f"✅ Calibration completed!")
        print(f"   📊 Quality Score: {calibration_result.quality_score:.2f}/1.0")
        print(f"   🔊 RT60: {calibration_result.reverberation_time_rt60:.2f}s")
        print(f"   🎤 Microphones calibrated: {len(calibration_result.microphone_calibrations)}")
        
        # Display recommended gains
        print(f"\n📈 Recommended Gain Settings:")
        for scenario, gain in calibration_result.recommended_gains.items():
            print(f"   {scenario}: {gain:.1f} dBFS")
        
        # Demonstrate scenario management
        print(f"\n🎭 Teaching Scenario Management:")
        
        scenarios_to_demo = [
            TeachingScenario.LECTURE,
            TeachingScenario.DISCUSSION,
            TeachingScenario.PRESENTATION
        ]
        
        for scenario in scenarios_to_demo:
            print(f"\n   Switching to {scenario.value} mode...")
            success = await scenario_manager.switch_scenario(scenario, force=True)
            
            if success:
                config = scenario_manager.get_scenario_config(scenario)
                print(f"   ✅ {config.name}")
                print(f"      Focus: {config.ssl_focus_area}")
                print(f"      Target Level: {config.agc_target_dbfs} dBFS")
                print(f"      Noise Reduction: {config.noise_reduction_level}")
                print(f"      Recording: {'Enabled' if config.recording_enabled else 'Disabled'}")
            
            # Simulate some processing time
            await asyncio.sleep(1)
        
        # Demonstrate performance optimization
        print(f"\n⚡ Performance Optimization:")
        
        # Get current performance summary
        perf_summary = performance_optimizer.get_performance_summary()
        print(f"   Current Strategy: {perf_summary.get('strategy_name', 'Unknown')}")
        
        # Simulate switching optimization strategies
        strategies = ['low_latency', 'balanced', 'high_quality']
        for strategy in strategies:
            print(f"\n   Testing {strategy} strategy...")
            success = performance_optimizer.set_optimization_strategy(strategy, force=True)
            if success:
                print(f"   ✅ Switched to {strategy} mode")
            await asyncio.sleep(0.5)
        
        # Simulate audio processing with scenario detection
        print(f"\n🎵 Simulating Audio Processing with Auto-Detection:")
        
        # Create sample audio frames for different scenarios
        audio_config = AudioConfig(sample_rate=48000, frame_size=480, channels=8)
        
        test_scenarios = [
            ("Teacher lecturing", TeachingScenario.LECTURE, {'ssl_direction': 0}),
            ("Student presentation", TeachingScenario.PRESENTATION, {'ssl_direction': 120}),
            ("Class discussion", TeachingScenario.DISCUSSION, {'ssl_direction': 45}),
        ]
        
        for description, expected_scenario, metadata in test_scenarios:
            print(f"\n   📝 {description}:")
            
            # Create test audio frame
            test_frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=audio_config.sample_rate,
                channels=audio_config.channels,
                frame_size=audio_config.frame_size,
                data=np.random.normal(0, 0.1, (audio_config.channels, audio_config.frame_size)),
                metadata=metadata
            )
            
            # Analyze for scenario detection
            detected_scenario = await scenario_manager.analyze_audio_for_scenario(test_frame)
            
            if detected_scenario:
                print(f"      🎯 Detected: {detected_scenario.value}")
                if detected_scenario == expected_scenario:
                    print(f"      ✅ Correct detection!")
                else:
                    print(f"      ⚠️  Expected: {expected_scenario.value}")
            else:
                print(f"      ❓ No scenario detected (low confidence)")
        
        print(f"\n📊 Final Status:")
        
        # Get calibration status
        cal_status = calibration_service.get_calibration_status()
        print(f"   Calibration: {'✅ Complete' if cal_status['last_calibration_time'] else '❌ Not done'}")
        
        # Get current scenario
        current_scenario = scenario_manager.get_current_scenario()
        print(f"   Current Scenario: {current_scenario.value}")
        
        # Get performance status
        perf_summary = performance_optimizer.get_performance_summary()
        print(f"   Optimization: {perf_summary.get('strategy_name', 'Unknown')}")
        
        print(f"\n🎉 Classroom calibration and optimization demo completed!")
        
    except Exception as e:
        logger.error(f"Demo failed: {e}")
        raise
    
    finally:
        # Clean up services
        print(f"\n🧹 Cleaning up services...")
        await calibration_service.stop()
        await scenario_manager.stop()
        await performance_optimizer.stop()
        print("✅ All services stopped")


if __name__ == "__main__":
    asyncio.run(main())