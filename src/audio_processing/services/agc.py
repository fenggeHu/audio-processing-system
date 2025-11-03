"""
Automatic Gain Control (AGC) Service for classroom audio processing.

This module implements the AGCService with intelligent source type identification,
anti-howling protection, and differentiated gain control strategies for teachers and students.
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


class SourceType(Enum):
    """Types of audio sources in classroom environment."""
    TEACHER = "teacher"          # Teacher/instructor voice
    STUDENT = "student"          # Student voice/questions
    AMBIENT = "ambient"          # Background noise/environment
    UNKNOWN = "unknown"          # Unclassified source


class AGCMode(Enum):
    """AGC operation modes."""
    CONSERVATIVE = "conservative"  # Gentle gain adjustments
    BALANCED = "balanced"         # Standard classroom operation
    AGGRESSIVE = "aggressive"     # Maximum level control
    BYPASS = "bypass"            # Pass-through mode


@dataclass
class AGCMetrics:
    """AGC performance metrics."""
    current_gain_db: float = 0.0           # Current applied gain in dB
    target_level_dbfs: float = -18.0       # Target output level
    actual_level_dbfs: float = -60.0       # Actual measured level
    gain_reduction_db: float = 0.0         # Applied gain reduction
    attack_time_ms: float = 20.0           # Current attack time
    release_time_ms: float = 400.0         # Current release time
    source_type: SourceType = SourceType.UNKNOWN  # Detected source type
    howling_detected: bool = False         # Howling detection status
    pumping_detected: bool = False         # Pumping effect detection
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            'current_gain_db': self.current_gain_db,
            'target_level_dbfs': self.target_level_dbfs,
            'actual_level_dbfs': self.actual_level_dbfs,
            'gain_reduction_db': self.gain_reduction_db,
            'attack_time_ms': self.attack_time_ms,
            'release_time_ms': self.release_time_ms,
            'source_type': self.source_type.value,
            'howling_detected': self.howling_detected,
            'pumping_detected': self.pumping_detected
        }


class SourceTypeIdentifier:
    """
    Intelligent source type identification for classroom environment.
    
    Identifies whether audio is from teacher, student, or ambient sources
    based on SSL direction information and audio characteristics.
    """
    
    def __init__(self, sample_rate: int = 48000):
        self.sample_rate = sample_rate
        
        # Classroom layout configuration
        self.teacher_area_angles = (-30, 30)  # degrees from center
        self.student_area_angles = (45, 135)  # degrees for student seating
        
        # Audio feature analysis
        self.energy_history = deque(maxlen=20)
        self.spectral_features_history = deque(maxlen=10)
        
        # Source classification thresholds
        self.teacher_energy_threshold = -25.0  # dBFS
        self.student_energy_threshold = -35.0  # dBFS
        self.ambient_energy_threshold = -45.0  # dBFS
        
        # Temporal analysis
        self.source_stability_frames = 5
        self.current_source = SourceType.UNKNOWN
        self.source_confidence = 0.0
        
        logger.info("Source type identifier initialized")
    
    def identify_source(self, frame: AudioFrame) -> Tuple[SourceType, float]:
        """
        Identify the type of audio source.
        
        Args:
            frame: Input audio frame with SSL metadata
            
        Returns:
            Tuple of (source_type, confidence_score)
        """
        # Extract SSL direction information
        ssl_direction = frame.metadata.get('ssl_direction', 0)
        ssl_confidence = frame.metadata.get('ssl_confidence', 0.0)
        
        # Calculate audio features
        signal_data = frame.data[0, :] if frame.channels > 0 else np.zeros(frame.frame_size)
        energy_db = self._calculate_energy_db(signal_data)
        spectral_centroid = self._calculate_spectral_centroid(signal_data)
        
        # Store features for temporal analysis
        self.energy_history.append(energy_db)
        self.spectral_features_history.append(spectral_centroid)
        
        # Direction-based classification
        direction_score = self._classify_by_direction(ssl_direction, ssl_confidence)
        
        # Energy-based classification
        energy_score = self._classify_by_energy(energy_db)
        
        # Spectral-based classification
        spectral_score = self._classify_by_spectral_features(spectral_centroid)
        
        # Combine classification scores
        combined_scores = self._combine_classification_scores(
            direction_score, energy_score, spectral_score
        )
        
        # Determine source type and confidence
        source_type = max(combined_scores.keys(), key=lambda k: combined_scores[k])
        confidence = combined_scores[source_type]
        
        # Apply temporal smoothing
        source_type, confidence = self._apply_temporal_smoothing(source_type, confidence)
        
        return source_type, confidence
    
    def _classify_by_direction(self, ssl_direction: float, 
                             ssl_confidence: float) -> Dict[SourceType, float]:
        """Classify source based on SSL direction information."""
        scores = {
            SourceType.TEACHER: 0.0,
            SourceType.STUDENT: 0.0,
            SourceType.AMBIENT: 0.0,
            SourceType.UNKNOWN: 0.0
        }
        
        if ssl_confidence < 0.3:
            scores[SourceType.AMBIENT] = 0.7
            scores[SourceType.UNKNOWN] = 0.3
            return scores
        
        # Teacher area detection
        if self.teacher_area_angles[0] <= ssl_direction <= self.teacher_area_angles[1]:
            scores[SourceType.TEACHER] = ssl_confidence * 0.8
        
        # Student area detection
        elif (self.student_area_angles[0] <= ssl_direction <= self.student_area_angles[1] or
              -self.student_area_angles[1] <= ssl_direction <= -self.student_area_angles[0]):
            scores[SourceType.STUDENT] = ssl_confidence * 0.6
        
        # Other directions - likely ambient
        else:
            scores[SourceType.AMBIENT] = ssl_confidence * 0.4
            scores[SourceType.UNKNOWN] = 0.3
        
        return scores
    
    def _classify_by_energy(self, energy_db: float) -> Dict[SourceType, float]:
        """Classify source based on energy level."""
        scores = {
            SourceType.TEACHER: 0.0,
            SourceType.STUDENT: 0.0,
            SourceType.AMBIENT: 0.0,
            SourceType.UNKNOWN: 0.0
        }
        
        if energy_db > self.teacher_energy_threshold:
            # High energy - likely teacher
            scores[SourceType.TEACHER] = 0.7
            scores[SourceType.STUDENT] = 0.2
        elif energy_db > self.student_energy_threshold:
            # Medium energy - could be student or distant teacher
            scores[SourceType.STUDENT] = 0.5
            scores[SourceType.TEACHER] = 0.3
        elif energy_db > self.ambient_energy_threshold:
            # Low energy - likely ambient or distant speech
            scores[SourceType.AMBIENT] = 0.6
            scores[SourceType.STUDENT] = 0.2
        else:
            # Very low energy - ambient noise
            scores[SourceType.AMBIENT] = 0.8
        
        return scores
    
    def _classify_by_spectral_features(self, spectral_centroid: float) -> Dict[SourceType, float]:
        """Classify source based on spectral characteristics."""
        scores = {
            SourceType.TEACHER: 0.0,
            SourceType.STUDENT: 0.0,
            SourceType.AMBIENT: 0.0,
            SourceType.UNKNOWN: 0.0
        }
        
        # Speech typically has spectral centroid in 1-4 kHz range
        if 1000 <= spectral_centroid <= 4000:
            # Speech-like spectrum
            scores[SourceType.TEACHER] = 0.4
            scores[SourceType.STUDENT] = 0.4
        elif spectral_centroid < 1000:
            # Low-frequency content - likely ambient noise
            scores[SourceType.AMBIENT] = 0.6
        else:
            # High-frequency content - could be noise or distant speech
            scores[SourceType.AMBIENT] = 0.5
            scores[SourceType.UNKNOWN] = 0.3
        
        return scores
    
    def _combine_classification_scores(self, direction_scores: Dict[SourceType, float],
                                     energy_scores: Dict[SourceType, float],
                                     spectral_scores: Dict[SourceType, float]) -> Dict[SourceType, float]:
        """Combine multiple classification scores."""
        combined_scores = {source_type: 0.0 for source_type in SourceType}
        
        # Weighted combination
        direction_weight = 0.5  # SSL direction is most reliable
        energy_weight = 0.3
        spectral_weight = 0.2
        
        for source_type in SourceType:
            combined_scores[source_type] = (
                direction_weight * direction_scores[source_type] +
                energy_weight * energy_scores[source_type] +
                spectral_weight * spectral_scores[source_type]
            )
        
        return combined_scores
    
    def _apply_temporal_smoothing(self, source_type: SourceType, 
                                confidence: float) -> Tuple[SourceType, float]:
        """Apply temporal smoothing to reduce classification jitter."""
        # Simple hysteresis - require higher confidence to change source type
        if source_type != self.current_source:
            if confidence > 0.7:  # High confidence required for change
                self.current_source = source_type
                self.source_confidence = confidence
            else:
                # Keep current source but update confidence
                source_type = self.current_source
                self.source_confidence = 0.9 * self.source_confidence + 0.1 * confidence
        else:
            # Same source type - update confidence
            self.source_confidence = 0.8 * self.source_confidence + 0.2 * confidence
        
        return source_type, self.source_confidence
    
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
        freqs = np.fft.fftfreq(len(signal), 1/self.sample_rate)[:len(fft)//2]
        
        if np.sum(magnitude) == 0:
            return 0.0
        
        centroid = np.sum(freqs * magnitude) / np.sum(magnitude)
        return centroid
    
    def reset(self) -> None:
        """Reset identifier state."""
        self.energy_history.clear()
        self.spectral_features_history.clear()
        self.current_source = SourceType.UNKNOWN
        self.source_confidence = 0.0


class HowlingProtection:
    """
    Anti-howling protection mechanism.
    
    Detects potential howling/feedback conditions and applies
    protective gain reduction to prevent acoustic feedback.
    """
    
    def __init__(self, sample_rate: int = 48000, frame_size: int = 480):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        
        # FFT parameters for frequency analysis
        self.fft_size = 2 ** int(np.ceil(np.log2(frame_size)))
        
        # Howling detection parameters
        self.howling_threshold_db = -10.0  # dBFS threshold for howling detection
        self.frequency_stability_frames = 10  # Frames to confirm stable frequency
        self.howling_frequencies = []  # List of detected howling frequencies
        
        # Spectral analysis
        self.magnitude_history = deque(maxlen=20)
        self.peak_frequencies = deque(maxlen=self.frequency_stability_frames)
        
        # Protection state
        self.howling_detected = False
        self.protection_gain_db = 0.0
        self.recovery_rate = 0.95  # Rate of gain recovery after howling stops
        
        # Frequency bands for analysis (Hz)
        self.analysis_bands = [
            (200, 500),    # Low frequencies
            (500, 1000),   # Low-mid frequencies
            (1000, 2000),  # Mid frequencies
            (2000, 4000),  # High-mid frequencies
            (4000, 8000),  # High frequencies
        ]
        
        logger.info("Howling protection initialized")
    
    def detect_and_protect(self, signal: np.ndarray, 
                          current_gain_db: float) -> Tuple[bool, float]:
        """
        Detect howling and apply protective gain reduction.
        
        Args:
            signal: Input audio signal
            current_gain_db: Current AGC gain
            
        Returns:
            Tuple of (howling_detected, protective_gain_db)
        """
        # Perform spectral analysis
        magnitude_spectrum = self._analyze_spectrum(signal)
        
        # Detect potential howling frequencies
        howling_detected = self._detect_howling_frequencies(magnitude_spectrum)
        
        # Update protection state
        if howling_detected:
            self.howling_detected = True
            # Apply immediate gain reduction
            self.protection_gain_db = min(self.protection_gain_db - 6.0, -20.0)
            logger.warning("Howling detected - applying protection gain", 
                         gain_reduction=abs(self.protection_gain_db))
        else:
            # Gradually recover gain if no howling
            if self.howling_detected:
                self.protection_gain_db *= self.recovery_rate
                if abs(self.protection_gain_db) < 0.5:
                    self.protection_gain_db = 0.0
                    self.howling_detected = False
                    logger.info("Howling protection recovery complete")
        
        return self.howling_detected, self.protection_gain_db
    
    def _analyze_spectrum(self, signal: np.ndarray) -> np.ndarray:
        """Analyze frequency spectrum of the signal."""
        # Apply window and FFT
        windowed_signal = signal * np.hanning(len(signal))
        
        # Pad to FFT size
        padded_signal = np.zeros(self.fft_size)
        padded_signal[:len(windowed_signal)] = windowed_signal
        
        # FFT and magnitude spectrum
        fft = np.fft.fft(padded_signal)
        magnitude_spectrum = np.abs(fft[:self.fft_size//2])
        
        # Store for temporal analysis
        self.magnitude_history.append(magnitude_spectrum)
        
        return magnitude_spectrum
    
    def _detect_howling_frequencies(self, magnitude_spectrum: np.ndarray) -> bool:
        """Detect howling based on spectral characteristics."""
        # Find spectral peaks
        peaks = self._find_spectral_peaks(magnitude_spectrum)
        
        # Check for sustained high-energy peaks
        howling_detected = False
        
        for peak_freq, peak_magnitude in peaks:
            # Convert magnitude to dB
            if peak_magnitude > 0:
                peak_db = 20 * np.log10(peak_magnitude)
                
                # Check if peak exceeds howling threshold
                if peak_db > self.howling_threshold_db:
                    # Check temporal stability
                    if self._is_frequency_stable(peak_freq):
                        howling_detected = True
                        if peak_freq not in self.howling_frequencies:
                            self.howling_frequencies.append(peak_freq)
                            logger.warning("Howling frequency detected", 
                                         frequency=peak_freq, magnitude_db=peak_db)
        
        # Clean up old howling frequencies
        self._cleanup_howling_frequencies(magnitude_spectrum)
        
        return howling_detected
    
    def _find_spectral_peaks(self, magnitude_spectrum: np.ndarray) -> List[Tuple[float, float]]:
        """Find prominent spectral peaks."""
        # Simple peak detection
        peaks = []
        
        # Find local maxima
        for i in range(2, len(magnitude_spectrum) - 2):
            if (magnitude_spectrum[i] > magnitude_spectrum[i-1] and
                magnitude_spectrum[i] > magnitude_spectrum[i+1] and
                magnitude_spectrum[i] > magnitude_spectrum[i-2] and
                magnitude_spectrum[i] > magnitude_spectrum[i+2]):
                
                # Convert bin to frequency
                frequency = (i * self.sample_rate) / (2 * len(magnitude_spectrum))
                magnitude = magnitude_spectrum[i]
                
                # Only consider peaks in relevant frequency range
                if 200 <= frequency <= 8000:
                    peaks.append((frequency, magnitude))
        
        # Sort by magnitude and return top peaks
        peaks.sort(key=lambda x: x[1], reverse=True)
        return peaks[:5]  # Top 5 peaks
    
    def _is_frequency_stable(self, frequency: float) -> bool:
        """Check if a frequency has been stable over multiple frames."""
        self.peak_frequencies.append(frequency)
        
        if len(self.peak_frequencies) < self.frequency_stability_frames:
            return False
        
        # Check if frequency appears consistently
        frequency_tolerance = 50.0  # Hz
        stable_count = 0
        
        for freq in self.peak_frequencies:
            if abs(freq - frequency) < frequency_tolerance:
                stable_count += 1
        
        stability_ratio = stable_count / len(self.peak_frequencies)
        return stability_ratio > 0.7  # 70% stability required
    
    def _cleanup_howling_frequencies(self, magnitude_spectrum: np.ndarray) -> None:
        """Remove howling frequencies that are no longer present."""
        active_frequencies = []
        
        for freq in self.howling_frequencies:
            # Convert frequency to bin
            bin_index = int((freq * 2 * len(magnitude_spectrum)) / self.sample_rate)
            
            if bin_index < len(magnitude_spectrum):
                magnitude_db = 20 * np.log10(magnitude_spectrum[bin_index] + 1e-10)
                
                # Keep frequency if still above threshold
                if magnitude_db > self.howling_threshold_db - 6.0:  # 6dB hysteresis
                    active_frequencies.append(freq)
        
        self.howling_frequencies = active_frequencies
    
    def reset(self) -> None:
        """Reset howling protection state."""
        self.magnitude_history.clear()
        self.peak_frequencies.clear()
        self.howling_frequencies.clear()
        self.howling_detected = False
        self.protection_gain_db = 0.0


class GainController:
    """
    Intelligent gain control with smooth adjustments and pumping prevention.
    
    Implements attack/release timing, soft limiting, and anti-pumping measures.
    """
    
    def __init__(self, sample_rate: int = 48000, frame_size: int = 480):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        
        # Target levels for different source types
        self.target_levels = {
            SourceType.TEACHER: -15.0,    # Higher level for teacher
            SourceType.STUDENT: -21.0,    # Lower level for students
            SourceType.AMBIENT: -30.0,    # Much lower for ambient
            SourceType.UNKNOWN: -18.0     # Default level
        }
        
        # Gain control parameters
        self.max_gain_db = 20.0
        self.min_gain_db = -40.0
        self.attack_time_ms = 20.0
        self.release_time_ms = 400.0
        
        # Current state
        self.current_gain_db = 0.0
        self.target_gain_db = 0.0
        self.envelope_follower = 0.0
        
        # Attack/release coefficients
        self.attack_coeff = self._calculate_time_constant(self.attack_time_ms)
        self.release_coeff = self._calculate_time_constant(self.release_time_ms)
        
        # Soft limiting
        self.limiter_threshold_db = -3.0
        self.limiter_ratio = 10.0  # 10:1 compression above threshold
        
        # Anti-pumping
        self.level_history = deque(maxlen=50)
        self.gain_change_history = deque(maxlen=20)
        self.pumping_threshold = 3.0  # dB variation threshold
        
        logger.info("Gain controller initialized")
    
    def process_gain_control(self, signal: np.ndarray, 
                           source_type: SourceType,
                           protection_gain_db: float = 0.0) -> Tuple[np.ndarray, float]:
        """
        Apply intelligent gain control to the signal.
        
        Args:
            signal: Input audio signal
            source_type: Detected source type
            protection_gain_db: Additional protective gain reduction
            
        Returns:
            Tuple of (processed_signal, applied_gain_db)
        """
        # Calculate input level
        input_level_db = self._calculate_level_db(signal)
        
        # Get target level for source type
        target_level_db = self.target_levels[source_type]
        
        # Calculate required gain
        required_gain_db = target_level_db - input_level_db
        
        # Apply gain limits
        required_gain_db = np.clip(required_gain_db, self.min_gain_db, self.max_gain_db)
        
        # Add protection gain
        total_required_gain_db = required_gain_db + protection_gain_db
        
        # Smooth gain changes with attack/release
        self.target_gain_db = total_required_gain_db
        self.current_gain_db = self._apply_attack_release(
            self.current_gain_db, self.target_gain_db, input_level_db
        )
        
        # Apply anti-pumping measures
        self.current_gain_db = self._apply_anti_pumping(self.current_gain_db)
        
        # Apply gain to signal
        gain_linear = 10 ** (self.current_gain_db / 20.0)
        processed_signal = signal * gain_linear
        
        # Apply soft limiting
        processed_signal = self._apply_soft_limiting(processed_signal)
        
        # Update history for pumping detection
        output_level_db = self._calculate_level_db(processed_signal)
        self.level_history.append(output_level_db)
        self.gain_change_history.append(abs(self.current_gain_db - self.target_gain_db))
        
        return processed_signal, self.current_gain_db
    
    def _calculate_level_db(self, signal: np.ndarray) -> float:
        """Calculate RMS level of signal in dB."""
        if len(signal) == 0:
            return -80.0
        
        rms = np.sqrt(np.mean(signal ** 2))
        if rms <= 0:
            return -80.0
        
        return 20 * np.log10(rms)
    
    def _calculate_time_constant(self, time_ms: float) -> float:
        """Calculate time constant coefficient for attack/release."""
        if time_ms <= 0:
            return 1.0
        
        # Convert to samples
        time_samples = (time_ms / 1000.0) * self.sample_rate
        
        # Calculate coefficient for exponential decay
        return 1.0 - np.exp(-1.0 / time_samples)
    
    def _apply_attack_release(self, current_gain: float, 
                            target_gain: float, input_level: float) -> float:
        """Apply attack/release timing to gain changes."""
        gain_difference = target_gain - current_gain
        
        if gain_difference < 0:
            # Gain reduction (attack) - faster response
            coeff = self.attack_coeff
        else:
            # Gain increase (release) - slower response
            coeff = self.release_coeff
        
        # Apply time constant
        new_gain = current_gain + coeff * gain_difference
        
        return new_gain
    
    def _apply_anti_pumping(self, gain_db: float) -> float:
        """Apply anti-pumping measures to prevent rapid gain changes."""
        if len(self.gain_change_history) < 10:
            return gain_db
        
        # Calculate recent gain change variance
        recent_changes = list(self.gain_change_history)[-10:]
        change_variance = np.var(recent_changes)
        
        # If variance is high, slow down gain changes
        if change_variance > self.pumping_threshold:
            # Reduce gain change rate
            smoothing_factor = 0.3
            smoothed_gain = (
                smoothing_factor * gain_db + 
                (1 - smoothing_factor) * self.current_gain_db
            )
            return smoothed_gain
        
        return gain_db
    
    def _apply_soft_limiting(self, signal: np.ndarray) -> np.ndarray:
        """Apply soft limiting to prevent clipping."""
        # Calculate signal level
        signal_level_db = self._calculate_level_db(signal)
        
        if signal_level_db > self.limiter_threshold_db:
            # Apply compression above threshold
            excess_db = signal_level_db - self.limiter_threshold_db
            compressed_excess_db = excess_db / self.limiter_ratio
            
            # Calculate limiter gain
            limiter_gain_db = compressed_excess_db - excess_db
            limiter_gain_linear = 10 ** (limiter_gain_db / 20.0)
            
            # Apply limiting with soft knee
            limited_signal = signal * limiter_gain_linear
            
            return limited_signal
        
        return signal
    
    def set_attack_time(self, attack_time_ms: float) -> None:
        """Set attack time in milliseconds."""
        self.attack_time_ms = np.clip(attack_time_ms, 10.0, 50.0)
        self.attack_coeff = self._calculate_time_constant(self.attack_time_ms)
        logger.debug("Attack time updated", attack_time_ms=self.attack_time_ms)
    
    def set_release_time(self, release_time_ms: float) -> None:
        """Set release time in milliseconds."""
        self.release_time_ms = np.clip(release_time_ms, 200.0, 1000.0)
        self.release_coeff = self._calculate_time_constant(self.release_time_ms)
        logger.debug("Release time updated", release_time_ms=self.release_time_ms)
    
    def set_target_level(self, source_type: SourceType, level_db: float) -> None:
        """Set target level for specific source type."""
        self.target_levels[source_type] = np.clip(level_db, -30.0, -6.0)
        logger.debug("Target level updated", 
                    source_type=source_type.value, level_db=level_db)
    
    def is_pumping_detected(self) -> bool:
        """Check if pumping effect is detected."""
        if len(self.level_history) < 20:
            return False
        
        # Analyze level stability
        recent_levels = list(self.level_history)[-20:]
        level_variance = np.var(recent_levels)
        
        return bool(level_variance > self.pumping_threshold)
    
    def reset(self) -> None:
        """Reset gain controller state."""
        self.current_gain_db = 0.0
        self.target_gain_db = 0.0
        self.envelope_follower = 0.0
        self.level_history.clear()
        self.gain_change_history.clear()


class AGCService(BaseAudioProcessor):
    """
    Automatic Gain Control Service for classroom audio processing.
    
    Provides intelligent level management with source type identification,
    anti-howling protection, and differentiated gain control strategies.
    """
    
    def __init__(self, service_name: str, config: AudioConfig,
                 mode: AGCMode = AGCMode.BALANCED,
                 metrics_collector: Optional[IMetricsCollector] = None):
        super().__init__(service_name, config, metrics_collector)
        
        self.mode = mode
        
        # AGC components
        self.source_identifier = SourceTypeIdentifier(config.sample_rate)
        self.howling_protection = HowlingProtection(config.sample_rate, config.frame_size)
        self.gain_controller = GainController(config.sample_rate, config.frame_size)
        
        # Performance metrics
        self.agc_metrics = AGCMetrics()
        
        # Processing statistics
        self.frames_processed = 0
        self.teacher_frames = 0
        self.student_frames = 0
        self.ambient_frames = 0
        
        # Configuration
        self._configure_for_mode(mode)
        
        logger.info(
            "AGC Service initialized",
            service=service_name,
            mode=mode.value
        )
    
    async def _initialize(self) -> None:
        """Initialize AGC service."""
        logger.info("Initializing AGC service", service=self.service_name)
        
        # Reset all components
        self.source_identifier.reset()
        self.howling_protection.reset()
        self.gain_controller.reset()
        
        # Reset metrics
        self.agc_metrics = AGCMetrics()
        
        # Reset statistics
        self.frames_processed = 0
        self.teacher_frames = 0
        self.student_frames = 0
        self.ambient_frames = 0
    
    async def _cleanup(self) -> None:
        """Cleanup AGC service."""
        logger.info("AGC service cleaned up")
    
    async def _process_frame(self, frame: AudioFrame) -> AudioFrame:
        """
        Process audio frame with automatic gain control.
        
        Args:
            frame: Input audio frame
            
        Returns:
            AGC-processed audio frame
        """
        if frame.channels != 1:
            raise ProcessingError("AGC service expects single-channel input")
        
        # Get input signal
        input_signal = frame.data[0, :]
        
        # Process based on current mode
        if self.mode == AGCMode.BYPASS:
            return frame
        else:
            return await self._process_agc(frame, input_signal)
    
    async def _process_agc(self, frame: AudioFrame, 
                          input_signal: np.ndarray) -> AudioFrame:
        """
        Perform AGC processing.
        
        Args:
            frame: Original audio frame
            input_signal: Input audio signal
            
        Returns:
            AGC-processed audio frame
        """
        self.frames_processed += 1
        
        # Step 1: Identify source type
        source_type, source_confidence = self.source_identifier.identify_source(frame)
        
        # Update statistics
        if source_type == SourceType.TEACHER:
            self.teacher_frames += 1
        elif source_type == SourceType.STUDENT:
            self.student_frames += 1
        elif source_type == SourceType.AMBIENT:
            self.ambient_frames += 1
        
        # Step 2: Howling protection
        howling_detected, protection_gain_db = self.howling_protection.detect_and_protect(
            input_signal, self.gain_controller.current_gain_db
        )
        
        # Step 3: Apply gain control
        processed_signal, applied_gain_db = self.gain_controller.process_gain_control(
            input_signal, source_type, protection_gain_db
        )
        
        # Step 4: Update metrics
        self._update_agc_metrics(
            input_signal, processed_signal, source_type, 
            applied_gain_db, protection_gain_db, howling_detected
        )
        
        # Create output frame
        output_frame = AudioFrame(
            timestamp=frame.timestamp,
            sample_rate=frame.sample_rate,
            channels=1,
            frame_size=frame.frame_size,
            data=processed_signal.reshape(1, -1),
            metadata=frame.metadata.copy() if frame.metadata else {}
        )
        
        # Add AGC metadata
        output_frame.metadata.update({
            'agc_applied': True,
            'agc_mode': self.mode.value,
            'source_type': source_type.value,
            'source_confidence': source_confidence,
            'applied_gain_db': applied_gain_db,
            'protection_gain_db': protection_gain_db,
            'howling_detected': howling_detected,
            'pumping_detected': self.gain_controller.is_pumping_detected(),
            'target_level_dbfs': self.gain_controller.target_levels[source_type]
        })
        
        return output_frame
    
    def _configure_for_mode(self, mode: AGCMode) -> None:
        """Configure AGC parameters based on operation mode."""
        if mode == AGCMode.CONSERVATIVE:
            # Gentle adjustments
            self.gain_controller.set_attack_time(30.0)
            self.gain_controller.set_release_time(600.0)
            self.gain_controller.max_gain_db = 15.0
            
        elif mode == AGCMode.AGGRESSIVE:
            # Fast, strong adjustments
            self.gain_controller.set_attack_time(15.0)
            self.gain_controller.set_release_time(300.0)
            self.gain_controller.max_gain_db = 25.0
            
        else:  # BALANCED mode
            # Standard classroom settings
            self.gain_controller.set_attack_time(20.0)
            self.gain_controller.set_release_time(400.0)
            self.gain_controller.max_gain_db = 20.0
    
    def _update_agc_metrics(self, input_signal: np.ndarray,
                           output_signal: np.ndarray,
                           source_type: SourceType,
                           applied_gain_db: float,
                           protection_gain_db: float,
                           howling_detected: bool) -> None:
        """Update AGC performance metrics."""
        # Calculate levels
        input_level = self._calculate_level_db(input_signal)
        output_level = self._calculate_level_db(output_signal)
        
        # Update metrics
        self.agc_metrics.current_gain_db = applied_gain_db
        self.agc_metrics.target_level_dbfs = self.gain_controller.target_levels[source_type]
        self.agc_metrics.actual_level_dbfs = output_level
        self.agc_metrics.gain_reduction_db = abs(min(0, protection_gain_db))
        self.agc_metrics.attack_time_ms = self.gain_controller.attack_time_ms
        self.agc_metrics.release_time_ms = self.gain_controller.release_time_ms
        self.agc_metrics.source_type = source_type
        self.agc_metrics.howling_detected = howling_detected
        self.agc_metrics.pumping_detected = self.gain_controller.is_pumping_detected()
    
    def _calculate_level_db(self, signal: np.ndarray) -> float:
        """Calculate RMS level of signal in dB."""
        if len(signal) == 0:
            return -80.0
        
        rms = np.sqrt(np.mean(signal ** 2))
        if rms <= 0:
            return -80.0
        
        return 20 * np.log10(rms)
    
    def set_mode(self, mode: AGCMode) -> None:
        """
        Set AGC operation mode.
        
        Args:
            mode: AGC operation mode
        """
        old_mode = self.mode
        self.mode = mode
        
        # Reconfigure for new mode
        self._configure_for_mode(mode)
        
        logger.info("AGC mode changed", old_mode=old_mode.value, new_mode=mode.value)
    
    def set_target_levels(self, teacher_level: float = -15.0,
                         student_level: float = -21.0,
                         ambient_level: float = -30.0) -> None:
        """
        Set target levels for different source types.
        
        Args:
            teacher_level: Target level for teacher voice in dBFS
            student_level: Target level for student voice in dBFS
            ambient_level: Target level for ambient sound in dBFS
        """
        self.gain_controller.set_target_level(SourceType.TEACHER, teacher_level)
        self.gain_controller.set_target_level(SourceType.STUDENT, student_level)
        self.gain_controller.set_target_level(SourceType.AMBIENT, ambient_level)
        
        logger.info("Target levels updated",
                   teacher=teacher_level, student=student_level, ambient=ambient_level)
    
    def set_attack_release_times(self, attack_ms: float, release_ms: float) -> None:
        """
        Set attack and release times.
        
        Args:
            attack_ms: Attack time in milliseconds (10-50ms)
            release_ms: Release time in milliseconds (200-1000ms)
        """
        self.gain_controller.set_attack_time(attack_ms)
        self.gain_controller.set_release_time(release_ms)
        
        logger.info("Attack/release times updated",
                   attack_ms=attack_ms, release_ms=release_ms)
    
    def reset_adaptation(self) -> None:
        """Reset AGC adaptation state."""
        self.source_identifier.reset()
        self.howling_protection.reset()
        self.gain_controller.reset()
        
        # Reset metrics and counters
        self.agc_metrics = AGCMetrics()
        self.frames_processed = 0
        self.teacher_frames = 0
        self.student_frames = 0
        
        logger.info("AGC adaptation state reset")
    
    def get_agc_metrics(self) -> Dict[str, Any]:
        """
        Get AGC-specific metrics.
        
        Returns:
            Dictionary with AGC performance metrics
        """
        metrics = self.agc_metrics.to_dict()
        
        # Add processing statistics
        total_frames = max(1, self.frames_processed)
        teacher_ratio = self.teacher_frames / total_frames
        student_ratio = self.student_frames / total_frames
        ambient_ratio = self.ambient_frames / total_frames
        
        metrics.update({
            'mode': self.mode.value,
            'frames_processed': self.frames_processed,
            'teacher_frame_ratio': teacher_ratio,
            'student_frame_ratio': student_ratio,
            'ambient_frame_ratio': ambient_ratio,
            'howling_frequencies_count': len(self.howling_protection.howling_frequencies),
            'max_gain_db': self.gain_controller.max_gain_db,
            'min_gain_db': self.gain_controller.min_gain_db
        })
        
        return metrics
    
    def get_config_schema(self) -> Dict[str, Any]:
        """Get configuration schema for AGC service."""
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": [mode.value for mode in AGCMode],
                    "description": "AGC operation mode"
                },
                "teacher_level_dbfs": {
                    "type": "number",
                    "minimum": -30.0,
                    "maximum": -6.0,
                    "description": "Target level for teacher voice in dBFS"
                },
                "student_level_dbfs": {
                    "type": "number",
                    "minimum": -30.0,
                    "maximum": -6.0,
                    "description": "Target level for student voice in dBFS"
                },
                "attack_time_ms": {
                    "type": "number",
                    "minimum": 10.0,
                    "maximum": 50.0,
                    "description": "Attack time in milliseconds"
                },
                "release_time_ms": {
                    "type": "number",
                    "minimum": 200.0,
                    "maximum": 1000.0,
                    "description": "Release time in milliseconds"
                }
            },
            "required": ["mode"]
        }