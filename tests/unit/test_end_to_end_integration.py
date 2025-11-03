"""
End-to-End Integration Tests using the Integration Test Framework

This module implements comprehensive end-to-end integration tests that validate
the complete audio processing system functionality using the integration test framework.

Requirements: 9.4, 9.5
"""

import pytest
import asyncio
import numpy as np
from datetime import datetime
from typing import Dict, Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audio_processing.models import AudioFrame, AudioConfig
from tests.unit.integration_test_framework import (
    IntegrationTestEnvironment, 
    AutomatedTestRunner, 
    RegressionTestSuite,
    TestSuite,
    create_integration_test_framework
)
from tests.unit.test_audio_mock_generator import MockAudioGenerator


class EndToEndIntegrationTests:
    """End-to-end integration test implementations."""
    
    @staticmethod
    async def test_complete_audio_pipeline(environment: IntegrationTestEnvironment):
        """Test complete audio processing pipeline from capture to output."""
        # Get all required services
        capture_service = await environment.get_service("CaptureService")
        denoise_service = await environment.get_service("DenoiseService")
        aec_service = await environment.get_service("AECService")
        ssl_service = await environment.get_service("SSLService")
        recorder_service = await environment.get_service("RecorderService")
        
        # Create realistic test audio
        mock_generator = MockAudioGenerator(environment.config)
        test_frame = mock_generator.generate_classroom_scenario_frame("teacher_lecture")
        
        # Process through complete pipeline
        # 1. Capture (simulated)
        capture_result = await capture_service.process(test_frame)
        assert capture_result.success, "Capture processing failed"
        
        # 2. Denoise
        denoise_result = await denoise_service.process(capture_result.data)
        assert denoise_result.success, "Denoise processing failed"
        
        # 3. AEC (Acoustic Echo Cancellation)
        aec_result = await aec_service.process(denoise_result.data)
        assert aec_result.success, "AEC processing failed"
        
        # 4. SSL (Sound Source Localization)
        ssl_result = await ssl_service.process(aec_result.data)
        assert ssl_result.success, "SSL processing failed"
        
        # 5. Recording
        record_result = await recorder_service.process(ssl_result.data)
        assert record_result.success, "Recording processing failed"
        
        # Verify pipeline integrity
        final_frame = record_result.data
        assert final_frame.sample_rate == environment.config.sample_rate
        assert final_frame.channels == environment.config.channels
        assert final_frame.frame_size == environment.config.frame_size
        
        # Verify audio quality is maintained
        input_rms = test_frame.get_rms_level()
        output_rms = final_frame.get_rms_level()
        assert abs(output_rms - input_rms) < 20, "Excessive audio level change through pipeline"
    
    @staticmethod
    async def test_real_time_processing_latency(environment: IntegrationTestEnvironment):
        """Test that the system meets real-time processing latency requirements."""
        denoise_service = await environment.get_service("DenoiseService")
        aec_service = await environment.get_service("AECService")
        ssl_service = await environment.get_service("SSLService")
        
        mock_generator = MockAudioGenerator(environment.config)
        latencies = []
        
        # Process 50 frames to get statistical data
        for i in range(50):
            test_frame = mock_generator.generate_speech_frame()
            
            start_time = asyncio.get_event_loop().time()
            
            # Process through core pipeline
            denoise_result = await denoise_service.process(test_frame)
            aec_result = await aec_service.process(denoise_result.data)
            ssl_result = await ssl_service.process(aec_result.data)
            
            end_time = asyncio.get_event_loop().time()
            
            assert denoise_result.success and aec_result.success and ssl_result.success
            
            pipeline_latency_ms = (end_time - start_time) * 1000
            latencies.append(pipeline_latency_ms)
        
        # Analyze latency performance
        avg_latency = np.mean(latencies)
        max_latency = np.max(latencies)
        p95_latency = np.percentile(latencies, 95)
        
        # Real-time requirements (10ms frame processing)
        assert avg_latency < 8.0, f"Average latency {avg_latency:.2f}ms exceeds 8ms requirement"
        assert max_latency < 15.0, f"Maximum latency {max_latency:.2f}ms exceeds 15ms requirement"
        assert p95_latency < 12.0, f"95th percentile latency {p95_latency:.2f}ms exceeds 12ms requirement"
    
    @staticmethod
    async def test_classroom_scenario_processing(environment: IntegrationTestEnvironment):
        """Test processing of realistic classroom audio scenarios."""
        denoise_service = await environment.get_service("DenoiseService")
        ssl_service = await environment.get_service("SSLService")
        
        mock_generator = MockAudioGenerator(environment.config)
        
        # Test different classroom scenarios
        scenarios = [
            "teacher_lecture",
            "student_presentation", 
            "group_discussion",
            "noisy_environment"
        ]
        
        scenario_results = {}
        
        for scenario in scenarios:
            # Generate 10 frames for each scenario
            frames = [
                mock_generator.generate_classroom_scenario_frame(scenario)
                for _ in range(10)
            ]
            
            processed_frames = []
            processing_times = []
            
            for frame in frames:
                start_time = asyncio.get_event_loop().time()
                
                # Process through denoise and SSL
                denoise_result = await denoise_service.process(frame)
                ssl_result = await ssl_service.process(denoise_result.data)
                
                end_time = asyncio.get_event_loop().time()
                
                assert denoise_result.success and ssl_result.success, f"Processing failed for {scenario}"
                
                processed_frames.append(ssl_result.data)
                processing_times.append((end_time - start_time) * 1000)
            
            # Analyze scenario processing
            avg_processing_time = np.mean(processing_times)
            
            scenario_results[scenario] = {
                'avg_processing_time_ms': avg_processing_time,
                'frames_processed': len(processed_frames),
                'success_rate': 1.0  # All frames processed successfully
            }
            
            # Each scenario should process within reasonable time
            assert avg_processing_time < 10.0, f"Scenario {scenario} processing too slow: {avg_processing_time:.2f}ms"
        
        # Verify all scenarios processed successfully
        assert len(scenario_results) == len(scenarios), "Not all scenarios were processed"
    
    @staticmethod
    async def test_concurrent_stream_processing(environment: IntegrationTestEnvironment):
        """Test concurrent processing of multiple audio streams."""
        denoise_service = await environment.get_service("DenoiseService")
        
        mock_generator = MockAudioGenerator(environment.config)
        
        async def process_stream(stream_id: int, frame_count: int):
            """Process a stream of audio frames."""
            latencies = []
            success_count = 0
            
            for i in range(frame_count):
                frame = mock_generator.generate_speech_frame()
                
                start_time = asyncio.get_event_loop().time()
                result = await denoise_service.process(frame)
                end_time = asyncio.get_event_loop().time()
                
                if result.success:
                    success_count += 1
                    latencies.append((end_time - start_time) * 1000)
                
                # Small delay to simulate real-time processing
                await asyncio.sleep(0.01)
            
            return stream_id, success_count, latencies
        
        # Test with 4 concurrent streams of 25 frames each
        stream_count = 4
        frames_per_stream = 25
        
        start_time = asyncio.get_event_loop().time()
        
        # Run streams concurrently
        tasks = [
            process_stream(i, frames_per_stream) 
            for i in range(stream_count)
        ]
        
        results = await asyncio.gather(*tasks)
        
        total_time = asyncio.get_event_loop().time() - start_time
        
        # Analyze concurrent processing results
        total_frames_processed = sum(result[1] for result in results)
        all_latencies = []
        for result in results:
            all_latencies.extend(result[2])
        
        avg_latency = np.mean(all_latencies) if all_latencies else 0
        throughput = total_frames_processed / total_time
        
        # Concurrent processing requirements
        expected_total_frames = stream_count * frames_per_stream
        success_rate = total_frames_processed / expected_total_frames
        
        assert success_rate > 0.95, f"Concurrent processing success rate {success_rate:.3f} below 95%"
        assert avg_latency < 15.0, f"Concurrent processing latency {avg_latency:.2f}ms too high"
        assert throughput > 50.0, f"Concurrent throughput {throughput:.1f} fps below 50 fps"
    
    @staticmethod
    async def test_error_recovery_and_resilience(environment: IntegrationTestEnvironment):
        """Test system error recovery and resilience."""
        denoise_service = await environment.get_service("DenoiseService")
        
        mock_generator = MockAudioGenerator(environment.config)
        
        # Test with various problematic inputs
        test_cases = [
            # Normal frame (should succeed)
            mock_generator.generate_speech_frame(),
            
            # Silent frame
            mock_generator.generate_silence_frame(),
            
            # High amplitude frame
            mock_generator.generate_sine_wave_frame(amplitude=0.9),
            
            # Frame with different sample rate (should be handled gracefully)
            mock_generator.generate_speech_frame(),  # We'll modify this
        ]
        
        # Modify one frame to have wrong sample rate
        invalid_frame = test_cases[-1]
        invalid_frame.sample_rate = 44100  # Wrong sample rate
        
        results = []
        
        for i, frame in enumerate(test_cases):
            try:
                result = await denoise_service.process(frame)
                results.append({
                    'frame_index': i,
                    'success': result.success,
                    'error': result.error if not result.success else None
                })
            except Exception as e:
                results.append({
                    'frame_index': i,
                    'success': False,
                    'error': str(e)
                })
        
        # Analyze error handling
        successful_frames = sum(1 for r in results if r['success'])
        
        # Most frames should succeed (except the invalid one)
        assert successful_frames >= 3, f"Only {successful_frames} frames processed successfully"
        
        # The invalid frame should be handled gracefully (not crash the system)
        invalid_frame_result = results[-1]
        assert not invalid_frame_result['success'], "Invalid frame should be rejected"
        assert invalid_frame_result['error'] is not None, "Error should be reported for invalid frame"
    
    @staticmethod
    async def test_system_stability_under_load(environment: IntegrationTestEnvironment):
        """Test system stability under sustained processing load."""
        services = [
            await environment.get_service("DenoiseService"),
            await environment.get_service("AECService"),
            await environment.get_service("SSLService")
        ]
        
        mock_generator = MockAudioGenerator(environment.config)
        
        # Run sustained load for 30 seconds
        duration = 30.0
        start_time = asyncio.get_event_loop().time()
        
        frame_count = 0
        error_count = 0
        latencies = []
        
        while (asyncio.get_event_loop().time() - start_time) < duration:
            frame = mock_generator.generate_speech_frame()
            
            try:
                proc_start = asyncio.get_event_loop().time()
                
                # Process through all services
                current_frame = frame
                for service in services:
                    result = await service.process(current_frame)
                    if not result.success:
                        error_count += 1
                        break
                    current_frame = result.data
                
                proc_end = asyncio.get_event_loop().time()
                
                latencies.append((proc_end - proc_start) * 1000)
                frame_count += 1
                
                # Simulate real-time processing interval
                await asyncio.sleep(0.01)
                
            except Exception as e:
                error_count += 1
        
        # Analyze stability metrics
        actual_duration = asyncio.get_event_loop().time() - start_time
        error_rate = error_count / frame_count if frame_count > 0 else 1.0
        avg_latency = np.mean(latencies) if latencies else 0
        throughput = frame_count / actual_duration
        
        # Stability requirements
        assert error_rate < 0.01, f"Error rate {error_rate:.4f} exceeds 1% threshold"
        assert frame_count > 1000, f"Only processed {frame_count} frames in {duration}s"
        assert avg_latency < 10.0, f"Average latency {avg_latency:.2f}ms too high under load"
        assert throughput > 80.0, f"Throughput {throughput:.1f} fps below 80 fps under load"


class TestEndToEndIntegration:
    """Pytest test class for end-to-end integration testing."""
    
    @pytest.fixture
    async def integration_config(self):
        """Audio configuration for integration testing."""
        return AudioConfig(
            sample_rate=48000,
            frame_size=480,  # 10ms frames
            channels=2,
            bit_depth=16
        )
    
    @pytest.fixture
    async def test_framework(self, integration_config):
        """Setup complete integration test framework."""
        environment, runner, regression_suite = create_integration_test_framework(integration_config)
        
        # Setup environment
        setup_success = await environment.setup_environment()
        assert setup_success, "Failed to setup integration test environment"
        
        yield environment, runner, regression_suite
        
        # Cleanup
        await environment.teardown_environment()
    
    async def test_run_complete_integration_suite(self, test_framework):
        """Run the complete integration test suite using the framework."""
        environment, runner, regression_suite = test_framework
        
        # Register test suites
        core_pipeline_suite = TestSuite(
            name="CorePipelineTests",
            description="Core audio processing pipeline integration tests",
            test_functions=[
                EndToEndIntegrationTests.test_complete_audio_pipeline,
                EndToEndIntegrationTests.test_real_time_processing_latency,
            ],
            timeout_seconds=120.0
        )
        
        classroom_scenario_suite = TestSuite(
            name="ClassroomScenarioTests", 
            description="Classroom-specific scenario integration tests",
            test_functions=[
                EndToEndIntegrationTests.test_classroom_scenario_processing,
            ],
            timeout_seconds=180.0
        )
        
        performance_suite = TestSuite(
            name="PerformanceTests",
            description="Performance and scalability integration tests", 
            test_functions=[
                EndToEndIntegrationTests.test_concurrent_stream_processing,
                EndToEndIntegrationTests.test_system_stability_under_load,
            ],
            timeout_seconds=300.0
        )
        
        resilience_suite = TestSuite(
            name="ResilienceTests",
            description="Error handling and system resilience tests",
            test_functions=[
                EndToEndIntegrationTests.test_error_recovery_and_resilience,
            ],
            timeout_seconds=60.0
        )
        
        # Register all suites
        runner.register_test_suite(core_pipeline_suite)
        runner.register_test_suite(classroom_scenario_suite)
        runner.register_test_suite(performance_suite)
        runner.register_test_suite(resilience_suite)
        
        # Run all tests
        report = await runner.run_all_tests()
        
        # Verify overall success
        success_rate = report['execution_summary']['success_rate']
        assert success_rate >= 0.90, f"Integration test success rate {success_rate:.2f} below 90%"
        
        # Verify no critical failures
        failed_tests = report['execution_summary']['failed']
        error_tests = report['execution_summary']['errors']
        
        assert failed_tests + error_tests <= 2, f"Too many test failures: {failed_tests} failed, {error_tests} errors"
        
        print(f"\n✓ Integration test suite completed successfully!")
        print(f"  Success rate: {success_rate*100:.1f}%")
        print(f"  Total tests: {report['execution_summary']['total_tests']}")
        print(f"  Duration: {report['execution_summary']['total_duration_ms']/1000:.1f}s")
    
    async def test_regression_testing_capabilities(self, test_framework):
        """Test the regression testing capabilities of the framework."""
        environment, runner, regression_suite = test_framework
        
        # Generate test data for regression baseline
        mock_generator = MockAudioGenerator(environment.config)
        denoise_service = await environment.get_service("DenoiseService")
        
        # Process test frames and collect metrics
        test_frames = [mock_generator.generate_speech_frame() for _ in range(10)]
        latencies = []
        
        for frame in test_frames:
            start_time = asyncio.get_event_loop().time()
            result = await denoise_service.process(frame)
            end_time = asyncio.get_event_loop().time()
            
            assert result.success
            latencies.append((end_time - start_time) * 1000)
        
        # Create baseline data
        baseline_data = {
            'performance_metrics': {
                'avg_latency_ms': np.mean(latencies),
                'max_latency_ms': np.max(latencies),
                'throughput_fps': len(test_frames) / (np.sum(latencies) / 1000)
            },
            'quality_metrics': {
                'overall_quality_score': 85.0,  # Simulated quality score
                'processing_success_rate': 1.0
            }
        }
        
        # Capture baseline
        test_name = "denoise_service_regression"
        await regression_suite.capture_baseline(test_name, baseline_data)
        
        # Simulate current test run (should be similar to baseline)
        current_data = {
            'performance_metrics': {
                'avg_latency_ms': np.mean(latencies) * 1.05,  # Slightly higher latency
                'max_latency_ms': np.max(latencies) * 1.03,
                'throughput_fps': len(test_frames) / (np.sum(latencies) / 1000) * 0.98
            },
            'quality_metrics': {
                'overall_quality_score': 84.0,  # Slightly lower quality
                'processing_success_rate': 1.0
            }
        }
        
        # Compare with baseline
        comparison_result = await regression_suite.compare_with_baseline(test_name, current_data)
        
        assert comparison_result['status'] == 'compared', "Baseline comparison should succeed"
        assert not comparison_result['regression_detected'], "Should not detect regression for small changes"
        
        print(f"✓ Regression testing framework working correctly")
        print(f"  Baseline comparison: {comparison_result['status']}")
        print(f"  Regression detected: {comparison_result['regression_detected']}")


# Standalone integration test runner
async def run_integration_tests():
    """Run integration tests as standalone script."""
    config = AudioConfig(sample_rate=48000, frame_size=480, channels=2)
    
    # Create test framework
    environment, runner, regression_suite = create_integration_test_framework(config)
    
    try:
        # Setup environment
        setup_success = await environment.setup_environment()
        if not setup_success:
            print("Failed to setup integration test environment")
            return False
        
        # Register and run tests
        test_suite = TestSuite(
            name="StandaloneIntegrationTests",
            description="Standalone integration test execution",
            test_functions=[
                EndToEndIntegrationTests.test_complete_audio_pipeline,
                EndToEndIntegrationTests.test_real_time_processing_latency,
                EndToEndIntegrationTests.test_classroom_scenario_processing,
            ]
        )
        
        runner.register_test_suite(test_suite)
        report = await runner.run_all_tests()
        
        success_rate = report['execution_summary']['success_rate']
        print(f"\nStandalone Integration Test Results:")
        print(f"Success Rate: {success_rate*100:.1f}%")
        
        return success_rate >= 0.90
        
    finally:
        await environment.teardown_environment()


if __name__ == "__main__":
    import sys
    success = asyncio.run(run_integration_tests())
    sys.exit(0 if success else 1)