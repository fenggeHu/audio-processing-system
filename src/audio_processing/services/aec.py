"""
Acoustic Echo Cancellation (AEC) Service for classroom audio processing.

This module implements the AECService with NLMS adaptive filtering,
double-talk detection, and residual echo suppression for classroom environments.
"""

import asyncio
import time
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime, timedelta
from enum import Enum
import numpy as np
import structlog
from scipy import signal
from collections import deque

from ..interfaces import IAudioService, IMetricsCollector
from ..base import BaseAudioProcessor
from ..models import AudioFrame, AudioConfig, ProcessingResult, AudioMetrics
from ..exceptions import ProcessingError, ServiceError

logger = structlog.get_logger(__name__)


class AECMode(Enum):
    """AEC operation modes."""
    FULL_DUPLEX = "full_duplex"      # Normal operation with echo cancellation
    HALF_DUPLEX = "half_duplex"      # Mute microphone during speaker activity
    BYPASS = "bypass"                # Pass-through mode (no AEC)
    CALIBRATION = "calibration"      # Room impulse response measurement


class DoubleTalkState(Enum):
    """Double-talk detection states."""
    SINGLE_TALK_FAR = "single_talk_far"    # Only far-end (speaker) active
    SINGLE_TALK_NEAR = "single_talk_near"  # Only near-end (microphone) active
    DOUBLE_TALK = "double_talk"            # Both ends active
    SILENCE = "silence"                    # No activity


@dataclass
class AECMetrics:
    """AEC performance metrics."""
    erle_db: float = 0.0                    # Echo Return Loss Enhancement
    residual_echo_level: float = 0.0        # Residual echo power
    double_talk_ratio: float = 0.0          # Percentage of double-talk frames
    adaptation_rate: float = 0.0            # Current adaptation step size
    filter_divergence: float = 0.0          # Filter stability metric
    echo_path_delay: int = 0                # Estimated echo path delay in samples
    comfort_noise_level: float = -60.0      # Comfort noise level in dBFS
    
    def to_dict(self) -> Dict[str, float]:
        """Convert metrics to dictionary."""
        return {
            'erle_db': self.erle_db,
            'residual_echo_level': self.residual_echo_level,
            'double_talk_ratio': self.double_talk_ratio,
            'adaptation_rate': self.adaptation_rate,
            'filter_divergence': self.filter_divergence,
            'echo_path_delay': float(self.echo_path_delay),
            'comfort_noise_level': self.comfort_noise_level
        }


class DoubleTalkDetector:
    """
    Double-talk detector for AEC systems.
    
    Detects when both near-end and far-end speakers are active
    to prevent filter adaptation during double-talk periods.
    """
    
    def __init__(self, frame_size: int = 480, 
                 sensitivity: float = 0.5,
                 hangover_frames: int = 10):
        self.frame_size = frame_size
        self.sensitivity = sensitivity
        self.hangover_frames = hangover_frames
        
        # Energy estimation
        self.near_energy_history = deque(maxlen=20)
        self.far_energy_history = deque(maxlen=20)
        self.echo_energy_history = deque(maxlen=20)
        
        # State tracking
        self.current_state = DoubleTalkState.SILENCE
        self.hangover_counter = 0
        
        # Thresholds
        self.silence_threshold = -50.0  # dBFS
        self.double_talk_threshold = 6.0  # dB difference
        
        logger.info(
            "Double-talk detector initialized",
            sensitivity=sensitivity,
            hangover_frames=hangover_frames
        )
    
    def detect(self, near_signal: np.ndarray, far_signal: np.ndarray,
               echo_estimate: Optional[np.ndarray] = None) -> DoubleTalkState:
        """
        Detect double-talk condition.
        
        Args:
            near_signal: Near-end (microphone) signal
            far_signal: Far-end (speaker) signal  
            echo_estimate: Estimated echo signal (optional)
            
        Returns:
            Current double-talk state
        """
        # Calculate signal energies
        near_energy = self._calculate_energy_db(near_signal)
        far_energy = self._calculate_energy_db(far_signal)
        
        # Update energy histories
        self.near_energy_history.append(near_energy)
        self.far_energy_history.append(far_energy)
        
        if echo_estimate is not None:
            echo_energy = self._calculate_energy_db(echo_estimate)
            self.echo_energy_history.append(echo_energy)
        
        # Get smoothed energies
        near_avg = np.mean(list(self.near_energy_history)[-5:]) if self.near_energy_history else near_energy
        far_avg = np.mean(list(self.far_energy_history)[-5:]) if self.far_energy_history else far_energy
        
        # Determine activity states
        near_active = near_avg > self.silence_threshold
        far_active = far_avg > self.silence_threshold
        
        # Basic state detection
        if not near_active and not far_active:
            new_state = DoubleTalkState.SILENCE
        elif far_active and not near_active:
            new_state = DoubleTalkState.SINGLE_TALK_FAR
        elif near_active and not far_active:
            new_state = DoubleTalkState.SINGLE_TALK_NEAR
        else:
            # Both active - check for double-talk
            if echo_estimate is not None and len(self.echo_energy_history) > 0:
                echo_avg = np.mean(list(self.echo_energy_history)[-3:])
                residual_energy = near_avg - echo_avg
                
                # If residual energy is significant, likely double-talk
                if residual_energy > self.double_talk_threshold:
                    new_state = DoubleTalkState.DOUBLE_TALK
                else:
                    new_state = DoubleTalkState.SINGLE_TALK_FAR
            else:
                # Conservative approach - assume double-talk when both active
                energy_diff = abs(near_avg - far_avg)
                if energy_diff < self.double_talk_threshold:
                    new_state = DoubleTalkState.DOUBLE_TALK
                else:
                    new_state = DoubleTalkState.SINGLE_TALK_FAR if far_avg > near_avg else DoubleTalkState.SINGLE_TALK_NEAR
        
        # Apply hangover for stability
        if new_state != self.current_state:
            if self.hangover_counter <= 0:
                self.current_state = new_state
                self.hangover_counter = self.hangover_frames
            else:
                self.hangover_counter -= 1
        else:
            self.hangover_counter = max(0, self.hangover_counter - 1)
        
        return self.current_state
    
    def _calculate_energy_db(self, signal: np.ndarray) -> float:
        """Calculate signal energy in dB."""
        if len(signal) == 0:
            return -80.0
        
        energy = np.mean(signal ** 2)
        if energy <= 0:
            return -80.0
        
        return 10 * np.log10(energy)
    
    def reset(self) -> None:
        """Reset detector state."""
        self.near_energy_history.clear()
        self.far_energy_history.clear()
        self.echo_energy_history.clear()
        self.current_state = DoubleTalkState.SILENCE
        self.hangover_counter = 0


class NLMSFilter:
    """
    Normalized Least Mean Squares (NLMS) adaptive filter for AEC.
    
    Implements the NLMS algorithm for acoustic echo cancellation
    with regularization and step-size control.
    """
    
    def __init__(self, filter_length: int = 256, 
                 step_size: float = 0.5,
                 regularization: float = 1e-6):
        self.filter_length = filter_length
        self.step_size = step_size
        self.regularization = regularization
        
        # Filter coefficients
        self.weights = np.zeros(filter_length)
        
        # Input buffer (delay line)
        self.input_buffer = np.zeros(filter_length)
        
        # Adaptation control
        self.adaptation_enabled = True
        self.step_size_min = 0.01
        self.step_size_max = 1.0
        
        # Performance tracking
        self.mse_history = deque(maxlen=100)
        self.convergence_metric = 0.0
        
        logger.info(
            "NLMS filter initialized",
            filter_length=filter_length,
            step_size=step_size,
            regularization=regularization
        )
    
    def filter(self, input_sample: float) -> float:
        """
        Filter single input sample.
        
        Args:
            input_sample: Input sample (far-end signal)
            
        Returns:
            Filter output (echo estimate)
        """
        # Shift input buffer
        self.input_buffer[1:] = self.input_buffer[:-1]
        self.input_buffer[0] = input_sample
        
        # Compute filter output
        output = np.dot(self.weights, self.input_buffer)
        
        return output
    
    def adapt(self, error: float, input_sample: float) -> None:
        """
        Adapt filter weights using NLMS algorithm.
        
        Args:
            error: Error signal (microphone - echo_estimate)
            input_sample: Current input sample
        """
        if not self.adaptation_enabled:
            return
        
        # Update input buffer
        self.input_buffer[1:] = self.input_buffer[:-1]
        self.input_buffer[0] = input_sample
        
        # Calculate input power
        input_power = np.dot(self.input_buffer, self.input_buffer)
        
        # NLMS update with regularization
        if input_power > self.regularization:
            # Normalized step size
            mu_normalized = self.step_size / (input_power + self.regularization)
            
            # Weight update
            self.weights += mu_normalized * error * self.input_buffer
        
        # Track MSE for convergence monitoring
        self.mse_history.append(error ** 2)
        
        # Update convergence metric
        if len(self.mse_history) >= 10:
            recent_mse = np.mean(list(self.mse_history)[-10:])
            older_mse = np.mean(list(self.mse_history)[-20:-10]) if len(self.mse_history) >= 20 else recent_mse
            
            if older_mse > 0:
                self.convergence_metric = (older_mse - recent_mse) / older_mse
            else:
                self.convergence_metric = 0.0
    
    def process_frame(self, input_frame: np.ndarray, error_frame: np.ndarray) -> np.ndarray:
        """
        Process entire audio frame.
        
        Args:
            input_frame: Input frame (far-end signal)
            error_frame: Error frame for adaptation
            
        Returns:
            Echo estimate frame
        """
        output_frame = np.zeros_like(input_frame)
        
        for i, (input_sample, error_sample) in enumerate(zip(input_frame, error_frame)):
            # Filter
            output_frame[i] = self.filter(input_sample)
            
            # Adapt
            self.adapt(error_sample, input_sample)
        
        return output_frame
    
    def set_adaptation_enabled(self, enabled: bool) -> None:
        """Enable or disable filter adaptation."""
        self.adaptation_enabled = enabled
        logger.debug("NLMS adaptation", enabled=enabled)
    
    def reset_filter(self) -> None:
        """Reset filter to initial state."""
        self.weights.fill(0.0)
        self.input_buffer.fill(0.0)
        self.mse_history.clear()
        self.convergence_metric = 0.0
        logger.info("NLMS filter reset")
    
    def get_filter_metrics(self) -> Dict[str, float]:
        """Get filter performance metrics."""
        avg_mse = np.mean(list(self.mse_history)) if self.mse_history else 0.0
        
        return {
            'mse': avg_mse,
            'convergence_metric': self.convergence_metric,
            'filter_norm': float(np.linalg.norm(self.weights)),
            'adaptation_enabled': float(self.adaptation_enabled)
        }


class ResidualEchoSuppressor:
    """
    Residual echo suppressor for post-processing after linear AEC.
    
    Uses spectral subtraction and Wiener filtering to suppress
    remaining echo components that linear filtering cannot remove.
    """
    
    def __init__(self, frame_size: int = 480, 
                 suppression_factor: float = 0.5,
                 noise_floor: float = 0.01):
        self.frame_size = frame_size
        self.suppression_factor = suppression_factor
        self.noise_floor = noise_floor
        
        # FFT parameters
        self.fft_size = 2 ** int(np.ceil(np.log2(frame_size)))
        self.overlap = frame_size // 2
        
        # Spectral estimation
        self.echo_spectrum_estimate = None
        self.noise_spectrum_estimate = None
        
        # Smoothing parameters
        self.alpha_echo = 0.9
        self.alpha_noise = 0.95
        
        # Over-subtraction parameters
        self.over_subtraction_factor = 2.0
        self.spectral_floor = 0.1
        
        logger.info(
            "Residual echo suppressor initialized",
            frame_size=frame_size,
            fft_size=self.fft_size,
            suppression_factor=suppression_factor
        )
    
    def suppress(self, microphone_frame: np.ndarray, 
                 echo_estimate_frame: np.ndarray,
                 far_end_frame: np.ndarray) -> np.ndarray:
        """
        Suppress residual echo in microphone signal.
        
        Args:
            microphone_frame: Microphone signal
            echo_estimate_frame: Linear echo estimate
            far_end_frame: Far-end reference signal
            
        Returns:
            Echo-suppressed signal
        """
        # Apply FFT
        mic_fft = np.fft.fft(microphone_frame, self.fft_size)
        echo_fft = np.fft.fft(echo_estimate_frame, self.fft_size)
        far_fft = np.fft.fft(far_end_frame, self.fft_size)
        
        # Get magnitude spectra
        mic_mag = np.abs(mic_fft)
        echo_mag = np.abs(echo_fft)
        far_mag = np.abs(far_fft)
        
        # Update echo spectrum estimate
        if self.echo_spectrum_estimate is None:
            self.echo_spectrum_estimate = echo_mag
        else:
            self.echo_spectrum_estimate = (
                self.alpha_echo * self.echo_spectrum_estimate + 
                (1 - self.alpha_echo) * echo_mag
            )
        
        # Estimate residual echo spectrum
        residual_echo_estimate = self.suppression_factor * self.echo_spectrum_estimate
        
        # Spectral subtraction with over-subtraction
        suppressed_mag = mic_mag - self.over_subtraction_factor * residual_echo_estimate
        
        # Apply spectral floor
        spectral_floor = self.spectral_floor * mic_mag
        suppressed_mag = np.maximum(suppressed_mag, spectral_floor)
        
        # Preserve phase from microphone signal
        mic_phase = np.angle(mic_fft)
        suppressed_fft = suppressed_mag * np.exp(1j * mic_phase)
        
        # Convert back to time domain
        suppressed_frame = np.real(np.fft.ifft(suppressed_fft))[:self.frame_size]
        
        return suppressed_frame
    
    def update_noise_estimate(self, noise_frame: np.ndarray) -> None:
        """Update background noise estimate during silence periods."""
        noise_fft = np.fft.fft(noise_frame, self.fft_size)
        noise_mag = np.abs(noise_fft)
        
        if self.noise_spectrum_estimate is None:
            self.noise_spectrum_estimate = noise_mag
        else:
            self.noise_spectrum_estimate = (
                self.alpha_noise * self.noise_spectrum_estimate +
                (1 - self.alpha_noise) * noise_mag
            )
    
    def reset(self) -> None:
        """Reset suppressor state."""
        self.echo_spectrum_estimate = None
        self.noise_spectrum_estimate = None


class ComfortNoiseGenerator:
    """
    Comfort noise generator for AEC systems.
    
    Generates low-level background noise during silence periods
    to avoid unnatural silence artifacts.
    """
    
    def __init__(self, noise_level_db: float = -60.0,
                 spectral_shape: str = "pink"):
        self.noise_level_db = noise_level_db
        self.spectral_shape = spectral_shape
        
        # Noise generation state
        self.noise_state = np.random.RandomState(42)  # Fixed seed for reproducibility
        
        # Spectral shaping filter
        if spectral_shape == "pink":
            # Pink noise filter coefficients (1/f spectrum)
            self.shaping_filter = self._design_pink_filter()
        else:
            # White noise (no shaping)
            self.shaping_filter = np.array([1.0])
        
        self.filter_state = np.zeros(len(self.shaping_filter) - 1)
        
        logger.info(
            "Comfort noise generator initialized",
            noise_level_db=noise_level_db,
            spectral_shape=spectral_shape
        )
    
    def generate(self, frame_size: int, 
                 reference_level: Optional[float] = None) -> np.ndarray:
        """
        Generate comfort noise frame.
        
        Args:
            frame_size: Number of samples to generate
            reference_level: Reference signal level for adaptive noise level
            
        Returns:
            Comfort noise samples
        """
        # Generate white noise
        white_noise = self.noise_state.randn(frame_size)
        
        # Apply spectral shaping
        if len(self.shaping_filter) > 1:
            shaped_noise, self.filter_state = signal.lfilter(
                self.shaping_filter, [1.0], white_noise, zi=self.filter_state
            )
        else:
            shaped_noise = white_noise
        
        # Apply noise level
        noise_level_linear = 10 ** (self.noise_level_db / 20.0)
        
        # Adaptive noise level based on reference
        if reference_level is not None:
            # Adjust noise level relative to reference signal
            adaptive_factor = max(0.1, min(1.0, reference_level / 0.1))
            noise_level_linear *= adaptive_factor
        
        comfort_noise = shaped_noise * noise_level_linear
        
        return comfort_noise
    
    def _design_pink_filter(self) -> np.ndarray:
        """Design pink noise shaping filter."""
        # Simple pink noise approximation using IIR filter
        # This is a simplified implementation
        return np.array([0.049922035, -0.095993537, 0.050612699, -0.004408786])
    
    def set_noise_level(self, level_db: float) -> None:
        """Set comfort noise level."""
        self.noise_level_db = level_db
        logger.debug("Comfort noise level set", level_db=level_db)


class AECService(BaseAudioProcessor):
    """
    Acoustic Echo Cancellation (AEC) Service.
    
    Provides real-time echo cancellation for classroom audio systems
    with NLMS adaptive filtering, double-talk detection, and residual echo suppression.
    """
    
    def __init__(self, service_name: str, config: AudioConfig,
                 filter_length: int = 256,
                 step_size: float = 0.5,
                 metrics_collector: Optional[IMetricsCollector] = None):
        super().__init__(service_name, config, metrics_collector)
        
        # Validate filter length
        if not (128 <= filter_length <= 512):
            raise ValueError("Filter length must be between 128 and 512 taps")
        
        self.filter_length = filter_length
        self.step_size = step_size
        
        # AEC components
        self.nlms_filter = NLMSFilter(
            filter_length=filter_length,
            step_size=step_size,
            regularization=1e-6
        )
        
        self.double_talk_detector = DoubleTalkDetector(
            frame_size=config.frame_size,
            sensitivity=0.5,
            hangover_frames=10
        )
        
        self.residual_suppressor = ResidualEchoSuppressor(
            frame_size=config.frame_size,
            suppression_factor=0.5,
            noise_floor=0.01
        )
        
        self.comfort_noise_generator = ComfortNoiseGenerator(
            noise_level_db=-60.0,
            spectral_shape="pink"
        )
        
        # AEC state
        self.mode = AECMode.FULL_DUPLEX
        self.adaptation_enabled = True
        
        # Reference signal buffer (speaker output)
        self.reference_buffer = deque(maxlen=1000)  # Store recent reference samples
        
        # Performance metrics
        self.aec_metrics = AECMetrics()
        self.erle_history = deque(maxlen=50)
        self.double_talk_frames = 0
        self.total_frames = 0
        
        # Echo path change detection
        self.last_adaptation_time = time.time()
        self.adaptation_timeout = 2.0  # seconds
        
        # Calibration state
        self.calibration_active = False
        self.room_impulse_response = None
        
        logger.info(
            "AEC Service initialized",
            service=service_name,
            filter_length=filter_length,
            step_size=step_size,
            mode=self.mode.value
        )
    
    async def _initialize(self) -> None:
        """Initialize AEC service."""
        logger.info("Initializing AEC service", service=self.service_name)
        
        # Reset all components
        self.nlms_filter.reset_filter()
        self.double_talk_detector.reset()
        self.residual_suppressor.reset()
        
        # Clear buffers
        self.reference_buffer.clear()
        self.erle_history.clear()
        
        # Reset metrics
        self.aec_metrics = AECMetrics()
        self.double_talk_frames = 0
        self.total_frames = 0
    
    async def _cleanup(self) -> None:
        """Cleanup AEC service."""
        logger.info("AEC service cleaned up")
    
    async def _process_frame(self, frame: AudioFrame) -> AudioFrame:
        """
        Process audio frame for echo cancellation.
        
        Args:
            frame: Input audio frame (microphone signal)
            
        Returns:
            Echo-cancelled audio frame
        """
        if frame.channels != 1:
            raise ProcessingError("AEC service expects single-channel input")
        
        # Get microphone signal
        microphone_signal = frame.data[0, :]
        
        # Get reference signal (speaker output) from metadata or buffer
        reference_signal = self._get_reference_signal(frame)
        
        if reference_signal is None:
            # No reference signal available - pass through with comfort noise
            logger.debug("No reference signal available for AEC")
            return self._add_comfort_noise(frame)
        
        # Process based on current mode
        if self.mode == AECMode.BYPASS:
            return frame
        elif self.mode == AECMode.CALIBRATION:
            return await self._process_calibration(frame, reference_signal)
        else:
            return await self._process_echo_cancellation(frame, microphone_signal, reference_signal)
    
    def _get_reference_signal(self, frame: AudioFrame) -> Optional[np.ndarray]:
        """
        Get reference signal (speaker output) for echo cancellation.
        
        Args:
            frame: Current audio frame
            
        Returns:
            Reference signal array or None if not available
        """
        # Check if reference signal is provided in metadata
        if frame.metadata and 'reference_signal' in frame.metadata:
            return np.array(frame.metadata['reference_signal'])
        
        # Check if we have buffered reference signal
        if len(self.reference_buffer) >= frame.frame_size:
            # Get most recent samples
            reference_samples = list(self.reference_buffer)[-frame.frame_size:]
            return np.array(reference_samples)
        
        # Generate synthetic reference for testing (in real system, this would come from speaker output)
        if hasattr(self, '_generate_test_reference') and self._generate_test_reference:
            return np.random.randn(frame.frame_size) * 0.1
        
        return None
    
    async def _process_echo_cancellation(self, frame: AudioFrame, 
                                       microphone_signal: np.ndarray,
                                       reference_signal: np.ndarray) -> AudioFrame:
        """
        Perform echo cancellation processing.
        
        Args:
            frame: Original audio frame
            microphone_signal: Microphone input signal
            reference_signal: Speaker output reference signal
            
        Returns:
            Echo-cancelled audio frame
        """
        self.total_frames += 1
        
        # Step 1: Generate echo estimate using NLMS filter
        echo_estimate = np.zeros_like(microphone_signal)
        error_signal = np.zeros_like(microphone_signal)
        
        for i in range(len(microphone_signal)):
            # Filter to get echo estimate
            echo_estimate[i] = self.nlms_filter.filter(reference_signal[i])
            
            # Calculate error (microphone - echo estimate)
            error_signal[i] = microphone_signal[i] - echo_estimate[i]
        
        # Step 2: Double-talk detection
        dt_state = self.double_talk_detector.detect(
            microphone_signal, reference_signal, echo_estimate
        )
        
        # Track double-talk statistics
        if dt_state == DoubleTalkState.DOUBLE_TALK:
            self.double_talk_frames += 1
        
        # Step 3: Adaptive filtering (only during single-talk far-end)
        adaptation_enabled = (
            dt_state == DoubleTalkState.SINGLE_TALK_FAR and 
            self.adaptation_enabled
        )
        
        self.nlms_filter.set_adaptation_enabled(adaptation_enabled)
        
        # Adapt filter with error signal
        if adaptation_enabled:
            for i in range(len(microphone_signal)):
                self.nlms_filter.adapt(error_signal[i], reference_signal[i])
            
            self.last_adaptation_time = time.time()
        
        # Step 4: Residual echo suppression
        if dt_state != DoubleTalkState.DOUBLE_TALK:
            suppressed_signal = self.residual_suppressor.suppress(
                error_signal, echo_estimate, reference_signal
            )
        else:
            # During double-talk, minimal suppression to preserve near-end speech
            suppressed_signal = error_signal
        
        # Step 5: Comfort noise generation during silence
        if dt_state == DoubleTalkState.SILENCE:
            comfort_noise = self.comfort_noise_generator.generate(
                len(suppressed_signal),
                reference_level=np.mean(np.abs(reference_signal))
            )
            suppressed_signal += comfort_noise
        
        # Step 6: Update performance metrics
        self._update_aec_metrics(microphone_signal, echo_estimate, suppressed_signal, dt_state)
        
        # Create output frame
        output_frame = AudioFrame(
            timestamp=frame.timestamp,
            sample_rate=frame.sample_rate,
            channels=1,
            frame_size=frame.frame_size,
            data=suppressed_signal.reshape(1, -1),
            metadata=frame.metadata.copy() if frame.metadata else {}
        )
        
        # Add AEC metadata
        output_frame.metadata.update({
            'aec_applied': True,
            'aec_mode': self.mode.value,
            'double_talk_state': dt_state.value,
            'erle_db': self.aec_metrics.erle_db,
            'adaptation_enabled': adaptation_enabled,
            'echo_path_delay': self.aec_metrics.echo_path_delay
        })
        
        return output_frame
    
    async def _process_calibration(self, frame: AudioFrame, 
                                 reference_signal: np.ndarray) -> AudioFrame:
        """
        Process frame during calibration mode.
        
        Args:
            frame: Input audio frame
            reference_signal: Reference signal for calibration
            
        Returns:
            Processed frame with calibration metadata
        """
        # During calibration, measure room impulse response
        # This is a simplified implementation
        
        microphone_signal = frame.data[0, :]
        
        # Cross-correlation to estimate impulse response
        correlation = np.correlate(microphone_signal, reference_signal, mode='full')
        
        # Find peak delay
        peak_idx = np.argmax(np.abs(correlation))
        delay_samples = peak_idx - len(reference_signal) + 1
        
        # Update echo path delay estimate
        self.aec_metrics.echo_path_delay = max(0, delay_samples)
        
        # Store impulse response estimate
        if self.room_impulse_response is None:
            self.room_impulse_response = correlation
        else:
            # Exponential averaging
            alpha = 0.1
            self.room_impulse_response = (
                (1 - alpha) * self.room_impulse_response + alpha * correlation
            )
        
        # Add calibration metadata
        output_frame = frame.copy()
        output_frame.metadata.update({
            'aec_calibration_active': True,
            'estimated_delay_samples': delay_samples,
            'correlation_peak': float(np.max(np.abs(correlation)))
        })
        
        return output_frame
    
    def _add_comfort_noise(self, frame: AudioFrame) -> AudioFrame:
        """Add comfort noise to frame when no processing is applied."""
        comfort_noise = self.comfort_noise_generator.generate(frame.frame_size)
        
        output_data = frame.data.copy()
        output_data[0, :] += comfort_noise
        
        output_frame = AudioFrame(
            timestamp=frame.timestamp,
            sample_rate=frame.sample_rate,
            channels=frame.channels,
            frame_size=frame.frame_size,
            data=output_data,
            metadata=frame.metadata.copy() if frame.metadata else {}
        )
        
        output_frame.metadata['comfort_noise_added'] = True
        return output_frame
    
    def _update_aec_metrics(self, microphone_signal: np.ndarray,
                           echo_estimate: np.ndarray,
                           output_signal: np.ndarray,
                           dt_state: DoubleTalkState) -> None:
        """Update AEC performance metrics."""
        # Calculate ERLE (Echo Return Loss Enhancement)
        mic_power = np.mean(microphone_signal ** 2)
        output_power = np.mean(output_signal ** 2)
        
        if mic_power > 0 and output_power > 0:
            erle_db = 10 * np.log10(mic_power / output_power)
            self.erle_history.append(erle_db)
            
            # Update running average
            if len(self.erle_history) > 0:
                self.aec_metrics.erle_db = np.mean(list(self.erle_history))
        
        # Calculate residual echo level
        echo_power = np.mean(echo_estimate ** 2)
        if echo_power > 0:
            self.aec_metrics.residual_echo_level = 10 * np.log10(output_power / echo_power)
        
        # Update double-talk ratio
        if self.total_frames > 0:
            self.aec_metrics.double_talk_ratio = self.double_talk_frames / self.total_frames
        
        # Get filter metrics
        filter_metrics = self.nlms_filter.get_filter_metrics()
        self.aec_metrics.adaptation_rate = self.step_size
        self.aec_metrics.filter_divergence = filter_metrics.get('convergence_metric', 0.0)
    
    def set_reference_signal(self, reference_samples: np.ndarray) -> None:
        """
        Set reference signal (speaker output) for echo cancellation.
        
        Args:
            reference_samples: Speaker output samples
        """
        # Add to reference buffer
        self.reference_buffer.extend(reference_samples.tolist())
    
    def set_mode(self, mode: AECMode) -> None:
        """
        Set AEC operation mode.
        
        Args:
            mode: AEC operation mode
        """
        old_mode = self.mode
        self.mode = mode
        
        if mode == AECMode.CALIBRATION:
            self.calibration_active = True
            self.room_impulse_response = None
        else:
            self.calibration_active = False
        
        logger.info("AEC mode changed", old_mode=old_mode.value, new_mode=mode.value)
    
    def set_filter_length(self, length: int) -> None:
        """
        Set adaptive filter length.
        
        Args:
            length: Filter length in taps (128-512)
        """
        if not (128 <= length <= 512):
            raise ValueError("Filter length must be between 128 and 512 taps")
        
        if length != self.filter_length:
            self.filter_length = length
            
            # Recreate NLMS filter with new length
            self.nlms_filter = NLMSFilter(
                filter_length=length,
                step_size=self.step_size,
                regularization=1e-6
            )
            
            logger.info("AEC filter length updated", length=length)
    
    def enable_adaptation(self, enabled: bool) -> None:
        """
        Enable or disable filter adaptation.
        
        Args:
            enabled: Whether to enable adaptation
        """
        self.adaptation_enabled = enabled
        logger.info("AEC adaptation", enabled=enabled)
    
    def reset_adaptation(self) -> None:
        """Reset AEC adaptation state."""
        self.nlms_filter.reset_filter()
        self.double_talk_detector.reset()
        self.residual_suppressor.reset()
        
        # Reset metrics
        self.aec_metrics = AECMetrics()
        self.erle_history.clear()
        self.double_talk_frames = 0
        self.total_frames = 0
        
        logger.info("AEC adaptation state reset")
    
    def get_aec_metrics(self) -> Dict[str, Any]:
        """
        Get AEC-specific metrics.
        
        Returns:
            Dictionary with AEC performance metrics
        """
        # Check for echo path change (requirement 3.5)
        time_since_adaptation = time.time() - self.last_adaptation_time
        echo_path_changed = time_since_adaptation > self.adaptation_timeout
        
        metrics = self.aec_metrics.to_dict()
        metrics.update({
            'filter_length': self.filter_length,
            'adaptation_enabled': self.adaptation_enabled,
            'mode': self.mode.value,
            'total_frames_processed': self.total_frames,
            'echo_path_change_detected': echo_path_changed,
            'time_since_last_adaptation': time_since_adaptation,
            'calibration_active': self.calibration_active
        })
        
        # Add filter-specific metrics
        filter_metrics = self.nlms_filter.get_filter_metrics()
        metrics.update({f'filter_{k}': v for k, v in filter_metrics.items()})
        
        return metrics
    
    def start_calibration(self) -> None:
        """Start room acoustic calibration."""
        self.set_mode(AECMode.CALIBRATION)
        logger.info("AEC calibration started")
    
    def stop_calibration(self) -> None:
        """Stop room acoustic calibration and return to normal operation."""
        self.set_mode(AECMode.FULL_DUPLEX)
        logger.info("AEC calibration completed")
    
    def get_room_impulse_response(self) -> Optional[np.ndarray]:
        """
        Get measured room impulse response.
        
        Returns:
            Room impulse response or None if not available
        """
        return self.room_impulse_response
    
    # Test helper method
    def _enable_test_reference(self, enabled: bool = True) -> None:
        """Enable synthetic reference signal for testing."""
        self._generate_test_reference = enabled
