"""
Test script for Component Tuning Platform

This script demonstrates the usage of the tuning platform components.
"""

import numpy as np
from datetime import datetime
import asyncio
import logging

from ..audio_core.interfaces import BaseAudioProcessor, ComponentInfo
from ..audio_core.models import AudioFrame
from .tuning_platform import (
    ComponentTuningPlatform, AlgorithmParameterLab, PerformanceBenchmarkSuite,
    AutoTuningEngine, ComponentEffectEvaluator, SafeTestingEnvironment,
    ABTestConfig, OptimizationTarget
)
from .component_visualization import (
    ComponentVisualizationInterface, ComponentConfigurationManager,
    ComponentPerformanceMonitor, VisualizationConfig, VisualizationType
)


class TestAudioProcessor(BaseAudioProcessor):
    """Simple test audio processor for demonstration"""
    
    def __init__(self):
        info = ComponentInfo(
            component_id="test_processor",
            name="Test Audio Processor",
            version="1.0.0",
            description="Simple test processor for tuning platform demo",
            author="Test",
            category="test"
        )
        super().__init__(info)
        self._gain = 1.0
        self._delay_samples = 0
        
    def _initialize_parameters(self):
        """Initialize default parameters"""
        self._parameters = {
            "gain": 1.0,
            "delay_samples": 0,
            "enable_processing": True
        }
    
    def _validate_parameter(self, name: str, value) -> bool:
        """Validate parameter values"""
        if name == "gain":
            return isinstance(value, (int, float)) and 0.0 <= value <= 10.0
        elif name == "delay_samples":
            return isinstance(value, int) and 0 <= value <= 1024
        elif name == "enable_processing":
            return isinstance(value, bool)
        return False
    
    def _on_parameter_changed(self, name: str, old_value, new_value):
        """Handle parameter changes"""
        if name == "gain":
            self._gain = new_value
        elif name == "delay_samples":
            self._delay_samples = new_value
    
    def process(self, audio_frame: AudioFrame) -> AudioFrame:
        """Process audio frame"""
        processed_data = audio_frame.data.copy()
        
        if self._parameters.get("enable_processing", True):
            # Apply gain
            processed_data *= self._gain
            
            # Apply delay (simplified)
            if self._delay_samples > 0:
                delayed_data = np.zeros_like(processed_data)
                if len(processed_data) > self._delay_samples:
                    delayed_data[self._delay_samples:] = processed_data[:-self._delay_samples]
                processed_data = delayed_data
        
        return AudioFrame(
            data=processed_data,
            sample_rate=audio_frame.sample_rate,
            channels=audio_frame.channels,
            timestamp=datetime.now()
        )
    
    def process_batch(self, audio_frames):
        """Process batch of audio frames"""
        return [self.process(frame) for frame in audio_frames]


def test_tuning_platform():
    """Test the component tuning platform"""
    print("Testing Component Tuning Platform...")
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Create test component
    test_component = TestAudioProcessor()
    test_component.initialize({})
    
    # Create tuning platform
    platform = ComponentTuningPlatform()
    
    # Create tuning session
    session_id = platform.create_tuning_session(
        "test_processor", 
        OptimizationTarget.QUALITY
    )
    print(f"Created tuning session: {session_id}")
    
    # Test safe testing environment
    print("\nTesting Safe Testing Environment...")
    with platform.create_safe_testing_environment(test_component) as env:
        # Test parameter changes
        result = env.test_parameter_change("gain", 2.0)
        print(f"Parameter test result: {result['success']}")
        
        # Test batch parameter changes
        batch_results = env.batch_test_parameters({
            "gain": 1.5,
            "delay_samples": 10
        })
        print(f"Batch test results: {len(batch_results)} parameters tested")
    
    # Test performance benchmark
    print("\nTesting Performance Benchmark...")
    benchmark_result = platform.run_performance_benchmark(test_component, "demo_test")
    print(f"Benchmark completed: {benchmark_result.processing_time_ms:.2f}ms processing time")
    
    # Test A/B testing
    print("\nTesting A/B Testing...")
    ab_config = ABTestConfig(
        test_id="gain_test_001",
        component_id="test_processor",
        parameter_name="gain",
        variant_a=1.0,
        variant_b=2.0,
        sample_size=50
    )
    
    test_id = platform.run_ab_test(ab_config)
    print(f"Started A/B test: {test_id}")
    
    # Test component effect evaluation
    print("\nTesting Component Effect Evaluation...")
    test_audio = AudioFrame(
        data=np.sin(2 * np.pi * 440 * np.linspace(0, 1, 44100)).astype(np.float32),
        sample_rate=44100,
        channels=1,
        timestamp=datetime.now()
    )
    
    effect_metrics = platform.evaluate_component_effect(test_component, test_audio)
    print(f"Effect evaluation completed: Overall quality = {effect_metrics.get('overall_quality', 0):.3f}")
    
    # Test auto-tuning
    print("\nTesting Auto-Tuning...")
    optimization_id = platform.start_auto_tuning(
        test_component,
        ["gain", "delay_samples"],
        OptimizationTarget.QUALITY
    )
    print(f"Started auto-tuning: {optimization_id}")
    
    # End tuning session
    platform.end_tuning_session(session_id)
    print(f"Ended tuning session: {session_id}")
    
    print("\nTuning Platform test completed successfully!")


def test_visualization_interface():
    """Test the visualization interface"""
    print("\nTesting Visualization Interface...")
    
    # Create visualization interface
    viz_interface = ComponentVisualizationInterface()
    
    # Create visualization
    viz_config = VisualizationConfig(
        viz_type=VisualizationType.WAVEFORM,
        update_rate_hz=30.0,
        display_duration_ms=1000
    )
    
    viz_id = viz_interface.create_visualization("test_processor", viz_config)
    print(f"Created visualization: {viz_id}")
    
    # Generate test data
    test_input = AudioFrame(
        data=np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 1024)).astype(np.float32),
        sample_rate=44100,
        channels=1,
        timestamp=datetime.now()
    )
    
    test_output = AudioFrame(
        data=test_input.data * 1.5,  # Amplified output
        sample_rate=44100,
        channels=1,
        timestamp=datetime.now()
    )
    
    # Update visualization
    viz_interface.update_visualization_data(
        viz_id, test_input, test_output, 
        {"processing_time_ms": 2.5, "cpu_usage_percent": 15.0}
    )
    
    # Get visualization data
    viz_data = viz_interface.get_visualization_data(viz_id)
    print(f"Visualization data points: {viz_data['visualization_info']['data_points']}")
    
    # Stop visualization
    viz_interface.stop_visualization(viz_id)
    print("Visualization stopped")


def test_configuration_manager():
    """Test the configuration manager"""
    print("\nTesting Configuration Manager...")
    
    # Create configuration manager
    config_manager = ComponentConfigurationManager()
    
    # Create test component
    test_component = TestAudioProcessor()
    test_component.initialize({})
    
    # Save current configuration as template
    template_id = config_manager.save_component_configuration(
        test_component,
        "Default Test Configuration",
        "Basic configuration for test processor",
        "testing"
    )
    print(f"Saved configuration template: {template_id}")
    
    # List templates
    templates = config_manager.list_templates()
    print(f"Available templates: {len(templates)}")
    
    # Modify component parameters
    test_component.set_parameter("gain", 3.0)
    test_component.set_parameter("delay_samples", 50)
    
    # Apply template to restore original configuration
    success = config_manager.apply_template(test_component, template_id)
    print(f"Template applied successfully: {success}")
    
    # Verify parameters were restored
    current_params = test_component.get_parameters()
    print(f"Current gain: {current_params.get('gain', 'N/A')}")


def test_performance_monitor():
    """Test the performance monitor"""
    print("\nTesting Performance Monitor...")
    
    # Create performance monitor
    monitor = ComponentPerformanceMonitor()
    
    # Start monitoring
    monitor.start_monitoring("test_processor")
    
    # Record some performance data
    for i in range(10):
        monitor.record_performance_data(
            "test_processor",
            processing_time_ms=2.0 + np.random.random(),
            cpu_usage_percent=15.0 + 5.0 * np.random.random(),
            memory_usage_mb=50.0 + 10.0 * np.random.random(),
            algorithm_metrics={"quality_score": 0.8 + 0.2 * np.random.random()}
        )
    
    # Get performance summary
    summary = monitor.get_performance_summary("test_processor", time_window_minutes=1)
    print(f"Performance summary - Avg processing time: {summary['processing_time']['avg_ms']:.2f}ms")
    
    # Stop monitoring
    monitor.stop_monitoring("test_processor")
    print("Performance monitoring stopped")


if __name__ == "__main__":
    """Run all tests"""
    try:
        test_tuning_platform()
        test_visualization_interface()
        test_configuration_manager()
        test_performance_monitor()
        print("\n✅ All tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()