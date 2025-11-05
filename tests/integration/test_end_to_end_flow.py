"""
Integration tests for end-to-end audio processing flow
Tests complete audio pipeline from input to output
"""

import pytest
import asyncio
import numpy as np
import time
import threading
from unittest.mock import Mock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor
import tempfile
import os

from tests.mocks.mock_portaudio import MockPyAudio, get_mock_portaudio
from src.audio_core.models import AudioFrame, AudioProcessingConfig
from src.audio_core.device_manager import DeviceManager
from src.audio_core.capture_service import RealCaptureService
from src.processing.visual_pipeline import VisualAudioPipeline


@pytest.mark.integration
class TestEndToEndAudioFlow:
    """Test complete end-to-end audio processing flow"""
    
    @pytest.fixture
    def audio_system_config(self):
        """Create test configuration for audio system"""
        return ProcessingConfig(
            sample_rate=48000,
            channels=2,
            frame_size=1024,
            buffer_size=4096,
            aec_enabled=True,
            agc_enabled=True,
            ns_enabled=True,
            ssl_enabled=True,
            beamforming_enabled=False
        )
    
    @pytest.fixture
    def mock_audio_system(self, audio_system_config):
        """Create mock audio system with all components"""
        with patch("pyaudio.PyAudio", MockPyAudio):
            device_manager = DeviceManager()
            capture_service = RealCaptureService(audio_system_config)
            pipeline = VisualAudioPipeline(audio_system_config)
            
            return {
                "device_manager": device_manager,
                "capture_service": capture_service,
                "pipeline": pipeline,
                "config": audio_system_config
            }
    
    def test_complete_audio_pipeline(self, mock_audio_system):
        """Test complete audio processing pipeline"""
        device_manager = mock_audio_system["device_manager"]
        capture_service = mock_audio_system["capture_service"]
        pipeline = mock_audio_system["pipeline"]
        
        # Initialize system
        devices = device_manager.scan_devices()
        assert len(devices) > 0
        
        # Select input device
        input_device = devices[0]
        capture_service.configure_device(input_device)
        
        # Start capture
        capture_service.start_capture()
        
        # Process audio frames
        processed_frames = []
        for _ in range(10):  # Process 10 frames
            # Simulate audio frame from capture
            audio_data = np.random.randn(1024, 2).astype(np.float32) * 0.1
            frame = AudioFrame(
                data=audio_data,
                sample_rate=48000,
                channels=2,
                timestamp=time.time()
            )
            
            # Process through pipeline
            processed_frame = pipeline.process(frame)
            processed_frames.append(processed_frame)
        
        # Stop capture
        capture_service.stop_capture()
        
        # Verify results
        assert len(processed_frames) == 10
        for frame in processed_frames:
            assert frame is not None
            assert frame.data.shape[1] == 2  # 2 channels
            assert frame.sample_rate == 48000
    
    def test_audio_flow_with_errors(self, mock_audio_system):
        """Test audio flow with simulated errors"""
        capture_service = mock_audio_system["capture_service"]
        pipeline = mock_audio_system["pipeline"]
        
        # Simulate device errors
        mock_pa = get_mock_portaudio()
        mock_pa.set_error_simulation(device_error=True)
        
        # System should handle errors gracefully
        try:
            capture_service.start_capture()
            # Should either succeed with fallback or fail gracefully
        except Exception as e:
            assert "Device error" in str(e)
        
        # Reset error simulation
        mock_pa.set_error_simulation(device_error=False)
    
    def test_audio_quality_preservation(self, mock_audio_system):
        """Test that audio quality is preserved through pipeline"""
        pipeline = mock_audio_system["pipeline"]
        
        # Create high-quality test signal
        sample_rate = 48000
        duration = 1.0
        t = np.linspace(0, duration, int(sample_rate * duration))
        
        # Pure sine wave at 1kHz
        frequency = 1000
        original_signal = 0.5 * np.sin(2 * np.pi * frequency * t)
        
        # Create stereo frame
        stereo_data = np.column_stack([original_signal, original_signal])
        
        frame = AudioFrame(
            data=stereo_data.astype(np.float32),
            sample_rate=sample_rate,
            channels=2,
            timestamp=0.0
        )
        
        # Process through pipeline
        processed_frame = pipeline.process(frame)
        
        # Analyze quality preservation
        original_power = np.mean(original_signal ** 2)
        processed_power = np.mean(processed_frame.data[:, 0] ** 2)
        
        # Power should be preserved within reasonable bounds
        power_ratio = processed_power / original_power
        assert 0.5 < power_ratio < 2.0  # Within 3dB
        
        # Frequency content should be preserved
        original_fft = np.fft.fft(original_signal)
        processed_fft = np.fft.fft(processed_frame.data[:, 0])
        
        # Find peak frequencies
        freqs = np.fft.fftfreq(len(original_signal), 1/sample_rate)
        original_peak_idx = np.argmax(np.abs(original_fft[:len(original_fft)//2]))
        processed_peak_idx = np.argmax(np.abs(processed_fft[:len(processed_fft)//2]))
        
        original_peak_freq = abs(freqs[original_peak_idx])
        processed_peak_freq = abs(freqs[processed_peak_idx])
        
        # Peak frequency should be preserved
        assert abs(original_peak_freq - processed_peak_freq) < 10  # Within 10 Hz
    
    def test_latency_measurement(self, mock_audio_system):
        """Test end-to-end latency measurement"""
        pipeline = mock_audio_system["pipeline"]
        
        latencies = []
        
        for _ in range(20):  # Measure 20 frames
            # Create test frame
            audio_data = np.random.randn(1024, 2).astype(np.float32) * 0.1
            
            start_time = time.perf_counter()
            
            frame = AudioFrame(
                data=audio_data,
                sample_rate=48000,
                channels=2,
                timestamp=start_time
            )
            
            # Process frame
            processed_frame = pipeline.process(frame)
            
            end_time = time.perf_counter()
            
            # Calculate latency
            processing_latency = (end_time - start_time) * 1000  # ms
            latencies.append(processing_latency)
        
        # Analyze latency statistics
        avg_latency = np.mean(latencies)
        max_latency = np.max(latencies)
        std_latency = np.std(latencies)
        
        # Verify latency requirements
        assert avg_latency < 10.0  # Average < 10ms
        assert max_latency < 20.0  # Max < 20ms
        assert std_latency < 5.0   # Low jitter
    
    def test_memory_usage_stability(self, mock_audio_system):
        """Test memory usage remains stable during processing"""
        import psutil
        
        pipeline = mock_audio_system["pipeline"]
        process = psutil.Process()
        
        # Measure initial memory
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Process many frames
        for i in range(100):
            audio_data = np.random.randn(1024, 2).astype(np.float32) * 0.1
            frame = AudioFrame(
                data=audio_data,
                sample_rate=48000,
                channels=2,
                timestamp=time.time()
            )
            
            processed_frame = pipeline.process(frame)
            
            # Periodic memory check
            if i % 20 == 0:
                current_memory = process.memory_info().rss / 1024 / 1024
                memory_increase = current_memory - initial_memory
                
                # Memory should not grow excessively
                assert memory_increase < 50  # Less than 50MB increase
    
    def test_configuration_changes_during_runtime(self, mock_audio_system):
        """Test configuration changes during runtime"""
        pipeline = mock_audio_system["pipeline"]
        config = mock_audio_system["config"]
        
        # Process with initial configuration
        audio_data = np.random.randn(1024, 2).astype(np.float32) * 0.1
        frame = AudioFrame(
            data=audio_data,
            sample_rate=48000,
            channels=2,
            timestamp=time.time()
        )
        
        result1 = pipeline.process(frame)
        assert result1 is not None
        
        # Change configuration
        config.agc_enabled = False
        config.ns_enabled = False
        pipeline.update_configuration(config)
        
        # Process with new configuration
        result2 = pipeline.process(frame)
        assert result2 is not None
        
        # Results should be different due to configuration change
        # (This is a simplified check - actual implementation would be more sophisticated)
        assert not np.array_equal(result1.data, result2.data)


@pytest.mark.integration
class TestMultiDeviceConcurrentProcessing:
    """Test concurrent processing with multiple audio devices"""
    
    def test_multiple_input_devices(self):
        """Test processing from multiple input devices simultaneously"""
        with patch("pyaudio.PyAudio", MockPyAudio):
            device_manager = DeviceManager()
            devices = device_manager.scan_devices()
            
            # Filter input devices
            input_devices = [d for d in devices if d.maxInputChannels > 0]
            assert len(input_devices) >= 2
            
            # Create capture services for multiple devices
            capture_services = []
            for device in input_devices[:2]:  # Use first 2 input devices
                config = ProcessingConfig(
                    sample_rate=48000,
                    channels=min(device.maxInputChannels, 2),
                    frame_size=1024
                )
                service = RealCaptureService(config)
                service.configure_device(device)
                capture_services.append(service)
            
            # Start all capture services
            for service in capture_services:
                service.start_capture()
            
            # Simulate concurrent processing
            results = []
            
            def process_device(service):
                frames = []
                for _ in range(5):  # Capture 5 frames per device
                    # Simulate frame capture
                    audio_data = np.random.randn(1024, service.config.channels).astype(np.float32) * 0.1
                    frame = AudioFrame(
                        data=audio_data,
                        sample_rate=48000,
                        channels=service.config.channels,
                        timestamp=time.time()
                    )
                    frames.append(frame)
                    time.sleep(0.02)  # 20ms between frames
                return frames
            
            # Process devices concurrently
            with ThreadPoolExecutor(max_workers=len(capture_services)) as executor:
                futures = [executor.submit(process_device, service) for service in capture_services]
                
                for future in futures:
                    device_frames = future.result()
                    results.extend(device_frames)
            
            # Stop all services
            for service in capture_services:
                service.stop_capture()
            
            # Verify results
            assert len(results) == len(capture_services) * 5
            for frame in results:
                assert frame is not None
                assert frame.data.shape[0] == 1024
    
    def test_device_hotplug_simulation(self):
        """Test device hot-plug scenarios"""
        with patch("pyaudio.PyAudio", MockPyAudio):
            device_manager = DeviceManager()
            mock_pa = get_mock_portaudio()
            
            # Initial device scan
            initial_devices = device_manager.scan_devices()
            initial_count = len(initial_devices)
            
            # Simulate device addition
            from tests.mocks.mock_portaudio import MockDeviceInfo
            new_device = MockDeviceInfo(
                index=0,
                name="Hot-plugged Device",
                hostApi=0,
                maxInputChannels=2,
                maxOutputChannels=2,
                defaultSampleRate=48000.0,
                defaultLowInputLatency=0.01,
                defaultLowOutputLatency=0.01,
                defaultHighInputLatency=0.1,
                defaultHighOutputLatency=0.1
            )
            
            mock_pa.add_mock_device(new_device)
            
            # Rescan devices
            updated_devices = device_manager.scan_devices()
            assert len(updated_devices) == initial_count + 1
            
            # Simulate device removal
            mock_pa.remove_mock_device(0)
            
            # Rescan again
            final_devices = device_manager.scan_devices()
            assert len(final_devices) == initial_count
    
    def test_concurrent_processing_performance(self):
        """Test performance under concurrent processing load"""
        with patch("pyaudio.PyAudio", MockPyAudio):
            num_concurrent_streams = 4
            frames_per_stream = 50
            
            def process_stream(stream_id):
                """Process audio stream"""
                config = ProcessingConfig(
                    sample_rate=48000,
                    channels=2,
                    frame_size=1024
                )
                
                pipeline = VisualAudioPipeline(config)
                processing_times = []
                
                for frame_idx in range(frames_per_stream):
                    # Generate test audio
                    audio_data = np.random.randn(1024, 2).astype(np.float32) * 0.1
                    frame = AudioFrame(
                        data=audio_data,
                        sample_rate=48000,
                        channels=2,
                        timestamp=time.time()
                    )
                    
                    # Measure processing time
                    start_time = time.perf_counter()
                    processed_frame = pipeline.process(frame)
                    end_time = time.perf_counter()
                    
                    processing_time = (end_time - start_time) * 1000  # ms
                    processing_times.append(processing_time)
                    
                    assert processed_frame is not None
                
                return {
                    "stream_id": stream_id,
                    "avg_processing_time": np.mean(processing_times),
                    "max_processing_time": np.max(processing_times),
                    "frames_processed": len(processing_times)
                }
            
            # Run concurrent streams
            with ThreadPoolExecutor(max_workers=num_concurrent_streams) as executor:
                futures = [
                    executor.submit(process_stream, i) 
                    for i in range(num_concurrent_streams)
                ]
                
                results = [future.result() for future in futures]
            
            # Analyze performance
            total_frames = sum(r["frames_processed"] for r in results)
            avg_processing_times = [r["avg_processing_time"] for r in results]
            max_processing_times = [r["max_processing_time"] for r in results]
            
            assert total_frames == num_concurrent_streams * frames_per_stream
            
            # Performance should not degrade significantly under load
            overall_avg = np.mean(avg_processing_times)
            overall_max = np.max(max_processing_times)
            
            assert overall_avg < 15.0  # Average < 15ms under load
            assert overall_max < 30.0  # Max < 30ms under load


@pytest.mark.integration
@pytest.mark.slow
class TestLongTermStability:
    """Test long-term stability and reliability"""
    
    def test_extended_processing_stability(self):
        """Test system stability over extended processing period"""
        with patch("pyaudio.PyAudio", MockPyAudio):
            config = ProcessingConfig(
                sample_rate=48000,
                channels=2,
                frame_size=1024
            )
            
            pipeline = VisualAudioPipeline(config)
            
            # Process for extended period (simulated)
            num_frames = 1000  # Represents ~20 seconds at 48kHz
            error_count = 0
            processing_times = []
            
            for frame_idx in range(num_frames):
                try:
                    # Generate test audio
                    audio_data = np.random.randn(1024, 2).astype(np.float32) * 0.1
                    frame = AudioFrame(
                        data=audio_data,
                        sample_rate=48000,
                        channels=2,
                        timestamp=frame_idx * 1024 / 48000
                    )
                    
                    # Process frame
                    start_time = time.perf_counter()
                    processed_frame = pipeline.process(frame)
                    end_time = time.perf_counter()
                    
                    processing_time = (end_time - start_time) * 1000
                    processing_times.append(processing_time)
                    
                    assert processed_frame is not None
                    
                except Exception as e:
                    error_count += 1
                    print(f"Error at frame {frame_idx}: {e}")
                
                # Periodic checks
                if frame_idx % 100 == 0:
                    # Check processing time stability
                    recent_times = processing_times[-100:] if len(processing_times) >= 100 else processing_times
                    avg_time = np.mean(recent_times)
                    
                    # Processing time should remain stable
                    assert avg_time < 20.0  # Less than 20ms average
            
            # Final stability checks
            error_rate = error_count / num_frames
            assert error_rate < 0.01  # Less than 1% error rate
            
            # Processing time should be consistent
            overall_avg = np.mean(processing_times)
            overall_std = np.std(processing_times)
            
            assert overall_avg < 15.0  # Average < 15ms
            assert overall_std < 5.0   # Low variance
    
    def test_memory_leak_detection(self):
        """Test for memory leaks during extended operation"""
        import psutil
        
        with patch("pyaudio.PyAudio", MockPyAudio):
            config = ProcessingConfig(
                sample_rate=48000,
                channels=2,
                frame_size=1024
            )
            
            pipeline = VisualAudioPipeline(config)
            process = psutil.Process()
            
            # Baseline memory measurement
            baseline_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_measurements = [baseline_memory]
            
            # Process frames and monitor memory
            for frame_idx in range(500):  # Process 500 frames
                audio_data = np.random.randn(1024, 2).astype(np.float32) * 0.1
                frame = AudioFrame(
                    data=audio_data,
                    sample_rate=48000,
                    channels=2,
                    timestamp=time.time()
                )
                
                processed_frame = pipeline.process(frame)
                
                # Measure memory every 50 frames
                if frame_idx % 50 == 0:
                    current_memory = process.memory_info().rss / 1024 / 1024
                    memory_measurements.append(current_memory)
            
            # Analyze memory trend
            memory_increase = memory_measurements[-1] - memory_measurements[0]
            
            # Memory should not increase significantly
            assert memory_increase < 20  # Less than 20MB increase
            
            # Check for consistent memory growth (potential leak)
            if len(memory_measurements) > 3:
                # Calculate trend
                x = np.arange(len(memory_measurements))
                coeffs = np.polyfit(x, memory_measurements, 1)
                slope = coeffs[0]  # MB per measurement
                
                # Slope should be minimal (no significant growth trend)
                assert abs(slope) < 1.0  # Less than 1MB per measurement period
    
    def test_error_recovery_resilience(self):
        """Test system resilience and error recovery"""
        with patch("pyaudio.PyAudio", MockPyAudio):
            config = ProcessingConfig(
                sample_rate=48000,
                channels=2,
                frame_size=1024
            )
            
            pipeline = VisualAudioPipeline(config)
            mock_pa = get_mock_portaudio()
            
            successful_frames = 0
            recovered_errors = 0
            
            for frame_idx in range(200):
                # Randomly inject errors
                if frame_idx % 50 == 0:  # Every 50th frame
                    mock_pa.set_error_simulation(device_error=True)
                else:
                    mock_pa.set_error_simulation(device_error=False)
                
                try:
                    audio_data = np.random.randn(1024, 2).astype(np.float32) * 0.1
                    frame = AudioFrame(
                        data=audio_data,
                        sample_rate=48000,
                        channels=2,
                        timestamp=time.time()
                    )
                    
                    processed_frame = pipeline.process(frame)
                    
                    if processed_frame is not None:
                        successful_frames += 1
                    
                except Exception as e:
                    # System should recover from errors
                    recovered_errors += 1
                    
                    # Reset error simulation to allow recovery
                    mock_pa.set_error_simulation(device_error=False)
            
            # System should maintain high success rate despite errors
            success_rate = successful_frames / 200
            assert success_rate > 0.8  # At least 80% success rate
            
            # Should recover from most errors
            if recovered_errors > 0:
                recovery_rate = successful_frames / (successful_frames + recovered_errors)
                assert recovery_rate > 0.7  # At least 70% recovery rate


@pytest.mark.integration
class TestPlatformCompatibility:
    """Test platform-specific compatibility"""
    
    def test_cross_platform_audio_formats(self):
        """Test audio format compatibility across platforms"""
        formats_to_test = [
            {"format": "float32", "sample_rate": 48000, "channels": 2},
            {"format": "int16", "sample_rate": 44100, "channels": 2},
            {"format": "int24", "sample_rate": 96000, "channels": 8},
        ]
        
        with patch("pyaudio.PyAudio", MockPyAudio):
            mock_pa = get_mock_portaudio()
            
            for format_config in formats_to_test:
                # Test format support
                is_supported = mock_pa.is_format_supported(
                    sample_rate=format_config["sample_rate"],
                    input_channels=format_config["channels"],
                    output_channels=format_config["channels"]
                )
                
                # Most common formats should be supported
                if format_config["sample_rate"] <= 96000 and format_config["channels"] <= 8:
                    assert is_supported
    
    def test_buffer_size_compatibility(self):
        """Test different buffer sizes for platform compatibility"""
        buffer_sizes = [128, 256, 512, 1024, 2048, 4096]
        
        with patch("pyaudio.PyAudio", MockPyAudio):
            for buffer_size in buffer_sizes:
                config = ProcessingConfig(
                    sample_rate=48000,
                    channels=2,
                    frame_size=buffer_size,
                    buffer_size=buffer_size * 4
                )
                
                pipeline = VisualAudioPipeline(config)
                
                # Test processing with different buffer sizes
                audio_data = np.random.randn(buffer_size, 2).astype(np.float32) * 0.1
                frame = AudioFrame(
                    data=audio_data,
                    sample_rate=48000,
                    channels=2,
                    timestamp=time.time()
                )
                
                processed_frame = pipeline.process(frame)
                assert processed_frame is not None
                assert processed_frame.data.shape[0] == buffer_size
    
    def test_sample_rate_compatibility(self):
        """Test different sample rates for platform compatibility"""
        sample_rates = [8000, 16000, 22050, 44100, 48000, 96000]
        
        with patch("pyaudio.PyAudio", MockPyAudio):
            for sample_rate in sample_rates:
                config = ProcessingConfig(
                    sample_rate=sample_rate,
                    channels=2,
                    frame_size=1024
                )
                
                pipeline = VisualAudioPipeline(config)
                
                # Generate appropriate test signal
                duration = 1024 / sample_rate
                t = np.linspace(0, duration, 1024)
                test_signal = 0.1 * np.sin(2 * np.pi * 440 * t)  # 440 Hz tone
                
                audio_data = np.column_stack([test_signal, test_signal])
                frame = AudioFrame(
                    data=audio_data.astype(np.float32),
                    sample_rate=sample_rate,
                    channels=2,
                    timestamp=0.0
                )
                
                processed_frame = pipeline.process(frame)
                assert processed_frame is not None
                assert processed_frame.sample_rate == sample_rate


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

