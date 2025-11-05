"""
Multi-Input Audio Access Layer

This module implements the intelligent multi-input audio access layer for dynamic
audio input detection, selective access management, and synchronized multi-input capture.
"""

import asyncio
import threading
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Callable, Any, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
from concurrent.futures import ThreadPoolExecutor
import queue

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    pyaudio = None

from .models import AudioDevice, DeviceType, AudioFrame, ProcessingStatus
from .interfaces import IMultiInputCapture


class InputDeviceState(Enum):
    """Input device state enumeration"""
    UNKNOWN = "unknown"
    DETECTED = "detected"
    AVAILABLE = "available"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    DISCONNECTED = "disconnected"


class SynchronizationMode(Enum):
    """Multi-input synchronization modes"""
    NONE = "none"
    TIMESTAMP = "timestamp"
    HARDWARE_SYNC = "hardware_sync"
    SOFTWARE_SYNC = "software_sync"


@dataclass
class InputDeviceStatus:
    """Status information for an input device"""
    device_id: str
    state: InputDeviceState
    is_enabled: bool = False
    priority: int = 0
    gain_db: float = 0.0
    is_muted: bool = False
    
    # Quality metrics
    signal_strength: float = 0.0
    noise_level_db: float = -60.0
    connection_quality: float = 1.0
    
    # Performance metrics
    frames_captured: int = 0
    frames_dropped: int = 0
    last_frame_timestamp: Optional[datetime] = None
    
    # Error tracking
    error_count: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    
    def update_quality_metrics(self, signal_strength: float, noise_level: float, connection_quality: float):
        """Update quality metrics"""
        self.signal_strength = signal_strength
        self.noise_level_db = noise_level
        self.connection_quality = connection_quality
    
    def record_frame(self, timestamp: datetime):
        """Record successful frame capture"""
        self.frames_captured += 1
        self.last_frame_timestamp = timestamp
    
    def record_dropped_frame(self):
        """Record dropped frame"""
        self.frames_dropped += 1
    
    def record_error(self, error_message: str):
        """Record error"""
        self.error_count += 1
        self.last_error = error_message
        self.last_error_time = datetime.now()
        self.state = InputDeviceState.ERROR


@dataclass
class InputConfiguration:
    """Configuration for input device management"""
    # Device selection
    auto_detect_devices: bool = True
    enable_all_by_default: bool = True
    selected_device_ids: List[str] = field(default_factory=list)
    
    # Synchronization
    sync_mode: SynchronizationMode = SynchronizationMode.SOFTWARE_SYNC
    sync_tolerance_ms: float = 5.0
    max_sync_drift_ms: float = 50.0
    
    # Quality monitoring
    enable_quality_monitoring: bool = True
    quality_check_interval_ms: int = 100
    min_signal_strength: float = 0.1
    max_noise_level_db: float = -40.0
    
    # Hot-plug support
    enable_hot_plug: bool = True
    device_scan_interval_ms: int = 1000
    
    # Buffer management
    buffer_size_frames: int = 256
    max_buffer_count: int = 8
    
    # Error handling
    max_consecutive_errors: int = 5
    error_recovery_delay_ms: int = 1000


class DynamicAudioInputDetector:
    """
    Dynamic audio input detector that automatically scans and detects 1~n audio input devices
    """
    
    def __init__(self, config: InputConfiguration):
        self.config = config
        self.logger = logging.getLogger(__name__ + ".DynamicAudioInputDetector")
        self._detected_devices: Dict[str, AudioDevice] = {}
        self._device_capabilities: Dict[str, Dict[str, Any]] = {}
        self._scan_thread: Optional[threading.Thread] = None
        self._stop_scanning = threading.Event()
        self._callbacks: List[Callable[[List[AudioDevice]], None]] = []
        
        if not PYAUDIO_AVAILABLE:
            self.logger.warning("PyAudio not available - device detection will be limited")
    
    def start_detection(self) -> bool:
        """Start continuous device detection"""
        try:
            if self._scan_thread and self._scan_thread.is_alive():
                self.logger.warning("Detection already running")
                return True
            
            self._stop_scanning.clear()
            self._scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
            self._scan_thread.start()
            
            self.logger.info("Started dynamic audio input detection")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start detection: {e}")
            return False
    
    def stop_detection(self):
        """Stop device detection"""
        self._stop_scanning.set()
        if self._scan_thread:
            self._scan_thread.join(timeout=2.0)
        self.logger.info("Stopped dynamic audio input detection")
    
    def scan_devices_once(self) -> List[AudioDevice]:
        """Perform a single device scan"""
        devices = []
        
        if not PYAUDIO_AVAILABLE:
            self.logger.warning("PyAudio not available - returning empty device list")
            return devices
        
        try:
            pa = pyaudio.PyAudio()
            device_count = pa.get_device_count()
            
            for i in range(device_count):
                try:
                    device_info = pa.get_device_info_by_index(i)
                    
                    # Only process input devices
                    if device_info['maxInputChannels'] > 0:
                        device = self._create_audio_device(i, device_info)
                        devices.append(device)
                        
                        # Cache device capabilities
                        self._device_capabilities[device.device_id] = self._analyze_device_capabilities(device_info)
                        
                except Exception as e:
                    self.logger.warning(f"Error processing device {i}: {e}")
                    continue
            
            pa.terminate()
            
        except Exception as e:
            self.logger.error(f"Error during device scan: {e}")
        
        return devices
    
    def get_detected_devices(self) -> List[AudioDevice]:
        """Get currently detected devices"""
        return list(self._detected_devices.values())
    
    def get_device_capabilities(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed capabilities of a specific device"""
        return self._device_capabilities.get(device_id)
    
    def register_detection_callback(self, callback: Callable[[List[AudioDevice]], None]):
        """Register callback for device detection events"""
        self._callbacks.append(callback)
    
    def _scan_loop(self):
        """Continuous device scanning loop"""
        while not self._stop_scanning.is_set():
            try:
                current_devices = self.scan_devices_once()
                
                # Check for changes
                current_device_ids = {device.device_id for device in current_devices}
                previous_device_ids = set(self._detected_devices.keys())
                
                if current_device_ids != previous_device_ids:
                    # Update detected devices
                    self._detected_devices = {device.device_id: device for device in current_devices}
                    
                    # Notify callbacks
                    for callback in self._callbacks:
                        try:
                            callback(current_devices)
                        except Exception as e:
                            self.logger.error(f"Error in detection callback: {e}")
                    
                    # Log changes
                    added = current_device_ids - previous_device_ids
                    removed = previous_device_ids - current_device_ids
                    
                    if added:
                        self.logger.info(f"Detected new devices: {added}")
                    if removed:
                        self.logger.info(f"Devices disconnected: {removed}")
                
            except Exception as e:
                self.logger.error(f"Error in scan loop: {e}")
            
            # Wait for next scan
            self._stop_scanning.wait(self.config.device_scan_interval_ms / 1000.0)
    
    def _create_audio_device(self, device_index: int, device_info: Dict[str, Any]) -> AudioDevice:
        """Create AudioDevice from PyAudio device info"""
        device_id = f"input_{device_index}"
        
        # Determine device type
        device_type = DeviceType.MICROPHONE
        name_lower = device_info['name'].lower()
        if 'line' in name_lower:
            device_type = DeviceType.LINE_INPUT
        elif 'usb' in name_lower:
            device_type = DeviceType.USB_AUDIO
        
        return AudioDevice(
            device_id=device_id,
            name=device_info['name'],
            device_type=device_type,
            is_input=True,
            is_output=False,
            max_input_channels=device_info['maxInputChannels'],
            max_output_channels=device_info['maxOutputChannels'],
            supported_sample_rates=[int(device_info['defaultSampleRate'])],
            is_available=True,
            is_connected=True,
            driver_name=device_info.get('hostApi', 'Unknown'),
            default_low_input_latency=device_info['defaultLowInputLatency'],
            default_high_input_latency=device_info['defaultHighInputLatency']
        )
    
    def _analyze_device_capabilities(self, device_info: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze and return device capabilities"""
        return {
            'max_channels': device_info['maxInputChannels'],
            'default_sample_rate': device_info['defaultSampleRate'],
            'low_latency': device_info['defaultLowInputLatency'],
            'high_latency': device_info['defaultHighInputLatency'],
            'host_api': device_info.get('hostApi', 'Unknown')
        }


class SelectiveAudioAccessManager:
    """
    Selective audio access manager that supports default access to all inputs
    or user selection of specific 1~n inputs for processing
    """
    
    def __init__(self, config: InputConfiguration):
        self.config = config
        self.logger = logging.getLogger(__name__ + ".SelectiveAudioAccessManager")
        self._available_devices: Dict[str, AudioDevice] = {}
        self._selected_devices: Set[str] = set()
        self._device_priorities: Dict[str, int] = {}
        self._access_callbacks: List[Callable[[str, bool], None]] = []
    
    def set_available_devices(self, devices: List[AudioDevice]):
        """Set the list of available devices"""
        self._available_devices = {device.device_id: device for device in devices}
        
        # Apply default selection policy
        if self.config.enable_all_by_default:
            self._selected_devices = set(self._available_devices.keys())
            self.logger.info(f"Auto-selected all {len(self._selected_devices)} available devices")
        else:
            # Use configured device list
            self._selected_devices = set(self.config.selected_device_ids) & set(self._available_devices.keys())
            self.logger.info(f"Selected {len(self._selected_devices)} configured devices")
    
    def select_devices(self, device_ids: List[str]) -> bool:
        """Select specific devices for processing"""
        try:
            # Validate device IDs
            invalid_devices = set(device_ids) - set(self._available_devices.keys())
            if invalid_devices:
                self.logger.error(f"Invalid device IDs: {invalid_devices}")
                return False
            
            # Update selection
            old_selection = self._selected_devices.copy()
            self._selected_devices = set(device_ids)
            
            # Notify callbacks about changes
            added = self._selected_devices - old_selection
            removed = old_selection - self._selected_devices
            
            for device_id in added:
                self._notify_access_change(device_id, True)
            
            for device_id in removed:
                self._notify_access_change(device_id, False)
            
            self.logger.info(f"Selected devices: {self._selected_devices}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error selecting devices: {e}")
            return False
    
    def enable_all_devices(self) -> bool:
        """Enable all available devices"""
        return self.select_devices(list(self._available_devices.keys()))
    
    def enable_device(self, device_id: str) -> bool:
        """Enable a specific device"""
        if device_id not in self._available_devices:
            self.logger.error(f"Device not available: {device_id}")
            return False
        
        if device_id not in self._selected_devices:
            self._selected_devices.add(device_id)
            self._notify_access_change(device_id, True)
            self.logger.info(f"Enabled device: {device_id}")
        
        return True
    
    def disable_device(self, device_id: str) -> bool:
        """Disable a specific device"""
        if device_id in self._selected_devices:
            self._selected_devices.remove(device_id)
            self._notify_access_change(device_id, False)
            self.logger.info(f"Disabled device: {device_id}")
        
        return True
    
    def get_selected_devices(self) -> List[AudioDevice]:
        """Get currently selected devices"""
        return [self._available_devices[device_id] for device_id in self._selected_devices 
                if device_id in self._available_devices]
    
    def is_device_selected(self, device_id: str) -> bool:
        """Check if a device is selected"""
        return device_id in self._selected_devices
    
    def set_device_priority(self, device_id: str, priority: int) -> bool:
        """Set priority for a device"""
        if device_id not in self._available_devices:
            return False
        
        self._device_priorities[device_id] = priority
        self.logger.debug(f"Set priority {priority} for device {device_id}")
        return True
    
    def get_device_priority(self, device_id: str) -> int:
        """Get device priority"""
        return self._device_priorities.get(device_id, 0)
    
    def get_devices_by_priority(self) -> List[AudioDevice]:
        """Get selected devices sorted by priority"""
        selected_devices = self.get_selected_devices()
        return sorted(selected_devices, 
                     key=lambda d: self.get_device_priority(d.device_id), 
                     reverse=True)
    
    def register_access_callback(self, callback: Callable[[str, bool], None]):
        """Register callback for device access changes"""
        self._access_callbacks.append(callback)
    
    def _notify_access_change(self, device_id: str, enabled: bool):
        """Notify callbacks about access changes"""
        for callback in self._access_callbacks:
            try:
                callback(device_id, enabled)
            except Exception as e:
                self.logger.error(f"Error in access callback: {e}")


class MultiInputAudioCapture:
    """
    Multi-input audio capture that supports simultaneous capture and processing
    from multiple audio input devices
    """
    
    def __init__(self, config: InputConfiguration):
        self.config = config
        self.logger = logging.getLogger(__name__ + ".MultiInputAudioCapture")
        self._capture_streams: Dict[str, Any] = {}  # PyAudio streams
        self._capture_threads: Dict[str, threading.Thread] = {}
        self._audio_queues: Dict[str, queue.Queue] = {}
        self._is_capturing = False
        self._stop_capture = threading.Event()
        self._frame_callbacks: List[Callable[[str, AudioFrame], None]] = []
        
        if not PYAUDIO_AVAILABLE:
            self.logger.error("PyAudio not available - capture functionality disabled")
    
    def start_capture(self, devices: List[AudioDevice], audio_config: Dict[str, Any]) -> bool:
        """Start multi-input audio capture"""
        if not PYAUDIO_AVAILABLE:
            self.logger.error("Cannot start capture - PyAudio not available")
            return False
        
        try:
            if self._is_capturing:
                self.logger.warning("Capture already running")
                return True
            
            self._stop_capture.clear()
            
            # Initialize PyAudio
            pa = pyaudio.PyAudio()
            
            # Start capture for each device
            for device in devices:
                device_index = int(device.device_id.split('_')[1])
                
                try:
                    # Create audio queue
                    self._audio_queues[device.device_id] = queue.Queue(maxsize=self.config.max_buffer_count)
                    
                    # Open audio stream
                    stream = pa.open(
                        format=pyaudio.paInt16,  # 16-bit audio
                        channels=min(device.max_input_channels, audio_config.get('channels', 2)),
                        rate=audio_config.get('sample_rate', 48000),
                        input=True,
                        input_device_index=device_index,
                        frames_per_buffer=self.config.buffer_size_frames,
                        stream_callback=lambda in_data, frame_count, time_info, status, dev_id=device.device_id: 
                            self._audio_callback(in_data, frame_count, time_info, status, dev_id)
                    )
                    
                    self._capture_streams[device.device_id] = stream
                    stream.start_stream()
                    
                    self.logger.info(f"Started capture for device: {device.name}")
                    
                except Exception as e:
                    self.logger.error(f"Failed to start capture for device {device.device_id}: {e}")
                    continue
            
            if self._capture_streams:
                self._is_capturing = True
                self.logger.info(f"Started multi-input capture for {len(self._capture_streams)} devices")
                return True
            else:
                self.logger.error("No devices successfully started")
                return False
                
        except Exception as e:
            self.logger.error(f"Error starting capture: {e}")
            return False
    
    def stop_capture(self) -> bool:
        """Stop multi-input audio capture"""
        try:
            if not self._is_capturing:
                return True
            
            self._stop_capture.set()
            self._is_capturing = False
            
            # Stop and close all streams
            for device_id, stream in self._capture_streams.items():
                try:
                    if stream.is_active():
                        stream.stop_stream()
                    stream.close()
                    self.logger.debug(f"Stopped capture for device: {device_id}")
                except Exception as e:
                    self.logger.error(f"Error stopping stream for {device_id}: {e}")
            
            self._capture_streams.clear()
            self._audio_queues.clear()
            
            self.logger.info("Stopped multi-input audio capture")
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping capture: {e}")
            return False
    
    def get_audio_frame(self, device_id: str, timeout: float = 0.1) -> Optional[AudioFrame]:
        """Get audio frame from specific device"""
        if device_id not in self._audio_queues:
            return None
        
        try:
            audio_data = self._audio_queues[device_id].get(timeout=timeout)
            return audio_data
        except queue.Empty:
            return None
    
    def register_frame_callback(self, callback: Callable[[str, AudioFrame], None]):
        """Register callback for audio frame events"""
        self._frame_callbacks.append(callback)
    
    def is_capturing(self) -> bool:
        """Check if capture is active"""
        return self._is_capturing
    
    def get_capture_status(self) -> Dict[str, Dict[str, Any]]:
        """Get capture status for all devices"""
        status = {}
        for device_id in self._capture_streams:
            stream = self._capture_streams[device_id]
            queue_obj = self._audio_queues.get(device_id)
            
            status[device_id] = {
                'is_active': stream.is_active() if stream else False,
                'queue_size': queue_obj.qsize() if queue_obj else 0,
                'queue_full': queue_obj.full() if queue_obj else False
            }
        
        return status
    
    def _audio_callback(self, in_data: bytes, frame_count: int, time_info: Dict, status: int, device_id: str):
        """Audio callback for PyAudio stream"""
        try:
            # Create audio frame
            import numpy as np
            audio_array = np.frombuffer(in_data, dtype=np.int16)
            
            frame = AudioFrame(
                frame_id=int(time.time() * 1000000),  # Microsecond timestamp as ID
                timestamp=datetime.now(),
                sample_rate=48000,  # TODO: Get from actual config
                channels=1 if len(audio_array.shape) == 1 else audio_array.shape[1],
                bit_depth=16,
                data=audio_array,
                frame_size=frame_count
            )
            
            # Add to queue if not full
            queue_obj = self._audio_queues.get(device_id)
            if queue_obj and not queue_obj.full():
                queue_obj.put_nowait(frame)
            
            # Notify callbacks
            for callback in self._frame_callbacks:
                try:
                    callback(device_id, frame)
                except Exception as e:
                    self.logger.error(f"Error in frame callback: {e}")
            
            return (None, pyaudio.paContinue)
            
        except Exception as e:
            self.logger.error(f"Error in audio callback for {device_id}: {e}")
            return (None, pyaudio.paAbort)


class InputDeviceManager:
    """
    Input device manager for dynamic enable/disable, priority settings,
    and processing strategy configuration
    """
    
    def __init__(self, config: InputConfiguration):
        self.config = config
        self.logger = logging.getLogger(__name__ + ".InputDeviceManager")
        self._device_status: Dict[str, InputDeviceStatus] = {}
        self._processing_strategies: Dict[str, str] = {}
        self._status_callbacks: List[Callable[[str, InputDeviceStatus], None]] = []
    
    def add_device(self, device: AudioDevice) -> bool:
        """Add device to management"""
        try:
            status = InputDeviceStatus(
                device_id=device.device_id,
                state=InputDeviceState.AVAILABLE,
                is_enabled=self.config.enable_all_by_default
            )
            
            self._device_status[device.device_id] = status
            self._processing_strategies[device.device_id] = "default"
            
            self.logger.info(f"Added device to management: {device.name}")
            self._notify_status_change(device.device_id, status)
            return True
            
        except Exception as e:
            self.logger.error(f"Error adding device {device.device_id}: {e}")
            return False
    
    def remove_device(self, device_id: str) -> bool:
        """Remove device from management"""
        if device_id in self._device_status:
            del self._device_status[device_id]
            del self._processing_strategies[device_id]
            self.logger.info(f"Removed device from management: {device_id}")
            return True
        return False
    
    def enable_device(self, device_id: str) -> bool:
        """Enable device for processing"""
        if device_id not in self._device_status:
            return False
        
        status = self._device_status[device_id]
        if status.state == InputDeviceState.AVAILABLE:
            status.is_enabled = True
            status.state = InputDeviceState.ACTIVE
            self.logger.info(f"Enabled device: {device_id}")
            self._notify_status_change(device_id, status)
            return True
        
        return False
    
    def disable_device(self, device_id: str) -> bool:
        """Disable device for processing"""
        if device_id not in self._device_status:
            return False
        
        status = self._device_status[device_id]
        status.is_enabled = False
        status.state = InputDeviceState.INACTIVE
        self.logger.info(f"Disabled device: {device_id}")
        self._notify_status_change(device_id, status)
        return True
    
    def set_device_priority(self, device_id: str, priority: int) -> bool:
        """Set device priority"""
        if device_id not in self._device_status:
            return False
        
        self._device_status[device_id].priority = priority
        self.logger.debug(f"Set priority {priority} for device {device_id}")
        return True
    
    def set_device_gain(self, device_id: str, gain_db: float) -> bool:
        """Set device gain"""
        if device_id not in self._device_status:
            return False
        
        self._device_status[device_id].gain_db = gain_db
        self.logger.debug(f"Set gain {gain_db}dB for device {device_id}")
        return True
    
    def mute_device(self, device_id: str, muted: bool) -> bool:
        """Mute/unmute device"""
        if device_id not in self._device_status:
            return False
        
        self._device_status[device_id].is_muted = muted
        self.logger.info(f"{'Muted' if muted else 'Unmuted'} device: {device_id}")
        return True
    
    def set_processing_strategy(self, device_id: str, strategy: str) -> bool:
        """Set processing strategy for device"""
        if device_id not in self._device_status:
            return False
        
        self._processing_strategies[device_id] = strategy
        self.logger.debug(f"Set processing strategy '{strategy}' for device {device_id}")
        return True
    
    def get_device_status(self, device_id: str) -> Optional[InputDeviceStatus]:
        """Get device status"""
        return self._device_status.get(device_id)
    
    def get_all_device_status(self) -> Dict[str, InputDeviceStatus]:
        """Get status of all managed devices"""
        return self._device_status.copy()
    
    def get_enabled_devices(self) -> List[str]:
        """Get list of enabled device IDs"""
        return [device_id for device_id, status in self._device_status.items() 
                if status.is_enabled and status.state == InputDeviceState.ACTIVE]
    
    def update_device_metrics(self, device_id: str, signal_strength: float, 
                            noise_level: float, connection_quality: float):
        """Update device quality metrics"""
        if device_id in self._device_status:
            status = self._device_status[device_id]
            status.update_quality_metrics(signal_strength, noise_level, connection_quality)
            self._notify_status_change(device_id, status)
    
    def record_device_frame(self, device_id: str, timestamp: datetime):
        """Record successful frame capture"""
        if device_id in self._device_status:
            self._device_status[device_id].record_frame(timestamp)
    
    def record_device_error(self, device_id: str, error_message: str):
        """Record device error"""
        if device_id in self._device_status:
            status = self._device_status[device_id]
            status.record_error(error_message)
            self._notify_status_change(device_id, status)
    
    def register_status_callback(self, callback: Callable[[str, InputDeviceStatus], None]):
        """Register callback for status changes"""
        self._status_callbacks.append(callback)
    
    def _notify_status_change(self, device_id: str, status: InputDeviceStatus):
        """Notify callbacks about status changes"""
        for callback in self._status_callbacks:
            try:
                callback(device_id, status)
            except Exception as e:
                self.logger.error(f"Error in status callback: {e}")


class MultiInputSynchronizationCoordinator:
    """
    Multi-input synchronization coordinator that ensures precise time synchronization
    and frame alignment between multiple inputs
    """
    
    def __init__(self, config: InputConfiguration):
        self.config = config
        self.logger = logging.getLogger(__name__ + ".MultiInputSynchronizationCoordinator")
        self._sync_buffers: Dict[str, List[AudioFrame]] = {}
        self._reference_device: Optional[str] = None
        self._sync_lock = threading.Lock()
        self._frame_counters: Dict[str, int] = {}
        self._time_offsets: Dict[str, float] = {}
        self._sync_callbacks: List[Callable[[Dict[str, AudioFrame]], None]] = []
    
    def add_input_device(self, device_id: str):
        """Add input device to synchronization"""
        with self._sync_lock:
            self._sync_buffers[device_id] = []
            self._frame_counters[device_id] = 0
            self._time_offsets[device_id] = 0.0
            
            # Set first device as reference
            if self._reference_device is None:
                self._reference_device = device_id
                self.logger.info(f"Set reference device: {device_id}")
    
    def remove_input_device(self, device_id: str):
        """Remove input device from synchronization"""
        with self._sync_lock:
            if device_id in self._sync_buffers:
                del self._sync_buffers[device_id]
                del self._frame_counters[device_id]
                del self._time_offsets[device_id]
                
                # Update reference device if needed
                if self._reference_device == device_id:
                    remaining_devices = list(self._sync_buffers.keys())
                    self._reference_device = remaining_devices[0] if remaining_devices else None
                    if self._reference_device:
                        self.logger.info(f"Updated reference device: {self._reference_device}")
    
    def add_frame(self, device_id: str, frame: AudioFrame):
        """Add frame for synchronization"""
        if device_id not in self._sync_buffers:
            return
        
        with self._sync_lock:
            # Add frame to buffer
            self._sync_buffers[device_id].append(frame)
            self._frame_counters[device_id] += 1
            
            # Limit buffer size
            max_buffer_size = self.config.max_buffer_count
            if len(self._sync_buffers[device_id]) > max_buffer_size:
                self._sync_buffers[device_id].pop(0)
            
            # Try to synchronize frames
            self._try_synchronize()
    
    def _try_synchronize(self):
        """Try to synchronize frames from all devices"""
        if not self._reference_device or len(self._sync_buffers) < 2:
            return
        
        # Check if all devices have frames
        if not all(len(buffer) > 0 for buffer in self._sync_buffers.values()):
            return
        
        if self.config.sync_mode == SynchronizationMode.NONE:
            # No synchronization - just take latest frames
            synchronized_frames = {}
            for device_id, buffer in self._sync_buffers.items():
                if buffer:
                    synchronized_frames[device_id] = buffer.pop(0)
            
            if synchronized_frames:
                self._notify_synchronized_frames(synchronized_frames)
        
        elif self.config.sync_mode == SynchronizationMode.TIMESTAMP:
            # Timestamp-based synchronization
            self._synchronize_by_timestamp()
        
        elif self.config.sync_mode == SynchronizationMode.SOFTWARE_SYNC:
            # Software synchronization with drift compensation
            self._synchronize_with_drift_compensation()
    
    def _synchronize_by_timestamp(self):
        """Synchronize frames by timestamp"""
        reference_buffer = self._sync_buffers[self._reference_device]
        if not reference_buffer:
            return
        
        reference_frame = reference_buffer[0]
        reference_time = reference_frame.timestamp
        tolerance = timedelta(milliseconds=self.config.sync_tolerance_ms)
        
        synchronized_frames = {self._reference_device: reference_frame}
        
        # Find matching frames from other devices
        for device_id, buffer in self._sync_buffers.items():
            if device_id == self._reference_device:
                continue
            
            best_frame = None
            best_diff = None
            best_index = -1
            
            for i, frame in enumerate(buffer):
                time_diff = abs((frame.timestamp - reference_time).total_seconds() * 1000)
                if time_diff <= self.config.sync_tolerance_ms:
                    if best_frame is None or time_diff < best_diff:
                        best_frame = frame
                        best_diff = time_diff
                        best_index = i
            
            if best_frame:
                synchronized_frames[device_id] = best_frame
                # Remove synchronized frame and any older frames
                self._sync_buffers[device_id] = buffer[best_index + 1:]
        
        # Only proceed if we have frames from all devices
        if len(synchronized_frames) == len(self._sync_buffers):
            # Remove reference frame
            self._sync_buffers[self._reference_device].pop(0)
            self._notify_synchronized_frames(synchronized_frames)
    
    def _synchronize_with_drift_compensation(self):
        """Synchronize with drift compensation"""
        # This is a simplified implementation
        # In production, this would include more sophisticated drift detection and compensation
        self._synchronize_by_timestamp()
    
    def get_synchronization_status(self) -> Dict[str, Any]:
        """Get synchronization status"""
        with self._sync_lock:
            status = {
                'reference_device': self._reference_device,
                'sync_mode': self.config.sync_mode.value,
                'device_count': len(self._sync_buffers),
                'buffer_sizes': {device_id: len(buffer) for device_id, buffer in self._sync_buffers.items()},
                'frame_counters': self._frame_counters.copy(),
                'time_offsets': self._time_offsets.copy()
            }
        
        return status
    
    def register_sync_callback(self, callback: Callable[[Dict[str, AudioFrame]], None]):
        """Register callback for synchronized frames"""
        self._sync_callbacks.append(callback)
    
    def _notify_synchronized_frames(self, frames: Dict[str, AudioFrame]):
        """Notify callbacks about synchronized frames"""
        for callback in self._sync_callbacks:
            try:
                callback(frames)
            except Exception as e:
                self.logger.error(f"Error in sync callback: {e}")


class InputQualityMonitor:
    """
    Input quality monitor for real-time monitoring of audio quality,
    connection status, and signal strength
    """
    
    def __init__(self, config: InputConfiguration):
        self.config = config
        self.logger = logging.getLogger(__name__ + ".InputQualityMonitor")
        self._monitoring_active = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitoring = threading.Event()
        self._quality_data: Dict[str, Dict[str, Any]] = {}
        self._quality_callbacks: List[Callable[[str, Dict[str, Any]], None]] = []
        self._device_manager: Optional[InputDeviceManager] = None
    
    def set_device_manager(self, device_manager: InputDeviceManager):
        """Set device manager for quality updates"""
        self._device_manager = device_manager
    
    def start_monitoring(self) -> bool:
        """Start quality monitoring"""
        try:
            if self._monitoring_active:
                return True
            
            self._stop_monitoring.clear()
            self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._monitor_thread.start()
            self._monitoring_active = True
            
            self.logger.info("Started input quality monitoring")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start monitoring: {e}")
            return False
    
    def stop_monitoring(self):
        """Stop quality monitoring"""
        self._stop_monitoring.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2.0)
        self._monitoring_active = False
        self.logger.info("Stopped input quality monitoring")
    
    def update_frame_quality(self, device_id: str, frame: AudioFrame):
        """Update quality metrics from audio frame"""
        if device_id not in self._quality_data:
            self._quality_data[device_id] = {
                'signal_strength': 0.0,
                'noise_level_db': -60.0,
                'connection_quality': 1.0,
                'frame_count': 0,
                'last_update': datetime.now()
            }
        
        quality = self._quality_data[device_id]
        
        # Calculate signal strength (simplified)
        if hasattr(frame, 'peak_level_db'):
            signal_strength = max(0.0, min(1.0, (frame.peak_level_db + 60) / 60))
        else:
            signal_strength = 0.5  # Default value
        
        # Update metrics
        quality['signal_strength'] = signal_strength
        quality['noise_level_db'] = getattr(frame, 'rms_level_db', -60.0)
        quality['frame_count'] += 1
        quality['last_update'] = datetime.now()
        
        # Update device manager if available
        if self._device_manager:
            self._device_manager.update_device_metrics(
                device_id, signal_strength, quality['noise_level_db'], quality['connection_quality']
            )
        
        # Notify callbacks
        self._notify_quality_update(device_id, quality)
    
    def get_quality_metrics(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Get quality metrics for a device"""
        return self._quality_data.get(device_id)
    
    def get_all_quality_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get quality metrics for all devices"""
        return self._quality_data.copy()
    
    def register_quality_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """Register callback for quality updates"""
        self._quality_callbacks.append(callback)
    
    def _monitor_loop(self):
        """Quality monitoring loop"""
        while not self._stop_monitoring.is_set():
            try:
                current_time = datetime.now()
                
                # Check for stale connections
                for device_id, quality in self._quality_data.items():
                    time_since_update = (current_time - quality['last_update']).total_seconds()
                    
                    if time_since_update > 5.0:  # 5 seconds timeout
                        quality['connection_quality'] = max(0.0, 1.0 - (time_since_update - 5.0) / 10.0)
                        
                        if self._device_manager:
                            self._device_manager.update_device_metrics(
                                device_id, quality['signal_strength'], 
                                quality['noise_level_db'], quality['connection_quality']
                            )
                
            except Exception as e:
                self.logger.error(f"Error in monitor loop: {e}")
            
            # Wait for next check
            self._stop_monitoring.wait(self.config.quality_check_interval_ms / 1000.0)
    
    def _notify_quality_update(self, device_id: str, quality: Dict[str, Any]):
        """Notify callbacks about quality updates"""
        for callback in self._quality_callbacks:
            try:
                callback(device_id, quality)
            except Exception as e:
                self.logger.error(f"Error in quality callback: {e}")


class HotPlugSupport:
    """
    Hot-plug support for automatic device list updates and processing chain adjustments
    when devices are plugged in or removed
    """
    
    def __init__(self, config: InputConfiguration):
        self.config = config
        self.logger = logging.getLogger(__name__ + ".HotPlugSupport")
        self._detector: Optional[DynamicAudioInputDetector] = None
        self._access_manager: Optional[SelectiveAudioAccessManager] = None
        self._device_manager: Optional[InputDeviceManager] = None
        self._capture: Optional[MultiInputAudioCapture] = None
        self._hotplug_callbacks: List[Callable[[str, AudioDevice, bool], None]] = []
    
    def set_components(self, detector: DynamicAudioInputDetector, 
                      access_manager: SelectiveAudioAccessManager,
                      device_manager: InputDeviceManager,
                      capture: MultiInputAudioCapture):
        """Set component references"""
        self._detector = detector
        self._access_manager = access_manager
        self._device_manager = device_manager
        self._capture = capture
        
        # Register for device detection events
        if self._detector:
            self._detector.register_detection_callback(self._handle_device_changes)
    
    def _handle_device_changes(self, current_devices: List[AudioDevice]):
        """Handle device changes from detector"""
        if not self._access_manager or not self._device_manager:
            return
        
        try:
            # Get previously known devices
            previous_devices = set(self._device_manager.get_all_device_status().keys())
            current_device_ids = {device.device_id for device in current_devices}
            
            # Find added and removed devices
            added_devices = current_device_ids - previous_devices
            removed_devices = previous_devices - current_device_ids
            
            # Handle added devices
            for device in current_devices:
                if device.device_id in added_devices:
                    self._handle_device_added(device)
            
            # Handle removed devices
            for device_id in removed_devices:
                self._handle_device_removed(device_id)
            
            # Update access manager with current devices
            self._access_manager.set_available_devices(current_devices)
            
        except Exception as e:
            self.logger.error(f"Error handling device changes: {e}")
    
    def _handle_device_added(self, device: AudioDevice):
        """Handle device addition"""
        try:
            # Add to device manager
            if self._device_manager:
                self._device_manager.add_device(device)
            
            self.logger.info(f"Hot-plugged device added: {device.name}")
            
            # Notify callbacks
            for callback in self._hotplug_callbacks:
                try:
                    callback(device.device_id, device, True)
                except Exception as e:
                    self.logger.error(f"Error in hotplug callback: {e}")
            
            # If auto-enable is configured and capture is running, start capture for new device
            if (self.config.enable_all_by_default and 
                self._capture and self._capture.is_capturing()):
                # This would require restarting capture with new device list
                # For now, just log the event
                self.logger.info(f"New device available for capture: {device.device_id}")
            
        except Exception as e:
            self.logger.error(f"Error handling device addition: {e}")
    
    def _handle_device_removed(self, device_id: str):
        """Handle device removal"""
        try:
            # Remove from device manager
            if self._device_manager:
                device_status = self._device_manager.get_device_status(device_id)
                self._device_manager.remove_device(device_id)
            
            self.logger.info(f"Hot-plugged device removed: {device_id}")
            
            # Notify callbacks
            for callback in self._hotplug_callbacks:
                try:
                    callback(device_id, None, False)
                except Exception as e:
                    self.logger.error(f"Error in hotplug callback: {e}")
            
            # If device was being captured, handle gracefully
            if self._capture and self._capture.is_capturing():
                capture_status = self._capture.get_capture_status()
                if device_id in capture_status:
                    self.logger.warning(f"Captured device removed: {device_id}")
                    # In a full implementation, this would trigger capture restart
            
        except Exception as e:
            self.logger.error(f"Error handling device removal: {e}")
    
    def register_hotplug_callback(self, callback: Callable[[str, Optional[AudioDevice], bool], None]):
        """Register callback for hot-plug events"""
        self._hotplug_callbacks.append(callback)
    
    def is_enabled(self) -> bool:
        """Check if hot-plug support is enabled"""
        return self.config.enable_hot_plug


class InputConfigurationVisualizationUI:
    """
    Visualization UI for graphical display of audio input devices and configuration
    """
    
    def __init__(self, config: InputConfiguration):
        self.config = config
        self.logger = logging.getLogger(__name__ + ".InputConfigurationVisualizationUI")
        self._device_manager: Optional[InputDeviceManager] = None
        self._quality_monitor: Optional[InputQualityMonitor] = None
        self._ui_data: Dict[str, Any] = {}
        self._ui_callbacks: List[Callable[[Dict[str, Any]], None]] = []
    
    def set_components(self, device_manager: InputDeviceManager, quality_monitor: InputQualityMonitor):
        """Set component references"""
        self._device_manager = device_manager
        self._quality_monitor = quality_monitor
        
        # Register for status updates
        if self._device_manager:
            self._device_manager.register_status_callback(self._handle_status_update)
        
        if self._quality_monitor:
            self._quality_monitor.register_quality_callback(self._handle_quality_update)
    
    def get_ui_data(self) -> Dict[str, Any]:
        """Get current UI data"""
        ui_data = {
            'devices': [],
            'system_status': {
                'total_devices': 0,
                'active_devices': 0,
                'error_devices': 0
            },
            'last_update': datetime.now().isoformat()
        }
        
        if not self._device_manager:
            return ui_data
        
        # Get device status
        all_status = self._device_manager.get_all_device_status()
        ui_data['system_status']['total_devices'] = len(all_status)
        
        for device_id, status in all_status.items():
            # Get quality metrics
            quality = {}
            if self._quality_monitor:
                quality = self._quality_monitor.get_quality_metrics(device_id) or {}
            
            device_ui_data = {
                'device_id': device_id,
                'state': status.state.value,
                'is_enabled': status.is_enabled,
                'priority': status.priority,
                'gain_db': status.gain_db,
                'is_muted': status.is_muted,
                'signal_strength': quality.get('signal_strength', 0.0),
                'noise_level_db': quality.get('noise_level_db', -60.0),
                'connection_quality': quality.get('connection_quality', 1.0),
                'frames_captured': status.frames_captured,
                'frames_dropped': status.frames_dropped,
                'error_count': status.error_count,
                'last_error': status.last_error
            }
            
            ui_data['devices'].append(device_ui_data)
            
            # Update system status
            if status.state == InputDeviceState.ACTIVE:
                ui_data['system_status']['active_devices'] += 1
            elif status.state == InputDeviceState.ERROR:
                ui_data['system_status']['error_devices'] += 1
        
        self._ui_data = ui_data
        return ui_data
    
    def get_device_visualization_data(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Get visualization data for specific device"""
        if not self._quality_monitor:
            return None
        
        quality = self._quality_monitor.get_quality_metrics(device_id)
        if not quality:
            return None
        
        return {
            'device_id': device_id,
            'waveform_data': [],  # Placeholder for waveform data
            'spectrum_data': [],  # Placeholder for spectrum data
            'level_meters': {
                'peak': quality.get('signal_strength', 0.0),
                'rms': max(0.0, (quality.get('noise_level_db', -60.0) + 60) / 60)
            },
            'quality_indicators': {
                'signal_strength': quality.get('signal_strength', 0.0),
                'noise_level': quality.get('noise_level_db', -60.0),
                'connection_quality': quality.get('connection_quality', 1.0)
            }
        }
    
    def register_ui_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Register callback for UI updates"""
        self._ui_callbacks.append(callback)
    
    def _handle_status_update(self, device_id: str, status: InputDeviceStatus):
        """Handle device status updates"""
        # Update UI data and notify callbacks
        ui_data = self.get_ui_data()
        self._notify_ui_update(ui_data)
    
    def _handle_quality_update(self, device_id: str, quality: Dict[str, Any]):
        """Handle quality updates"""
        # Update UI data and notify callbacks
        ui_data = self.get_ui_data()
        self._notify_ui_update(ui_data)
    
    def _notify_ui_update(self, ui_data: Dict[str, Any]):
        """Notify callbacks about UI updates"""
        for callback in self._ui_callbacks:
            try:
                callback(ui_data)
            except Exception as e:
                self.logger.error(f"Error in UI callback: {e}")