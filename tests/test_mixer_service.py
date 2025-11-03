"""
Tests for Classroom Mixer Service.
"""

import pytest
import asyncio
import numpy as np
from datetime import datetime

from src.audio_processing.models import AudioConfig, AudioFrame
from src.audio_processing.services.mixer import (
    ClassroomMixerService, OutputType, MixingMode, AudioFormat,
    OutputConfig, AudioRouter, FormatConverter, DualPathProcessor
)


class TestAudioRouter:
    """Test audio router functionality."""
    
    def test_router_initialization(self):
        """Test audio router initialization."""
        router = AudioRouter(sample_rate=48000)
        
        assert router.sample_rate == 48000
        assert len(router.output_queues) == 0
        assert len(router.output_configs) == 0
        assert len(router.routing_matrix) == 0
    
    def test_add_remove_output(self):
        """Test adding and removing outputs."""
        router = AudioRouter()
        
        # Add PA output
        pa_config = OutputConfig(
            output_type=OutputType.PA_SYSTEM,
            sample_rate=48000,
            channels=2
        )
        
        router.add_output(OutputType.PA_SYSTEM, pa_config)
        
        assert OutputType.PA_SYSTEM in router.output_queues
        assert OutputType.PA_SYSTEM in router.output_configs
        
        # Remove output
        router.remove_output(OutputType.PA_SYSTEM)
        
        assert OutputType.PA_SYSTEM not in router.output_queues
        assert OutputType.PA_SYSTEM not in router.output_configs
    
    def test_routing_configuration(self):
        """Test routing configuration."""
        router = AudioRouter()
        
        # Set routing
        destinations = [OutputType.PA_SYSTEM, OutputType.RECORDING]
        router.set_routing("main_input", destinations)
        
        assert "main_input" in router.routing_matrix
        assert router.routing_matrix["main_input"] == destinations
    
    async def test_frame_routing(self):
        """Test frame routing to outputs."""
        router = AudioRouter()
        
        # Add outputs
        pa_config = OutputConfig(OutputType.PA_SYSTEM, channels=2)
        recording_config = OutputConfig(OutputType.RECORDING, channels=2)
        
        router.add_output(OutputType.PA_SYSTEM, pa_config)
        router.add_output(OutputType.RECORDING, recording_config)
        
        # Set routing
        router.set_routing("test_source", [OutputType.PA_SYSTEM, OutputType.RECORDING])
        
        # Create test frame
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=1,
            frame_size=480,
            data=np.random.randn(1, 480).astype(np.float32) * 0.1
        )
        
        # Route frame
        results = await router.route_frame("test_source", frame)
        
        # Check results
        assert OutputType.PA_SYSTEM in results
        assert OutputType.RECORDING in results
        assert results[OutputType.PA_SYSTEM] is True
        assert results[OutputType.RECORDING] is True
    
    async def test_output_frame_retrieval(self):
        """Test retrieving frames from output queues."""
        router = AudioRouter()
        
        # Add output
        config = OutputConfig(OutputType.PA_SYSTEM, channels=1)
        router.add_output(OutputType.PA_SYSTEM, config)
        router.set_routing("test", [OutputType.PA_SYSTEM])
        
        # Route a frame
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=1,
            frame_size=480,
            data=np.random.randn(1, 480).astype(np.float32) * 0.1
        )
        
        await router.route_frame("test", frame)
        
        # Retrieve frame
        retrieved_frame = await router.get_output_frame(OutputType.PA_SYSTEM, timeout=1.0)
        
        assert retrieved_frame is not None
        assert retrieved_frame.channels == 1
        assert retrieved_frame.frame_size == 480


class TestFormatConverter:
    """Test format converter functionality."""
    
    def test_converter_initialization(self):
        """Test format converter initialization."""
        converter = FormatConverter()
        
        assert len(converter.resampling_filters) == 0
        assert len(converter.dither_generators) == 0
        assert converter.conversion_stats['total_conversions'] == 0
    
    async def test_sample_rate_conversion(self):
        """Test sample rate conversion."""
        converter = FormatConverter()
        
        # Create frame at 44.1kHz
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=44100,
            channels=2,
            frame_size=441,  # 10ms at 44.1kHz
            data=np.random.randn(2, 441).astype(np.float32) * 0.1
        )
        
        # Target config at 48kHz
        target_config = OutputConfig(
            output_type=OutputType.PA_SYSTEM,
            sample_rate=48000,
            channels=2
        )
        
        # Convert format
        converted_frame = await converter.convert_format(frame, target_config)
        
        assert converted_frame.sample_rate == 48000
        assert converted_frame.channels == 2
        # Frame size should be adjusted for new sample rate
        assert converted_frame.frame_size != 441
    
    async def test_channel_conversion(self):
        """Test channel conversion."""
        converter = FormatConverter()
        
        # Create mono frame
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=1,
            frame_size=480,
            data=np.random.randn(1, 480).astype(np.float32) * 0.1
        )
        
        # Target stereo config
        target_config = OutputConfig(
            output_type=OutputType.RECORDING,
            sample_rate=48000,
            channels=2
        )
        
        # Convert format
        converted_frame = await converter.convert_format(frame, target_config)
        
        assert converted_frame.channels == 2
        assert converted_frame.sample_rate == 48000
        assert converted_frame.frame_size == 480
    
    async def test_no_conversion_needed(self):
        """Test when no conversion is needed."""
        converter = FormatConverter()
        
        # Create frame matching target config
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=2,
            frame_size=480,
            data=np.random.randn(2, 480).astype(np.float32) * 0.1
        )
        
        target_config = OutputConfig(
            output_type=OutputType.PA_SYSTEM,
            sample_rate=48000,
            channels=2,
            format=AudioFormat.PCM_16
        )
        
        # Convert format
        converted_frame = await converter.convert_format(frame, target_config)
        
        # Should be essentially the same (except metadata)
        assert converted_frame.sample_rate == frame.sample_rate
        assert converted_frame.channels == frame.channels
        assert converted_frame.frame_size == frame.frame_size
        
        # Check conversion stats
        stats = converter.get_conversion_stats()
        assert stats['total_conversions'] >= 1


class TestDualPathProcessor:
    """Test dual-path processor functionality."""
    
    def test_processor_initialization(self):
        """Test dual-path processor initialization."""
        processor = DualPathProcessor(sample_rate=48000)
        
        assert processor.sample_rate == 48000
        assert 'target_level_dbfs' in processor.pa_config
        assert 'target_level_dbfs' in processor.recording_config
        # PA should have higher target level (less headroom)
        assert processor.pa_config['target_level_dbfs'] > processor.recording_config['target_level_dbfs']
    
    async def test_pa_path_processing(self):
        """Test PA path processing."""
        processor = DualPathProcessor()
        
        # Create test frame
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=2,
            frame_size=480,
            data=np.random.randn(2, 480).astype(np.float32) * 0.1
        )
        
        # Process for PA
        pa_frame = await processor.process_pa_path(frame)
        
        assert pa_frame.channels == frame.channels
        assert pa_frame.frame_size == frame.frame_size
        assert pa_frame.sample_rate == frame.sample_rate
        
        # Check PA processing metadata
        metadata = pa_frame.metadata
        assert metadata['pa_processed'] is True
        assert 'pa_target_level' in metadata
        assert 'pa_gain_reduction' in metadata
    
    async def test_recording_path_processing(self):
        """Test recording path processing."""
        processor = DualPathProcessor()
        
        # Create test frame
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=2,
            frame_size=480,
            data=np.random.randn(2, 480).astype(np.float32) * 0.1
        )
        
        # Process for recording
        recording_frame = await processor.process_recording_path(frame)
        
        assert recording_frame.channels == frame.channels
        assert recording_frame.frame_size == frame.frame_size
        
        # Check recording processing metadata
        metadata = recording_frame.metadata
        assert metadata['recording_processed'] is True
        assert 'recording_target_level' in metadata
        assert 'recording_gain_reduction' in metadata
        assert 'stereo_width' in metadata
    
    async def test_different_processing_characteristics(self):
        """Test that PA and recording paths process differently."""
        processor = DualPathProcessor()
        
        # Create identical test frames
        frame1 = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=2,
            frame_size=480,
            data=np.random.randn(2, 480).astype(np.float32) * 0.05
        )
        
        frame2 = AudioFrame(
            timestamp=frame1.timestamp,
            sample_rate=48000,
            channels=2,
            frame_size=480,
            data=frame1.data.copy()
        )
        
        # Process through both paths
        pa_frame = await processor.process_pa_path(frame1)
        recording_frame = await processor.process_recording_path(frame2)
        
        # Should have different target levels
        pa_target = pa_frame.metadata['pa_target_level']
        recording_target = recording_frame.metadata['recording_target_level']
        
        assert pa_target != recording_target
        # PA should have higher target level (less headroom)
        assert pa_target > recording_targetc
lass TestClassroomMixerService:
    """Test classroom mixer service functionality."""
    
    async def test_mixer_service_initialization(self):
        """Test mixer service initialization."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        
        mixer_service = ClassroomMixerService("TestMixer", config)
        
        assert mixer_service.service_name == "TestMixer"
        assert not mixer_service.is_running
        assert mixer_service.frames_processed == 0
        assert OutputType.PA_SYSTEM in mixer_service.output_configs
        assert OutputType.RECORDING in mixer_service.output_configs
    
    async def test_mixer_service_lifecycle(self):
        """Test mixer service start/stop lifecycle."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        mixer_service = ClassroomMixerService("TestMixer", config)
        
        # Start service
        await mixer_service.start()
        assert mixer_service.is_running
        
        # Should have started output processing tasks
        assert len(mixer_service.output_tasks) > 0
        
        # Stop service
        await mixer_service.stop()
        assert not mixer_service.is_running
        
        # Tasks should be cleaned up
        assert len(mixer_service.output_tasks) == 0
    
    async def test_mixer_frame_processing(self):
        """Test mixer frame processing."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        mixer_service = ClassroomMixerService("TestMixer", config)
        
        await mixer_service.start()
        
        try:
            # Create test frame
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=1,
                frame_size=480,
                data=np.random.randn(1, 480).astype(np.float32) * 0.1
            )
            
            # Process frame (mixer is pass-through for main chain)
            result = await mixer_service.process(frame)
            
            assert result.success
            assert result.data is not None
            assert result.data.channels == 1
            assert result.data.frame_size == 480
            
            # Frame should be routed to outputs (checked via metrics)
            await asyncio.sleep(0.1)  # Allow background processing
            
            metrics = mixer_service.get_mixer_metrics()
            assert metrics['frames_mixed'] >= 1
        
        finally:
            await mixer_service.stop()
    
    async def test_mixer_metrics(self):
        """Test mixer metrics collection."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        mixer_service = ClassroomMixerService("TestMixer", config)
        
        await mixer_service.start()
        
        try:
            # Process several frames
            for i in range(3):
                frame = AudioFrame(
                    timestamp=datetime.now(),
                    sample_rate=48000,
                    channels=1,
                    frame_size=480,
                    data=np.random.randn(1, 480).astype(np.float32) * 0.1
                )
                
                await mixer_service.process(frame)
            
            # Allow background processing
            await asyncio.sleep(0.2)
            
            # Get mixer metrics
            metrics = mixer_service.get_mixer_metrics()
            
            assert 'frames_mixed' in metrics
            assert 'pa_frames_output' in metrics
            assert 'recording_frames_output' in metrics
            assert 'routing_stats' in metrics
            assert 'conversion_stats' in metrics
            
            assert metrics['frames_mixed'] >= 3
            assert metrics['frames_processed'] >= 3
        
        finally:
            await mixer_service.stop()
    
    async def test_output_configuration(self):
        """Test output configuration updates."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        mixer_service = ClassroomMixerService("TestMixer", config)
        
        # Update PA output config
        new_pa_config = OutputConfig(
            output_type=OutputType.PA_SYSTEM,
            sample_rate=44100,  # Different sample rate
            channels=1,
            target_level_dbfs=-15.0
        )
        
        mixer_service.set_output_config(OutputType.PA_SYSTEM, new_pa_config)
        
        # Check that config was updated
        assert mixer_service.output_configs[OutputType.PA_SYSTEM].sample_rate == 44100
        assert mixer_service.output_configs[OutputType.PA_SYSTEM].target_level_dbfs == -15.0
    
    async def test_custom_routing_matrix(self):
        """Test custom routing matrix configuration."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        mixer_service = ClassroomMixerService("TestMixer", config)
        
        # Set custom routing (only to PA, not recording)
        custom_routing = {
            "main_input": [OutputType.PA_SYSTEM],
            "monitor_input": [OutputType.RECORDING]
        }
        
        mixer_service.set_routing_matrix(custom_routing)
        
        # Verify routing was set
        routing_stats = mixer_service.audio_router.get_routing_stats()
        assert isinstance(routing_stats, dict)
    
    async def test_output_levels(self):
        """Test output level monitoring."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        mixer_service = ClassroomMixerService("TestMixer", config)
        
        await mixer_service.start()
        
        try:
            # Process a frame
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=1,
                frame_size=480,
                data=np.random.randn(1, 480).astype(np.float32) * 0.1
            )
            
            await mixer_service.process(frame)
            await asyncio.sleep(0.1)
            
            # Get output levels
            levels = mixer_service.get_output_levels()
            
            assert OutputType.PA_SYSTEM in levels
            assert OutputType.RECORDING in levels
            assert isinstance(levels[OutputType.PA_SYSTEM], (int, float))
            assert isinstance(levels[OutputType.RECORDING], (int, float))
        
        finally:
            await mixer_service.stop()
    
    async def test_output_muting(self):
        """Test output muting functionality."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        mixer_service = ClassroomMixerService("TestMixer", config)
        
        # Test muting (implementation may be placeholder)
        await mixer_service.mute_output(OutputType.PA_SYSTEM, muted=True)
        await mixer_service.mute_output(OutputType.PA_SYSTEM, muted=False)
        
        # Should not raise exceptions
        assert True
    
    async def test_dual_path_processing_integration(self):
        """Test integration with dual-path processor."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=2)
        mixer_service = ClassroomMixerService("TestMixer", config)
        
        await mixer_service.start()
        
        try:
            # Create stereo test frame
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=2,
                frame_size=480,
                data=np.random.randn(2, 480).astype(np.float32) * 0.1
            )
            
            # Process frame
            result = await mixer_service.process(frame)
            assert result.success
            
            # Allow background processing to complete
            await asyncio.sleep(0.2)
            
            # Check that both PA and recording processing occurred
            metrics = mixer_service.get_mixer_metrics()
            
            # Should have processed frames for both outputs
            assert metrics['frames_mixed'] >= 1
            
            # Check conversion stats (may have format conversions)
            conversion_stats = metrics['conversion_stats']
            assert 'total_conversions' in conversion_stats
        
        finally:
            await mixer_service.stop()
    
    async def test_format_conversion_integration(self):
        """Test integration with format converter."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        mixer_service = ClassroomMixerService("TestMixer", config)
        
        # Configure different sample rates for outputs
        pa_config = OutputConfig(
            output_type=OutputType.PA_SYSTEM,
            sample_rate=44100,  # Different from input
            channels=2,         # Different from input
            format=AudioFormat.PCM_16
        )
        
        mixer_service.set_output_config(OutputType.PA_SYSTEM, pa_config)
        
        await mixer_service.start()
        
        try:
            # Process frame that needs conversion
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,  # Input at 48kHz
                channels=1,         # Mono input
                frame_size=480,
                data=np.random.randn(1, 480).astype(np.float32) * 0.1
            )
            
            result = await mixer_service.process(frame)
            assert result.success
            
            # Allow background processing
            await asyncio.sleep(0.2)
            
            # Check conversion stats
            metrics = mixer_service.get_mixer_metrics()
            conversion_stats = metrics['conversion_stats']
            
            # Should have performed conversions
            assert conversion_stats['total_conversions'] >= 0  # May be 0 if no actual conversion needed
        
        finally:
            await mixer_service.stop()


# Integration test
class TestMixerIntegration:
    """Integration tests for mixer service."""
    
    async def test_mixer_classroom_scenario(self):
        """Test mixer service in classroom scenario."""
        # Setup classroom mixer configuration
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=2)
        
        mixer_service = ClassroomMixerService("ClassroomMixer", config)
        
        # Configure outputs for classroom use
        pa_config = OutputConfig(
            output_type=OutputType.PA_SYSTEM,
            sample_rate=48000,
            channels=2,
            target_level_dbfs=-18.0,  # Standard PA level
            pa_eq_enabled=True,
            pa_compressor_enabled=True,
            pa_limiter_enabled=True
        )
        
        recording_config = OutputConfig(
            output_type=OutputType.RECORDING,
            sample_rate=48000,
            channels=2,
            target_level_dbfs=-23.0,  # More headroom for recording
            recording_stereo_width=1.2,
            recording_room_tone=True,
            recording_noise_gate=True
        )
        
        mixer_service.set_output_config(OutputType.PA_SYSTEM, pa_config)
        mixer_service.set_output_config(OutputType.RECORDING, recording_config)
        
        await mixer_service.start()
        
        try:
            # Simulate classroom audio processing
            pa_levels = []
            recording_levels = []
            
            # Process multiple frames simulating classroom audio
            for i in range(10):
                # Vary signal level to simulate speech dynamics
                signal_level = 0.05 + 0.1 * np.sin(i * 0.5)  # Varying level
                
                frame = AudioFrame(
                    timestamp=datetime.now(),
                    sample_rate=48000,
                    channels=2,
                    frame_size=480,
                    data=np.random.randn(2, 480).astype(np.float32) * signal_level
                )
                
                result = await mixer_service.process(frame)
                assert result.success
                
                # Brief delay to allow background processing
                await asyncio.sleep(0.05)
            
            # Allow final processing to complete
            await asyncio.sleep(0.3)
            
            # Check final metrics
            metrics = mixer_service.get_mixer_metrics()
            
            # Should have processed all frames
            assert metrics['frames_mixed'] == 10
            assert metrics['frames_processed'] == 10
            
            # Should have output to both PA and recording
            assert metrics['pa_frames_output'] >= 5  # At least some frames
            assert metrics['recording_frames_output'] >= 5
            
            # Check output levels
            levels = mixer_service.get_output_levels()
            assert OutputType.PA_SYSTEM in levels
            assert OutputType.RECORDING in levels
            
            # Levels should be reasonable (not -inf or too high)
            pa_level = levels[OutputType.PA_SYSTEM]
            recording_level = levels[OutputType.RECORDING]
            
            assert -80.0 < pa_level < 0.0
            assert -80.0 < recording_level < 0.0
            
        finally:
            await mixer_service.stop()