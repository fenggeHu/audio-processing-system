"""
Long-term stability and reliability integration tests
Tests system behavior over extended periods and under stress
"""

import pytest
import time
import threading
import numpy as np
import psutil
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from tests.mocks.mock_portaudio import MockPyAudio
from src.audio_core.models import AudioProcessingConfig, AudioFrame
from src.processing.visual_pipeline import VisualAudioPipeline


@pytest.mark.integration
@pytest.mark.slow
class TestLongTermStability:
    """Test long-term system stability"""
    
    def test_extended_processing_no_degradation(self):
        """Test processing performance doesn't degrade over time"""
        with patch("pyaudio.PyAudio", MockPyAudio):
            config = ProcessingConfig(
                sample_rate=48000,
                channels=2,
                frame_size=1024
            )
            
            pipeline = VisualAudioPipeline(config)
            processing_times = []
            
            # Process for extended period
            for frame_idx in range(500):  # ~10 seconds worth
                audio_data = np.random.randn(1024, 2).astype(np.float32) * 0.1
                frame = AudioFrame(
                    data=audio_data,
                    sample_rate=48000,
                    channels=2,
                    timestamp=time.time()
                )
                
                start_time = time.perf_counter()
                processed_frame = pipeline.process(frame)
                end_time = time.perf_counter()
                
                processing_time = (end_time - start_time) * 1000
                processing_times.append(processing_time)
                
                assert processed_frame is not None
            
            # Analyze performance stability
            first_half = processing_times[:250]
            second_half = processing_times[250:]
            
            avg_first = np.mean(first_half)
            avg_second = np.mean(second_half)
            
            # Performance should not degrade significantly
            degradation = (avg_second - avg_first) / avg_first
            assert abs(degradation) < 0.2  # Less than 20% change
    
    def test_memory_stability_over_time(self):
        """Test memory usage remains stable over extended operation"""
        with patch("pyaudio.PyAudio", MockPyAudio):
            config = ProcessingConfig(
                sample_rate=48000,
                channels=2,
                frame_size=1024
            )
            
            pipeline = VisualAudioPipeline(config)
            process = psutil.Process()
            
            memory_measurements = []
            
            for frame_idx in range(200):
                # Measure memory every 10 frames
                if frame_idx % 10 == 0:
                    memory_mb = process.memory_info().rss / 1024 / 1024
                    memory_measurements.append(memory_mb)
                
                audio_data = np.random.randn(1024, 2).astype(np.float32) * 0.1
                frame = AudioFrame(
                    data=audio_data,
                    sample_rate=48000,
                    channels=2,
                    timestamp=time.time()
                )
                
                processed_frame = pipeline.process(frame)
                assert processed_frame is not None
            
            # Check memory stability
            memory_increase = memory_measurements[-1] - memory_measurements[0]
            assert memory_increase < 10  # Less than 10MB increase
    
    def test_error_recovery_resilience(self):
        """Test system resilience to repeated errors"""
        with patch("pyaudio.PyAudio", MockPyAudio):
            config = ProcessingConfig(
                sample_rate=48000,
                channels=2,
                frame_size=1024
            )
            
            pipeline = VisualAudioPipeline(config)
            
            successful_frames = 0
            error_frames = 0
            
            for frame_idx in range(100):
                try:
                    # Inject errors periodically
                    if frame_idx % 20 == 0:
                        # Simulate corrupted audio data
                        audio_data = np.full((1024, 2), np.inf, dtype=np.float32)
                    else:
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
                    
                except Exception:
                    error_frames += 1
            
            # System should maintain high success rate
            success_rate = successful_frames / (successful_frames + error_frames)
            assert success_rate > 0.8  # At least 80% success rate


@pytest.mark.integration
class TestStressConditions:
    """Test system behavior under stress conditions"""
    
    def test_high_cpu_load_handling(self):
        """Test system behavior under high CPU load"""
        with patch("pyaudio.PyAudio", MockPyAudio):
            config = ProcessingConfig(
                sample_rate=48000,
                channels=2,
                frame_size=1024
            )
            
            pipeline = VisualAudioPipeline(config)
            
            def cpu_stress_task():
                """Generate CPU load"""
                for _ in range(1000000):
                    _ = sum(i * i for i in range(100))
            
            # Start CPU stress in background
            stress_thread = threading.Thread(target=cpu_stress_task)
            stress_thread.daemon = True
            stress_thread.start()
            
            processing_times = []
            
            # Process audio under CPU stress
            for _ in range(50):
                audio_data = np.random.randn(1024, 2).astype(np.float32) * 0.1
                frame = AudioFrame(
                    data=audio_data,
                    sample_rate=48000,
                    channels=2,
                    timestamp=time.time()
                )
                
                start_time = time.perf_counter()
                processed_frame = pipeline.process(frame)
                end_time = time.perf_counter()
                
                processing_time = (end_time - start_time) * 1000
                processing_times.append(processing_time)
                
                assert processed_frame is not None
            
            # Processing should still meet timing requirements
            avg_time = np.mean(processing_times)
            max_time = np.max(processing_times)
            
            assert avg_time < 50.0  # Average < 50ms under stress
            assert max_time < 100.0  # Max < 100ms under stress
    
    def test_memory_pressure_handling(self):
        """Test system behavior under memory pressure"""
        with patch("pyaudio.PyAudio", MockPyAudio):
            config = ProcessingConfig(
                sample_rate=48000,
                channels=2,
                frame_size=1024
            )
            
            pipeline = VisualAudioPipeline(config)
            
            # Create memory pressure
            memory_hogs = []
            for _ in range(10):
                # Allocate large arrays
                memory_hog = np.zeros((1000, 1000), dtype=np.float64)
                memory_hogs.append(memory_hog)
            
            successful_frames = 0
            
            try:
                # Process audio under memory pressure
                for _ in range(30):
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
                
            finally:
                # Cleanup memory
                del memory_hogs
            
            # Should process most frames successfully
            assert successful_frames >= 25  # At least 25/30 frames


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
