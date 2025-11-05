"""
Frame Alignment System

This module implements multi-channel time synchronization algorithms, audio drift
detection and compensation, precise frame boundary alignment, and high-precision
timestamp management for real-time audio processing.

Implements requirements: 2.4, 5.1, 5.2, 5.4
"""

import threading
import time
import logging
from typing import Dict, List, Optional, Tuple, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import numpy as np
from collections import deque

from .models import AudioFrame
from .buffer_management import CircularBuffer


class AlignmentState(Enum):
    """Frame alignment state"""
    INITIALIZING = "initializing"
    CALIBRATING = "calibrating"
    ALIGNED = "aligned"
    DRIFT_DETECTED = "drift_detected"
    REALIGNING = "realigning"
    ERROR = "error"


class DriftType(Enum):
    """Types of audio drift"""
    CLOCK_DRIFT = "clock_drift"
    SAMPLE_RATE_DRIFT = "sample_rate_drift"
    BUFFER_DRIFT = "buffer_drift"
    NETWORK_JITTER = "network_jitter"


@dataclass
class TimestampInfo:
    """High-precision timestamp information"""
    device_id: str
    frame_id: int
    
    # Timestamps
    capture_timestamp: datetime
    system_timestamp: datetime
    aligned_timestamp: datetime
    
    # Timing metrics
    sample_rate: int
    samples_per_frame: int
    frame_duration_us: float  # microseconds
    
    # Drift information
    clock_offset_us: float = 0.0  # microseconds
    drift_rate_ppm: float = 0.0   # parts per million
    jitter_us: float = 0.0        # microseconds
    
    def get_frame_time_us(self) -> float:
        """Get frame time in microseconds since epoch"""
        return self.aligned_timestamp.timestamp() * 1_000_000


@dataclass
class AlignmentMetrics:
    """Frame alignment performance metrics"""
    device_id: str
    
    # Alignment statistics
    frames_processed: int = 0
    frames_aligned: int = 0
    frames_dropped: int = 0
    frames_interpolated: int = 0
    
    # Timing accuracy
    average_alignment_error_us: float = 0.0
    max_alignment_error_us: float = 0.0
    rms_alignment_error_us: float = 0.0
    
    # Drift tracking
    detected_drift_ppm: float = 0.0
    drift_correction_count: int = 0
    last_drift_correction: Optional[datetime] = None
    
    # Performance
    processing_time_us: float = 0.0
    cpu_usage_percent: float = 0.0
    
    # Quality metrics
    alignment_quality_score: float = 1.0  # 0.0 to 1.0
    stability_score: float = 1.0          # 0.0 to 1.0
    
    def update_alignment_error(self, error_us: float):
        """Update alignment error statistics"""
        if self.frames_aligned == 0:
            self.average_alignment_error_us = error_us
            self.rms_alignment_error_us = error_us * error_us
        else:
            # Update running average
            self.average_alignment_error_us = (
                (self.average_alignment_error_us * self.frames_aligned + error_us) /
                (self.frames_aligned + 1)
            )
            
            # Update RMS
            self.rms_alignment_error_us = (
                (self.rms_alignment_error_us * self.frames_aligned + error_us * error_us) /
                (self.frames_aligned + 1)
            )
        
        self.max_alignment_error_us = max(self.max_alignment_error_us, abs(error_us))
        self.frames_aligned += 1


class DriftDetector:
    """
    Audio drift detection and compensation system
    """
    
    def __init__(self, device_id: str, sample_rate: int):
        self.device_id = device_id
        self.sample_rate = sample_rate
        self.logger = logging.getLogger(__name__ + f".DriftDetector.{device_id}")
        
        # Drift detection parameters
        self._detection_window_size = 100  # frames
        self._drift_threshold_ppm = 10.0   # parts per million
        self._correction_threshold_ppm = 50.0
        
        # Timestamp history
        self._timestamp_history: deque = deque(maxlen=self._detection_window_size)
        self._expected_intervals: deque = deque(maxlen=self._detection_window_size)
        
        # Drift state
        self._current_drift_ppm = 0.0
        self._drift_trend = 0.0
        self._last_correction_time = datetime.now()
        self._correction_count = 0
        
        # Statistics
        self._frame_count = 0
        self._drift_history: List[float] = []
    
    def add_timestamp(self, timestamp_info: TimestampInfo) -> Tuple[bool, float]:
        """
        Add timestamp and detect drift
        Returns: (drift_detected, drift_ppm)
        """
        try:
            self._frame_count += 1
            current_time = timestamp_info.get_frame_time_us()
            
            # Calculate expected interval
            expected_interval_us = (timestamp_info.samples_per_frame / self.sample_rate) * 1_000_000
            
            if len(self._timestamp_history) > 0:
                # Calculate actual interval
                last_time = self._timestamp_history[-1]
                actual_interval_us = current_time - last_time
                
                # Store intervals
                self._expected_intervals.append(expected_interval_us)
                
                # Calculate drift if we have enough samples
                if len(self._timestamp_history) >= 10:
                    drift_ppm = self._calculate_drift_ppm(actual_interval_us, expected_interval_us)
                    self._current_drift_ppm = drift_ppm
                    self._drift_history.append(drift_ppm)
                    
                    # Keep drift history manageable
                    if len(self._drift_history) > 1000:
                        self._drift_history = self._drift_history[-500:]
                    
                    # Check for significant drift
                    drift_detected = abs(drift_ppm) > self._drift_threshold_ppm
                    
                    if drift_detected:
                        self.logger.debug(f"Drift detected: {drift_ppm:.2f} ppm")
                    
                    return drift_detected, drift_ppm
            
            # Store timestamp
            self._timestamp_history.append(current_time)
            
            return False, 0.0
            
        except Exception as e:
            self.logger.error(f"Error in drift detection: {e}")
            return False, 0.0
    
    def _calculate_drift_ppm(self, actual_interval_us: float, expected_interval_us: float) -> float:
        """Calculate drift in parts per million"""
        if expected_interval_us == 0:
            return 0.0
        
        # Calculate instantaneous drift
        interval_error = actual_interval_us - expected_interval_us
        instantaneous_drift_ppm = (interval_error / expected_interval_us) * 1_000_000
        
        # Apply smoothing filter
        if len(self._drift_history) > 0:
            # Exponential moving average
            alpha = 0.1
            smoothed_drift = alpha * instantaneous_drift_ppm + (1 - alpha) * self._drift_history[-1]
        else:
            smoothed_drift = instantaneous_drift_ppm
        
        return smoothed_drift
    
    def get_drift_statistics(self) -> Dict[str, Any]:
        """Get drift detection statistics"""
        if not self._drift_history:
            return {
                "current_drift_ppm": 0.0,
                "average_drift_ppm": 0.0,
                "max_drift_ppm": 0.0,
                "drift_stability": 1.0,
                "correction_count": self._correction_count
            }
        
        return {
            "current_drift_ppm": self._current_drift_ppm,
            "average_drift_ppm": np.mean(self._drift_history),
            "max_drift_ppm": np.max(np.abs(self._drift_history)),
            "drift_stability": self._calculate_stability_score(),
            "correction_count": self._correction_count,
            "samples_count": len(self._drift_history)
        }
    
    def _calculate_stability_score(self) -> float:
        """Calculate drift stability score (0.0 to 1.0)"""
        if len(self._drift_history) < 10:
            return 1.0
        
        # Calculate variance of recent drift measurements
        recent_drift = self._drift_history[-50:]  # Last 50 measurements
        variance = np.var(recent_drift)
        
        # Convert variance to stability score (lower variance = higher stability)
        max_variance = 100.0  # ppm^2
        stability = max(0.0, 1.0 - (variance / max_variance))
        
        return stability
    
    def needs_correction(self) -> bool:
        """Check if drift correction is needed"""
        return abs(self._current_drift_ppm) > self._correction_threshold_ppm
    
    def apply_correction(self) -> float:
        """Apply drift correction and return correction factor"""
        correction_factor = 1.0 + (self._current_drift_ppm / 1_000_000)
        self._correction_count += 1
        self._last_correction_time = datetime.now()
        
        self.logger.info(f"Applied drift correction: {self._current_drift_ppm:.2f} ppm, factor: {correction_factor:.6f}")
        
        return correction_factor


class FrameBoundaryAligner:
    """
    Precise frame boundary alignment system
    """
    
    def __init__(self, reference_sample_rate: int = 48000):
        self.reference_sample_rate = reference_sample_rate
        self.logger = logging.getLogger(__name__ + ".FrameBoundaryAligner")
        
        # Alignment parameters
        self._alignment_tolerance_us = 100.0  # microseconds
        self._interpolation_enabled = True
        self._max_interpolation_samples = 10
        
        # Reference timing
        self._reference_frame_duration_us = 0.0
        self._reference_start_time: Optional[datetime] = None
        self._frame_counter = 0
        
        # Alignment buffers
        self._alignment_buffers: Dict[str, CircularBuffer] = {}
        self._pending_frames: Dict[str, List[AudioFrame]] = {}
        
        # Statistics
        self._alignment_stats: Dict[str, AlignmentMetrics] = {}
    
    def set_reference_timing(self, start_time: datetime, frame_size: int):
        """Set reference timing parameters"""
        self._reference_start_time = start_time
        self._reference_frame_duration_us = (frame_size / self.reference_sample_rate) * 1_000_000
        self._frame_counter = 0
        
        self.logger.info(f"Reference timing set: start={start_time}, frame_duration={self._reference_frame_duration_us:.2f}us")
    
    def add_device(self, device_id: str, buffer_size: int = 100):
        """Add device for frame alignment"""
        self._alignment_buffers[device_id] = CircularBuffer(buffer_size)
        self._pending_frames[device_id] = []
        self._alignment_stats[device_id] = AlignmentMetrics(device_id=device_id)
        
        self.logger.info(f"Added device for alignment: {device_id}")
    
    def remove_device(self, device_id: str):
        """Remove device from alignment"""
        if device_id in self._alignment_buffers:
            del self._alignment_buffers[device_id]
            del self._pending_frames[device_id]
            del self._alignment_stats[device_id]
            
            self.logger.info(f"Removed device from alignment: {device_id}")
    
    def align_frame(self, device_id: str, frame: AudioFrame, timestamp_info: TimestampInfo) -> Optional[AudioFrame]:
        """
        Align frame to reference timing
        Returns aligned frame or None if frame should be dropped
        """
        if device_id not in self._alignment_buffers:
            return None
        
        try:
            start_time = time.perf_counter()
            
            # Calculate expected frame time
            expected_time_us = self._calculate_expected_frame_time()
            actual_time_us = timestamp_info.get_frame_time_us()
            
            # Calculate alignment error
            alignment_error_us = actual_time_us - expected_time_us
            
            # Update statistics
            stats = self._alignment_stats[device_id]
            stats.frames_processed += 1
            stats.update_alignment_error(alignment_error_us)
            
            # Check if frame is within tolerance
            if abs(alignment_error_us) <= self._alignment_tolerance_us:
                # Frame is aligned
                aligned_frame = self._create_aligned_frame(frame, timestamp_info, expected_time_us)
                stats.frames_aligned += 1
                
                # Update processing time
                processing_time = (time.perf_counter() - start_time) * 1_000_000
                stats.processing_time_us = processing_time
                
                return aligned_frame
            
            elif alignment_error_us < -self._alignment_tolerance_us:
                # Frame is early - buffer it
                self._pending_frames[device_id].append((frame, timestamp_info))
                return None
            
            else:
                # Frame is late - try interpolation or drop
                if self._interpolation_enabled and abs(alignment_error_us) <= self._max_interpolation_samples * 1000:
                    interpolated_frame = self._interpolate_frame(device_id, frame, timestamp_info, expected_time_us)
                    if interpolated_frame:
                        stats.frames_interpolated += 1
                        return interpolated_frame
                
                # Drop frame
                stats.frames_dropped += 1
                self.logger.debug(f"Dropped late frame from {device_id}: error={alignment_error_us:.2f}us")
                return None
                
        except Exception as e:
            self.logger.error(f"Error aligning frame from {device_id}: {e}")
            return None
    
    def _calculate_expected_frame_time(self) -> float:
        """Calculate expected frame time in microseconds"""
        if not self._reference_start_time:
            return 0.0
        
        reference_time_us = self._reference_start_time.timestamp() * 1_000_000
        expected_time_us = reference_time_us + (self._frame_counter * self._reference_frame_duration_us)
        
        return expected_time_us
    
    def _create_aligned_frame(self, frame: AudioFrame, timestamp_info: TimestampInfo, aligned_time_us: float) -> AudioFrame:
        """Create aligned frame with corrected timestamp"""
        aligned_frame = AudioFrame(
            frame_id=frame.frame_id,
            timestamp=datetime.fromtimestamp(aligned_time_us / 1_000_000),
            sample_rate=frame.sample_rate,
            channels=frame.channels,
            bit_depth=frame.bit_depth,
            data=frame.data,
            frame_size=frame.frame_size
        )
        
        # Copy quality metrics
        aligned_frame.peak_level_db = frame.peak_level_db
        aligned_frame.rms_level_db = frame.rms_level_db
        aligned_frame.zero_crossing_rate = frame.zero_crossing_rate
        aligned_frame.spectral_centroid = frame.spectral_centroid
        
        # Update processing info
        aligned_frame.processing_chain = frame.processing_chain.copy()
        aligned_frame.processing_chain.append("frame_aligner")
        
        return aligned_frame
    
    def _interpolate_frame(self, device_id: str, frame: AudioFrame, timestamp_info: TimestampInfo, target_time_us: float) -> Optional[AudioFrame]:
        """Interpolate frame to target time"""
        try:
            # Simple linear interpolation for now
            # In a full implementation, this would use more sophisticated interpolation
            
            # Check if we have previous frame for interpolation
            pending_frames = self._pending_frames[device_id]
            if not pending_frames:
                return None
            
            # Use the most recent pending frame
            prev_frame, prev_timestamp = pending_frames[-1]
            
            # Calculate interpolation factor
            current_time_us = timestamp_info.get_frame_time_us()
            prev_time_us = prev_timestamp.get_frame_time_us()
            
            if current_time_us == prev_time_us:
                return None
            
            interpolation_factor = (target_time_us - prev_time_us) / (current_time_us - prev_time_us)
            interpolation_factor = max(0.0, min(1.0, interpolation_factor))
            
            # Create interpolated frame
            interpolated_frame = self._create_aligned_frame(frame, timestamp_info, target_time_us)
            
            # Simple amplitude interpolation if data is available
            if hasattr(frame, 'data') and hasattr(prev_frame, 'data') and frame.data is not None and prev_frame.data is not None:
                try:
                    # Linear interpolation of audio data
                    interpolated_data = (1 - interpolation_factor) * prev_frame.data + interpolation_factor * frame.data
                    interpolated_frame.data = interpolated_data
                except Exception:
                    # If interpolation fails, use original data
                    pass
            
            return interpolated_frame
            
        except Exception as e:
            self.logger.error(f"Error interpolating frame: {e}")
            return None
    
    def advance_frame_counter(self):
        """Advance the reference frame counter"""
        self._frame_counter += 1
    
    def get_alignment_metrics(self, device_id: str) -> Optional[AlignmentMetrics]:
        """Get alignment metrics for device"""
        return self._alignment_stats.get(device_id)
    
    def get_all_alignment_metrics(self) -> Dict[str, AlignmentMetrics]:
        """Get alignment metrics for all devices"""
        return self._alignment_stats.copy()
    
    def reset_alignment(self, device_id: Optional[str] = None):
        """Reset alignment for device or all devices"""
        if device_id:
            if device_id in self._alignment_stats:
                self._alignment_stats[device_id] = AlignmentMetrics(device_id=device_id)
                self._pending_frames[device_id].clear()
        else:
            for dev_id in self._alignment_stats:
                self._alignment_stats[dev_id] = AlignmentMetrics(device_id=dev_id)
                self._pending_frames[dev_id].clear()
            self._frame_counter = 0


class MultiChannelFrameAligner:
    """
    Multi-channel frame aligner with comprehensive synchronization and drift compensation
    """
    
    def __init__(self, reference_sample_rate: int = 48000):
        self.reference_sample_rate = reference_sample_rate
        self.logger = logging.getLogger(__name__ + ".MultiChannelFrameAligner")
        
        # Core components
        self._drift_detectors: Dict[str, DriftDetector] = {}
        self._frame_aligner = FrameBoundaryAligner(reference_sample_rate)
        
        # State management
        self._state = AlignmentState.INITIALIZING
        self._reference_device: Optional[str] = None
        self._active_devices: Set[str] = set()
        
        # Synchronization
        self._sync_lock = threading.RLock()
        self._alignment_callbacks: List[Callable[[str, AudioFrame], None]] = []
        
        # Monitoring
        self._monitoring_active = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_interval = 1.0
        self._monitor_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        
        # Configuration
        self._auto_drift_correction = True
        self._alignment_quality_threshold = 0.8
    
    def add_device(self, device_id: str, sample_rate: int, buffer_size: int = 100):
        """Add device for multi-channel alignment"""
        with self._sync_lock:
            # Create drift detector
            self._drift_detectors[device_id] = DriftDetector(device_id, sample_rate)
            
            # Add to frame aligner
            self._frame_aligner.add_device(device_id, buffer_size)
            
            # Add to active devices
            self._active_devices.add(device_id)
            
            # Set as reference device if first device
            if not self._reference_device:
                self._reference_device = device_id
                self.logger.info(f"Set reference device: {device_id}")
            
            self.logger.info(f"Added device to multi-channel aligner: {device_id}")
    
    def remove_device(self, device_id: str):
        """Remove device from alignment"""
        with self._sync_lock:
            if device_id in self._drift_detectors:
                del self._drift_detectors[device_id]
            
            self._frame_aligner.remove_device(device_id)
            self._active_devices.discard(device_id)
            
            # Update reference device if needed
            if self._reference_device == device_id:
                self._reference_device = next(iter(self._active_devices)) if self._active_devices else None
                if self._reference_device:
                    self.logger.info(f"Updated reference device: {self._reference_device}")
            
            self.logger.info(f"Removed device from multi-channel aligner: {device_id}")
    
    def start_alignment(self, start_time: Optional[datetime] = None, frame_size: int = 256):
        """Start multi-channel alignment"""
        with self._sync_lock:
            if not start_time:
                start_time = datetime.now()
            
            # Set reference timing
            self._frame_aligner.set_reference_timing(start_time, frame_size)
            
            # Start monitoring
            self.start_monitoring()
            
            self._state = AlignmentState.CALIBRATING
            self.logger.info("Started multi-channel frame alignment")
    
    def stop_alignment(self):
        """Stop multi-channel alignment"""
        with self._sync_lock:
            self.stop_monitoring()
            self._state = AlignmentState.INITIALIZING
            self.logger.info("Stopped multi-channel frame alignment")
    
    def process_frame(self, device_id: str, frame: AudioFrame) -> Optional[AudioFrame]:
        """
        Process frame through alignment pipeline
        Returns aligned frame or None if frame should be dropped
        """
        if device_id not in self._active_devices:
            return None
        
        try:
            with self._sync_lock:
                # Create timestamp info
                timestamp_info = TimestampInfo(
                    device_id=device_id,
                    frame_id=frame.frame_id,
                    capture_timestamp=frame.capture_timestamp or frame.timestamp,
                    system_timestamp=datetime.now(),
                    aligned_timestamp=frame.timestamp,
                    sample_rate=frame.sample_rate,
                    samples_per_frame=frame.frame_size,
                    frame_duration_us=(frame.frame_size / frame.sample_rate) * 1_000_000
                )
                
                # Detect drift
                drift_detector = self._drift_detectors[device_id]
                drift_detected, drift_ppm = drift_detector.add_timestamp(timestamp_info)
                
                # Apply drift correction if needed
                if self._auto_drift_correction and drift_detector.needs_correction():
                    correction_factor = drift_detector.apply_correction()
                    # Apply correction to timestamp
                    corrected_time_us = timestamp_info.get_frame_time_us() * correction_factor
                    timestamp_info.aligned_timestamp = datetime.fromtimestamp(corrected_time_us / 1_000_000)
                    timestamp_info.drift_rate_ppm = drift_ppm
                
                # Align frame
                aligned_frame = self._frame_aligner.align_frame(device_id, frame, timestamp_info)
                
                if aligned_frame:
                    # Advance frame counter for reference device
                    if device_id == self._reference_device:
                        self._frame_aligner.advance_frame_counter()
                    
                    # Update state based on alignment quality
                    self._update_alignment_state()
                    
                    # Notify callbacks
                    for callback in self._alignment_callbacks:
                        try:
                            callback(device_id, aligned_frame)
                        except Exception as e:
                            self.logger.error(f"Error in alignment callback: {e}")
                
                return aligned_frame
                
        except Exception as e:
            self.logger.error(f"Error processing frame from {device_id}: {e}")
            return None
    
    def _update_alignment_state(self):
        """Update alignment state based on current metrics"""
        try:
            # Calculate overall alignment quality
            all_metrics = self._frame_aligner.get_all_alignment_metrics()
            if not all_metrics:
                return
            
            quality_scores = [metrics.alignment_quality_score for metrics in all_metrics.values()]
            average_quality = sum(quality_scores) / len(quality_scores)
            
            # Update state
            if average_quality >= self._alignment_quality_threshold:
                if self._state != AlignmentState.ALIGNED:
                    self._state = AlignmentState.ALIGNED
                    self.logger.info("Frame alignment achieved")
            else:
                if self._state == AlignmentState.ALIGNED:
                    self._state = AlignmentState.DRIFT_DETECTED
                    self.logger.warning("Alignment quality degraded")
                    
        except Exception as e:
            self.logger.error(f"Error updating alignment state: {e}")
    
    def get_alignment_status(self) -> Dict[str, Any]:
        """Get comprehensive alignment status"""
        with self._sync_lock:
            status = {
                "state": self._state.value,
                "reference_device": self._reference_device,
                "active_devices": list(self._active_devices),
                "device_count": len(self._active_devices),
                "alignment_metrics": {},
                "drift_statistics": {},
                "overall_quality": 0.0
            }
            
            # Collect metrics from all devices
            quality_scores = []
            for device_id in self._active_devices:
                # Alignment metrics
                alignment_metrics = self._frame_aligner.get_alignment_metrics(device_id)
                if alignment_metrics:
                    status["alignment_metrics"][device_id] = {
                        "frames_processed": alignment_metrics.frames_processed,
                        "frames_aligned": alignment_metrics.frames_aligned,
                        "frames_dropped": alignment_metrics.frames_dropped,
                        "alignment_error_us": alignment_metrics.average_alignment_error_us,
                        "quality_score": alignment_metrics.alignment_quality_score
                    }
                    quality_scores.append(alignment_metrics.alignment_quality_score)
                
                # Drift statistics
                drift_detector = self._drift_detectors.get(device_id)
                if drift_detector:
                    status["drift_statistics"][device_id] = drift_detector.get_drift_statistics()
            
            # Calculate overall quality
            if quality_scores:
                status["overall_quality"] = sum(quality_scores) / len(quality_scores)
            
            return status
    
    def calibrate_alignment(self) -> bool:
        """Perform alignment calibration"""
        try:
            with self._sync_lock:
                self._state = AlignmentState.CALIBRATING
                
                # Reset all alignment metrics
                self._frame_aligner.reset_alignment()
                
                # Reset drift detectors
                for detector in self._drift_detectors.values():
                    detector._drift_history.clear()
                    detector._correction_count = 0
                
                self.logger.info("Alignment calibration completed")
                return True
                
        except Exception as e:
            self.logger.error(f"Calibration failed: {e}")
            self._state = AlignmentState.ERROR
            return False
    
    def register_alignment_callback(self, callback: Callable[[str, AudioFrame], None]):
        """Register callback for aligned frames"""
        self._alignment_callbacks.append(callback)
    
    def unregister_alignment_callback(self, callback: Callable[[str, AudioFrame], None]):
        """Unregister alignment callback"""
        if callback in self._alignment_callbacks:
            self._alignment_callbacks.remove(callback)
    
    def start_monitoring(self):
        """Start alignment monitoring"""
        if self._monitoring_active:
            return
        
        self._monitoring_active = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        
        self.logger.info("Started alignment monitoring")
    
    def stop_monitoring(self):
        """Stop alignment monitoring"""
        self._monitoring_active = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
        
        self.logger.info("Stopped alignment monitoring")
    
    def register_monitor_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Register monitoring callback"""
        self._monitor_callbacks.append(callback)
    
    def _monitor_loop(self):
        """Alignment monitoring loop"""
        while self._monitoring_active:
            try:
                # Collect status
                status = self.get_alignment_status()
                status["timestamp"] = datetime.now().isoformat()
                
                # Notify callbacks
                for callback in self._monitor_callbacks:
                    try:
                        callback(status)
                    except Exception as e:
                        self.logger.error(f"Error in monitor callback: {e}")
                
                time.sleep(self._monitor_interval)
                
            except Exception as e:
                self.logger.error(f"Error in monitor loop: {e}")
                time.sleep(0.1)


# Factory functions
def create_drift_detector(device_id: str, sample_rate: int) -> DriftDetector:
    """Create a drift detector instance"""
    return DriftDetector(device_id, sample_rate)


def create_frame_boundary_aligner(reference_sample_rate: int = 48000) -> FrameBoundaryAligner:
    """Create a frame boundary aligner instance"""
    return FrameBoundaryAligner(reference_sample_rate)


def create_multi_channel_frame_aligner(reference_sample_rate: int = 48000) -> MultiChannelFrameAligner:
    """Create a multi-channel frame aligner instance"""
    return MultiChannelFrameAligner(reference_sample_rate)