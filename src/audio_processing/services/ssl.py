# SSL Service Implementation
"""
Sound Source Localization (SSL) Service for real-time direction estimation.

This module implements the SSLService using SRP-PHAT algorithm for
classroom audio processing with direction tracking and area recognition.
"""

import time
import math
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from enum import Enum
import numpy as np
import structlog
from scipy.fft import fft, ifft

from ..interfaces import IMetricsCollector
from ..base import BaseAudioProcessor
from ..models import AudioFrame, AudioConfig
from ..exceptions import ProcessingError, ServiceError

logger = structlog.get_logger(__name__)


class ClassroomArea(Enum):
    """Classroom area classifications."""
    TEACHER_AREA = "teacher_area"
    STUDENT_AREA = "student_area"
    AMBIENT = "ambient"
    UNKNOWN = "unknown"


@dataclass
class MicrophonePosition:
    """3D position of a microphone in the array."""
    x: float  # meters
    y: float  # meters
    z: float  # meters
    channel: int  # audio channel number
    
    def distance_to(self, other: 'MicrophonePosition') -> float:
        """Calculate Euclidean distance to another microphone."""
        return math.sqrt(
            (self.x - other.x) ** 2 + 
            (self.y - other.y) ** 2 + 
            (self.z - other.z) ** 2
        )


@dataclass
class DirectionEstimate:
    """Sound source direction estimation result."""
    azimuth: float  # degrees, 0 = front, positive = clockwise
    elevation: float  # degrees, 0 = horizontal, positive = up
    confidence: float  # 0.0 to 1.0
    timestamp: datetime
    area: ClassroomArea
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Normalize angles after initialization."""
        # Normalize azimuth to [-180, 180]
        while self.azimuth > 180:
            self.azimuth -= 360
        while self.azimuth <= -180:
            self.azimuth += 360
        
        # Clamp elevation to [-90, 90]
        self.elevation = max(-90, min(90, self.elevation))
        
        # Clamp confidence to [0, 1]
        self.confidence = max(0.0, min(1.0, self.confidence))


@dataclass
class ClassroomGeometry:
    """Classroom geometry configuration for area recognition."""
    length: float  # meters
    width: float  # meters
    height: float  # meters
    teacher_area_bounds: Tuple[float, float, float, float]  # x_min, x_max, y_min, y_max
    microphone_array_position: Tuple[float, float, float]  # x, y, z in room coordinates
    
    def classify_direction(self, azimuth: float, elevation: float) -> ClassroomArea:
        """Classify direction into classroom areas."""
        # Convert azimuth to room coordinates
        # Assume 0° azimuth points to front of classroom (teacher area)
        
        # Teacher area is typically in front (azimuth around 0°)
        if -45 <= azimuth <= 45:
            return ClassroomArea.TEACHER_AREA
        
        # Student area is typically behind and to sides
        elif abs(azimuth) > 45 and abs(azimuth) < 135:
            return ClassroomArea.STUDENT_AREA
        
        # Back of room or very high/low elevation
        elif abs(elevation) > 30:
            return ClassroomArea.AMBIENT
        
        else:
            return ClassroomArea.STUDENT_AREA


class SRPPHATProcessor:
    """
    Steered Response Power with Phase Transform (SRP-PHAT) processor.
    
    Implements the core SRP-PHAT algorithm for sound source localization
    using cross-correlation with phase transform weighting.
    """
    
    def __init__(self, microphone_positions: List[MicrophonePosition],
                 sample_rate: int, frame_size: int,
                 search_resolution: float = 5.0):
        self.microphone_positions = microphone_positions
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.search_resolution = search_resolution  # degrees
        
        # Speed of sound (m/s)
        self.sound_speed = 343.0
        
        # Generate search grid
        self.search_azimuths = np.arange(-180, 180, search_resolution)
        self.search_elevations = np.arange(-30, 31, search_resolution)  # Limited elevation range
        
        # Precompute microphone pairs and delays
        self._precompute_delays()
        
        # FFT parameters
        self.fft_size = 2 ** int(np.ceil(np.log2(2 * frame_size - 1)))
        
        logger.info(
            "SRP-PHAT processor initialized",
            microphones=len(microphone_positions),
            search_points=len(self.search_azimuths) * len(self.search_elevations),
            fft_size=self.fft_size
        )
    
    def _precompute_delays(self) -> None:
        """Precompute time delays for all microphone pairs and search directions."""
        self.mic_pairs = []
        self.delay_maps = {}
        
        # Generate all unique microphone pairs
        for i in range(len(self.microphone_positions)):
            for j in range(i + 1, len(self.microphone_positions)):
                self.mic_pairs.append((i, j))
        
        # Precompute delays for each pair and search direction
        for pair_idx, (i, j) in enumerate(self.mic_pairs):
            mic1 = self.microphone_positions[i]
            mic2 = self.microphone_positions[j]
            
            delay_map = np.zeros((len(self.search_azimuths), len(self.search_elevations)))
            
            for az_idx, azimuth in enumerate(self.search_azimuths):
                for el_idx, elevation in enumerate(self.search_elevations):
                    # Convert spherical to Cartesian direction
                    az_rad = np.radians(azimuth)
                    el_rad = np.radians(elevation)
                    
                    direction = np.array([
                        np.cos(el_rad) * np.cos(az_rad),
                        np.cos(el_rad) * np.sin(az_rad),
                        np.sin(el_rad)
                    ])
                    
                    # Calculate time delay between microphones
                    mic1_pos = np.array([mic1.x, mic1.y, mic1.z])
                    mic2_pos = np.array([mic2.x, mic2.y, mic2.z])
                    
                    # Project microphone separation onto direction vector
                    separation = mic2_pos - mic1_pos
                    delay_distance = np.dot(separation, direction)
                    delay_time = delay_distance / self.sound_speed
                    
                    delay_map[az_idx, el_idx] = delay_time
            
            self.delay_maps[pair_idx] = delay_map
    
    def estimate_direction(self, audio_frame: AudioFrame) -> DirectionEstimate:
        """
        Estimate sound source direction using SRP-PHAT algorithm.
        
        Args:
            audio_frame: Multi-channel audio frame
            
        Returns:
            Direction estimate with confidence
        """
        if audio_frame.channels != len(self.microphone_positions):
            raise ProcessingError(
                f"Audio frame has {audio_frame.channels} channels, "
                f"but {len(self.microphone_positions)} microphones configured"
            )
        
        # Initialize SRP power map
        srp_map = np.zeros((len(self.search_azimuths), len(self.search_elevations)))
        
        # Process each microphone pair
        for pair_idx, (i, j) in enumerate(self.mic_pairs):
            # Get audio signals for this pair
            signal1 = audio_frame.data[i, :]
            signal2 = audio_frame.data[j, :]
            
            # Compute cross-correlation with PHAT weighting
            gcc_phat = self._compute_gcc_phat(signal1, signal2)
            
            # Add contribution to SRP map
            delay_map = self.delay_maps[pair_idx]
            
            for az_idx in range(len(self.search_azimuths)):
                for el_idx in range(len(self.search_elevations)):
                    # Get expected delay for this direction
                    expected_delay = delay_map[az_idx, el_idx]
                    
                    # Convert delay to sample index
                    delay_samples = int(expected_delay * self.sample_rate)
                    
                    # Interpolate GCC-PHAT value at expected delay
                    if abs(delay_samples) < len(gcc_phat) // 2:
                        gcc_idx = delay_samples + len(gcc_phat) // 2
                        if 0 <= gcc_idx < len(gcc_phat):
                            srp_map[az_idx, el_idx] += gcc_phat[gcc_idx]
        
        # Find peak in SRP map
        max_idx = np.unravel_index(np.argmax(srp_map), srp_map.shape)
        best_azimuth = self.search_azimuths[max_idx[0]]
        best_elevation = self.search_elevations[max_idx[1]]
        
        # Calculate confidence based on peak sharpness
        max_power = srp_map[max_idx]
        mean_power = np.mean(srp_map)
        std_power = np.std(srp_map)
        
        if std_power > 0:
            confidence = min(1.0, (max_power - mean_power) / (3 * std_power))
        else:
            confidence = 0.0
        
        confidence = max(0.0, confidence)
        
        return DirectionEstimate(
            azimuth=best_azimuth,
            elevation=best_elevation,
            confidence=confidence,
            timestamp=audio_frame.timestamp,
            area=ClassroomArea.UNKNOWN,  # Will be classified later
            metadata={
                'max_power': float(max_power),
                'mean_power': float(mean_power),
                'std_power': float(std_power),
                'search_points': srp_map.size
            }
        )
    
    def _compute_gcc_phat(self, signal1: np.ndarray, signal2: np.ndarray) -> np.ndarray:
        """
        Compute Generalized Cross-Correlation with Phase Transform (GCC-PHAT).
        
        Args:
            signal1: First signal
            signal2: Second signal
            
        Returns:
            GCC-PHAT correlation function
        """
        # Zero-pad signals to FFT size
        padded_signal1 = np.zeros(self.fft_size)
        padded_signal2 = np.zeros(self.fft_size)
        
        padded_signal1[:len(signal1)] = signal1
        padded_signal2[:len(signal2)] = signal2
        
        # Compute FFTs
        fft1 = fft(padded_signal1)
        fft2 = fft(padded_signal2)
        
        # Cross-power spectrum
        cross_spectrum = fft1 * np.conj(fft2)
        
        # PHAT weighting (phase transform)
        magnitude = np.abs(cross_spectrum)
        magnitude[magnitude == 0] = 1e-12  # Avoid division by zero
        phat_weighted = cross_spectrum / magnitude
        
        # Inverse FFT to get correlation
        correlation = np.real(ifft(phat_weighted))
        
        # Rearrange to center zero lag
        correlation = np.fft.fftshift(correlation)
        
        return correlation


class DirectionTracker:
    """
    Direction tracking with smoothing and history management.
    
    Provides temporal smoothing of direction estimates and tracks
    direction changes over time.
    """
    
    def __init__(self, smoothing_factor: float = 0.7,
                 confidence_threshold: float = 0.3,
                 max_history: int = 50):
        self.smoothing_factor = smoothing_factor
        self.confidence_threshold = confidence_threshold
        self.max_history = max_history
        
        # Tracking state
        self.current_direction: Optional[DirectionEstimate] = None
        self.direction_history: List[DirectionEstimate] = []
        self.last_update_time = time.time()
        
        # Change detection
        self.direction_change_threshold = 15.0  # degrees
        self.last_significant_change = time.time()
    
    def update(self, new_estimate: DirectionEstimate) -> DirectionEstimate:
        """
        Update direction tracking with new estimate.
        
        Args:
            new_estimate: New direction estimate
            
        Returns:
            Smoothed direction estimate
        """
        current_time = time.time()
        
        # Filter low-confidence estimates
        if new_estimate.confidence < self.confidence_threshold:
            if self.current_direction:
                # Return previous direction with updated timestamp
                return DirectionEstimate(
                    azimuth=self.current_direction.azimuth,
                    elevation=self.current_direction.elevation,
                    confidence=self.current_direction.confidence * 0.9,  # Decay confidence
                    timestamp=new_estimate.timestamp,
                    area=self.current_direction.area,
                    metadata={'tracking_status': 'low_confidence_filtered'}
                )
            else:
                return new_estimate
        
        # First estimate
        if self.current_direction is None:
            self.current_direction = new_estimate
            self.direction_history.append(new_estimate)
            self.last_update_time = current_time
            return new_estimate
        
        # Check for significant direction change
        angle_diff = self._calculate_angle_difference(
            self.current_direction.azimuth, new_estimate.azimuth
        )
        
        if angle_diff > self.direction_change_threshold:
            self.last_significant_change = current_time
            logger.debug(
                "Significant direction change detected",
                old_azimuth=self.current_direction.azimuth,
                new_azimuth=new_estimate.azimuth,
                angle_diff=angle_diff
            )
        
        # Apply temporal smoothing
        smoothed_azimuth = self._smooth_angle(
            self.current_direction.azimuth,
            new_estimate.azimuth,
            self.smoothing_factor
        )
        
        smoothed_elevation = (
            self.smoothing_factor * self.current_direction.elevation +
            (1 - self.smoothing_factor) * new_estimate.elevation
        )
        
        smoothed_confidence = (
            self.smoothing_factor * self.current_direction.confidence +
            (1 - self.smoothing_factor) * new_estimate.confidence
        )
        
        # Create smoothed estimate
        smoothed_estimate = DirectionEstimate(
            azimuth=smoothed_azimuth,
            elevation=smoothed_elevation,
            confidence=smoothed_confidence,
            timestamp=new_estimate.timestamp,
            area=new_estimate.area,
            metadata={
                'tracking_status': 'smoothed',
                'raw_azimuth': new_estimate.azimuth,
                'raw_elevation': new_estimate.elevation,
                'raw_confidence': new_estimate.confidence,
                'angle_change': angle_diff,
                'time_since_change': current_time - self.last_significant_change
            }
        )
        
        # Update tracking state
        self.current_direction = smoothed_estimate
        self.direction_history.append(smoothed_estimate)
        
        # Maintain history size
        if len(self.direction_history) > self.max_history:
            self.direction_history.pop(0)
        
        self.last_update_time = current_time
        
        return smoothed_estimate
    
    def _calculate_angle_difference(self, angle1: float, angle2: float) -> float:
        """Calculate the smallest angle difference between two angles."""
        diff = abs(angle1 - angle2)
        return min(diff, 360 - diff)
    
    def _smooth_angle(self, current: float, new: float, factor: float) -> float:
        """Smooth angle values handling wraparound."""
        # Handle angle wraparound
        diff = new - current
        if diff > 180:
            diff -= 360
        elif diff < -180:
            diff += 360
        
        smoothed = current + (1 - factor) * diff
        
        # Normalize to [-180, 180]
        while smoothed > 180:
            smoothed -= 360
        while smoothed <= -180:
            smoothed += 360
        
        return smoothed
    
    def get_direction_stability(self) -> float:
        """
        Calculate direction stability metric.
        
        Returns:
            Stability value from 0.0 (unstable) to 1.0 (stable)
        """
        if len(self.direction_history) < 5:
            return 0.0
        
        # Calculate variance in recent directions
        recent_directions = self.direction_history[-10:]
        azimuths = [d.azimuth for d in recent_directions]
        
        # Handle angle wraparound for variance calculation
        mean_azimuth = np.mean(azimuths)
        adjusted_azimuths = []
        
        for az in azimuths:
            diff = az - mean_azimuth
            if diff > 180:
                diff -= 360
            elif diff < -180:
                diff += 360
            adjusted_azimuths.append(mean_azimuth + diff)
        
        variance = np.var(adjusted_azimuths)
        stability = max(0.0, 1.0 - variance / 100.0)  # Normalize variance
        
        return stability




# Utility functions for creating common microphone array configurations
def create_linear_array(num_mics: int, spacing: float = 0.05, 
                       start_channel: int = 0) -> List[MicrophonePosition]:
    """Create a linear microphone array."""
    positions = []
    for i in range(num_mics):
        x = i * spacing - (num_mics - 1) * spacing / 2
        positions.append(MicrophonePosition(
            x=x, y=0.0, z=0.0, channel=start_channel + i
        ))
    return positions

def create_circular_array(num_mics: int, radius: float = 0.1,
                         start_channel: int = 0) -> List[MicrophonePosition]:
    """Create a circular microphone array."""
    positions = []
    for i in range(num_mics):
        angle = 2 * math.pi * i / num_mics
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        positions.append(MicrophonePosition(
            x=x, y=y, z=0.0, channel=start_channel + i
        ))
    return positions

def create_classroom_array() -> List[MicrophonePosition]:
    """Create a typical classroom microphone array configuration."""
    inner_array = create_circular_array(4, radius=0.05, start_channel=0)
    outer_array = create_circular_array(4, radius=0.15, start_channel=4)
    return inner_array + outer_array



class SSLService(BaseAudioProcessor):
    """
    Sound Source Localization (SSL) Service.
    
    Provides real-time sound source direction estimation using SRP-PHAT
    algorithm with direction tracking and classroom area recognition.
    """
    
    def __init__(self, service_name: str, config: AudioConfig,
                 microphone_positions: List[MicrophonePosition],
                 classroom_geometry: Optional[ClassroomGeometry] = None,
                 metrics_collector: Optional[IMetricsCollector] = None):
        super().__init__(service_name, config, metrics_collector)
        
        self.microphone_positions = microphone_positions
        self.classroom_geometry = classroom_geometry or self._create_default_geometry()
        
        # Initialize SRP-PHAT processor
        self.srp_processor = SRPPHATProcessor(
            microphone_positions=microphone_positions,
            sample_rate=config.sample_rate,
            frame_size=config.frame_size,
            search_resolution=5.0
        )
        
        # Initialize direction tracker
        self.direction_tracker = DirectionTracker(
            smoothing_factor=0.7,
            confidence_threshold=0.3,
            max_history=50
        )
        
        # Processing parameters
        self.estimation_interval_ms = 100.0
        self.last_estimation_time = 0.0
        
        # Statistics
        self.directions_estimated = 0
        self.direction_changes = 0
        self.last_direction: Optional[DirectionEstimate] = None
        
        # Area classification
        self.area_history: List[ClassroomArea] = []
        self.current_area = ClassroomArea.UNKNOWN
        
        logger.info(
            "SSL Service initialized",
            service=service_name,
            microphones=len(microphone_positions),
            estimation_interval=self.estimation_interval_ms
        )
    
    def _create_default_geometry(self) -> ClassroomGeometry:
        """Create default classroom geometry for typical classroom."""
        return ClassroomGeometry(
            length=12.0, width=8.0, height=3.0,
            teacher_area_bounds=(0.0, 4.0, 0.0, 8.0),
            microphone_array_position=(6.0, 4.0, 2.5)
        )
    
    async def _initialize(self) -> None:
        """Initialize SSL service."""
        logger.info("Initializing SSL service", service=self.service_name)
        
        if len(self.microphone_positions) < 2:
            raise ServiceError("SSL requires at least 2 microphones")
        
        if len(self.microphone_positions) != self._audio_config.channels:
            raise ServiceError(
                f"Microphone count ({len(self.microphone_positions)}) "
                f"doesn't match audio channels ({self._audio_config.channels})"
            )
    
    async def _cleanup(self) -> None:
        """Cleanup SSL service."""
        logger.info("SSL service cleaned up")
    
    async def _process_frame(self, frame: AudioFrame) -> AudioFrame:
        """Process audio frame for sound source localization."""
        current_time = time.time()
        time_since_last = (current_time - self.last_estimation_time) * 1000
        
        if time_since_last >= self.estimation_interval_ms:
            try:
                raw_estimate = self.srp_processor.estimate_direction(frame)
                raw_estimate.area = self.classroom_geometry.classify_direction(
                    raw_estimate.azimuth, raw_estimate.elevation
                )
                
                tracked_estimate = self.direction_tracker.update(raw_estimate)
                self.directions_estimated += 1
                
                if self.last_direction:
                    angle_diff = self._calculate_angle_difference(
                        self.last_direction.azimuth, tracked_estimate.azimuth
                    )
                    if angle_diff > 15.0:
                        self.direction_changes += 1
                
                self.last_direction = tracked_estimate
                self.last_estimation_time = current_time
                self._update_area_tracking(tracked_estimate.area)
                
                frame.metadata = frame.metadata or {}
                frame.metadata.update({
                    'ssl_azimuth': tracked_estimate.azimuth,
                    'ssl_elevation': tracked_estimate.elevation,
                    'ssl_confidence': tracked_estimate.confidence,
                    'ssl_area': tracked_estimate.area.value,
                    'ssl_estimation_count': self.directions_estimated
                })
                
            except Exception as e:
                logger.error("SSL processing error", error=str(e))
                frame.metadata = frame.metadata or {}
                frame.metadata['ssl_error'] = str(e)
        
        return frame
    
    def _calculate_angle_difference(self, angle1: float, angle2: float) -> float:
        """Calculate the smallest angle difference between two angles."""
        diff = abs(angle1 - angle2)
        return min(diff, 360 - diff)
    
    def _update_area_tracking(self, new_area: ClassroomArea) -> None:
        """Update area classification tracking."""
        self.area_history.append(new_area)
        if len(self.area_history) > 20:
            self.area_history.pop(0)
        
        if len(self.area_history) >= 5:
            area_counts = {}
            for area in self.area_history[-10:]:
                area_counts[area] = area_counts.get(area, 0) + 1
            
            most_common_area = max(area_counts, key=area_counts.get)
            if most_common_area != self.current_area:
                self.current_area = most_common_area
    
    def get_current_direction(self) -> Optional[DirectionEstimate]:
        """Get the current direction estimate."""
        return self.last_direction
    
    def get_current_area(self) -> ClassroomArea:
        """Get the current classified area."""
        return self.current_area
    
    def get_ssl_metrics(self) -> Dict[str, Any]:
        """Get SSL-specific metrics."""
        stability = 0.0
        if self.direction_tracker.current_direction:
            stability = self.direction_tracker.get_direction_stability()
        
        return {
            'directions_estimated': self.directions_estimated,
            'direction_changes': self.direction_changes,
            'current_azimuth': self.last_direction.azimuth if self.last_direction else None,
            'current_elevation': self.last_direction.elevation if self.last_direction else None,
            'current_confidence': self.last_direction.confidence if self.last_direction else None,
            'current_area': self.current_area.value,
            'direction_stability': stability,
            'estimation_interval_ms': self.estimation_interval_ms,
            'microphone_count': len(self.microphone_positions)
        }
    
    def set_estimation_interval(self, interval_ms: float) -> None:
        """Set the direction estimation interval."""
        if interval_ms < 50.0:
            interval_ms = 50.0
        elif interval_ms > 1000.0:
            interval_ms = 1000.0
        
        self.estimation_interval_ms = interval_ms
        logger.info("SSL estimation interval updated", interval_ms=interval_ms)
    
    def reset_tracking(self) -> None:
        """Reset direction tracking state."""
        self.direction_tracker = DirectionTracker(
            smoothing_factor=0.7, confidence_threshold=0.3, max_history=50
        )
        self.last_direction = None
        self.area_history.clear()
        self.current_area = ClassroomArea.UNKNOWN
        logger.info("SSL tracking state reset")
