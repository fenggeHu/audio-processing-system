"""
Mock Audio Data Generator for Testing.

This module provides utilities for generating realistic test audio data
for unit tests, including speech-like signals, noise, and classroom scenarios.
"""

import numpy as np
import math
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict, Any
from enum import Enum

from src.audio_processing.models import AudioFrame, AudioConfig


class SignalType(Enum):
    """Types of test signals."""
    SILENCE = "silence"
    WHITE_NOISE = "white_noise"
    PINK_NOISE = "pink_noise"
    SINE_WAVE = "sine_wave"
    SPEECH_LIKE = "speech_like"
    CLASSROOM_AMBIENT = "classroom_ambient"
    TEACHER_VOICE = "teacher_voice"
    STUDENT_VOICE = "student_voice"
    HOWLING = "howling"


class MockAudioGenerator:
    """
    Mock audio data generator for testing audio processing systems.
    
    Generates realistic test signals including speech-like audio,
    classroom scenarios, and various noise types.
    """
    
    def __init__(self, sample_rate: int = 48000, seed: Optional[int] = None):
        self.sample_rate = sample_rate
        self.rng = np.random.default_rng(seed)
        
        # Speech synthesis parameters
        self.formant_frequencies = [800, 1200, 2400]  # Typical formants
        self.fundamental_freq_range = (80, 300)  # F0 range for speech
        
        # Classroom acoustic parameters
        self.room_rt60 = 0.8  # Reverberation time in seconds
        self.ambient_noise_level = -50.0  # dBFS
        
        # Signal generation state
        self.phase_accumulators = {}
        self.noise_filters = {}
        
    def generate_frame(self, signal_type: SignalType, 
                      frame_size: int = 480,
                      channels: int = 1,
                      level_dbfs: float = -20.0,
                      **kwargs) -> AudioFrame:
        """
        Generate a single audio frame of specified type.
        
        Args:
            signal_type: Type of signal to generate
            frame_size: Number of samples per frame
            channels: Number of audio channels
            level_dbfs: Target signal level in dBFS
            **kwargs: Additional parameters for specific signal types
            
        Returns:
            AudioFrame with generated audio data
        """
        # Generate base signal
        if signal_type == SignalType.SILENCE:
            data = self._generate_silence(frame_size, channels)
            
        elif signal_type == SignalType.WHITE_NOISE:
            data = self._generate_white_noise(frame_size, channels)
            
        elif signal_type == SignalType.PINK_NOISE:
            data = self._generate_pink_noise(frame_size, channels)
            
        elif signal_type == SignalType.SINE_WAVE:
            frequency = kwargs.get('frequency', 1000.0)
            data = self._generate_sine_wave(frame_size, channels, frequency)
            
        elif signal_type == SignalType.SPEECH_LIKE:
            data = self._generate_speech_like(frame_size, channels, **kwargs)
            
        elif signal_type == SignalType.CLASSROOM_AMBIENT:
            data = self._generate_classroom_ambient(frame_size, channels)
            
        elif signal_type == SignalType.TEACHER_VOICE:
            data = self._generate_teacher_voice(frame_size, channels, **kwargs)
            
        elif signal_type == SignalType.STUDENT_VOICE:
            data = self._generate_student_voice(frame_size, channels, **kwargs)
            
        elif signal_type == SignalType.HOWLING:
            frequency = kwargs.get('frequency', 2000.0)
            data = self._generate_howling(frame_size, channels, frequency)
            
        else:
            raise ValueError(f"Unknown signal type: {signal_type}")
        
        # Apply level scaling
        data = self._scale_to_level(data, level_dbfs)
        
        # Create AudioFrame
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=self.sample_rate,
            channels=channels,
            frame_size=frame_size,
            data=data.astype(np.float32),
            metadata=self._generate_metadata(signal_type, **kwargs)
        )
        
        return frame
    
    def generate_sequence(self, signal_types: List[SignalType],
                         durations_ms: List[float],
                         frame_size: int = 480,
                         channels: int = 1,
                         **kwargs) -> List[AudioFrame]:
        """
        Generate a sequence of audio frames with different signal types.
        
        Args:
            signal_types: List of signal types for each segment
            durations_ms: Duration of each segment in milliseconds
            frame_size: Number of samples per frame
            channels: Number of audio channels
            **kwargs: Additional parameters
            
        Returns:
            List of AudioFrame objects
        """
        frames = []
        current_time = datetime.now()
        
        for signal_type, duration_ms in zip(signal_types, durations_ms):
            # Calculate number of frames for this duration
            frames_per_second = self.sample_rate / frame_size
            num_frames = int((duration_ms / 1000.0) * frames_per_second)
            
            # Generate frames for this segment
            for i in range(num_frames):
                frame = self.generate_frame(
                    signal_type, frame_size, channels, **kwargs
                )
                frame.timestamp = current_time
                frames.append(frame)
                
                # Advance time
                frame_duration = timedelta(milliseconds=duration_ms / num_frames)
                current_time += frame_duration
        
        return frames
    
    def generate_classroom_scenario(self, duration_seconds: float = 10.0,
                                  frame_size: int = 480,
                                  channels: int = 8) -> List[AudioFrame]:
        """
        Generate a realistic classroom audio scenario.
        
        Args:
            duration_seconds: Total duration of scenario
            frame_size: Samples per frame
            channels: Number of microphone channels
            
        Returns:
            List of AudioFrame objects simulating classroom audio
        """
        frames = []
        frames_per_second = self.sample_rate / frame_size
        total_frames = int(duration_seconds * frames_per_second)
        
        current_time = datetime.now()
        frame_duration = timedelta(seconds=1.0 / frames_per_second)
        
        for i in range(total_frames):
            # Determine scenario phase
            phase_progress = i / total_frames
            
            if phase_progress < 0.3:
                # Teacher introduction
                signal_type = SignalType.TEACHER_VOICE
                ssl_direction = 0.0  # Front center
                ssl_confidence = 0.9
                
            elif phase_progress < 0.6:
                # Student question
                signal_type = SignalType.STUDENT_VOICE
                ssl_direction = 90.0 + self.rng.normal(0, 10)  # Side with variation
                ssl_confidence = 0.7
                
            elif phase_progress < 0.8:
                # Teacher response
                signal_type = SignalType.TEACHER_VOICE
                ssl_direction = 0.0 + self.rng.normal(0, 5)  # Front with small variation
                ssl_confidence = 0.85
                
            else:
                # Ambient classroom noise
                signal_type = SignalType.CLASSROOM_AMBIENT
                ssl_direction = self.rng.uniform(-180, 180)
                ssl_confidence = 0.3
            
            # Generate multi-channel frame
            frame = self._generate_multichannel_frame(
                signal_type, frame_size, channels,
                ssl_direction, ssl_confidence
            )
            
            frame.timestamp = current_time
            frames.append(frame)
            current_time += frame_duration
        
        return frames
    
    def _generate_silence(self, frame_size: int, channels: int) -> np.ndarray:
        """Generate silence."""
        return np.zeros((channels, frame_size))
    
    def _generate_white_noise(self, frame_size: int, channels: int) -> np.ndarray:
        """Generate white noise."""
        return self.rng.normal(0, 1, (channels, frame_size))
    
    def _generate_pink_noise(self, frame_size: int, channels: int) -> np.ndarray:
        """Generate pink noise (1/f spectrum)."""
        # Simple pink noise approximation using filtered white noise
        white_noise = self.rng.normal(0, 1, (channels, frame_size))
        
        # Apply simple 1/f filtering (approximation)
        pink_noise = np.zeros_like(white_noise)
        for ch in range(channels):
            # Simple first-order filter approximation
            filtered = np.zeros(frame_size)
            state = 0.0
            for i in range(frame_size):
                state = 0.99 * state + 0.01 * white_noise[ch, i]
                filtered[i] = state + 0.1 * white_noise[ch, i]
            pink_noise[ch] = filtered
        
        return pink_noise
    
    def _generate_sine_wave(self, frame_size: int, channels: int, 
                           frequency: float) -> np.ndarray:
        """Generate sine wave."""
        t = np.arange(frame_size) / self.sample_rate
        
        # Get or initialize phase accumulator
        if frequency not in self.phase_accumulators:
            self.phase_accumulators[frequency] = 0.0
        
        # Generate sine wave with continuous phase
        phase_start = self.phase_accumulators[frequency]
        phases = phase_start + 2 * np.pi * frequency * t
        sine_wave = np.sin(phases)
        
        # Update phase accumulator
        self.phase_accumulators[frequency] = phases[-1] % (2 * np.pi)
        
        # Replicate to all channels
        return np.tile(sine_wave, (channels, 1))
    
    def _generate_speech_like(self, frame_size: int, channels: int,
                            **kwargs) -> np.ndarray:
        """Generate speech-like signal with formants."""
        # Parameters
        f0 = kwargs.get('f0', self.rng.uniform(*self.fundamental_freq_range))
        voiced_prob = kwargs.get('voiced_prob', 0.7)
        
        # Generate excitation
        t = np.arange(frame_size) / self.sample_rate
        
        if self.rng.random() < voiced_prob:
            # Voiced speech - use periodic excitation
            excitation = np.sin(2 * np.pi * f0 * t)
            # Add some harmonics
            excitation += 0.5 * np.sin(2 * np.pi * 2 * f0 * t)
            excitation += 0.25 * np.sin(2 * np.pi * 3 * f0 * t)
        else:
            # Unvoiced speech - use noise excitation
            excitation = self.rng.normal(0, 1, frame_size)
        
        # Apply formant filtering (simplified)
        speech_signal = excitation
        for formant_freq in self.formant_frequencies:
            # Simple resonant filter approximation
            q_factor = 10.0
            omega = 2 * np.pi * formant_freq / self.sample_rate
            
            # Apply simple bandpass filter effect
            filtered = np.zeros_like(speech_signal)
            for i in range(1, len(speech_signal)):
                filtered[i] = (speech_signal[i] + 
                             0.8 * np.cos(omega) * filtered[i-1])
            
            speech_signal += 0.3 * filtered
        
        # Apply speech envelope
        envelope = self._generate_speech_envelope(frame_size)
        speech_signal *= envelope
        
        return np.tile(speech_signal, (channels, 1))
    
    def _generate_speech_envelope(self, frame_size: int) -> np.ndarray:
        """Generate realistic speech amplitude envelope."""
        # Simple envelope with attack and decay
        envelope = np.ones(frame_size)
        
        # Random amplitude modulation
        modulation_freq = self.rng.uniform(5, 15)  # Hz
        t = np.arange(frame_size) / self.sample_rate
        modulation = 0.5 + 0.5 * np.sin(2 * np.pi * modulation_freq * t)
        
        envelope *= modulation
        
        # Add some random variations
        envelope *= (0.8 + 0.4 * self.rng.random(frame_size))
        
        return envelope
    
    def _generate_classroom_ambient(self, frame_size: int, 
                                  channels: int) -> np.ndarray:
        """Generate classroom ambient noise."""
        # Base noise
        ambient = self._generate_pink_noise(frame_size, channels) * 0.1
        
        # Add HVAC noise (low frequency)
        hvac_freq = 60.0  # Hz
        hvac_noise = self._generate_sine_wave(frame_size, channels, hvac_freq) * 0.05
        
        # Add occasional paper rustling (high frequency bursts)
        if self.rng.random() < 0.1:  # 10% chance
            rustle = self.rng.normal(0, 1, (channels, frame_size)) * 0.02
            # High-pass filter effect
            rustle[:, 1:] -= 0.9 * rustle[:, :-1]
            ambient += rustle
        
        return ambient + hvac_noise
    
    def _generate_teacher_voice(self, frame_size: int, channels: int,
                              **kwargs) -> np.ndarray:
        """Generate teacher voice characteristics."""
        # Teachers typically have more consistent, projected voice
        f0 = kwargs.get('f0', self.rng.uniform(120, 200))  # Slightly lower F0
        voiced_prob = 0.8  # More voiced segments
        
        speech = self._generate_speech_like(
            frame_size, channels, f0=f0, voiced_prob=voiced_prob
        )
        
        # Teachers speak louder and clearer
        speech *= 1.5
        
        return speech
    
    def _generate_student_voice(self, frame_size: int, channels: int,
                              **kwargs) -> np.ndarray:
        """Generate student voice characteristics."""
        # Students may be more hesitant, quieter
        f0 = kwargs.get('f0', self.rng.uniform(150, 250))  # Higher F0
        voiced_prob = 0.6  # More unvoiced segments (hesitation)
        
        speech = self._generate_speech_like(
            frame_size, channels, f0=f0, voiced_prob=voiced_prob
        )
        
        # Students typically speak quieter
        speech *= 0.7
        
        return speech
    
    def _generate_howling(self, frame_size: int, channels: int,
                         frequency: float) -> np.ndarray:
        """Generate howling/feedback signal."""
        # Pure tone that builds up over time
        sine_wave = self._generate_sine_wave(frame_size, channels, frequency)
        
        # Add slight frequency modulation
        mod_freq = 5.0  # Hz
        t = np.arange(frame_size) / self.sample_rate
        freq_mod = 1.0 + 0.02 * np.sin(2 * np.pi * mod_freq * t)
        
        # Apply modulation
        for ch in range(channels):
            sine_wave[ch] *= freq_mod
        
        return sine_wave
    
    def _generate_multichannel_frame(self, signal_type: SignalType,
                                   frame_size: int, channels: int,
                                   ssl_direction: float,
                                   ssl_confidence: float) -> AudioFrame:
        """Generate multichannel frame with spatial characteristics."""
        # Generate base signal
        base_frame = self.generate_frame(signal_type, frame_size, 1)
        base_signal = base_frame.data[0]
        
        # Create multichannel data with spatial simulation
        multichannel_data = np.zeros((channels, frame_size))
        
        # Simple spatial simulation - vary amplitude and delay based on direction
        for ch in range(channels):
            # Simulate microphone positions in linear array
            mic_angle = (ch - channels/2) * 30.0  # degrees
            
            # Calculate relative amplitude based on direction
            angle_diff = abs(ssl_direction - mic_angle)
            if angle_diff > 180:
                angle_diff = 360 - angle_diff
            
            # Amplitude falls off with angle
            amplitude = np.cos(np.radians(angle_diff / 2))
            amplitude = max(0.1, amplitude)  # Minimum amplitude
            
            # Add small random delay (simulate slight position errors)
            delay_samples = int(self.rng.uniform(-2, 2))
            
            # Apply amplitude and delay
            if delay_samples >= 0 and delay_samples < frame_size:
                if delay_samples == 0:
                    multichannel_data[ch, :] = base_signal * amplitude
                else:
                    multichannel_data[ch, delay_samples:] = (
                        base_signal[:-delay_samples] * amplitude
                    )
            elif delay_samples < 0 and abs(delay_samples) < frame_size:
                multichannel_data[ch, :delay_samples] = (
                    base_signal[-delay_samples:] * amplitude
                )
            else:
                # No delay or delay too large, just apply amplitude
                multichannel_data[ch, :] = base_signal * amplitude
        
        # Add uncorrelated noise to each channel
        noise_level = 0.01
        for ch in range(channels):
            multichannel_data[ch] += self.rng.normal(0, noise_level, frame_size)
        
        # Create frame with SSL metadata
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=self.sample_rate,
            channels=channels,
            frame_size=frame_size,
            data=multichannel_data.astype(np.float32),
            metadata={
                'ssl_direction': ssl_direction,
                'ssl_azimuth': ssl_direction,
                'ssl_elevation': 0.0,
                'ssl_confidence': ssl_confidence,
                'signal_type': signal_type.value
            }
        )
        
        return frame
    
    def _scale_to_level(self, data: np.ndarray, target_dbfs: float) -> np.ndarray:
        """Scale audio data to target level in dBFS."""
        if target_dbfs == -np.inf:
            return np.zeros_like(data)
        
        # Calculate current RMS level
        rms = np.sqrt(np.mean(data ** 2))
        if rms == 0:
            return data
        
        # Calculate target RMS
        target_rms = 10 ** (target_dbfs / 20.0)
        
        # Scale data
        scale_factor = target_rms / rms
        return data * scale_factor
    
    def _generate_metadata(self, signal_type: SignalType, **kwargs) -> Dict[str, Any]:
        """Generate metadata for the audio frame."""
        metadata = {
            'signal_type': signal_type.value,
            'generator': 'MockAudioGenerator'
        }
        
        # Add signal-specific metadata
        if signal_type == SignalType.SINE_WAVE:
            metadata['frequency'] = kwargs.get('frequency', 1000.0)
        elif signal_type in [SignalType.SPEECH_LIKE, SignalType.TEACHER_VOICE, SignalType.STUDENT_VOICE]:
            metadata['f0'] = kwargs.get('f0', 150.0)
            metadata['voiced_prob'] = kwargs.get('voiced_prob', 0.7)
        
        return metadata


# Convenience functions for common test scenarios
def create_test_frame(signal_type: SignalType = SignalType.WHITE_NOISE,
                     sample_rate: int = 48000,
                     frame_size: int = 480,
                     channels: int = 1,
                     level_dbfs: float = -20.0,
                     **kwargs) -> AudioFrame:
    """Create a single test audio frame."""
    generator = MockAudioGenerator(sample_rate)
    return generator.generate_frame(
        signal_type, frame_size, channels, level_dbfs, **kwargs
    )


def create_classroom_sequence(duration_seconds: float = 5.0,
                            sample_rate: int = 48000,
                            frame_size: int = 480,
                            channels: int = 8) -> List[AudioFrame]:
    """Create a classroom audio sequence for testing."""
    generator = MockAudioGenerator(sample_rate)
    return generator.generate_classroom_scenario(
        duration_seconds, frame_size, channels
    )


def create_speech_sequence(duration_seconds: float = 2.0,
                          sample_rate: int = 48000,
                          frame_size: int = 480,
                          channels: int = 1) -> List[AudioFrame]:
    """Create a speech-like audio sequence."""
    generator = MockAudioGenerator(sample_rate)
    
    # Create alternating voiced and unvoiced segments
    segment_duration = 200  # ms
    num_segments = int((duration_seconds * 1000) / segment_duration)
    
    signal_types = []
    durations = []
    
    for i in range(num_segments):
        if i % 2 == 0:
            signal_types.append(SignalType.SPEECH_LIKE)
        else:
            signal_types.append(SignalType.SILENCE)
        durations.append(segment_duration)
    
    return generator.generate_sequence(
        signal_types, durations, frame_size, channels
    )

class TestMockAudioGenerator:
    """Test mock audio generator functionality."""
    
    def test_generator_initialization(self):
        """Test generator initialization."""
        generator = MockAudioGenerator(sample_rate=48000, seed=42)
        
        assert generator.sample_rate == 48000
        assert generator.rng is not None
        assert len(generator.formant_frequencies) == 3
        assert generator.fundamental_freq_range == (80, 300)
    
    def test_silence_generation(self):
        """Test silence generation."""
        generator = MockAudioGenerator(seed=42)
        
        frame = generator.generate_frame(
            SignalType.SILENCE,
            frame_size=480,
            channels=2,
            level_dbfs=-60.0
        )
        
        assert frame.channels == 2
        assert frame.frame_size == 480
        assert frame.sample_rate == 48000
        
        # Should be very quiet
        rms_level = frame.get_rms_level()
        assert rms_level < -50.0
    
    def test_white_noise_generation(self):
        """Test white noise generation."""
        generator = MockAudioGenerator(seed=42)
        
        frame = generator.generate_frame(
            SignalType.WHITE_NOISE,
            frame_size=480,
            channels=1,
            level_dbfs=-20.0
        )
        
        assert frame.channels == 1
        assert frame.frame_size == 480
        
        # Should have reasonable level
        rms_level = frame.get_rms_level()
        assert -25.0 < rms_level < -15.0
    
    def test_sine_wave_generation(self):
        """Test sine wave generation."""
        generator = MockAudioGenerator(seed=42)
        
        frame = generator.generate_frame(
            SignalType.SINE_WAVE,
            frame_size=480,
            channels=1,
            level_dbfs=-20.0,
            frequency=1000.0
        )
        
        assert frame.channels == 1
        assert frame.frame_size == 480
        assert 'frequency' in frame.metadata
        assert frame.metadata['frequency'] == 1000.0
    
    def test_speech_like_generation(self):
        """Test speech-like signal generation."""
        generator = MockAudioGenerator(seed=42)
        
        frame = generator.generate_frame(
            SignalType.SPEECH_LIKE,
            frame_size=480,
            channels=1,
            level_dbfs=-20.0
        )
        
        assert frame.channels == 1
        assert frame.frame_size == 480
        assert frame.metadata['signal_type'] == SignalType.SPEECH_LIKE.value
    
    def test_teacher_voice_generation(self):
        """Test teacher voice generation."""
        generator = MockAudioGenerator(seed=42)
        
        frame = generator.generate_frame(
            SignalType.TEACHER_VOICE,
            frame_size=480,
            channels=1,
            level_dbfs=-15.0
        )
        
        assert frame.channels == 1
        assert frame.frame_size == 480
        assert frame.metadata['signal_type'] == SignalType.TEACHER_VOICE.value
    
    def test_sequence_generation(self):
        """Test sequence generation."""
        generator = MockAudioGenerator(seed=42)
        
        signal_types = [SignalType.SILENCE, SignalType.SPEECH_LIKE, SignalType.SILENCE]
        durations_ms = [100.0, 200.0, 100.0]  # Total 400ms
        
        frames = generator.generate_sequence(
            signal_types, durations_ms,
            frame_size=480, channels=1
        )
        
        # Should have approximately 40 frames (400ms at 10ms per frame)
        assert 35 <= len(frames) <= 45
        
        # All frames should be valid
        for frame in frames:
            assert frame.channels == 1
            assert frame.frame_size == 480
            assert frame.sample_rate == 48000
    
    def test_classroom_scenario_generation(self):
        """Test classroom scenario generation."""
        generator = MockAudioGenerator(seed=42)
        
        frames = generator.generate_classroom_scenario(
            duration_seconds=2.0,
            frame_size=480,
            channels=4
        )
        
        # Should have approximately 200 frames (2 seconds at 10ms per frame)
        assert 180 <= len(frames) <= 220
        
        # All frames should be multichannel with SSL metadata
        for frame in frames:
            assert frame.channels == 4
            assert frame.frame_size == 480
            assert 'ssl_direction' in frame.metadata
            assert 'ssl_confidence' in frame.metadata
    
    def test_multichannel_frame_generation(self):
        """Test multichannel frame generation with spatial characteristics."""
        generator = MockAudioGenerator(seed=42)
        
        frame = generator._generate_multichannel_frame(
            SignalType.TEACHER_VOICE,
            frame_size=480,
            channels=8,
            ssl_direction=0.0,  # Front center
            ssl_confidence=0.9
        )
        
        assert frame.channels == 8
        assert frame.frame_size == 480
        assert frame.metadata['ssl_direction'] == 0.0
        assert frame.metadata['ssl_confidence'] == 0.9
        
        # Different channels should have different amplitudes based on direction
        channel_levels = []
        for ch in range(8):
            ch_rms = np.sqrt(np.mean(frame.data[ch] ** 2))
            channel_levels.append(ch_rms)
        
        # Should have variation between channels
        assert max(channel_levels) > min(channel_levels)


class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_create_test_frame(self):
        """Test create_test_frame function."""
        frame = create_test_frame(
            signal_type=SignalType.WHITE_NOISE,
            sample_rate=44100,
            frame_size=441,
            channels=2,
            level_dbfs=-30.0
        )
        
        assert frame.sample_rate == 44100
        assert frame.frame_size == 441
        assert frame.channels == 2
        
        # Should be at approximately the right level
        rms_level = frame.get_rms_level()
        assert -35.0 < rms_level < -25.0
    
    def test_create_classroom_sequence(self):
        """Test create_classroom_sequence function."""
        frames = create_classroom_sequence(
            duration_seconds=1.0,
            sample_rate=48000,
            frame_size=480,
            channels=6
        )
        
        # Should have approximately 100 frames
        assert 90 <= len(frames) <= 110
        
        # All frames should be 6-channel
        for frame in frames:
            assert frame.channels == 6
            assert frame.sample_rate == 48000
    
    def test_create_speech_sequence(self):
        """Test create_speech_sequence function."""
        frames = create_speech_sequence(
            duration_seconds=1.0,
            sample_rate=48000,
            frame_size=480,
            channels=1
        )
        
        # Should have approximately 100 frames
        assert 90 <= len(frames) <= 110
        
        # Should alternate between speech and silence
        signal_types = [frame.metadata.get('signal_type') for frame in frames]
        
        # Should have both speech and silence
        assert SignalType.SPEECH_LIKE.value in signal_types
        assert SignalType.SILENCE.value in signal_types