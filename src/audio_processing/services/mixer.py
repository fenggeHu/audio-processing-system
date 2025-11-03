"""
Classroom Mixer Service for dual-output audio routing and processing.

This module implements the ClassroomMixerService with intelligent mixing,
dual-path routing (PA/recording), and real-time format conversion.
"""

import asyncio
import time
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple, Union, AsyncGenerator
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
from ..communication.audio_pipeline import AudioPipeline, PipelineNode

logger = structlog.get_logger(__name__)


class OutputType(Enum):
    """Audio output types for classroom system."""
    PA_SYSTEM = "pa_system"          # Public address/amplification output
    RECORDING = "recording"          # Recording/streaming output
    MONITOR = "monitor"              # Monitoring output
    BACKUP = "backup"                # Backup output


class MixingMode(Enum):
    """Mixing operation modes."""
    STEREO = "stereo"                # Stereo mixing
    MONO = "mono"                    # Mono mixing
    SURROUND = "surround"            # Surround sound mixing
    BINAURAL = "binaural"            # Binaural processing


class AudioFormat(Enum):
    """Supported audio formats."""
    PCM_16 = "pcm_16"               # 16-bit PCM
    PCM_24 = "pcm_24"               # 24-bit PCM
    PCM_32 = "pcm_32"               # 32-bit PCM
    FLOAT_32 = "float_32"           # 32-bit float
    COMPRESSED = "compressed"        # Compressed format


@dataclass
class MixerMetrics:
    """Mixer performance metrics."""
    frames_mixed: int = 0
    pa_frames_output: int = 0
    recording_frames_output: int = 0
    format_conversions: int = 0
    routing_latency_ms: float = 0.0
    mixing_latency_ms: float = 0.0
    pa_level_dbfs: float = -60.0
    recording_level_dbfs: float = -60.0
    crossfade_active: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            'frames_mixed': self.frames_mixed,
            'pa_frames_output': self.pa_frames_output,
            'recording_frames_output': self.recording_frames_output,
            'format_conversions': self.format_conversions,
            'routing_latency_ms': self.routing_latency_ms,
            'mixing_latency_ms': self.mixing_latency_ms,
            'pa_level_dbfs': self.pa_level_dbfs,
            'recording_level_dbfs': self.recording_level_dbfs,
            'crossfade_active': self.crossfade_active
        }


@dataclass
class OutputConfig:
    """Configuration for audio output channel."""
    output_type: OutputType
    sample_rate: int = 48000
    channels: int = 2
    format: AudioFormat = AudioFormat.PCM_16
    buffer_size: int = 1024
    target_level_dbfs: float = -18.0
    limiter_threshold_dbfs: float = -3.0
    enable_processing: bool = True
    
    # PA-specific settings
    pa_eq_enabled: bool = True
    pa_compressor_enabled: bool = True
    pa_limiter_enabled: bool = True
    
    # Recording-specific settings
    recording_stereo_width: float = 1.0
    recording_room_tone: bool = True
    recording_noise_gate: bool = True


class AudioRouter:
    """
    Audio routing system for classroom mixer.
    
    Manages routing of audio signals to different outputs
    with independent processing chains.
    """
    
    def __init__(self, sample_rate: int = 48000):
        self.sample_rate = sample_rate
        
        # Output queues for different destinations
        self.output_queues: Dict[OutputType, asyncio.Queue] = {}
        self.output_configs: Dict[OutputType, OutputConfig] = {}
        
        # Routing matrix
        self.routing_matrix: Dict[str, List[OutputType]] = {}
        
        # Processing chains for each output
        self.processing_chains: Dict[OutputType, List] = {}
        
        # Statistics
        self.routing_stats = {
            'frames_routed': 0,
            'routing_errors': 0,
            'queue_overflows': 0
        }
        
        logger.info("Audio router initialized")
    
    def add_output(self, output_type: OutputType, config: OutputConfig) -> None:
        """Add an output destination."""
        self.output_queues[output_type] = asyncio.Queue(maxsize=config.buffer_size)
        self.output_configs[output_type] = config
        self.processing_chains[output_type] = []
        
        logger.info("Output added", output_type=output_type.value, config=config)
    
    def remove_output(self, output_type: OutputType) -> None:
        """Remove an output destination."""
        if output_type in self.output_queues:
            del self.output_queues[output_type]
            del self.output_configs[output_type]
            del self.processing_chains[output_type]
            
            logger.info("Output removed", output_type=output_type.value)
    
    def set_routing(self, source: str, destinations: List[OutputType]) -> None:
        """Set routing for a source to multiple destinations."""
        self.routing_matrix[source] = destinations
        logger.info("Routing configured", source=source, 
                   destinations=[d.value for d in destinations])
    
    async def route_frame(self, source: str, frame: AudioFrame) -> Dict[OutputType, bool]:
        """
        Route audio frame to configured destinations.
        
        Args:
            source: Source identifier
            frame: Audio frame to route
            
        Returns:
            Dictionary mapping output types to success status
        """
        results = {}
        
        if source not in self.routing_matrix:
            logger.debug("No routing configured for source", source=source)
            return results
        
        destinations = self.routing_matrix[source]
        
        for output_type in destinations:
            try:
                # Apply output-specific processing
                processed_frame = await self._process_for_output(frame, output_type)
                
                # Queue frame for output
                queue = self.output_queues[output_type]
                
                try:
                    queue.put_nowait(processed_frame)
                    results[output_type] = True
                    self.routing_stats['frames_routed'] += 1
                    
                except asyncio.QueueFull:
                    logger.warning("Output queue full", output_type=output_type.value)
                    results[output_type] = False
                    self.routing_stats['queue_overflows'] += 1
                    
            except Exception as e:
                logger.error("Routing error", 
                           source=source, 
                           output_type=output_type.value, 
                           error=str(e))
                results[output_type] = False
                self.routing_stats['routing_errors'] += 1
        
        return results
    
    async def _process_for_output(self, frame: AudioFrame, 
                                output_type: OutputType) -> AudioFrame:
        """Apply output-specific processing to frame."""
        config = self.output_configs[output_type]
        processed_frame = frame.copy()
        
        # Format conversion if needed
        if processed_frame.sample_rate != config.sample_rate:
            processed_frame = processed_frame.resample(config.sample_rate)
        
        # Channel configuration
        if config.channels == 1 and processed_frame.channels > 1:
            processed_frame = processed_frame.to_mono()
        elif config.channels == 2 and processed_frame.channels == 1:
            processed_frame = self._mono_to_stereo(processed_frame)
        
        # Apply processing chain
        for processor in self.processing_chains[output_type]:
            processed_frame = await processor.process(processed_frame)
        
        return processed_frame
    
    def _mono_to_stereo(self, frame: AudioFrame) -> AudioFrame:
        """Convert mono frame to stereo."""
        if frame.channels != 1:
            return frame
        
        # Duplicate mono channel to create stereo
        stereo_data = np.repeat(frame.data, 2, axis=0)
        
        return AudioFrame(
            timestamp=frame.timestamp,
            sample_rate=frame.sample_rate,
            channels=2,
            frame_size=frame.frame_size,
            data=stereo_data,
            metadata=frame.metadata.copy() if frame.metadata else {}
        )
    
    async def get_output_frame(self, output_type: OutputType, 
                             timeout: Optional[float] = None) -> Optional[AudioFrame]:
        """Get frame from output queue."""
        if output_type not in self.output_queues:
            return None
        
        try:
            if timeout:
                return await asyncio.wait_for(
                    self.output_queues[output_type].get(), 
                    timeout=timeout
                )
            else:
                return await self.output_queues[output_type].get()
        except asyncio.TimeoutError:
            return None
    
    def get_routing_stats(self) -> Dict[str, Any]:
        """Get routing statistics."""
        return self.routing_stats.copy()


class FormatConverter:
    """
    Real-time audio format converter.
    
    Handles sample rate conversion, bit depth changes,
    and channel configuration adjustments.
    """
    
    def __init__(self):
        # Resampling filters cache
        self.resampling_filters: Dict[Tuple[int, int], Any] = {}
        
        # Dithering for bit depth reduction
        self.dither_generators: Dict[int, np.random.Generator] = {}
        
        # Format conversion statistics
        self.conversion_stats = {
            'sample_rate_conversions': 0,
            'bit_depth_conversions': 0,
            'channel_conversions': 0,
            'total_conversions': 0
        }
        
        logger.info("Format converter initialized")
    
    async def convert_format(self, frame: AudioFrame, 
                           target_config: OutputConfig) -> AudioFrame:
        """
        Convert audio frame to target format.
        
        Args:
            frame: Input audio frame
            target_config: Target format configuration
            
        Returns:
            Converted audio frame
        """
        converted_frame = frame.copy()
        
        # Sample rate conversion
        if frame.sample_rate != target_config.sample_rate:
            converted_frame = await self._convert_sample_rate(
                converted_frame, target_config.sample_rate
            )
            self.conversion_stats['sample_rate_conversions'] += 1
        
        # Channel conversion
        if frame.channels != target_config.channels:
            converted_frame = await self._convert_channels(
                converted_frame, target_config.channels
            )
            self.conversion_stats['channel_conversions'] += 1
        
        # Bit depth/format conversion
        converted_frame = await self._convert_bit_depth(
            converted_frame, target_config.format
        )
        self.conversion_stats['bit_depth_conversions'] += 1
        
        self.conversion_stats['total_conversions'] += 1
        
        return converted_frame
    
    async def _convert_sample_rate(self, frame: AudioFrame, 
                                 target_rate: int) -> AudioFrame:
        """Convert sample rate using high-quality resampling."""
        if frame.sample_rate == target_rate:
            return frame
        
        # Get or create resampling filter
        filter_key = (frame.sample_rate, target_rate)
        if filter_key not in self.resampling_filters:
            # Use scipy's resample_poly for high-quality resampling
            gcd_rate = math.gcd(frame.sample_rate, target_rate)
            up_factor = target_rate // gcd_rate
            down_factor = frame.sample_rate // gcd_rate
            self.resampling_filters[filter_key] = (up_factor, down_factor)
        
        up_factor, down_factor = self.resampling_filters[filter_key]
        
        # Resample each channel
        resampled_data = []
        for ch in range(frame.channels):
            resampled_channel = signal.resample_poly(
                frame.data[ch], up_factor, down_factor
            )
            resampled_data.append(resampled_channel)
        
        resampled_data = np.array(resampled_data)
        new_frame_size = resampled_data.shape[1]
        
        return AudioFrame(
            timestamp=frame.timestamp,
            sample_rate=target_rate,
            channels=frame.channels,
            frame_size=new_frame_size,
            data=resampled_data,
            metadata=frame.metadata.copy() if frame.metadata else {}
        )
    
    async def _convert_channels(self, frame: AudioFrame, 
                              target_channels: int) -> AudioFrame:
        """Convert channel configuration."""
        if frame.channels == target_channels:
            return frame
        
        if target_channels == 1:
            # Convert to mono by averaging channels
            mono_data = np.mean(frame.data, axis=0, keepdims=True)
            
        elif target_channels == 2 and frame.channels == 1:
            # Convert mono to stereo by duplicating
            mono_data = frame.data[0]
            stereo_data = np.array([mono_data, mono_data])
            mono_data = stereo_data
            
        elif target_channels > frame.channels:
            # Upmix by duplicating channels
            current_data = frame.data
            additional_channels = target_channels - frame.channels
            
            # Duplicate last channel for additional channels
            last_channel = current_data[-1:, :]
            additional_data = np.repeat(last_channel, additional_channels, axis=0)
            mono_data = np.vstack([current_data, additional_data])
            
        else:
            # Downmix by selecting first N channels
            mono_data = frame.data[:target_channels, :]
        
        return AudioFrame(
            timestamp=frame.timestamp,
            sample_rate=frame.sample_rate,
            channels=target_channels,
            frame_size=frame.frame_size,
            data=mono_data,
            metadata=frame.metadata.copy() if frame.metadata else {}
        )
    
    async def _convert_bit_depth(self, frame: AudioFrame, 
                               target_format: AudioFormat) -> AudioFrame:
        """Convert bit depth and format."""
        # For now, keep data as float32 internally
        # Actual bit depth conversion would happen at output stage
        converted_frame = frame.copy()
        
        # Add format information to metadata
        if not converted_frame.metadata:
            converted_frame.metadata = {}
        converted_frame.metadata['target_format'] = target_format.value
        
        return converted_frame
    
    def get_conversion_stats(self) -> Dict[str, int]:
        """Get format conversion statistics."""
        return self.conversion_stats.copy()


class DualPathProcessor:
    """
    Dual-path audio processor for PA and recording outputs.
    
    Implements independent processing chains optimized for
    live sound reinforcement and high-quality recording.
    """
    
    def __init__(self, sample_rate: int = 48000):
        self.sample_rate = sample_rate
        
        # Processing parameters for each path
        self.pa_config = {
            'target_level_dbfs': -18.0,
            'limiter_threshold_dbfs': -3.0,
            'compressor_ratio': 3.0,
            'compressor_attack_ms': 5.0,
            'compressor_release_ms': 50.0,
            'eq_enabled': True,
            'high_freq_boost_db': 2.0,  # Enhance speech clarity
            'low_cut_freq_hz': 80.0     # Remove rumble
        }
        
        self.recording_config = {
            'target_level_dbfs': -23.0,  # More headroom for post-processing
            'limiter_threshold_dbfs': -6.0,
            'compressor_ratio': 2.0,     # Gentler compression
            'compressor_attack_ms': 10.0,
            'compressor_release_ms': 100.0,
            'stereo_width': 1.0,
            'room_tone_level_db': -45.0,
            'noise_gate_threshold_dbfs': -50.0
        }
        
        # Processing state
        self.pa_compressor_state = self._init_compressor_state()
        self.recording_compressor_state = self._init_compressor_state()
        
        # EQ filters
        self.pa_eq_filters = self._init_eq_filters('pa')
        self.recording_eq_filters = self._init_eq_filters('recording')
        
        logger.info("Dual-path processor initialized")
    
    def _init_compressor_state(self) -> Dict[str, float]:
        """Initialize compressor state variables."""
        return {
            'envelope': 0.0,
            'gain_reduction_db': 0.0,
            'attack_coeff': 0.0,
            'release_coeff': 0.0
        }
    
    def _init_eq_filters(self, path: str) -> Dict[str, Any]:
        """Initialize EQ filters for processing path."""
        # Placeholder for EQ filter initialization
        # In production, would use proper filter design
        return {
            'high_shelf': None,
            'low_cut': None,
            'parametric_bands': []
        }
    
    async def process_pa_path(self, frame: AudioFrame) -> AudioFrame:
        """
        Process audio for PA system output.
        
        Optimized for live sound reinforcement:
        - Fast attack compression for feedback prevention
        - High-frequency enhancement for speech clarity
        - Aggressive limiting to protect speakers
        """
        processed_frame = frame.copy()
        
        # 1. Low-cut filter to remove rumble
        processed_frame = self._apply_low_cut_filter(
            processed_frame, self.pa_config['low_cut_freq_hz']
        )
        
        # 2. EQ for speech enhancement
        if self.pa_config['eq_enabled']:
            processed_frame = self._apply_pa_eq(processed_frame)
        
        # 3. Fast compressor for level control
        processed_frame = self._apply_compressor(
            processed_frame, self.pa_config, self.pa_compressor_state
        )
        
        # 4. Aggressive limiter for speaker protection
        processed_frame = self._apply_limiter(
            processed_frame, self.pa_config['limiter_threshold_dbfs']
        )
        
        # Add processing metadata
        if not processed_frame.metadata:
            processed_frame.metadata = {}
        processed_frame.metadata.update({
            'pa_processed': True,
            'pa_target_level': self.pa_config['target_level_dbfs'],
            'pa_gain_reduction': self.pa_compressor_state['gain_reduction_db']
        })
        
        return processed_frame
    
    async def process_recording_path(self, frame: AudioFrame) -> AudioFrame:
        """
        Process audio for recording output.
        
        Optimized for high-quality recording:
        - Gentle compression preserving dynamics
        - Wider stereo image for immersive recording
        - More headroom for post-production
        """
        processed_frame = frame.copy()
        
        # 1. Noise gate to remove low-level noise
        processed_frame = self._apply_noise_gate(
            processed_frame, self.recording_config['noise_gate_threshold_dbfs']
        )
        
        # 2. Gentle EQ for natural sound
        processed_frame = self._apply_recording_eq(processed_frame)
        
        # 3. Gentle compressor preserving dynamics
        processed_frame = self._apply_compressor(
            processed_frame, self.recording_config, self.recording_compressor_state
        )
        
        # 4. Stereo width enhancement
        if processed_frame.channels >= 2:
            processed_frame = self._apply_stereo_width(
                processed_frame, self.recording_config['stereo_width']
            )
        
        # 5. Gentle limiter with more headroom
        processed_frame = self._apply_limiter(
            processed_frame, self.recording_config['limiter_threshold_dbfs']
        )
        
        # Add processing metadata
        if not processed_frame.metadata:
            processed_frame.metadata = {}
        processed_frame.metadata.update({
            'recording_processed': True,
            'recording_target_level': self.recording_config['target_level_dbfs'],
            'recording_gain_reduction': self.recording_compressor_state['gain_reduction_db'],
            'stereo_width': self.recording_config['stereo_width']
        })
        
        return processed_frame
    
    def _apply_low_cut_filter(self, frame: AudioFrame, cutoff_hz: float) -> AudioFrame:
        """Apply low-cut filter to remove rumble and handling noise."""
        # Placeholder implementation
        # In production, would use proper high-pass filter
        return frame
    
    def _apply_pa_eq(self, frame: AudioFrame) -> AudioFrame:
        """Apply EQ optimized for PA system."""
        # Placeholder for PA-optimized EQ
        # Would enhance speech frequencies (1-4 kHz)
        return frame
    
    def _apply_recording_eq(self, frame: AudioFrame) -> AudioFrame:
        """Apply EQ optimized for recording."""
        # Placeholder for recording-optimized EQ
        # Would provide natural, balanced sound
        return frame
    
    def _apply_compressor(self, frame: AudioFrame, config: Dict[str, Any], 
                         state: Dict[str, float]) -> AudioFrame:
        """Apply dynamic range compression."""
        # Simplified compressor implementation
        # In production, would use proper envelope detection and gain reduction
        
        # Calculate input level
        input_level_db = frame.get_rms_level()
        target_level = config['target_level_dbfs']
        
        # Simple gain calculation
        if input_level_db > target_level:
            excess_db = input_level_db - target_level
            gain_reduction_db = excess_db / config['compressor_ratio']
            state['gain_reduction_db'] = gain_reduction_db
            
            # Apply gain reduction
            gain_linear = 10 ** (-gain_reduction_db / 20.0)
            compressed_data = frame.data * gain_linear
            
            return AudioFrame(
                timestamp=frame.timestamp,
                sample_rate=frame.sample_rate,
                channels=frame.channels,
                frame_size=frame.frame_size,
                data=compressed_data,
                metadata=frame.metadata.copy() if frame.metadata else {}
            )
        
        state['gain_reduction_db'] = 0.0
        return frame
    
    def _apply_limiter(self, frame: AudioFrame, threshold_dbfs: float) -> AudioFrame:
        """Apply hard limiter to prevent clipping."""
        # Simple peak limiter
        threshold_linear = 10 ** (threshold_dbfs / 20.0)
        
        # Find peaks above threshold
        peak_level = np.max(np.abs(frame.data))
        
        if peak_level > threshold_linear:
            # Apply limiting
            gain_reduction = threshold_linear / peak_level
            limited_data = frame.data * gain_reduction
            
            return AudioFrame(
                timestamp=frame.timestamp,
                sample_rate=frame.sample_rate,
                channels=frame.channels,
                frame_size=frame.frame_size,
                data=limited_data,
                metadata=frame.metadata.copy() if frame.metadata else {}
            )
        
        return frame
    
    def _apply_noise_gate(self, frame: AudioFrame, threshold_dbfs: float) -> AudioFrame:
        """Apply noise gate to remove low-level noise."""
        input_level_db = frame.get_rms_level()
        
        if input_level_db < threshold_dbfs:
            # Gate is closed - attenuate signal
            gate_attenuation = 0.1  # -20dB attenuation
            gated_data = frame.data * gate_attenuation
            
            return AudioFrame(
                timestamp=frame.timestamp,
                sample_rate=frame.sample_rate,
                channels=frame.channels,
                frame_size=frame.frame_size,
                data=gated_data,
                metadata=frame.metadata.copy() if frame.metadata else {}
            )
        
        return frame
    
    def _apply_stereo_width(self, frame: AudioFrame, width: float) -> AudioFrame:
        """Apply stereo width enhancement."""
        if frame.channels < 2:
            return frame
        
        # Simple M/S processing for stereo width
        left = frame.data[0, :]
        right = frame.data[1, :]
        
        # Convert to M/S
        mid = (left + right) / 2.0
        side = (left - right) / 2.0
        
        # Apply width adjustment
        side_adjusted = side * width
        
        # Convert back to L/R
        left_out = mid + side_adjusted
        right_out = mid - side_adjusted
        
        stereo_data = np.array([left_out, right_out])
        
        return AudioFrame(
            timestamp=frame.timestamp,
            sample_rate=frame.sample_rate,
            channels=frame.channels,
            frame_size=frame.frame_size,
            data=stereo_data,
            metadata=frame.metadata.copy() if frame.metadata else {}
        )


class ClassroomMixerService(BaseAudioProcessor):
    """
    Classroom Mixer Service for dual-output audio routing and processing.
    
    Provides intelligent mixing, dual-path routing (PA/recording),
    and real-time format conversion optimized for classroom environments.
    """
    
    def __init__(self, service_name: str, config: AudioConfig,
                 metrics_collector: Optional[IMetricsCollector] = None):
        super().__init__(service_name, config, metrics_collector)
        
        # Core components
        self.audio_router = AudioRouter(config.sample_rate)
        self.format_converter = FormatConverter()
        self.dual_path_processor = DualPathProcessor(config.sample_rate)
        
        # Output configurations
        self.output_configs = {
            OutputType.PA_SYSTEM: OutputConfig(
                output_type=OutputType.PA_SYSTEM,
                sample_rate=config.sample_rate,
                channels=2,  # Stereo for PA
                format=AudioFormat.PCM_16,
                target_level_dbfs=-18.0,
                pa_eq_enabled=True,
                pa_compressor_enabled=True,
                pa_limiter_enabled=True
            ),
            OutputType.RECORDING: OutputConfig(
                output_type=OutputType.RECORDING,
                sample_rate=config.sample_rate,
                channels=2,  # Stereo for recording
                format=AudioFormat.PCM_24,
                target_level_dbfs=-23.0,
                recording_stereo_width=1.2,
                recording_room_tone=True,
                recording_noise_gate=True
            )
        }
        
        # Performance metrics
        self.mixer_metrics = MixerMetrics()
        
        # Processing statistics
        self.frames_processed = 0
        self.pa_frames_sent = 0
        self.recording_frames_sent = 0
        
        # Background tasks
        self.output_tasks: Dict[OutputType, asyncio.Task] = {}
        
        logger.info(
            "Classroom Mixer Service initialized",
            service=service_name,
            sample_rate=config.sample_rate
        )
    
    async def _initialize(self) -> None:
        """Initialize mixer service."""
        logger.info("Initializing Classroom Mixer Service", service=self.service_name)
        
        # Setup output destinations
        for output_type, config in self.output_configs.items():
            self.audio_router.add_output(output_type, config)
        
        # Configure default routing
        self.audio_router.set_routing("main_input", [
            OutputType.PA_SYSTEM,
            OutputType.RECORDING
        ])
        
        # Start output processing tasks
        for output_type in self.output_configs.keys():
            task = asyncio.create_task(self._output_processor(output_type))
            self.output_tasks[output_type] = task
        
        # Reset metrics
        self.mixer_metrics = MixerMetrics()
        self.frames_processed = 0
        self.pa_frames_sent = 0
        self.recording_frames_sent = 0
    
    async def _cleanup(self) -> None:
        """Cleanup mixer service."""
        logger.info("Cleaning up Classroom Mixer Service", service=self.service_name)
        
        # Cancel output processing tasks
        for task in self.output_tasks.values():
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        if self.output_tasks:
            await asyncio.gather(*self.output_tasks.values(), return_exceptions=True)
        
        self.output_tasks.clear()
    
    async def _process_frame(self, frame: AudioFrame) -> AudioFrame:
        """
        Process audio frame through classroom mixer.
        
        Args:
            frame: Input audio frame
            
        Returns:
            Processed audio frame (pass-through for main chain)
        """
        self.frames_processed += 1
        start_time = time.time()
        
        try:
            # Route frame to all configured outputs
            routing_results = await self.audio_router.route_frame("main_input", frame)
            
            # Update metrics
            processing_time = (time.time() - start_time) * 1000  # ms
            self._update_mixer_metrics(frame, routing_results, processing_time)
            
            # Return original frame (mixer is a side-chain processor)
            return frame
            
        except Exception as e:
            logger.error("Error in mixer processing", 
                        service=self.service_name, error=str(e))
            return frame
    
    async def _output_processor(self, output_type: OutputType) -> None:
        """
        Background task to process output queue for specific output type.
        
        Args:
            output_type: Type of output to process
        """
        logger.info("Output processor started", 
                   service=self.service_name, output_type=output_type.value)
        
        while self._is_running:
            try:
                # Get frame from output queue
                frame = await self.audio_router.get_output_frame(
                    output_type, timeout=0.1
                )
                
                if frame is None:
                    continue
                
                # Apply output-specific processing
                if output_type == OutputType.PA_SYSTEM:
                    processed_frame = await self.dual_path_processor.process_pa_path(frame)
                    self.pa_frames_sent += 1
                    
                elif output_type == OutputType.RECORDING:
                    processed_frame = await self.dual_path_processor.process_recording_path(frame)
                    self.recording_frames_sent += 1
                    
                else:
                    processed_frame = frame
                
                # Format conversion if needed
                output_config = self.output_configs[output_type]
                final_frame = await self.format_converter.convert_format(
                    processed_frame, output_config
                )
                
                # Send to actual output (placeholder)
                await self._send_to_output_device(output_type, final_frame)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in output processor", 
                           output_type=output_type.value, error=str(e))
                await asyncio.sleep(0.001)
        
        logger.info("Output processor stopped", 
                   service=self.service_name, output_type=output_type.value)
    
    async def _send_to_output_device(self, output_type: OutputType, 
                                   frame: AudioFrame) -> None:
        """
        Send processed frame to actual output device.
        
        This is a placeholder for actual hardware/software output.
        In production, would interface with audio drivers or streaming APIs.
        """
        # Placeholder implementation
        # In production, would send to:
        # - Audio interface for PA system
        # - File writer or streaming encoder for recording
        pass
    
    def _update_mixer_metrics(self, frame: AudioFrame, 
                            routing_results: Dict[OutputType, bool],
                            processing_time_ms: float) -> None:
        """Update mixer performance metrics."""
        self.mixer_metrics.frames_mixed += 1
        self.mixer_metrics.routing_latency_ms = processing_time_ms
        
        # Update output frame counts
        if OutputType.PA_SYSTEM in routing_results and routing_results[OutputType.PA_SYSTEM]:
            self.mixer_metrics.pa_frames_output += 1
        
        if OutputType.RECORDING in routing_results and routing_results[OutputType.RECORDING]:
            self.mixer_metrics.recording_frames_output += 1
        
        # Update level measurements
        input_level = frame.get_rms_level()
        self.mixer_metrics.pa_level_dbfs = input_level  # Simplified
        self.mixer_metrics.recording_level_dbfs = input_level  # Simplified
    
    def set_output_config(self, output_type: OutputType, config: OutputConfig) -> None:
        """
        Update configuration for specific output.
        
        Args:
            output_type: Output type to configure
            config: New configuration
        """
        self.output_configs[output_type] = config
        
        # Update router configuration
        self.audio_router.remove_output(output_type)
        self.audio_router.add_output(output_type, config)
        
        logger.info("Output configuration updated", 
                   output_type=output_type.value, config=config)
    
    def set_routing_matrix(self, routing_matrix: Dict[str, List[OutputType]]) -> None:
        """
        Set custom routing matrix.
        
        Args:
            routing_matrix: Dictionary mapping sources to output destinations
        """
        for source, destinations in routing_matrix.items():
            self.audio_router.set_routing(source, destinations)
        
        logger.info("Routing matrix updated", routing_matrix=routing_matrix)
    
    def get_mixer_metrics(self) -> Dict[str, Any]:
        """
        Get mixer-specific metrics.
        
        Returns:
            Dictionary with mixer performance metrics
        """
        metrics = self.mixer_metrics.to_dict()
        
        # Add processing statistics
        metrics.update({
            'frames_processed': self.frames_processed,
            'pa_frames_sent': self.pa_frames_sent,
            'recording_frames_sent': self.recording_frames_sent,
            'routing_stats': self.audio_router.get_routing_stats(),
            'conversion_stats': self.format_converter.get_conversion_stats()
        })
        
        return metrics
    
    def get_output_levels(self) -> Dict[OutputType, float]:
        """
        Get current output levels for all outputs.
        
        Returns:
            Dictionary mapping output types to current levels in dBFS
        """
        return {
            OutputType.PA_SYSTEM: float(self.mixer_metrics.pa_level_dbfs),
            OutputType.RECORDING: float(self.mixer_metrics.recording_level_dbfs)
        }
    
    async def mute_output(self, output_type: OutputType, muted: bool = True) -> None:
        """
        Mute or unmute specific output.
        
        Args:
            output_type: Output to mute/unmute
            muted: True to mute, False to unmute
        """
        # Implementation would modify routing or add mute processor
        logger.info("Output mute changed", 
                   output_type=output_type.value, muted=muted)
    
    def get_config_schema(self) -> Dict[str, Any]:
        """Get configuration schema for mixer service."""
        return {
            "type": "object",
            "properties": {
                "pa_target_level_dbfs": {
                    "type": "number",
                    "minimum": -30.0,
                    "maximum": -6.0,
                    "description": "Target level for PA output in dBFS"
                },
                "recording_target_level_dbfs": {
                    "type": "number",
                    "minimum": -30.0,
                    "maximum": -6.0,
                    "description": "Target level for recording output in dBFS"
                },
                "pa_sample_rate": {
                    "type": "integer",
                    "enum": [44100, 48000, 96000],
                    "description": "Sample rate for PA output"
                },
                "recording_sample_rate": {
                    "type": "integer",
                    "enum": [44100, 48000, 96000],
                    "description": "Sample rate for recording output"
                },
                "stereo_width": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 2.0,
                    "description": "Stereo width for recording output"
                }
            },
            "required": []
        }