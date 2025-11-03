"""
Noise Reduction and Speech Enhancement Service for classroom audio processing.

This module implements the DenoiseService with RNNoise integration,
adjustable noise reduction strength, and speech quality protection mechanisms.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple
from enum import Enum
import numpy as np
import structlog
from collections import deque

from ..interfaces import IMetricsCollector
from ..base import BaseAudioProcessor
from ..models import AudioFrame, AudioConfig
from ..exceptions import ProcessingError

logger = structlog.get_logger(__name__)


class DenoiseMode(Enum):
    """Denoise operation modes."""
    FIDELITY = "fidelity"        # High fidelity mode with minimal processing
    BALANCED = "balanced"        # Balanced noise reduction and speech quality
    AGGRESSIVE = "aggressive"    # Maximum noise reduction
    BYPASS = "bypass"           # Pass-through mode (no denoising)


class NoiseType(Enum):
    """Types of noise that can be detected and processed."""
    STATIONARY = "stationary"      # Constant background noise (HVAC, fan)
    NON_STATIONARY = "non_stationary"  # Variable noise (keyboard, footsteps)
    SPEECH_LIKE = "speech_like"    # Speech-like interference
    MUSIC = "music"               # Musical interference
    UNKNOWN = "unknown"           # Unclassified noise


@dataclass
class DenoiseMetrics:
    """Denoise performance metrics."""
    noise_reduction_db: float = 0.0        # Achieved noise reduction in dB
    speech_quality_score: float = 0.0      # PESQ-like speech quality score
    processing_latency_ms: float = 0.0     # Processing latency
    noise_floor_estimate: float = -60.0    # Estimated noise floor in dBFS
    speech_presence_prob: float = 0.0      # Probability of speech presence
    noise_type: NoiseType = NoiseType.UNKNOWN  # Detected noise type
    adaptation_rate: float = 0.0           # Current adaptation rate
    
    def to_dict(self) -> Dict[str, float]:
        """Convert metrics to dictionary."""
        return {
            'noise_reduction_db': self.noise_reduction_db,
            'speech_quality_score': self.speech_quality_score,
            'processing_latency_ms': self.processing_latency_ms,
            'noise_floor_estimate': self.noise_floor_estimate,
            'speech_presence_prob': self.speech_presence_prob,
            'noise_type': self.noise_type.value,
            'adaptation_rate': self.adaptation_rate
        }


class SpeechActivityDetector:
    """
    Voice Activity Detection (VAD) for speech/noise classification.
    
    Detects speech presence to protect speech quality during denoising.
    """
    
    def __init__(self, frame_size: int = 480, 
                 sensitivity: float = 0.5,
                 hangover_frames: int = 5):
        self.frame_size = frame_size
        self.sensitivity = sensitivity
        self.hangover_frames = hangover_frames
        
        # Energy-based features
        self.energy_history = deque(maxlen=20)
        self.spectral_centroid_history = deque(maxlen=10)
        self.zero_crossing_history = deque(maxlen=10)
        
        # State tracking
        self.speech_active = False
        self.hangover_counter = 0
        
        # Thresholds
        self.energy_threshold = -40.0  # dBFS
        self.spectral_threshold = 2000.0  # Hz
        self.zcr_threshold = 0.1
        
        logger.info(
            "Speech activity detector initialized",
            sensitivity=sensitivity,
            hangover_frames=hangover_frames
        )
    
    def detect(self, signal: np.ndarray) -> Tuple[bool, float]:
        """
        Detect speech activity in audio signal.
        
        Args:
            signal: Input audio signal
            
        Returns:
            Tuple of (is_speech_active, speech_probability)
        """
        # Calculate energy
        energy = self._calculate_energy_db(signal)
        self.energy_history.append(energy)
        
        # Calculate spectral centroid
        spectral_centroid = self._calculate_spectral_centroid(signal)
        self.spectral_centroid_history.append(spectral_centroid)
        
        # Calculate zero crossing rate
        zcr = self._calculate_zero_crossing_rate(signal)
        self.zero_crossing_history.append(zcr)
        
        # Energy-based detection
        energy_active = energy > self.energy_threshold
        
        # Spectral-based detection (speech typically has lower centroid than noise)
        spectral_active = spectral_centroid < self.spectral_threshold
        
        # Zero crossing rate (speech has moderate ZCR)
        zcr_active = 0.02 < zcr < self.zcr_threshold
        
        # Combine features
        feature_score = 0.0
        if energy_active:
            feature_score += 0.4
        if spectral_active:
            feature_score += 0.3
        if zcr_active:
            feature_score += 0.3
        
        # Apply sensitivity
        speech_prob = feature_score * (0.5 + self.sensitivity * 0.5)
        
        # Decision with hysteresis
        if speech_prob > 0.6:
            new_speech_state = True
        elif speech_prob < 0.3:
            new_speech_state = False
        else:
            new_speech_state = self.speech_active  # Keep current state
        
        # Apply hangover
        if new_speech_state != self.speech_active:
            if self.hangover_counter <= 0:
                self.speech_active = new_speech_state
                self.hangover_counter = self.hangover_frames
            else:
                self.hangover_counter -= 1
        else:
            self.hangover_counter = max(0, self.hangover_counter - 1)
        
        return self.speech_active, speech_prob
    
    def _calculate_energy_db(self, signal: np.ndarray) -> float:
        """Calculate signal energy in dB."""
        if len(signal) == 0:
            return -80.0
        
        energy = np.mean(signal ** 2)
        if energy <= 0:
            return -80.0
        
        return 10 * np.log10(energy)
    
    def _calculate_spectral_centroid(self, signal: np.ndarray) -> float:
        """Calculate spectral centroid."""
        if len(signal) == 0:
            return 0.0
        
        # Simple FFT-based spectral centroid
        fft = np.fft.fft(signal)
        magnitude = np.abs(fft[:len(fft)//2])
        freqs = np.fft.fftfreq(len(signal), 1/48000)[:len(fft)//2]
        
        if np.sum(magnitude) == 0:
            return 0.0
        
        centroid = np.sum(freqs * magnitude) / np.sum(magnitude)
        return centroid
    
    def _calculate_zero_crossing_rate(self, signal: np.ndarray) -> float:
        """Calculate zero crossing rate."""
        if len(signal) <= 1:
            return 0.0
        
        zero_crossings = np.sum(np.diff(np.sign(signal)) != 0)
        return zero_crossings / (len(signal) - 1)
    
    def reset(self) -> None:
        """Reset detector state."""
        self.energy_history.clear()
        self.spectral_centroid_history.clear()
        self.zero_crossing_history.clear()
        self.speech_active = False
        self.hangover_counter = 0


class NoiseEstimator:
    """
    Noise spectrum estimation for adaptive denoising.
    
    Estimates background noise characteristics during non-speech periods.
    """
    
    def __init__(self, frame_size: int = 480, 
                 adaptation_rate: float = 0.1):
        self.frame_size = frame_size
        self.adaptation_rate = adaptation_rate
        
        # FFT parameters
        self.fft_size = 2 ** int(np.ceil(np.log2(frame_size)))
        
        # Noise spectrum estimate
        self.noise_spectrum = None
        self.noise_floor = -60.0  # dBFS
        
        # Adaptation control
        self.frames_since_update = 0
        self.min_update_interval = 5  # frames
        
        # Noise classification
        self.noise_type = NoiseType.UNKNOWN
        self.spectral_flatness_history = deque(maxlen=10)
        
        logger.info(
            "Noise estimator initialized",
            frame_size=frame_size,
            fft_size=self.fft_size,
            adaptation_rate=adaptation_rate
        )
    
    def update(self, signal: np.ndarray, is_speech_active: bool) -> None:
        """
        Update noise estimate during non-speech periods.
        
        Args:
            signal: Input audio signal
            is_speech_active: Whether speech is currently active
        """
        self.frames_since_update += 1
        
        # Only update during non-speech periods
        if is_speech_active or self.frames_since_update < self.min_update_interval:
            return
        
        # Calculate spectrum
        windowed_signal = signal * np.hanning(len(signal))
        fft = np.fft.fft(windowed_signal, self.fft_size)
        magnitude_spectrum = np.abs(fft[:self.fft_size//2])
        
        # Initialize noise spectrum if needed
        if self.noise_spectrum is None:
            self.noise_spectrum = magnitude_spectrum
        else:
            # Exponential averaging
            self.noise_spectrum = (
                (1 - self.adaptation_rate) * self.noise_spectrum +
                self.adaptation_rate * magnitude_spectrum
            )
        
        # Update noise floor estimate
        signal_power = np.mean(signal ** 2)
        if signal_power > 0:
            signal_level = 10 * np.log10(signal_power)
            self.noise_floor = (
                0.9 * self.noise_floor + 0.1 * signal_level
            )
        
        # Classify noise type
        self._classify_noise_type(magnitude_spectrum)
        
        self.frames_since_update = 0
    
    def get_noise_spectrum(self) -> Optional[np.ndarray]:
        """Get current noise spectrum estimate."""
        return self.noise_spectrum
    
    def get_noise_floor(self) -> float:
        """Get current noise floor estimate in dBFS."""
        return self.noise_floor
    
    def get_noise_type(self) -> NoiseType:
        """Get detected noise type."""
        return self.noise_type
    
    def _classify_noise_type(self, spectrum: np.ndarray) -> None:
        """Classify noise type based on spectral characteristics."""
        # Calculate spectral flatness (Wiener entropy)
        geometric_mean = np.exp(np.mean(np.log(spectrum + 1e-10)))
        arithmetic_mean = np.mean(spectrum)
        
        if arithmetic_mean > 0:
            spectral_flatness = geometric_mean / arithmetic_mean
        else:
            spectral_flatness = 0.0
        
        self.spectral_flatness_history.append(spectral_flatness)
        
        # Classify based on spectral flatness
        avg_flatness = np.mean(list(self.spectral_flatness_history))
        
        if avg_flatness > 0.8:
            self.noise_type = NoiseType.STATIONARY  # White/pink noise
        elif avg_flatness > 0.5:
            self.noise_type = NoiseType.NON_STATIONARY  # Variable noise
        elif avg_flatness > 0.2:
            self.noise_type = NoiseType.SPEECH_LIKE  # Speech-like interference
        else:
            self.noise_type = NoiseType.MUSIC  # Tonal/musical content
    
    def reset(self) -> None:
        """Reset noise estimator."""
        self.noise_spectrum = None
        self.noise_floor = -60.0
        self.frames_since_update = 0
        self.noise_type = NoiseType.UNKNOWN
        self.spectral_flatness_history.clear()


class RNNoiseProcessor:
    """
    RNNoise-inspired denoising processor.
    
    Implements a simplified version of RNNoise algorithm using
    spectral subtraction and Wiener filtering techniques.
    """
    
    def __init__(self, frame_size: int = 480,
                 noise_reduction_factor: float = 0.5):
        self.frame_size = frame_size
        self.noise_reduction_factor = noise_reduction_factor
        
        # FFT parameters
        self.fft_size = 2 ** int(np.ceil(np.log2(frame_size)))
        self.overlap = frame_size // 2
        
        # Processing buffers
        self.input_buffer = np.zeros(self.fft_size)
        self.output_buffer = np.zeros(self.fft_size)
        
        # Spectral processing
        self.prev_magnitude = None
        self.prev_phase = None
        
        # Smoothing parameters
        self.alpha_smooth = 0.8
        self.beta_smooth = 0.9
        
        # Over-subtraction parameters
        self.over_subtraction_factor = 2.0
        self.spectral_floor = 0.1
        
        logger.info(
            "RNNoise processor initialized",
            frame_size=frame_size,
            fft_size=self.fft_size,
            noise_reduction_factor=noise_reduction_factor
        )
    
    def process(self, signal: np.ndarray, 
                noise_spectrum: Optional[np.ndarray] = None,
                speech_prob: float = 0.5) -> np.ndarray:
        """
        Process audio signal for noise reduction.
        
        Args:
            signal: Input audio signal
            noise_spectrum: Estimated noise spectrum
            speech_prob: Probability of speech presence
            
        Returns:
            Denoised audio signal
        """
        if noise_spectrum is None:
            # No noise estimate available - minimal processing
            return signal * 0.9
        
        # Apply window and FFT
        windowed_signal = signal * np.hanning(len(signal))
        
        # Pad to FFT size
        padded_signal = np.zeros(self.fft_size)
        padded_signal[:len(windowed_signal)] = windowed_signal
        
        # FFT
        signal_fft = np.fft.fft(padded_signal)
        signal_magnitude = np.abs(signal_fft)
        signal_phase = np.angle(signal_fft)
        
        # Use only positive frequencies
        half_size = self.fft_size // 2
        signal_mag_half = signal_magnitude[:half_size]
        noise_spec_half = noise_spectrum[:half_size] if len(noise_spectrum) >= half_size else noise_spectrum
        
        # Spectral subtraction with over-subtraction
        enhanced_magnitude = self._spectral_subtraction(
            signal_mag_half, noise_spec_half, speech_prob
        )
        
        # Wiener filtering for additional smoothing
        enhanced_magnitude = self._wiener_filter(
            enhanced_magnitude, signal_mag_half, noise_spec_half
        )
        
        # Reconstruct full spectrum by padding to match signal_phase length
        full_enhanced_mag = np.zeros(len(signal_phase))
        copy_length = min(len(enhanced_magnitude), len(full_enhanced_mag))
        full_enhanced_mag[:copy_length] = enhanced_magnitude[:copy_length]
        
        # Reconstruct complex spectrum
        enhanced_fft = full_enhanced_mag * np.exp(1j * signal_phase)
        
        # IFFT and overlap-add
        enhanced_signal = np.real(np.fft.ifft(enhanced_fft))
        
        # Extract processed frame
        processed_frame = enhanced_signal[:self.frame_size]
        
        # Apply output gain based on speech probability
        output_gain = 0.7 + 0.3 * speech_prob  # Reduce gain during noise-only periods
        processed_frame *= output_gain
        
        return processed_frame
    
    def _spectral_subtraction(self, signal_mag: np.ndarray, 
                            noise_mag: np.ndarray,
                            speech_prob: float) -> np.ndarray:
        """Apply spectral subtraction for noise reduction."""
        # Adaptive over-subtraction based on speech probability
        over_sub_factor = self.over_subtraction_factor * (1.0 - speech_prob * 0.5)
        
        # Spectral subtraction
        enhanced_mag = signal_mag - over_sub_factor * noise_mag
        
        # Apply spectral floor
        spectral_floor = self.spectral_floor * signal_mag
        enhanced_mag = np.maximum(enhanced_mag, spectral_floor)
        
        return enhanced_mag
    
    def _wiener_filter(self, enhanced_mag: np.ndarray,
                      signal_mag: np.ndarray,
                      noise_mag: np.ndarray) -> np.ndarray:
        """Apply Wiener filtering for additional smoothing."""
        # Estimate SNR
        snr = (signal_mag ** 2) / (noise_mag ** 2 + 1e-10)
        
        # Wiener gain
        wiener_gain = snr / (snr + 1.0)
        
        # Apply gain with smoothing
        if self.prev_magnitude is not None:
            # Smooth the gain
            wiener_gain = (
                self.alpha_smooth * wiener_gain +
                (1 - self.alpha_smooth) * (self.prev_magnitude / (signal_mag + 1e-10))
            )
        
        # Apply Wiener filter
        wiener_enhanced = enhanced_mag * wiener_gain
        
        # Store for next frame
        self.prev_magnitude = wiener_enhanced
        
        return wiener_enhanced
    
    def set_noise_reduction_factor(self, factor: float) -> None:
        """Set noise reduction strength (0.0 = no reduction, 1.0 = maximum)."""
        self.noise_reduction_factor = np.clip(factor, 0.0, 1.0)
        
        # Update over-subtraction factor
        self.over_subtraction_factor = 1.0 + factor * 2.0
        
        logger.debug("Noise reduction factor updated", factor=factor)
    
    def reset(self) -> None:
        """Reset processor state."""
        self.input_buffer.fill(0.0)
        self.output_buffer.fill(0.0)
        self.prev_magnitude = None
        self.prev_phase = None


class DenoiseService(BaseAudioProcessor):
    """
    Noise Reduction and Speech Enhancement Service.
    
    Provides real-time denoising with RNNoise integration,
    adjustable noise reduction strength, and speech quality protection.
    """
    
    def __init__(self, service_name: str, config: AudioConfig,
                 noise_reduction_factor: float = 0.5,
                 mode: DenoiseMode = DenoiseMode.BALANCED,
                 metrics_collector: Optional[IMetricsCollector] = None):
        super().__init__(service_name, config, metrics_collector)
        
        # Validate parameters
        if not (0.0 <= noise_reduction_factor <= 1.0):
            raise ValueError("Noise reduction factor must be between 0.0 and 1.0")
        
        self.noise_reduction_factor = noise_reduction_factor
        self.mode = mode
        
        # Denoise components
        self.speech_detector = SpeechActivityDetector(
            frame_size=config.frame_size,
            sensitivity=0.5,
            hangover_frames=5
        )
        
        self.noise_estimator = NoiseEstimator(
            frame_size=config.frame_size,
            adaptation_rate=0.1
        )
        
        self.rnnoise_processor = RNNoiseProcessor(
            frame_size=config.frame_size,
            noise_reduction_factor=noise_reduction_factor
        )
        
        # Performance metrics
        self.denoise_metrics = DenoiseMetrics()
        self.noise_reduction_history = deque(maxlen=50)
        self.speech_quality_history = deque(maxlen=20)
        
        # Processing statistics
        self.frames_processed = 0
        self.speech_frames = 0
        self.noise_frames = 0
        
        logger.info(
            "Denoise Service initialized",
            service=service_name,
            noise_reduction_factor=noise_reduction_factor,
            mode=mode.value
        )
    
    async def _initialize(self) -> None:
        """Initialize denoise service."""
        logger.info("Initializing Denoise service", service=self.service_name)
        
        # Reset all components
        self.speech_detector.reset()
        self.noise_estimator.reset()
        self.rnnoise_processor.reset()
        
        # Reset metrics
        self.denoise_metrics = DenoiseMetrics()
        self.noise_reduction_history.clear()
        self.speech_quality_history.clear()
        
        # Reset statistics
        self.frames_processed = 0
        self.speech_frames = 0
        self.noise_frames = 0
    
    async def _cleanup(self) -> None:
        """Cleanup denoise service."""
        logger.info("Denoise service cleaned up")
    
    async def _process_frame(self, frame: AudioFrame) -> AudioFrame:
        """
        Process audio frame for noise reduction.
        
        Args:
            frame: Input audio frame
            
        Returns:
            Denoised audio frame
        """
        if frame.channels != 1:
            raise ProcessingError("Denoise service expects single-channel input")
        
        # Get input signal
        input_signal = frame.data[0, :]
        
        # Process based on current mode
        if self.mode == DenoiseMode.BYPASS:
            return frame
        else:
            return await self._process_denoising(frame, input_signal)
    
    async def _process_denoising(self, frame: AudioFrame, 
                               input_signal: np.ndarray) -> AudioFrame:
        """
        Perform noise reduction processing.
        
        Args:
            frame: Original audio frame
            input_signal: Input audio signal
            
        Returns:
            Denoised audio frame
        """
        self.frames_processed += 1
        
        # Step 1: Speech activity detection
        is_speech_active, speech_prob = self.speech_detector.detect(input_signal)
        
        # Update statistics
        if is_speech_active:
            self.speech_frames += 1
        else:
            self.noise_frames += 1
        
        # Step 2: Update noise estimate during non-speech periods
        self.noise_estimator.update(input_signal, is_speech_active)
        
        # Step 3: Apply noise reduction
        noise_spectrum = self.noise_estimator.get_noise_spectrum()
        
        if noise_spectrum is not None:
            # Apply RNNoise processing
            denoised_signal = self.rnnoise_processor.process(
                input_signal, noise_spectrum, speech_prob
            )
        else:
            # No noise estimate yet - apply minimal processing
            denoised_signal = input_signal * 0.95
        
        # Step 4: Apply mode-specific processing
        denoised_signal = self._apply_mode_processing(
            denoised_signal, input_signal, speech_prob
        )
        
        # Step 5: Update performance metrics
        self._update_denoise_metrics(input_signal, denoised_signal, speech_prob)
        
        # Create output frame
        output_frame = AudioFrame(
            timestamp=frame.timestamp,
            sample_rate=frame.sample_rate,
            channels=1,
            frame_size=frame.frame_size,
            data=denoised_signal.reshape(1, -1),
            metadata=frame.metadata.copy() if frame.metadata else {}
        )
        
        # Add denoise metadata
        output_frame.metadata.update({
            'denoise_applied': True,
            'denoise_mode': self.mode.value,
            'noise_reduction_factor': self.noise_reduction_factor,
            'speech_active': is_speech_active,
            'speech_probability': speech_prob,
            'noise_reduction_db': self.denoise_metrics.noise_reduction_db,
            'noise_type': self.noise_estimator.get_noise_type().value,
            'noise_floor_db': self.noise_estimator.get_noise_floor()
        })
        
        return output_frame
    
    def _apply_mode_processing(self, denoised_signal: np.ndarray,
                             original_signal: np.ndarray,
                             speech_prob: float) -> np.ndarray:
        """Apply mode-specific processing adjustments."""
        if self.mode == DenoiseMode.FIDELITY:
            # High fidelity - minimal processing, preserve original during speech
            if speech_prob > 0.7:
                # Blend more towards original during strong speech
                blend_factor = 0.8
                return blend_factor * original_signal + (1 - blend_factor) * denoised_signal
            else:
                return denoised_signal
        
        elif self.mode == DenoiseMode.AGGRESSIVE:
            # Aggressive - maximum noise reduction
            # Apply additional spectral gating
            return self._apply_spectral_gating(denoised_signal, speech_prob)
        
        else:  # BALANCED mode
            # Balanced processing
            return denoised_signal
    
    def _apply_spectral_gating(self, signal: np.ndarray, 
                             speech_prob: float) -> np.ndarray:
        """Apply spectral gating for aggressive noise reduction."""
        # Simple spectral gating based on energy
        gate_threshold = -50.0 + speech_prob * 10.0  # Adaptive threshold
        
        signal_energy = 20 * np.log10(np.abs(signal) + 1e-10)
        gate_mask = signal_energy > gate_threshold
        
        # Apply soft gating
        gated_signal = signal.copy()
        gated_signal[~gate_mask] *= 0.1  # Reduce low-energy components
        
        return gated_signal
    
    def _update_denoise_metrics(self, input_signal: np.ndarray,
                              output_signal: np.ndarray,
                              speech_prob: float) -> None:
        """Update denoise performance metrics."""
        # Calculate noise reduction
        input_power = np.mean(input_signal ** 2)
        output_power = np.mean(output_signal ** 2)
        
        if input_power > 0 and output_power > 0:
            # During noise-only periods, calculate actual noise reduction
            if speech_prob < 0.3:
                noise_reduction_db = 10 * np.log10(input_power / output_power)
                self.noise_reduction_history.append(noise_reduction_db)
                
                if len(self.noise_reduction_history) > 0:
                    self.denoise_metrics.noise_reduction_db = np.mean(
                        list(self.noise_reduction_history)
                    )
        
        # Estimate speech quality (simplified PESQ-like metric)
        if speech_prob > 0.5:
            # During speech periods, estimate quality preservation
            correlation = np.corrcoef(input_signal, output_signal)[0, 1]
            if not np.isnan(correlation):
                quality_score = max(1.0, min(5.0, 1.0 + 4.0 * abs(correlation)))
                self.speech_quality_history.append(quality_score)
                
                if len(self.speech_quality_history) > 0:
                    self.denoise_metrics.speech_quality_score = np.mean(
                        list(self.speech_quality_history)
                    )
        
        # Update other metrics
        self.denoise_metrics.speech_presence_prob = speech_prob
        self.denoise_metrics.noise_floor_estimate = self.noise_estimator.get_noise_floor()
        self.denoise_metrics.noise_type = self.noise_estimator.get_noise_type()
        self.denoise_metrics.adaptation_rate = self.noise_estimator.adaptation_rate
    
    def set_mode(self, mode: DenoiseMode) -> None:
        """
        Set denoise operation mode.
        
        Args:
            mode: Denoise operation mode
        """
        old_mode = self.mode
        self.mode = mode
        
        # Adjust processing parameters based on mode
        if mode == DenoiseMode.FIDELITY:
            self.rnnoise_processor.set_noise_reduction_factor(0.3)
            self.speech_detector.sensitivity = 0.7  # More sensitive to speech
        elif mode == DenoiseMode.AGGRESSIVE:
            self.rnnoise_processor.set_noise_reduction_factor(0.8)
            self.speech_detector.sensitivity = 0.3  # Less sensitive to speech
        elif mode == DenoiseMode.BALANCED:
            self.rnnoise_processor.set_noise_reduction_factor(0.5)
            self.speech_detector.sensitivity = 0.5  # Balanced sensitivity
        
        logger.info("Denoise mode changed", old_mode=old_mode.value, new_mode=mode.value)
    
    def set_noise_reduction_factor(self, factor: float) -> None:
        """
        Set noise reduction strength.
        
        Args:
            factor: Noise reduction factor (0.0 = no reduction, 1.0 = maximum)
        """
        if not (0.0 <= factor <= 1.0):
            raise ValueError("Noise reduction factor must be between 0.0 and 1.0")
        
        old_factor = self.noise_reduction_factor
        self.noise_reduction_factor = factor
        
        # Update processor
        self.rnnoise_processor.set_noise_reduction_factor(factor)
        
        logger.info("Noise reduction factor updated", 
                   old_factor=old_factor, new_factor=factor)
    
    def reset_adaptation(self) -> None:
        """Reset noise adaptation state."""
        self.noise_estimator.reset()
        self.rnnoise_processor.reset()
        
        # Reset metrics
        self.denoise_metrics = DenoiseMetrics()
        self.noise_reduction_history.clear()
        self.speech_quality_history.clear()
        
        logger.info("Denoise adaptation state reset")
    
    def get_denoise_metrics(self) -> Dict[str, Any]:
        """
        Get denoise-specific metrics.
        
        Returns:
            Dictionary with denoise performance metrics
        """
        metrics = self.denoise_metrics.to_dict()
        
        # Add processing statistics
        speech_ratio = self.speech_frames / max(1, self.frames_processed)
        noise_ratio = self.noise_frames / max(1, self.frames_processed)
        
        metrics.update({
            'mode': self.mode.value,
            'noise_reduction_factor': self.noise_reduction_factor,
            'frames_processed': self.frames_processed,
            'speech_frame_ratio': speech_ratio,
            'noise_frame_ratio': noise_ratio,
            'adaptation_active': len(self.noise_reduction_history) > 0
        })
        
        return metrics
    
    def get_config_schema(self) -> Dict[str, Any]:
        """Get configuration schema for denoise service."""
        return {
            "type": "object",
            "properties": {
                "noise_reduction_factor": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Noise reduction strength (0.0-1.0)"
                },
                "mode": {
                    "type": "string",
                    "enum": [mode.value for mode in DenoiseMode],
                    "description": "Denoise operation mode"
                },
                "speech_sensitivity": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Speech detection sensitivity (0.0-1.0)"
                }
            },
            "required": ["noise_reduction_factor", "mode"]
        }