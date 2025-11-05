"""
Unit tests for audio processing algorithms
Tests SSL, beamforming, and AEC algorithms with known signals
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch
import tempfile
import os

from src.processing.components import SoundSourceLocalizer
from src.processing.beamforming import BeamformingProcessor
from src.processing.webrtc_components import WebRTCAECProcessor, WebRTCAGCProcessor, WebRTCNSProcessor
from src.audio_core.data_models import AudioFrame, ProcessingConfig


class TestSoundSourceLocalizer:
    """Test sound source localization algorithms"""
    
    @pytest.fixture
    def ssl_processor(self):
        """Create SSL processor for testing"""
        config = ProcessingConfig(
            sample_rate=48000,
            channels=4,
            frame_size=1024,
            ssl_algorithm="gcc_phat"
        )
        return SoundSourceLocalizer(config)
    
    def test_ssl_initialization(self, ssl_processor):
        """Test SSL processor initialization"""
        assert ssl_processor.sample_rate == 48000
        assert ssl_processor.channels == 4
        assert ssl_processor.frame_size == 1024
        assert ssl_processor.algorithm == "gcc_phat"
    
    def test_ssl_single_source_detection(self, ssl_processor):
        """Test detection of single sound source with known signal"""
        # Create test signal with known source position
        num_samples = 1024
        frequency = 1000  # 1kHz test tone
        
        # Simulate 4-microphone array with 10cm spacing
        mic_positions = np.array([
            [0.0, 0.0, 0.0],    # Reference microphone
            [0.1, 0.0, 0.0],    # 10cm to the right
            [0.0, 0.1, 0.0],    # 10cm forward
            [0.1, 0.1, 0.0]     # 10cm diagonal
        ])
        
        # Source at 45 degrees, 1 meter distance
        source_position = np.array([0.707, 0.707, 0.0])
        
        # Generate test signals with appropriate delays
        t = np.linspace(0, num_samples / 48000, num_samples)
        base_signal = np.sin(2 * np.pi * frequency * t)
        
        # Calculate time delays based on geometry
        sound_speed = 343.0  # m/s
        delays = []
        for mic_pos in mic_positions:
            distance = np.linalg.norm(source_position - mic_pos)
            delay_samples = int((distance / sound_speed) * 48000)
            delays.append(delay_samples)
        
        # Create multi-channel signal with delays
        multichannel_signal = np.zeros((num_samples, 4))
        for ch, delay in enumerate(delays):
            if delay < num_samples:
                multichannel_signal[delay:, ch] = base_signal[:num_samples-delay]
        
        # Add small amount of noise
        noise_level = 0.01
        multichannel_signal += noise_level * np.random.randn(*multichannel_signal.shape)
        
        # Create audio frame
        audio_frame = AudioFrame(
            data=multichannel_signal.astype(np.float32),
            sample_rate=48000,
            channels=4,
            timestamp=0.0
        )
        
        # Process with SSL
        result = ssl_processor.process(audio_frame)
        
        # Verify results
        assert result is not None
        assert hasattr(result, 'source_angles')
        assert len(result.source_angles) > 0
        
        # Check if detected angle is close to expected (45 degrees)
        detected_angle = result.source_angles[0]
        expected_angle = 45.0
        assert abs(detected_angle - expected_angle) < 10.0  # Within 10 degrees
    
    def test_ssl_multiple_sources(self, ssl_processor):
        """Test detection of multiple sound sources"""
        num_samples = 1024
        
        # Create two sources at different angles
        angles = [30, 120]  # degrees
        frequencies = [800, 1200]  # Hz
        
        multichannel_signal = np.zeros((num_samples, 4))
        t = np.linspace(0, num_samples / 48000, num_samples)
        
        for angle, freq in zip(angles, frequencies):
            # Simple delay model for each source
            angle_rad = np.radians(angle)
            base_signal = 0.5 * np.sin(2 * np.pi * freq * t)
            
            # Simulate delays for 4-mic array
            for ch in range(4):
                delay_samples = int(ch * 0.1 * np.cos(angle_rad) * 48000 / 343.0)
                if delay_samples < num_samples:
                    multichannel_signal[delay_samples:, ch] += base_signal[:num_samples-delay_samples]
        
        audio_frame = AudioFrame(
            data=multichannel_signal.astype(np.float32),
            sample_rate=48000,
            channels=4,
            timestamp=0.0
        )
        
        result = ssl_processor.process(audio_frame)
        
        # Should detect multiple sources
        assert len(result.source_angles) >= 2
    
    def test_ssl_no_source(self, ssl_processor):
        """Test SSL with noise only (no clear source)"""
        num_samples = 1024
        
        # Pure noise signal
        multichannel_signal = 0.1 * np.random.randn(num_samples, 4)
        
        audio_frame = AudioFrame(
            data=multichannel_signal.astype(np.float32),
            sample_rate=48000,
            channels=4,
            timestamp=0.0
        )
        
        result = ssl_processor.process(audio_frame)
        
        # Should detect no clear sources or very low confidence
        assert len(result.source_angles) == 0 or all(conf < 0.5 for conf in result.confidence_scores)
    
    def test_ssl_algorithm_switching(self):
        """Test switching between different SSL algorithms"""
        algorithms = ["gcc_phat", "music", "esprit"]
        
        for algorithm in algorithms:
            config = ProcessingConfig(
                sample_rate=48000,
                channels=4,
                frame_size=1024,
                ssl_algorithm=algorithm
            )
            
            ssl_processor = SoundSourceLocalizer(config)
            assert ssl_processor.algorithm == algorithm


class TestBeamformingProcessor:
    """Test beamforming algorithms"""
    
    @pytest.fixture
    def beamforming_processor(self):
        """Create beamforming processor for testing"""
        config = ProcessingConfig(
            sample_rate=48000,
            channels=4,
            frame_size=1024,
            beamforming_algorithm="mvdr",
            num_beams=1
        )
        return BeamformingProcessor(config)
    
    def test_beamforming_initialization(self, beamforming_processor):
        """Test beamforming processor initialization"""
        assert beamforming_processor.sample_rate == 48000
        assert beamforming_processor.channels == 4
        assert beamforming_processor.algorithm == "mvdr"
        assert beamforming_processor.num_beams == 1
    
    def test_mvdr_beamforming(self, beamforming_processor):
        """Test MVDR beamforming with known signal"""
        num_samples = 1024
        
        # Create signal with interference
        t = np.linspace(0, num_samples / 48000, num_samples)
        
        # Target signal at 0 degrees (broadside)
        target_signal = np.sin(2 * np.pi * 1000 * t)
        
        # Interference at 90 degrees
        interference = 0.5 * np.sin(2 * np.pi * 1500 * t)
        
        # 4-microphone linear array
        multichannel_signal = np.zeros((num_samples, 4))
        
        # Target signal (no delay for broadside)
        for ch in range(4):
            multichannel_signal[:, ch] = target_signal
        
        # Add interference with delays (90 degrees)
        for ch in range(4):
            delay_samples = ch * 2  # Simple delay model
            if delay_samples < num_samples:
                multichannel_signal[delay_samples:, ch] += interference[:num_samples-delay_samples]
        
        # Add noise
        multichannel_signal += 0.05 * np.random.randn(*multichannel_signal.shape)
        
        audio_frame = AudioFrame(
            data=multichannel_signal.astype(np.float32),
            sample_rate=48000,
            channels=4,
            timestamp=0.0
        )
        
        # Set target direction (0 degrees)
        beamforming_processor.set_target_direction(0.0)
        
        result = beamforming_processor.process(audio_frame)
        
        # Verify output
        assert result is not None
        assert result.data.shape[1] == 1  # Single beam output
        
        # Check interference suppression
        # Output should have better SNR than input
        input_power = np.mean(multichannel_signal[:, 0] ** 2)
        output_power = np.mean(result.data[:, 0] ** 2)
        
        # Beamforming should maintain or improve signal quality
        assert output_power > 0.1 * input_power
    
    def test_adaptive_beamforming(self, beamforming_processor):
        """Test adaptive beamforming behavior"""
        num_frames = 10
        frame_size = 1024
        
        # Process multiple frames to test adaptation
        for frame_idx in range(num_frames):
            t = np.linspace(frame_idx * frame_size / 48000, 
                          (frame_idx + 1) * frame_size / 48000, 
                          frame_size)
            
            # Slowly moving source
            angle = 30 * np.sin(2 * np.pi * 0.1 * frame_idx)
            signal = np.sin(2 * np.pi * 1000 * t)
            
            multichannel_signal = np.zeros((frame_size, 4))
            for ch in range(4):
                delay = ch * 0.1 * np.sin(np.radians(angle)) * 48000 / 343.0
                delay_samples = int(delay)
                if delay_samples < frame_size:
                    multichannel_signal[delay_samples:, ch] = signal[:frame_size-delay_samples]
            
            audio_frame = AudioFrame(
                data=multichannel_signal.astype(np.float32),
                sample_rate=48000,
                channels=4,
                timestamp=frame_idx * frame_size / 48000
            )
            
            result = beamforming_processor.process(audio_frame)
            assert result is not None
    
    def test_beamforming_algorithms(self):
        """Test different beamforming algorithms"""
        algorithms = ["mvdr", "lcmv", "gsc"]
        
        for algorithm in algorithms:
            config = ProcessingConfig(
                sample_rate=48000,
                channels=4,
                frame_size=1024,
                beamforming_algorithm=algorithm,
                num_beams=1
            )
            
            processor = BeamformingProcessor(config)
            assert processor.algorithm == algorithm


class TestWebRTCComponents:
    """Test WebRTC audio processing components"""
    
    def test_aec_processor(self):
        """Test WebRTC AEC processor"""
        config = ProcessingConfig(
            sample_rate=48000,
            channels=1,
            frame_size=480,  # WebRTC prefers 10ms frames
            aec_enabled=True
        )
        
        aec_processor = WebRTCAECProcessor(config)
        
        # Test initialization
        assert aec_processor.sample_rate == 48000
        assert aec_processor.frame_size == 480
        
        # Create test signals
        num_samples = 480
        t = np.linspace(0, num_samples / 48000, num_samples)
        
        # Near-end signal (microphone input)
        near_end = 0.5 * np.sin(2 * np.pi * 1000 * t) + 0.1 * np.random.randn(num_samples)
        
        # Far-end signal (speaker output)
        far_end = 0.3 * np.sin(2 * np.pi * 800 * t)
        
        # Create echo (delayed and attenuated far-end)
        echo_delay = 100  # samples
        echo_signal = np.zeros(num_samples)
        if echo_delay < num_samples:
            echo_signal[echo_delay:] = 0.2 * far_end[:num_samples-echo_delay]
        
        # Mix near-end with echo
        microphone_signal = near_end + echo_signal
        
        # Create audio frames
        near_frame = AudioFrame(
            data=microphone_signal.reshape(-1, 1).astype(np.float32),
            sample_rate=48000,
            channels=1,
            timestamp=0.0
        )
        
        far_frame = AudioFrame(
            data=far_end.reshape(-1, 1).astype(np.float32),
            sample_rate=48000,
            channels=1,
            timestamp=0.0
        )
        
        # Process with AEC
        result = aec_processor.process(near_frame, far_frame)
        
        # Verify echo reduction
        assert result is not None
        assert result.data.shape == near_frame.data.shape
        
        # Echo should be reduced (output power should be less than input)
        input_power = np.mean(microphone_signal ** 2)
        output_power = np.mean(result.data.flatten() ** 2)
        
        # AEC should reduce echo while preserving near-end signal
        assert output_power < input_power
        assert output_power > 0.1 * input_power  # Don't over-suppress
    
    def test_agc_processor(self):
        """Test WebRTC AGC processor"""
        config = ProcessingConfig(
            sample_rate=48000,
            channels=1,
            frame_size=480,
            agc_enabled=True,
            agc_target_level=3,
            agc_compression_gain=9
        )
        
        agc_processor = WebRTCAGCProcessor(config)
        
        # Test with varying input levels
        test_levels = [0.1, 0.5, 0.9]  # Low, medium, high
        
        for level in test_levels:
            num_samples = 480
            t = np.linspace(0, num_samples / 48000, num_samples)
            
            # Create signal with specific level
            signal = level * np.sin(2 * np.pi * 1000 * t)
            
            audio_frame = AudioFrame(
                data=signal.reshape(-1, 1).astype(np.float32),
                sample_rate=48000,
                channels=1,
                timestamp=0.0
            )
            
            result = agc_processor.process(audio_frame)
            
            assert result is not None
            assert result.data.shape == audio_frame.data.shape
            
            # AGC should normalize levels
            output_level = np.sqrt(np.mean(result.data.flatten() ** 2))
            
            # Output level should be more consistent across inputs
            assert 0.1 < output_level < 1.0
    
    def test_ns_processor(self):
        """Test WebRTC noise suppression processor"""
        config = ProcessingConfig(
            sample_rate=48000,
            channels=1,
            frame_size=480,
            ns_enabled=True,
            ns_suppression_level=2
        )
        
        ns_processor = WebRTCNSProcessor(config)
        
        # Create signal with noise
        num_samples = 480
        t = np.linspace(0, num_samples / 48000, num_samples)
        
        # Clean speech signal
        speech = 0.5 * np.sin(2 * np.pi * 1000 * t)
        
        # Add noise
        noise = 0.3 * np.random.randn(num_samples)
        noisy_signal = speech + noise
        
        audio_frame = AudioFrame(
            data=noisy_signal.reshape(-1, 1).astype(np.float32),
            sample_rate=48000,
            channels=1,
            timestamp=0.0
        )
        
        result = ns_processor.process(audio_frame)
        
        assert result is not None
        assert result.data.shape == audio_frame.data.shape
        
        # Noise should be reduced
        input_noise_power = np.var(noisy_signal)
        output_noise_power = np.var(result.data.flatten())
        
        # NS should reduce noise
        assert output_noise_power < input_noise_power
    
    def test_webrtc_component_integration(self):
        """Test integration of multiple WebRTC components"""
        config = ProcessingConfig(
            sample_rate=48000,
            channels=1,
            frame_size=480,
            aec_enabled=True,
            agc_enabled=True,
            ns_enabled=True
        )
        
        # Create processing chain
        aec = WebRTCAECProcessor(config)
        agc = WebRTCAGCProcessor(config)
        ns = WebRTCNSProcessor(config)
        
        # Create test signal
        num_samples = 480
        t = np.linspace(0, num_samples / 48000, num_samples)
        
        # Complex signal with echo, noise, and level variations
        clean_signal = 0.3 * np.sin(2 * np.pi * 1000 * t)
        echo = 0.1 * np.sin(2 * np.pi * 800 * t)
        noise = 0.2 * np.random.randn(num_samples)
        
        input_signal = clean_signal + echo + noise
        
        near_frame = AudioFrame(
            data=input_signal.reshape(-1, 1).astype(np.float32),
            sample_rate=48000,
            channels=1,
            timestamp=0.0
        )
        
        far_frame = AudioFrame(
            data=(0.5 * np.sin(2 * np.pi * 800 * t)).reshape(-1, 1).astype(np.float32),
            sample_rate=48000,
            channels=1,
            timestamp=0.0
        )
        
        # Process through chain
        aec_output = aec.process(near_frame, far_frame)
        agc_output = agc.process(aec_output)
        final_output = ns.process(agc_output)
        
        assert final_output is not None
        assert final_output.data.shape == near_frame.data.shape
        
        # Final output should be cleaner than input
        input_power = np.mean(input_signal ** 2)
        output_power = np.mean(final_output.data.flatten() ** 2)
        
        # Should maintain reasonable signal level
        assert 0.01 < output_power < 1.0


@pytest.fixture
def temp_audio_file():
    """Create temporary audio file for testing"""
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        # Create simple test audio
        sample_rate = 48000
        duration = 1.0  # 1 second
        t = np.linspace(0, duration, int(sample_rate * duration))
        audio_data = 0.5 * np.sin(2 * np.pi * 440 * t)  # 440 Hz tone
        
        # Write as 16-bit WAV (simplified)
        audio_16bit = (audio_data * 32767).astype(np.int16)
        f.write(audio_16bit.tobytes())
        
        yield f.name
    
    # Cleanup
    os.unlink(f.name)


class TestAlgorithmAccuracy:
    """Test algorithm accuracy with known test signals"""
    
    def test_frequency_detection_accuracy(self):
        """Test frequency detection accuracy"""
        sample_rate = 48000
        duration = 1.0
        test_frequencies = [440, 880, 1760]  # A4, A5, A6
        
        for freq in test_frequencies:
            t = np.linspace(0, duration, int(sample_rate * duration))
            signal = np.sin(2 * np.pi * freq * t)
            
            # Simple FFT-based frequency detection
            fft = np.fft.fft(signal)
            freqs = np.fft.fftfreq(len(signal), 1/sample_rate)
            
            # Find peak frequency
            peak_idx = np.argmax(np.abs(fft[:len(fft)//2]))
            detected_freq = abs(freqs[peak_idx])
            
            # Should be within 1 Hz
            assert abs(detected_freq - freq) < 1.0
    
    def test_snr_calculation_accuracy(self):
        """Test SNR calculation accuracy"""
        # Create signal with known SNR
        signal_power = 1.0
        noise_power = 0.1
        expected_snr_db = 10 * np.log10(signal_power / noise_power)  # 10 dB
        
        num_samples = 48000
        signal = np.sqrt(signal_power) * np.sin(2 * np.pi * 1000 * np.linspace(0, 1, num_samples))
        noise = np.sqrt(noise_power) * np.random.randn(num_samples)
        
        noisy_signal = signal + noise
        
        # Calculate SNR
        signal_est_power = np.mean(signal ** 2)
        noise_est_power = np.mean(noise ** 2)
        calculated_snr_db = 10 * np.log10(signal_est_power / noise_est_power)
        
        # Should be within 1 dB
        assert abs(calculated_snr_db - expected_snr_db) < 1.0