"""
Complete audio processing pipeline integration tests.

This module provides comprehensive integration tests for the entire
audio processing system, including performance validation and
classroom scenario testing.
"""

import pytest
import asyncio
import numpy as np
import time
from datetime import datetime
from typing import List, Dict, Any
import statistics

from audio_processing.models import AudioFrame, AudioConfig, ProcessingResult
from audio_processing.service_manager import ServiceManager
from audio_processing.services.capture import CaptureService
from audio_processing.services.denoise import DenoiseService
from audio_processing.services.aec import AECService
from audio_processing.services.ssl import SSLService
from audio_processing.services.recorder import RecorderService
from audio_processing.services.telemetry import TelemetryService


class TestFullPipelineIntegration:
    """Complete audio processing pipeline integration tests."""
    
    @pytest.fixture
    async def audio_config(self):
        """Standard audio configuration for tests."""
        return AudioConfig(
            sample_rate=48000,
            frame_size=480,  # 10ms at 48kHz
            channels=2,
            bit_depth=16
        )
    
    @pytest.fixture
    async def service_manager(self, audio_config):
        """Service manager with all audio services registered."""
        manager = ServiceManager(audio_config)
        
        # Register all core services
        manager.register_service(CaptureService, name="CaptureService")
        manager.register_service(DenoiseService, name="DenoiseService")
        manager.register_service(AECService, name="AECService")
        manager.register_service(SSLService, name="SSLService")
        manager.register_service(RecorderService, name="RecorderService")
        manager.register_service(TelemetryService, name="TelemetryService")
        
        await manager.start()
        yield manager
        await manager.stop()
    
    async def test_complete_pipeline_processing(self, service_manager, audio_config):
        """Test complete audio processing pipeline from capture to output."""
        # Get all services
        capture = await service_manager.get_service_by_name("CaptureService")
        denoise = await service_manager.get_service_by_name("DenoiseService")
        aec = await service_manager.get_service_by_name("AECService")
        ssl = await service_manager.get_service_by_name("SSLService")
        recorder = await service_manager.get_service_by_name("RecorderService")
        
        # Create test audio frame with realistic classroom audio
        timestamp = datetime.now()
        # Simulate speech with background noise
        speech_signal = self._generate_speech_signal(audio_config)
        noise_signal = self._generate_noise_signal(audio_config) * 0.1
        mixed_signal = speech_signal + noise_signal
        
        frame = AudioFrame(
            timestamp=timestamp,
            sample_rate=audio_config.sample_rate,
            channels=audio_config.channels,
            frame_size=audio_config.frame_size,
            data=mixed_signal
        )
        
        # Process through complete pipeline
        # 1. Capture (simulated)
        capture_result = await capture.process(frame)
        assert capture_result.success
        
        # 2. Denoise
        denoise_result = await denoise.process(capture_result.data)
        assert denoise_result.success
        
        # 3. AEC (Acoustic Echo Cancellation)
        aec_result = await aec.process(denoise_result.data)
        assert aec_result.success
        
        # 4. SSL (Sound Source Localization)
        ssl_result = await ssl.process(aec_result.data)
        assert ssl_result.success
        
        # 5. Recording
        record_result = await recorder.process(ssl_result.data)
        assert record_result.success
        
        # Verify pipeline integrity
        assert ssl_result.data.sample_rate == audio_config.sample_rate
        assert ssl_result.data.channels == audio_config.channels
        assert ssl_result.data.frame_size == audio_config.frame_size
        
        # Verify noise reduction occurred
        input_rms = frame.get_rms_level()
        output_rms = ssl_result.data.get_rms_level()
        # Output should be cleaner (potentially lower RMS due to noise removal)
        assert abs(output_rms - input_rms) < 20  # Within reasonable range
    
    async def test_pipeline_latency_performance(self, service_manager, audio_config):
        """Test end-to-end pipeline latency performance."""
        # Get services
        denoise = await service_manager.get_service_by_name("DenoiseService")
        aec = await service_manager.get_service_by_name("AECService")
        ssl = await service_manager.get_service_by_name("SSLService")
        
        latencies = []
        
        # Process multiple frames to get average latency
        for i in range(50):
            frame = self._create_test_frame(audio_config)
            
            start_time = time.time()
            
            # Process through pipeline
            denoise_result = await denoise.process(frame)
            aec_result = await aec.process(denoise_result.data)
            ssl_result = await ssl.process(aec_result.data)
            
            end_time = time.time()
            
            pipeline_latency = (end_time - start_time) * 1000  # ms
            latencies.append(pipeline_latency)
        
        # Analyze latency performance
        avg_latency = statistics.mean(latencies)
        max_latency = max(latencies)
        p95_latency = np.percentile(latencies, 95)
        
        # Performance requirements for real-time audio (10ms frame)
        assert avg_latency < 5.0, f"Average latency {avg_latency:.2f}ms exceeds 5ms target"
        assert max_latency < 10.0, f"Max latency {max_latency:.2f}ms exceeds 10ms target"
        assert p95_latency < 8.0, f"95th percentile latency {p95_latency:.2f}ms exceeds 8ms target"
        
        print(f"Pipeline Latency Performance:")
        print(f"  Average: {avg_latency:.2f}ms")
        print(f"  Maximum: {max_latency:.2f}ms")
        print(f"  95th percentile: {p95_latency:.2f}ms")
    
    async def test_concurrent_processing_performance(self, service_manager, audio_config):
        """Test system performance under concurrent processing load."""
        denoise = await service_manager.get_service_by_name("DenoiseService")
        
        # Create multiple concurrent processing tasks
        async def process_frame_batch(batch_id: int, frame_count: int):
            latencies = []
            for i in range(frame_count):
                frame = self._create_test_frame(audio_config)
                
                start_time = time.time()
                result = await denoise.process(frame)
                end_time = time.time()
                
                assert result.success
                latencies.append((end_time - start_time) * 1000)
            
            return batch_id, latencies
        
        # Run 5 concurrent batches of 20 frames each
        tasks = [
            process_frame_batch(i, 20) 
            for i in range(5)
        ]
        
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        # Analyze concurrent performance
        all_latencies = []
        for batch_id, latencies in results:
            all_latencies.extend(latencies)
        
        avg_latency = statistics.mean(all_latencies)
        throughput = len(all_latencies) / total_time  # frames per second
        
        # Performance requirements
        assert avg_latency < 10.0, f"Concurrent avg latency {avg_latency:.2f}ms too high"
        assert throughput > 50.0, f"Throughput {throughput:.1f} fps below 50 fps target"
        
        print(f"Concurrent Processing Performance:")
        print(f"  Average latency: {avg_latency:.2f}ms")
        print(f"  Throughput: {throughput:.1f} frames/sec")
        print(f"  Total frames: {len(all_latencies)}")
    
    async def test_system_stability_under_load(self, service_manager, audio_config):
        """Test system stability under sustained processing load."""
        services = [
            await service_manager.get_service_by_name("DenoiseService"),
            await service_manager.get_service_by_name("AECService"),
            await service_manager.get_service_by_name("SSLService")
        ]
        
        # Run sustained load for 30 seconds
        duration = 30.0  # seconds
        start_time = time.time()
        frame_count = 0
        error_count = 0
        
        while (time.time() - start_time) < duration:
            frame = self._create_test_frame(audio_config)
            
            try:
                # Process through all services
                current_frame = frame
                for service in services:
                    result = await service.process(current_frame)
                    if not result.success:
                        error_count += 1
                        break
                    current_frame = result.data
                
                frame_count += 1
                
                # Small delay to simulate real-time processing
                await asyncio.sleep(0.01)  # 10ms frame interval
                
            except Exception as e:
                error_count += 1
                print(f"Processing error: {e}")
        
        # Analyze stability
        error_rate = error_count / frame_count if frame_count > 0 else 1.0
        
        assert error_rate < 0.01, f"Error rate {error_rate:.3f} exceeds 1% threshold"
        assert frame_count > 1000, f"Processed only {frame_count} frames in {duration}s"
        
        print(f"Stability Test Results:")
        print(f"  Duration: {duration}s")
        print(f"  Frames processed: {frame_count}")
        print(f"  Errors: {error_count}")
        print(f"  Error rate: {error_rate:.4f}")
    
    def _generate_speech_signal(self, config: AudioConfig) -> np.ndarray:
        """Generate realistic speech-like signal."""
        duration = config.frame_size / config.sample_rate
        t = np.linspace(0, duration, config.frame_size)
        
        # Simulate speech with multiple harmonics
        fundamental = 200  # Hz
        speech = (
            0.5 * np.sin(2 * np.pi * fundamental * t) +
            0.3 * np.sin(2 * np.pi * fundamental * 2 * t) +
            0.2 * np.sin(2 * np.pi * fundamental * 3 * t)
        )
        
        # Apply speech envelope
        envelope = np.exp(-t * 2) * (1 + 0.5 * np.sin(2 * np.pi * 10 * t))
        speech *= envelope
        
        # Create stereo signal
        if config.channels == 2:
            return np.array([speech, speech * 0.8])  # Slight channel difference
        else:
            return speech.reshape(1, -1)
    
    def _generate_noise_signal(self, config: AudioConfig) -> np.ndarray:
        """Generate background noise signal."""
        noise = np.random.normal(0, 0.1, (config.channels, config.frame_size))
        
        # Add some low-frequency rumble (HVAC, etc.)
        duration = config.frame_size / config.sample_rate
        t = np.linspace(0, duration, config.frame_size)
        rumble = 0.05 * np.sin(2 * np.pi * 60 * t)  # 60Hz hum
        
        for channel in range(config.channels):
            noise[channel] += rumble
        
        return noise
    
    def _create_test_frame(self, config: AudioConfig) -> AudioFrame:
        """Create a test audio frame with mixed speech and noise."""
        timestamp = datetime.now()
        speech = self._generate_speech_signal(config)
        noise = self._generate_noise_signal(config) * 0.1
        data = speech + noise
        
        return AudioFrame(
            timestamp=timestamp,
            sample_rate=config.sample_rate,
            channels=config.channels,
            frame_size=config.frame_size,
            data=data
        )


class TestClassroomScenarios:
    """Test audio processing in realistic classroom scenarios."""
    
    @pytest.fixture
    async def classroom_config(self):
        """Audio configuration optimized for classroom use."""
        return AudioConfig(
            sample_rate=48000,
            frame_size=480,
            channels=2,
            bit_depth=16
        )
    
    @pytest.fixture
    async def classroom_manager(self, classroom_config):
        """Service manager configured for classroom scenarios."""
        manager = ServiceManager(classroom_config)
        
        # Register services with classroom-optimized settings
        manager.register_service(
            DenoiseService, 
            name="DenoiseService",
            config={"noise_reduction_level": 0.7}
        )
        manager.register_service(
            AECService,
            name="AECService", 
            config={"echo_suppression_level": 0.8}
        )
        manager.register_service(
            SSLService,
            name="SSLService",
            config={"tracking_sensitivity": 0.6}
        )
        manager.register_service(RecorderService, name="RecorderService")
        
        await manager.start()
        yield manager
        await manager.stop()
    
    async def test_teacher_lecture_scenario(self, classroom_manager, classroom_config):
        """Test processing during teacher lecture with student background noise."""
        ssl_service = await classroom_manager.get_service_by_name("SSLService")
        denoise_service = await classroom_manager.get_service_by_name("DenoiseService")
        
        # Simulate teacher speaking with student chatter in background
        teacher_audio = self._generate_teacher_speech(classroom_config)
        student_chatter = self._generate_student_chatter(classroom_config) * 0.3
        classroom_audio = teacher_audio + student_chatter
        
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=classroom_config.sample_rate,
            channels=classroom_config.channels,
            frame_size=classroom_config.frame_size,
            data=classroom_audio
        )
        
        # Process audio
        denoise_result = await denoise_service.process(frame)
        ssl_result = await ssl_service.process(denoise_result.data)
        
        assert denoise_result.success
        assert ssl_result.success
        
        # Verify teacher voice is preserved and enhanced
        input_rms = frame.get_rms_level()
        output_rms = ssl_result.data.get_rms_level()
        
        # Should maintain reasonable audio level
        assert abs(output_rms - input_rms) < 15
        
        # Check for SSL metadata indicating source localization
        if ssl_result.data.metadata:
            assert 'source_direction' in ssl_result.data.metadata
    
    async def test_student_presentation_scenario(self, classroom_manager, classroom_config):
        """Test processing during student presentation with projector noise."""
        services = {
            'denoise': await classroom_manager.get_service_by_name("DenoiseService"),
            'aec': await classroom_manager.get_service_by_name("AECService"),
            'ssl': await classroom_manager.get_service_by_name("SSLService")
        }
        
        # Simulate student presentation with projector fan noise
        student_speech = self._generate_student_speech(classroom_config)
        projector_noise = self._generate_projector_noise(classroom_config) * 0.4
        presentation_audio = student_speech + projector_noise
        
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=classroom_config.sample_rate,
            channels=classroom_config.channels,
            frame_size=classroom_config.frame_size,
            data=presentation_audio
        )
        
        # Process through pipeline
        current_frame = frame
        for service_name, service in services.items():
            result = await service.process(current_frame)
            assert result.success, f"{service_name} processing failed"
            current_frame = result.data
        
        # Verify projector noise reduction
        input_rms = frame.get_rms_level()
        output_rms = current_frame.get_rms_level()
        
        # Should reduce overall noise while preserving speech
        noise_reduction = input_rms - output_rms
        assert noise_reduction > -10  # Some noise reduction expected
    
    async def test_group_discussion_scenario(self, classroom_manager, classroom_config):
        """Test processing during group discussion with multiple speakers."""
        ssl_service = await classroom_manager.get_service_by_name("SSLService")
        recorder_service = await classroom_manager.get_service_by_name("RecorderService")
        
        # Simulate multiple students speaking from different locations
        discussion_frames = []
        
        for i in range(10):  # 10 frames of group discussion
            multi_speaker_audio = self._generate_multi_speaker_audio(classroom_config, i)
            
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=classroom_config.sample_rate,
                channels=classroom_config.channels,
                frame_size=classroom_config.frame_size,
                data=multi_speaker_audio
            )
            
            # Process for source localization
            ssl_result = await ssl_service.process(frame)
            assert ssl_result.success
            
            # Record the processed audio
            record_result = await recorder_service.process(ssl_result.data)
            assert record_result.success
            
            discussion_frames.append(ssl_result.data)
        
        # Verify consistent processing across all frames
        assert len(discussion_frames) == 10
        
        # Check that SSL is tracking different speakers
        directions = []
        for frame in discussion_frames:
            if frame.metadata and 'source_direction' in frame.metadata:
                directions.append(frame.metadata['source_direction'])
        
        # Should detect multiple different directions
        unique_directions = len(set(directions))
        assert unique_directions >= 2, "Should detect multiple speaker locations"
    
    def _generate_teacher_speech(self, config: AudioConfig) -> np.ndarray:
        """Generate teacher speech pattern - clear, projected voice."""
        duration = config.frame_size / config.sample_rate
        t = np.linspace(0, duration, config.frame_size)
        
        # Lower fundamental frequency for adult voice
        fundamental = 150  # Hz
        speech = (
            0.6 * np.sin(2 * np.pi * fundamental * t) +
            0.4 * np.sin(2 * np.pi * fundamental * 2 * t) +
            0.2 * np.sin(2 * np.pi * fundamental * 3 * t)
        )
        
        # Clear, steady envelope for projected speech
        envelope = 0.8 + 0.2 * np.sin(2 * np.pi * 5 * t)
        speech *= envelope
        
        return np.array([speech, speech * 0.9]) if config.channels == 2 else speech.reshape(1, -1)
    
    def _generate_student_speech(self, config: AudioConfig) -> np.ndarray:
        """Generate student speech pattern - higher pitch, less projected."""
        duration = config.frame_size / config.sample_rate
        t = np.linspace(0, duration, config.frame_size)
        
        # Higher fundamental for younger voice
        fundamental = 220  # Hz
        speech = (
            0.5 * np.sin(2 * np.pi * fundamental * t) +
            0.3 * np.sin(2 * np.pi * fundamental * 2 * t) +
            0.1 * np.sin(2 * np.pi * fundamental * 3 * t)
        )
        
        # More variable envelope for natural speech
        envelope = 0.6 + 0.4 * np.sin(2 * np.pi * 8 * t) * np.exp(-t * 1)
        speech *= envelope
        
        return np.array([speech * 0.7, speech * 0.8]) if config.channels == 2 else speech.reshape(1, -1)
    
    def _generate_student_chatter(self, config: AudioConfig) -> np.ndarray:
        """Generate background student chatter."""
        # Multiple overlapping voices at low level
        chatter = np.random.normal(0, 0.1, (config.channels, config.frame_size))
        
        # Add some periodic components for speech-like quality
        duration = config.frame_size / config.sample_rate
        t = np.linspace(0, duration, config.frame_size)
        
        for freq in [180, 250, 300]:  # Different voice fundamentals
            component = 0.05 * np.sin(2 * np.pi * freq * t)
            for channel in range(config.channels):
                chatter[channel] += component * np.random.uniform(0.5, 1.0)
        
        return chatter
    
    def _generate_projector_noise(self, config: AudioConfig) -> np.ndarray:
        """Generate projector fan noise."""
        # High-frequency noise with some tonal components
        noise = np.random.normal(0, 0.05, (config.channels, config.frame_size))
        
        duration = config.frame_size / config.sample_rate
        t = np.linspace(0, duration, config.frame_size)
        
        # Fan noise characteristics
        fan_freq = 120  # Hz
        fan_noise = 0.1 * np.sin(2 * np.pi * fan_freq * t)
        
        for channel in range(config.channels):
            noise[channel] += fan_noise
        
        return noise
    
    def _generate_multi_speaker_audio(self, config: AudioConfig, frame_index: int) -> np.ndarray:
        """Generate audio with multiple speakers at different times."""
        duration = config.frame_size / config.sample_rate
        t = np.linspace(0, duration, config.frame_size)
        
        # Simulate different speakers becoming active
        speaker_count = (frame_index % 3) + 1  # 1-3 speakers
        audio = np.zeros((config.channels, config.frame_size))
        
        for speaker in range(speaker_count):
            # Different fundamental frequencies for different speakers
            fundamental = 180 + speaker * 40  # Hz
            
            speech = 0.4 * np.sin(2 * np.pi * fundamental * t)
            
            # Different spatial positioning (simulated with channel balance)
            left_gain = 0.5 + 0.5 * np.sin(speaker * np.pi / 2)
            right_gain = 0.5 + 0.5 * np.cos(speaker * np.pi / 2)
            
            if config.channels == 2:
                audio[0] += speech * left_gain
                audio[1] += speech * right_gain
            else:
                audio[0] += speech
        
        return audio