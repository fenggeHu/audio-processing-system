"""
Classroom application scenario validation tests.

This module provides comprehensive testing of the audio processing system
in realistic classroom environments and use cases.
"""

import pytest
import asyncio
import numpy as np
from datetime import datetime
from typing import List, Dict, Any
import json

from audio_processing.models import AudioFrame, AudioConfig, ProcessingResult
from audio_processing.service_manager import ServiceManager
from audio_processing.services.capture import CaptureService
from audio_processing.services.denoise import DenoiseService
from audio_processing.services.aec import AECService
from audio_processing.services.ssl import SSLService
from audio_processing.services.recorder import RecorderService
from audio_processing.quality_assessment import AudioQualityAssessment


class ClassroomScenarioValidator:
    """Validator for classroom-specific audio processing scenarios."""
    
    def __init__(self, config: AudioConfig):
        self.config = config
        self.quality_assessor = AudioQualityAssessment(config.sample_rate)
        self.scenario_results = {}
    
    async def validate_all_scenarios(self, service_manager: ServiceManager) -> Dict[str, Any]:
        """Run all classroom scenario validations."""
        scenarios = [
            self.validate_teacher_lecture,
            self.validate_student_presentation,
            self.validate_group_discussion,
            self.validate_remote_learning,
            self.validate_multimedia_playback,
            self.validate_noisy_environment,
            self.validate_multiple_microphones
        ]
        
        results = {}
        
        for scenario in scenarios:
            scenario_name = scenario.__name__.replace('validate_', '')
            try:
                result = await scenario(service_manager)
                results[scenario_name] = result
                print(f"✓ {scenario_name}: PASSED")
            except Exception as e:
                results[scenario_name] = {'status': 'FAILED', 'error': str(e)}
                print(f"✗ {scenario_name}: FAILED - {e}")
        
        return results
    
    async def validate_teacher_lecture(self, service_manager: ServiceManager) -> Dict[str, Any]:
        """Validate teacher lecture scenario with student background noise."""
        # Get required services
        denoise = await service_manager.get_service_by_name("DenoiseService")
        ssl = await service_manager.get_service_by_name("SSLService")
        
        # Generate teacher lecture audio with background noise
        lecture_frames = self._generate_teacher_lecture_scenario()
        
        results = {
            'scenario': 'teacher_lecture',
            'frame_count': len(lecture_frames),
            'processing_results': [],
            'quality_metrics': {},
            'performance_metrics': {}
        }
        
        processed_frames = []
        processing_times = []
        
        for i, frame in enumerate(lecture_frames):
            start_time = asyncio.get_event_loop().time()
            
            # Process through denoise and SSL
            denoise_result = await denoise.process(frame)
            assert denoise_result.success, f"Denoise failed on frame {i}"
            
            ssl_result = await ssl.process(denoise_result.data)
            assert ssl_result.success, f"SSL failed on frame {i}"
            
            end_time = asyncio.get_event_loop().time()
            processing_time = (end_time - start_time) * 1000  # ms
            processing_times.append(processing_time)
            
            processed_frames.append(ssl_result.data)
            
            results['processing_results'].append({
                'frame_index': i,
                'processing_time_ms': processing_time,
                'denoise_success': denoise_result.success,
                'ssl_success': ssl_result.success
            })
        
        # Analyze quality improvement
        quality_report = self.quality_assessor.generate_quality_report(
            lecture_frames, processed_frames
        )
        results['quality_metrics'] = quality_report
        
        # Performance analysis
        results['performance_metrics'] = {
            'avg_processing_time_ms': np.mean(processing_times),
            'max_processing_time_ms': np.max(processing_times),
            'processing_consistency': np.std(processing_times)
        }
        
        # Validate requirements
        assert np.mean(processing_times) < 10.0, "Average processing time exceeds 10ms"
        assert quality_report.get('overall_quality_score', 0) > 70, "Quality score below 70"
        
        # Check noise reduction effectiveness
        if 'processing_impact' in quality_report:
            noise_reduction = quality_report['processing_impact'].get('avg_noise_reduction_db', 0)
            assert noise_reduction > 3.0, f"Insufficient noise reduction: {noise_reduction:.1f}dB"
        
        results['status'] = 'PASSED'
        return results
    
    async def validate_student_presentation(self, service_manager: ServiceManager) -> Dict[str, Any]:
        """Validate student presentation with projector noise and echo."""
        aec = await service_manager.get_service_by_name("AECService")
        denoise = await service_manager.get_service_by_name("DenoiseService")
        recorder = await service_manager.get_service_by_name("RecorderService")
        
        # Generate student presentation scenario
        presentation_frames = self._generate_student_presentation_scenario()
        
        results = {
            'scenario': 'student_presentation',
            'frame_count': len(presentation_frames),
            'echo_cancellation_effectiveness': [],
            'recording_quality': []
        }
        
        for i, frame in enumerate(presentation_frames):
            # Process through AEC, denoise, and recording
            aec_result = await aec.process(frame)
            assert aec_result.success, f"AEC failed on frame {i}"
            
            denoise_result = await denoise.process(aec_result.data)
            assert denoise_result.success, f"Denoise failed on frame {i}"
            
            record_result = await recorder.process(denoise_result.data)
            assert record_result.success, f"Recording failed on frame {i}"
            
            # Assess echo cancellation
            echo_reduction = self._assess_echo_cancellation(frame, aec_result.data)
            results['echo_cancellation_effectiveness'].append(echo_reduction)
            
            # Assess recording quality
            recording_quality = self.quality_assessor.assess_frame_quality(record_result.data)
            results['recording_quality'].append(recording_quality.speech_intelligibility_score)
        
        # Validate echo cancellation performance
        avg_echo_reduction = np.mean(results['echo_cancellation_effectiveness'])
        assert avg_echo_reduction > 10.0, f"Insufficient echo cancellation: {avg_echo_reduction:.1f}dB"
        
        # Validate recording quality
        avg_recording_quality = np.mean(results['recording_quality'])
        assert avg_recording_quality > 0.7, f"Recording quality too low: {avg_recording_quality:.2f}"
        
        results['status'] = 'PASSED'
        return results
    
    async def validate_group_discussion(self, service_manager: ServiceManager) -> Dict[str, Any]:
        """Validate group discussion with multiple speakers."""
        ssl = await service_manager.get_service_by_name("SSLService")
        
        # Generate group discussion scenario
        discussion_frames = self._generate_group_discussion_scenario()
        
        results = {
            'scenario': 'group_discussion',
            'speaker_tracking': [],
            'source_localization_accuracy': []
        }
        
        expected_speakers = 4  # Number of simulated speakers
        detected_directions = set()
        
        for i, frame in enumerate(discussion_frames):
            ssl_result = await ssl.process(frame)
            assert ssl_result.success, f"SSL failed on frame {i}"
            
            # Check for source localization metadata
            if ssl_result.data.metadata and 'source_direction' in ssl_result.data.metadata:
                direction = ssl_result.data.metadata['source_direction']
                detected_directions.add(direction)
                
                results['speaker_tracking'].append({
                    'frame_index': i,
                    'detected_direction': direction,
                    'confidence': ssl_result.data.metadata.get('confidence', 0.0)
                })
        
        # Validate speaker detection
        unique_speakers_detected = len(detected_directions)
        detection_rate = unique_speakers_detected / expected_speakers
        
        assert detection_rate >= 0.75, f"Speaker detection rate too low: {detection_rate:.2f}"
        
        results['unique_speakers_detected'] = unique_speakers_detected
        results['detection_rate'] = detection_rate
        results['status'] = 'PASSED'
        return results
    
    async def validate_remote_learning(self, service_manager: ServiceManager) -> Dict[str, Any]:
        """Validate remote learning scenario with network audio artifacts."""
        denoise = await service_manager.get_service_by_name("DenoiseService")
        aec = await service_manager.get_service_by_name("AECService")
        
        # Generate remote learning audio with compression artifacts
        remote_frames = self._generate_remote_learning_scenario()
        
        results = {
            'scenario': 'remote_learning',
            'artifact_reduction': [],
            'speech_clarity_improvement': []
        }
        
        for i, frame in enumerate(remote_frames):
            # Process for artifact reduction
            denoise_result = await denoise.process(frame)
            aec_result = await aec.process(denoise_result.data)
            
            assert denoise_result.success and aec_result.success
            
            # Assess artifact reduction
            input_quality = self.quality_assessor.assess_frame_quality(frame)
            output_quality = self.quality_assessor.assess_frame_quality(aec_result.data)
            
            artifact_reduction = input_quality.thd_percent - output_quality.thd_percent
            speech_improvement = (output_quality.speech_intelligibility_score - 
                                input_quality.speech_intelligibility_score)
            
            results['artifact_reduction'].append(artifact_reduction)
            results['speech_clarity_improvement'].append(speech_improvement)
        
        # Validate improvements
        avg_artifact_reduction = np.mean(results['artifact_reduction'])
        avg_speech_improvement = np.mean(results['speech_clarity_improvement'])
        
        assert avg_artifact_reduction > 0, "No artifact reduction achieved"
        assert avg_speech_improvement > 0, "No speech clarity improvement"
        
        results['status'] = 'PASSED'
        return results
    
    async def validate_multimedia_playback(self, service_manager: ServiceManager) -> Dict[str, Any]:
        """Validate multimedia content playback processing."""
        denoise = await service_manager.get_service_by_name("DenoiseService")
        
        # Generate multimedia audio (music, video content)
        multimedia_frames = self._generate_multimedia_scenario()
        
        results = {
            'scenario': 'multimedia_playback',
            'frequency_preservation': [],
            'dynamic_range_preservation': []
        }
        
        for i, frame in enumerate(multimedia_frames):
            denoise_result = await denoise.process(frame)
            assert denoise_result.success
            
            # Assess multimedia quality preservation
            quality_impact = self.quality_assessor.assess_processing_quality(
                frame, denoise_result.data
            )
            
            results['frequency_preservation'].append(
                quality_impact['frequency_response_preservation']
            )
            results['dynamic_range_preservation'].append(
                quality_impact['dynamic_range_change_db']
            )
        
        # Validate multimedia quality preservation
        avg_freq_preservation = np.mean(results['frequency_preservation'])
        avg_dynamic_preservation = np.mean(results['dynamic_range_preservation'])
        
        assert avg_freq_preservation > 0.8, "Poor frequency response preservation"
        assert abs(avg_dynamic_preservation) < 3.0, "Excessive dynamic range change"
        
        results['status'] = 'PASSED'
        return results
    
    async def validate_noisy_environment(self, service_manager: ServiceManager) -> Dict[str, Any]:
        """Validate processing in very noisy classroom environment."""
        denoise = await service_manager.get_service_by_name("DenoiseService")
        
        # Generate high-noise scenario
        noisy_frames = self._generate_noisy_environment_scenario()
        
        results = {
            'scenario': 'noisy_environment',
            'noise_reduction_performance': [],
            'speech_preservation': []
        }
        
        for i, frame in enumerate(noisy_frames):
            denoise_result = await denoise.process(frame)
            assert denoise_result.success
            
            # Assess noise reduction in challenging conditions
            input_metrics = self.quality_assessor.assess_frame_quality(frame)
            output_metrics = self.quality_assessor.assess_frame_quality(denoise_result.data)
            
            noise_reduction = input_metrics.snr_db - output_metrics.snr_db
            speech_preservation = output_metrics.speech_intelligibility_score
            
            results['noise_reduction_performance'].append(noise_reduction)
            results['speech_preservation'].append(speech_preservation)
        
        # Validate performance in challenging conditions
        avg_noise_reduction = np.mean(results['noise_reduction_performance'])
        avg_speech_preservation = np.mean(results['speech_preservation'])
        
        assert avg_noise_reduction > 5.0, f"Insufficient noise reduction: {avg_noise_reduction:.1f}dB"
        assert avg_speech_preservation > 0.6, f"Poor speech preservation: {avg_speech_preservation:.2f}"
        
        results['status'] = 'PASSED'
        return results
    
    async def validate_multiple_microphones(self, service_manager: ServiceManager) -> Dict[str, Any]:
        """Validate multi-microphone array processing."""
        ssl = await service_manager.get_service_by_name("SSLService")
        
        # Generate multi-microphone scenario
        multi_mic_frames = self._generate_multi_microphone_scenario()
        
        results = {
            'scenario': 'multiple_microphones',
            'spatial_processing': [],
            'beamforming_effectiveness': []
        }
        
        for i, frame in enumerate(multi_mic_frames):
            ssl_result = await ssl.process(frame)
            assert ssl_result.success
            
            # Assess spatial processing
            if ssl_result.data.metadata:
                spatial_info = ssl_result.data.metadata.get('spatial_processing', {})
                beamforming_gain = spatial_info.get('beamforming_gain', 0)
                
                results['spatial_processing'].append(spatial_info)
                results['beamforming_effectiveness'].append(beamforming_gain)
        
        # Validate multi-microphone processing
        if results['beamforming_effectiveness']:
            avg_beamforming_gain = np.mean(results['beamforming_effectiveness'])
            assert avg_beamforming_gain > 3.0, f"Low beamforming gain: {avg_beamforming_gain:.1f}dB"
        
        results['status'] = 'PASSED'
        return results
    
    def _generate_teacher_lecture_scenario(self) -> List[AudioFrame]:
        """Generate audio frames simulating teacher lecture with student noise."""
        frames = []
        
        for i in range(20):  # 20 frames of lecture
            # Teacher speech (clear, projected)
            teacher_signal = self._generate_teacher_speech()
            
            # Student background chatter
            student_noise = self._generate_student_background_noise() * 0.2
            
            # HVAC noise
            hvac_noise = self._generate_hvac_noise() * 0.1
            
            # Combine signals
            combined_signal = teacher_signal + student_noise + hvac_noise
            
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=self.config.sample_rate,
                channels=self.config.channels,
                frame_size=self.config.frame_size,
                data=combined_signal
            )
            
            frames.append(frame)
        
        return frames
    
    def _generate_student_presentation_scenario(self) -> List[AudioFrame]:
        """Generate student presentation with projector noise and echo."""
        frames = []
        
        for i in range(15):
            # Student speech (less projected than teacher)
            student_signal = self._generate_student_speech()
            
            # Projector fan noise
            projector_noise = self._generate_projector_noise() * 0.3
            
            # Echo from room acoustics
            echo_signal = self._add_echo(student_signal, delay_ms=50, decay=0.3)
            
            combined_signal = student_signal + echo_signal + projector_noise
            
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=self.config.sample_rate,
                channels=self.config.channels,
                frame_size=self.config.frame_size,
                data=combined_signal
            )
            
            frames.append(frame)
        
        return frames
    
    def _generate_group_discussion_scenario(self) -> List[AudioFrame]:
        """Generate group discussion with multiple speakers."""
        frames = []
        
        for i in range(25):
            # Simulate 4 different speakers taking turns
            active_speaker = i % 4
            
            # Generate speech from different spatial positions
            speaker_signals = []
            for speaker_id in range(4):
                if speaker_id == active_speaker:
                    signal = self._generate_student_speech() * 0.8
                else:
                    signal = self._generate_student_speech() * 0.1  # Background
                
                # Apply spatial positioning
                positioned_signal = self._apply_spatial_positioning(signal, speaker_id)
                speaker_signals.append(positioned_signal)
            
            # Combine all speakers
            combined_signal = sum(speaker_signals)
            
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=self.config.sample_rate,
                channels=self.config.channels,
                frame_size=self.config.frame_size,
                data=combined_signal
            )
            
            frames.append(frame)
        
        return frames
    
    def _generate_remote_learning_scenario(self) -> List[AudioFrame]:
        """Generate remote learning audio with compression artifacts."""
        frames = []
        
        for i in range(15):
            # Clean speech signal
            speech_signal = self._generate_teacher_speech()
            
            # Add compression artifacts
            compressed_signal = self._add_compression_artifacts(speech_signal)
            
            # Add network jitter effects
            jittered_signal = self._add_network_jitter(compressed_signal)
            
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=self.config.sample_rate,
                channels=self.config.channels,
                frame_size=self.config.frame_size,
                data=jittered_signal
            )
            
            frames.append(frame)
        
        return frames
    
    def _generate_multimedia_scenario(self) -> List[AudioFrame]:
        """Generate multimedia content audio."""
        frames = []
        
        for i in range(10):
            # Music-like signal with rich harmonics
            music_signal = self._generate_music_signal()
            
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=self.config.sample_rate,
                channels=self.config.channels,
                frame_size=self.config.frame_size,
                data=music_signal
            )
            
            frames.append(frame)
        
        return frames
    
    def _generate_noisy_environment_scenario(self) -> List[AudioFrame]:
        """Generate very noisy classroom environment."""
        frames = []
        
        for i in range(20):
            # Speech signal
            speech_signal = self._generate_teacher_speech() * 0.5
            
            # High level of various noises
            construction_noise = self._generate_construction_noise() * 0.4
            student_noise = self._generate_student_background_noise() * 0.6
            hvac_noise = self._generate_hvac_noise() * 0.3
            
            combined_signal = speech_signal + construction_noise + student_noise + hvac_noise
            
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=self.config.sample_rate,
                channels=self.config.channels,
                frame_size=self.config.frame_size,
                data=combined_signal
            )
            
            frames.append(frame)
        
        return frames
    
    def _generate_multi_microphone_scenario(self) -> List[AudioFrame]:
        """Generate multi-microphone array scenario."""
        frames = []
        
        for i in range(15):
            # Speech from specific direction
            speech_signal = self._generate_teacher_speech()
            
            # Simulate microphone array with spatial information
            # This would normally come from actual microphone array processing
            array_signal = self._simulate_microphone_array(speech_signal, direction=45)
            
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=self.config.sample_rate,
                channels=self.config.channels,
                frame_size=self.config.frame_size,
                data=array_signal
            )
            
            frames.append(frame)
        
        return frames
    
    # Signal generation helper methods
    def _generate_teacher_speech(self) -> np.ndarray:
        """Generate teacher speech pattern."""
        duration = self.config.frame_size / self.config.sample_rate
        t = np.linspace(0, duration, self.config.frame_size)
        
        # Adult voice characteristics
        fundamental = 150  # Hz
        speech = (
            0.6 * np.sin(2 * np.pi * fundamental * t) +
            0.4 * np.sin(2 * np.pi * fundamental * 2 * t) +
            0.2 * np.sin(2 * np.pi * fundamental * 3 * t)
        )
        
        # Speech envelope
        envelope = 0.8 + 0.2 * np.sin(2 * np.pi * 5 * t)
        speech *= envelope
        
        return np.array([speech, speech * 0.9]) if self.config.channels == 2 else speech.reshape(1, -1)
    
    def _generate_student_speech(self) -> np.ndarray:
        """Generate student speech pattern."""
        duration = self.config.frame_size / self.config.sample_rate
        t = np.linspace(0, duration, self.config.frame_size)
        
        # Younger voice characteristics
        fundamental = 220  # Hz
        speech = (
            0.5 * np.sin(2 * np.pi * fundamental * t) +
            0.3 * np.sin(2 * np.pi * fundamental * 2 * t) +
            0.1 * np.sin(2 * np.pi * fundamental * 3 * t)
        )
        
        # More variable envelope
        envelope = 0.6 + 0.4 * np.sin(2 * np.pi * 8 * t) * np.exp(-t * 1)
        speech *= envelope
        
        return np.array([speech * 0.7, speech * 0.8]) if self.config.channels == 2 else speech.reshape(1, -1)
    
    def _generate_student_background_noise(self) -> np.ndarray:
        """Generate student background chatter."""
        noise = np.random.normal(0, 0.1, (self.config.channels, self.config.frame_size))
        
        # Add speech-like components
        duration = self.config.frame_size / self.config.sample_rate
        t = np.linspace(0, duration, self.config.frame_size)
        
        for freq in [180, 250, 300]:
            component = 0.05 * np.sin(2 * np.pi * freq * t)
            for channel in range(self.config.channels):
                noise[channel] += component * np.random.uniform(0.5, 1.0)
        
        return noise
    
    def _generate_hvac_noise(self) -> np.ndarray:
        """Generate HVAC system noise."""
        noise = np.random.normal(0, 0.03, (self.config.channels, self.config.frame_size))
        
        # Add low-frequency rumble
        duration = self.config.frame_size / self.config.sample_rate
        t = np.linspace(0, duration, self.config.frame_size)
        rumble = 0.02 * np.sin(2 * np.pi * 60 * t)  # 60Hz hum
        
        for channel in range(self.config.channels):
            noise[channel] += rumble
        
        return noise
    
    def _generate_projector_noise(self) -> np.ndarray:
        """Generate projector fan noise."""
        noise = np.random.normal(0, 0.05, (self.config.channels, self.config.frame_size))
        
        # Fan noise characteristics
        duration = self.config.frame_size / self.config.sample_rate
        t = np.linspace(0, duration, self.config.frame_size)
        fan_noise = 0.08 * np.sin(2 * np.pi * 120 * t)
        
        for channel in range(self.config.channels):
            noise[channel] += fan_noise
        
        return noise
    
    def _generate_construction_noise(self) -> np.ndarray:
        """Generate construction/drilling noise."""
        noise = np.random.normal(0, 0.2, (self.config.channels, self.config.frame_size))
        
        # Add impulsive components
        duration = self.config.frame_size / self.config.sample_rate
        t = np.linspace(0, duration, self.config.frame_size)
        
        # Drilling-like sound
        drill_sound = 0.15 * np.sin(2 * np.pi * 800 * t) * (1 + 0.5 * np.sin(2 * np.pi * 20 * t))
        
        for channel in range(self.config.channels):
            noise[channel] += drill_sound
        
        return noise
    
    def _generate_music_signal(self) -> np.ndarray:
        """Generate music-like signal."""
        duration = self.config.frame_size / self.config.sample_rate
        t = np.linspace(0, duration, self.config.frame_size)
        
        # Multiple harmonics for rich sound
        music = (
            0.4 * np.sin(2 * np.pi * 440 * t) +  # A4
            0.3 * np.sin(2 * np.pi * 554 * t) +  # C#5
            0.2 * np.sin(2 * np.pi * 659 * t) +  # E5
            0.1 * np.sin(2 * np.pi * 880 * t)    # A5
        )
        
        return np.array([music, music * 0.8]) if self.config.channels == 2 else music.reshape(1, -1)
    
    def _add_echo(self, signal: np.ndarray, delay_ms: float, decay: float) -> np.ndarray:
        """Add echo to signal."""
        delay_samples = int(delay_ms * self.config.sample_rate / 1000)
        
        if delay_samples >= signal.shape[-1]:
            return signal * 0  # No echo if delay too long
        
        echo = np.zeros_like(signal)
        echo[:, delay_samples:] = signal[:, :-delay_samples] * decay
        
        return echo
    
    def _add_compression_artifacts(self, signal: np.ndarray) -> np.ndarray:
        """Add audio compression artifacts."""
        # Simulate quantization noise
        quantized = np.round(signal * 32767) / 32767
        
        # Add slight harmonic distortion
        distorted = quantized + 0.01 * quantized ** 3
        
        return distorted
    
    def _add_network_jitter(self, signal: np.ndarray) -> np.ndarray:
        """Add network jitter effects."""
        # Simulate packet loss with brief dropouts
        dropout_mask = np.random.random(signal.shape[-1]) > 0.02  # 2% dropout
        
        jittered = signal.copy()
        for channel in range(signal.shape[0]):
            jittered[channel] *= dropout_mask
        
        return jittered
    
    def _apply_spatial_positioning(self, signal: np.ndarray, speaker_id: int) -> np.ndarray:
        """Apply spatial positioning for different speakers."""
        if self.config.channels == 1:
            return signal
        
        # Simple stereo positioning
        positions = [0.2, 0.8, 0.3, 0.7]  # Left-right balance for 4 speakers
        position = positions[speaker_id % len(positions)]
        
        left_gain = 1.0 - position
        right_gain = position
        
        positioned = signal.copy()
        positioned[0] *= left_gain
        positioned[1] *= right_gain
        
        return positioned
    
    def _simulate_microphone_array(self, signal: np.ndarray, direction: float) -> np.ndarray:
        """Simulate microphone array processing."""
        # Simple simulation of beamforming
        # In reality, this would involve complex spatial processing
        
        # Apply directional gain based on simulated direction
        directional_gain = np.cos(np.radians(direction - 0)) ** 2  # Peak at 0 degrees
        
        array_signal = signal * (0.5 + 0.5 * directional_gain)
        
        return array_signal
    
    def _assess_echo_cancellation(self, input_frame: AudioFrame, output_frame: AudioFrame) -> float:
        """Assess echo cancellation effectiveness."""
        # Simple echo assessment based on signal correlation
        input_data = input_frame.to_mono().data.flatten()
        output_data = output_frame.to_mono().data.flatten()
        
        # Calculate reduction in signal correlation (simplified)
        input_power = np.mean(input_data ** 2)
        output_power = np.mean(output_data ** 2)
        
        if input_power > 0 and output_power > 0:
            power_reduction = 10 * np.log10(input_power / output_power)
            return max(0, power_reduction)
        else:
            return 0.0


class TestClassroomValidation:
    """Test class for classroom scenario validation."""
    
    @pytest.fixture
    async def classroom_config(self):
        """Classroom-optimized audio configuration."""
        return AudioConfig(
            sample_rate=48000,
            frame_size=480,
            channels=2,
            bit_depth=16
        )
    
    @pytest.fixture
    async def classroom_service_manager(self, classroom_config):
        """Service manager configured for classroom use."""
        manager = ServiceManager(classroom_config)
        
        # Register services with classroom-optimized settings
        manager.register_service(CaptureService, name="CaptureService")
        manager.register_service(DenoiseService, name="DenoiseService")
        manager.register_service(AECService, name="AECService")
        manager.register_service(SSLService, name="SSLService")
        manager.register_service(RecorderService, name="RecorderService")
        
        await manager.start()
        yield manager
        await manager.stop()
    
    async def test_complete_classroom_validation(self, classroom_service_manager, classroom_config):
        """Run complete classroom scenario validation suite."""
        validator = ClassroomScenarioValidator(classroom_config)
        
        # Run all classroom scenarios
        results = await validator.validate_all_scenarios(classroom_service_manager)
        
        # Verify all scenarios passed
        failed_scenarios = [name for name, result in results.items() 
                          if result.get('status') != 'PASSED']
        
        assert not failed_scenarios, f"Failed scenarios: {failed_scenarios}"
        
        # Generate summary report
        total_scenarios = len(results)
        passed_scenarios = sum(1 for result in results.values() 
                             if result.get('status') == 'PASSED')
        
        print(f"\nClassroom Validation Summary:")
        print(f"  Total scenarios: {total_scenarios}")
        print(f"  Passed: {passed_scenarios}")
        print(f"  Success rate: {passed_scenarios/total_scenarios*100:.1f}%")
        
        # Save detailed results
        with open('classroom_validation_results.json', 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"  Detailed results saved to: classroom_validation_results.json")


# Standalone validation runner
async def run_classroom_validation():
    """Run classroom validation as standalone script."""
    config = AudioConfig(sample_rate=48000, frame_size=480, channels=2)
    
    # Setup service manager
    manager = ServiceManager(config)
    manager.register_service(DenoiseService, name="DenoiseService")
    manager.register_service(AECService, name="AECService")
    manager.register_service(SSLService, name="SSLService")
    manager.register_service(RecorderService, name="RecorderService")
    
    await manager.start()
    
    try:
        validator = ClassroomScenarioValidator(config)
        results = await validator.validate_all_scenarios(manager)
        
        print("\nClassroom Validation Complete!")
        print(f"Results: {json.dumps(results, indent=2, default=str)}")
        
    finally:
        await manager.stop()


if __name__ == "__main__":
    asyncio.run(run_classroom_validation())