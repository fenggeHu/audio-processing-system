"""
Beamforming Service for directional audio enhancement.

This module implements the BeamformerService with Delay-and-Sum (DAS) and
MVDR algorithms for classroom audio processing with SSL-based steering.
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
from scipy.linalg import inv, pinv

from ..interfaces import IAudioService, IMetricsCollector
from ..base import BaseAudioProcessor
from ..models import AudioFrame, AudioConfig, ProcessingResult, AudioMetrics
from ..exceptions import ProcessingError, ServiceError
from .ssl import MicrophonePosition, DirectionEstimate, ClassroomArea

logger = structlog.get_logger(__name__)


class BeamformingAlgorithm(Enum):
    """Beamforming algorithm types."""
    DAS = "delay_and_sum"
    MVDR = "mvdr"
    FROST = "frost"
    GSC = "generalized_sidelobe_canceller"


class BeamformingMode(Enum):
    """Beamforming operation modes."""
    FIXED = "fixed"          # Fixed beam direction
    ADAPTIVE = "adaptive"    # SSL-based adaptive steering
    TRACKING = "tracking"    # Continuous direction tracking


@dataclass
class BeamPattern:
    """Beamforming pattern configuration."""
    target_azimuth: float    # degrees
    target_elevation: float  # degrees
    beam_width: float        # degrees (3dB beamwidth)
    sidelobe_level: float    # dB (relative to main lobe)
    null_directions: List[Tuple[float, float]] = field(default_factory=list)  # (az, el) pairs
    
    def __post_init__(self):
        """Normalize angles after initialization."""
        # Normalize azimuth to [-180, 180]
        while self.target_azimuth > 180:
            self.target_azimuth -= 360
        while self.target_azimuth <= -180:
            self.target_azimuth += 360
        
        # Clamp elevation to [-90, 90]
        self.target_elevation = max(-90, min(90, self.target_elevation))


@dataclass
class BeamformingWeights:
    """Beamforming weight coefficients."""
    weights: np.ndarray      # Complex weights (channels, frequency_bins)
    frequency_bins: np.ndarray  # Frequency bin centers
    algorithm: BeamformingAlgorithm
    target_direction: Tuple[float, float]  # (azimuth, elevation)
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


class DelayAndSumBeamformer:
    """
    Delay-and-Sum (DAS) beamformer implementation.
    
    Classic beamforming algorithm that delays and sums signals
    from different microphones to enhance signals from target direction.
    """
    
    def __init__(self, microphone_positions: List[MicrophonePosition],
                 sample_rate: int, frame_size: int):
        self.microphone_positions = microphone_positions
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        
        # Speed of sound (m/s)
        self.sound_speed = 343.0
        
        # FFT parameters
        self.fft_size = 2 ** int(np.ceil(np.log2(frame_size)))
        self.frequency_bins = np.fft.fftfreq(self.fft_size, 1/sample_rate)[:self.fft_size//2 + 1]
        
        # Reference microphone (usually center or first)
        self.reference_mic = 0
        
        logger.info(
            "DAS beamformer initialized",
            microphones=len(microphone_positions),
            fft_size=self.fft_size,
            frequency_bins=len(self.frequency_bins)
        )
    
    def compute_weights(self, target_azimuth: float, target_elevation: float) -> BeamformingWeights:
        """
        Compute DAS beamforming weights for target direction.
        
        Args:
            target_azimuth: Target azimuth in degrees
            target_elevation: Target elevation in degrees
            
        Returns:
            BeamformingWeights object with computed coefficients
        """
        # Convert to radians
        az_rad = np.radians(target_azimuth)
        el_rad = np.radians(target_elevation)
        
        # Direction vector
        direction = np.array([
            np.cos(el_rad) * np.cos(az_rad),
            np.cos(el_rad) * np.sin(az_rad),
            np.sin(el_rad)
        ])
        
        # Compute delays relative to reference microphone
        ref_pos = np.array([
            self.microphone_positions[self.reference_mic].x,
            self.microphone_positions[self.reference_mic].y,
            self.microphone_positions[self.reference_mic].z
        ])
        
        delays = np.zeros(len(self.microphone_positions))
        
        for i, mic in enumerate(self.microphone_positions):
            mic_pos = np.array([mic.x, mic.y, mic.z])
            
            # Time delay relative to reference microphone
            relative_pos = mic_pos - ref_pos
            delay_distance = np.dot(relative_pos, direction)
            delays[i] = delay_distance / self.sound_speed
        
        # Convert delays to phase shifts for each frequency
        weights = np.zeros((len(self.microphone_positions), len(self.frequency_bins)), dtype=complex)
        
        for i, delay in enumerate(delays):
            for j, freq in enumerate(self.frequency_bins):
                if freq == 0:
                    weights[i, j] = 1.0
                else:
                    # Phase shift: e^(-j*2*pi*f*tau)
                    phase_shift = -2j * np.pi * freq * delay
                    weights[i, j] = np.exp(phase_shift)
        
        # Normalize weights (equal gain combining)
        weights = weights / len(self.microphone_positions)
        
        return BeamformingWeights(
            weights=weights,
            frequency_bins=self.frequency_bins,
            algorithm=BeamformingAlgorithm.DAS,
            target_direction=(target_azimuth, target_elevation),
            timestamp=datetime.now(),
            metadata={
                'delays_seconds': delays.tolist(),
                'reference_mic': self.reference_mic,
                'sound_speed': self.sound_speed
            }
        )
    
    def apply_beamforming(self, audio_frame: AudioFrame, weights: BeamformingWeights) -> AudioFrame:
        """
        Apply DAS beamforming to audio frame.
        
        Args:
            audio_frame: Input multi-channel audio frame
            weights: Precomputed beamforming weights
            
        Returns:
            Beamformed audio frame (single channel)
        """
        if audio_frame.channels != len(self.microphone_positions):
            raise ProcessingError(
                f"Audio frame has {audio_frame.channels} channels, "
                f"but {len(self.microphone_positions)} microphones configured"
            )
        
        # Apply FFT to each channel
        channel_ffts = []
        for ch in range(audio_frame.channels):
            # Zero-pad to FFT size
            padded_signal = np.zeros(self.fft_size)
            padded_signal[:audio_frame.frame_size] = audio_frame.data[ch, :]
            
            # Apply FFT
            fft_result = np.fft.fft(padded_signal)
            channel_ffts.append(fft_result[:len(self.frequency_bins)])
        
        channel_ffts = np.array(channel_ffts)
        
        # Apply beamforming weights
        beamformed_fft = np.zeros(len(self.frequency_bins), dtype=complex)
        
        for ch in range(audio_frame.channels):
            beamformed_fft += channel_ffts[ch] * weights.weights[ch, :]
        
        # Convert back to time domain
        # Reconstruct full FFT (including negative frequencies)
        full_fft = np.zeros(self.fft_size, dtype=complex)
        full_fft[:len(self.frequency_bins)] = beamformed_fft
        
        # Mirror for negative frequencies (excluding DC and Nyquist)
        if self.fft_size % 2 == 0:
            full_fft[len(self.frequency_bins):] = np.conj(beamformed_fft[1:-1][::-1])
        else:
            full_fft[len(self.frequency_bins):] = np.conj(beamformed_fft[1:][::-1])
        
        # IFFT
        time_domain = np.real(np.fft.ifft(full_fft))
        
        # Extract original frame size
        beamformed_data = time_domain[:audio_frame.frame_size]
        
        # Create output frame (single channel)
        output_frame = AudioFrame(
            timestamp=audio_frame.timestamp,
            sample_rate=audio_frame.sample_rate,
            channels=1,
            frame_size=audio_frame.frame_size,
            data=beamformed_data.reshape(1, -1),
            metadata=audio_frame.metadata.copy() if audio_frame.metadata else {}
        )
        
        # Add beamforming metadata
        output_frame.metadata.update({
            'beamforming_algorithm': weights.algorithm.value,
            'target_azimuth': weights.target_direction[0],
            'target_elevation': weights.target_direction[1],
            'beamforming_applied': True
        })
        
        return output_frame


class MVDRBeamformer:
    """
    Minimum Variance Distortionless Response (MVDR) beamformer.
    
    Adaptive beamforming algorithm that minimizes output power
    while maintaining unity gain in the target direction.
    """
    
    def __init__(self, microphone_positions: List[MicrophonePosition],
                 sample_rate: int, frame_size: int,
                 adaptation_rate: float = 0.01):
        self.microphone_positions = microphone_positions
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.adaptation_rate = adaptation_rate
        
        # Speed of sound
        self.sound_speed = 343.0
        
        # FFT parameters
        self.fft_size = 2 ** int(np.ceil(np.log2(frame_size)))
        self.frequency_bins = np.fft.fftfreq(self.fft_size, 1/sample_rate)[:self.fft_size//2 + 1]
        
        # Covariance matrix estimation
        self.covariance_matrices = None
        self.adaptation_count = 0
        
        # Regularization parameter
        self.regularization = 1e-6
        
        logger.info(
            "MVDR beamformer initialized",
            microphones=len(microphone_positions),
            adaptation_rate=adaptation_rate,
            regularization=self.regularization
        )
    
    def update_covariance(self, audio_frame: AudioFrame) -> None:
        """
        Update covariance matrix estimation with new audio frame.
        
        Args:
            audio_frame: Input multi-channel audio frame
        """
        # Apply FFT to each channel
        channel_ffts = []
        for ch in range(audio_frame.channels):
            padded_signal = np.zeros(self.fft_size)
            padded_signal[:audio_frame.frame_size] = audio_frame.data[ch, :]
            fft_result = np.fft.fft(padded_signal)
            channel_ffts.append(fft_result[:len(self.frequency_bins)])
        
        channel_ffts = np.array(channel_ffts)
        
        # Initialize covariance matrices if needed
        if self.covariance_matrices is None:
            self.covariance_matrices = np.zeros(
                (len(self.frequency_bins), audio_frame.channels, audio_frame.channels),
                dtype=complex
            )
        
        # Update covariance matrix for each frequency bin
        for f_idx in range(len(self.frequency_bins)):
            # Get frequency domain data for this bin
            x = channel_ffts[:, f_idx].reshape(-1, 1)  # Column vector
            
            # Instantaneous covariance matrix
            instant_cov = x @ x.conj().T
            
            # Exponential averaging
            if self.adaptation_count == 0:
                self.covariance_matrices[f_idx] = instant_cov
            else:
                alpha = self.adaptation_rate
                self.covariance_matrices[f_idx] = (
                    (1 - alpha) * self.covariance_matrices[f_idx] + alpha * instant_cov
                )
        
        self.adaptation_count += 1
    
    def compute_weights(self, target_azimuth: float, target_elevation: float) -> BeamformingWeights:
        """
        Compute MVDR beamforming weights for target direction.
        
        Args:
            target_azimuth: Target azimuth in degrees
            target_elevation: Target elevation in degrees
            
        Returns:
            BeamformingWeights object with computed coefficients
        """
        if self.covariance_matrices is None:
            raise ProcessingError("Covariance matrices not initialized. Call update_covariance first.")
        
        # Convert to radians
        az_rad = np.radians(target_azimuth)
        el_rad = np.radians(target_elevation)
        
        # Direction vector
        direction = np.array([
            np.cos(el_rad) * np.cos(az_rad),
            np.cos(el_rad) * np.sin(az_rad),
            np.sin(el_rad)
        ])
        
        # Compute steering vector for each frequency
        weights = np.zeros((len(self.microphone_positions), len(self.frequency_bins)), dtype=complex)
        
        for f_idx, freq in enumerate(self.frequency_bins):
            if freq == 0:
                # DC component - use equal weights
                weights[:, f_idx] = 1.0 / len(self.microphone_positions)
                continue
            
            # Compute steering vector
            steering_vector = np.zeros(len(self.microphone_positions), dtype=complex)
            
            for i, mic in enumerate(self.microphone_positions):
                mic_pos = np.array([mic.x, mic.y, mic.z])
                
                # Phase delay for plane wave from target direction
                delay_distance = np.dot(mic_pos, direction)
                delay_time = delay_distance / self.sound_speed
                
                # Steering vector element
                steering_vector[i] = np.exp(1j * 2 * np.pi * freq * delay_time)
            
            # Get covariance matrix for this frequency
            R = self.covariance_matrices[f_idx]
            
            # Add regularization
            R_reg = R + self.regularization * np.eye(len(self.microphone_positions))
            
            try:
                # MVDR weights: w = (R^-1 * a) / (a^H * R^-1 * a)
                R_inv = inv(R_reg)
                numerator = R_inv @ steering_vector
                denominator = steering_vector.conj().T @ numerator
                
                if abs(denominator) > 1e-12:
                    weights[:, f_idx] = numerator / denominator
                else:
                    # Fallback to DAS if denominator is too small
                    weights[:, f_idx] = steering_vector / len(self.microphone_positions)
                    
            except np.linalg.LinAlgError:
                # Fallback to DAS if matrix inversion fails
                weights[:, f_idx] = steering_vector / len(self.microphone_positions)
        
        return BeamformingWeights(
            weights=weights,
            frequency_bins=self.frequency_bins,
            algorithm=BeamformingAlgorithm.MVDR,
            target_direction=(target_azimuth, target_elevation),
            timestamp=datetime.now(),
            metadata={
                'adaptation_count': self.adaptation_count,
                'regularization': self.regularization,
                'covariance_condition_numbers': [
                    float(np.linalg.cond(self.covariance_matrices[i])) 
                    for i in range(min(5, len(self.frequency_bins)))  # First 5 bins
                ]
            }
        )
    
    def apply_beamforming(self, audio_frame: AudioFrame, weights: BeamformingWeights) -> AudioFrame:
        """
        Apply MVDR beamforming to audio frame.
        
        Args:
            audio_frame: Input multi-channel audio frame
            weights: Precomputed MVDR weights
            
        Returns:
            Beamformed audio frame (single channel)
        """
        # Update covariance matrix with current frame
        self.update_covariance(audio_frame)
        
        # Apply beamforming (same as DAS implementation)
        if audio_frame.channels != len(self.microphone_positions):
            raise ProcessingError(
                f"Audio frame has {audio_frame.channels} channels, "
                f"but {len(self.microphone_positions)} microphones configured"
            )
        
        # Apply FFT to each channel
        channel_ffts = []
        for ch in range(audio_frame.channels):
            padded_signal = np.zeros(self.fft_size)
            padded_signal[:audio_frame.frame_size] = audio_frame.data[ch, :]
            fft_result = np.fft.fft(padded_signal)
            channel_ffts.append(fft_result[:len(self.frequency_bins)])
        
        channel_ffts = np.array(channel_ffts)
        
        # Apply beamforming weights
        beamformed_fft = np.zeros(len(self.frequency_bins), dtype=complex)
        
        for ch in range(audio_frame.channels):
            beamformed_fft += channel_ffts[ch] * weights.weights[ch, :]
        
        # Convert back to time domain
        full_fft = np.zeros(self.fft_size, dtype=complex)
        full_fft[:len(self.frequency_bins)] = beamformed_fft
        
        # Mirror for negative frequencies
        if self.fft_size % 2 == 0:
            full_fft[len(self.frequency_bins):] = np.conj(beamformed_fft[1:-1][::-1])
        else:
            full_fft[len(self.frequency_bins):] = np.conj(beamformed_fft[1:][::-1])
        
        # IFFT
        time_domain = np.real(np.fft.ifft(full_fft))
        beamformed_data = time_domain[:audio_frame.frame_size]
        
        # Create output frame
        output_frame = AudioFrame(
            timestamp=audio_frame.timestamp,
            sample_rate=audio_frame.sample_rate,
            channels=1,
            frame_size=audio_frame.frame_size,
            data=beamformed_data.reshape(1, -1),
            metadata=audio_frame.metadata.copy() if audio_frame.metadata else {}
        )
        
        # Add beamforming metadata
        output_frame.metadata.update({
            'beamforming_algorithm': weights.algorithm.value,
            'target_azimuth': weights.target_direction[0],
            'target_elevation': weights.target_direction[1],
            'beamforming_applied': True,
            'mvdr_adaptation_count': self.adaptation_count
        })
        
        return output_frame
    
    def reset_adaptation(self) -> None:
        """Reset MVDR adaptation state."""
        self.covariance_matrices = None
        self.adaptation_count = 0
        logger.info("MVDR adaptation state reset")
