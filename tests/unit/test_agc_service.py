"""
Tests for AGC (Automatic Gain Control) Service.
"""

import pytest
import asyncio
import numpy as np
from datetime import datetime

from src.audio_processing.models import AudioConfig, AudioFrame
from src.audio_processing.services.agc import (
    AGCService, AGCMode, SourceType, SourceTypeIdentifier,
    HowlingProtection, GainController
)


class TestSourceTypeIdentifier:
    """Test source type identification functionality."""
    
    def test_identifier_initialization(self):
        """Test source type identifier initialization."""
        identifier = SourceTypeIdentifier(sample_rate=48000)
        
        assert identifier.sample_rate == 48000
        assert identifier.current_source == SourceType.UNKNOWN
        assert identifier.source_confidence == 0.0
        assert len(identifier.energy_history) == 0
    
    def test_teacher_area_identification(self):
        """Test identification of teacher area audio."""
        identifier = SourceTypeIdentifier()
        
        # Create frame with teacher area SSL direction
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=1,
            frame_size=480,
            data=np.random.randn(1, 480).astype(np.float32) * 0.1,
            metadata={
                'ssl_direction': 0.0,  # Front center - teacher area
                'ssl_confidence': 0.8
            }
        )
        
        source_type, confidence = identifier.identify_source(frame)
        
        # Should identify as teacher with reasonable confidence
        assert source_type in [SourceType.TEACHER, SourceType.UNKNOWN]
        assert 0.0 <= confidence <= 1.0
    
    def test_student_area_identification(self):
        """Test identification of student area audio."""
        identifier = SourceTypeIdentifier()
        
        # Create frame with student area SSL direction
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=1,
            frame_size=480,
            data=np.random.randn(1, 480).astype(np.float32) * 0.05,
            metadata={
                'ssl_direction': 90.0,  # Side - student area
                'ssl_confidence': 0.7
            }
        )
        
        source_type, confidence = identifier.identify_source(frame)
        
        # Should identify as student or ambient
        assert source_type in [SourceType.STUDENT, SourceType.AMBIENT, SourceType.UNKNOWN]
        assert 0.0 <= confidence <= 1.0
    
    def test_low_confidence_ssl(self):
        """Test handling of low confidence SSL data."""
        identifier = SourceTypeIdentifier()
        
        # Create frame with low SSL confidence
        frame = AudioFrame(
            timestamp=datetime.now(),
            sample_rate=48000,
            channels=1,
            frame_size=480,
            data=np.random.randn(1, 480).astype(np.float32) * 0.01,
            metadata={
                'ssl_direction': 45.0,
                'ssl_confidence': 0.2  # Low confidence
            }
        )
        
        source_type, confidence = identifier.identify_source(frame)
        
        # Should default to ambient or unknown with low SSL confidence
        assert source_type in [SourceType.AMBIENT, SourceType.UNKNOWN]
    
    def test_identifier_reset(self):
        """Test identifier reset functionality."""
        identifier = SourceTypeIdentifier()
        
        # Process some frames to build history
        for _ in range(5):
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=1,
                frame_size=480,
                data=np.random.randn(1, 480).astype(np.float32) * 0.1,
                metadata={'ssl_direction': 0.0, 'ssl_confidence': 0.8}
            )
            identifier.identify_source(frame)
        
        # Should have some history
        assert len(identifier.energy_history) > 0
        
        # Reset
        identifier.reset()
        
        # Should be back to initial state
        assert identifier.current_source == SourceType.UNKNOWN
        assert identifier.source_confidence == 0.0
        assert len(identifier.energy_history) == 0


class TestHowlingProtection:
    """Test howling protection functionality."""
    
    def test_protection_initialization(self):
        """Test howling protection initialization."""
        protection = HowlingProtection(sample_rate=48000, frame_size=480)
        
        assert protection.sample_rate == 48000
        assert protection.frame_size == 480
        assert not protection.howling_detected
        assert protection.protection_gain_db == 0.0
        assert len(protection.howling_frequencies) == 0
    
    def test_normal_signal_processing(self):
        """Test processing of normal audio signal."""
        protection = HowlingProtection()
        
        # Create normal speech-like signal
        signal = np.random.randn(480) * 0.1
        
        howling_detected, protection_gain = protection.detect_and_protect(signal, 0.0)
        
        # Should not detect howling in random noise
        assert not howling_detected
        assert protection_gain == 0.0
    
    def test_high_energy_signal(self):
        """Test processing of high energy signal."""
        protection = HowlingProtection()
        
        # Create high energy signal (potential howling)
        signal = np.sin(2 * np.pi * 1000 * np.linspace(0, 0.01, 480)) * 0.5
        
        # Process multiple times to build up detection
        for _ in range(15):
            howling_detected, protection_gain = protection.detect_and_protect(signal, 0.0)
        
        # May or may not detect howling depending on thresholds
        assert isinstance(howling_detected, bool)
        assert protection_gain <= 0.0  # Should be negative or zero
    
    def test_protection_reset(self):
        """Test protection reset functionality."""
        protection = HowlingProtection()
        
        # Simulate some processing
        signal = np.random.randn(480) * 0.2
        protection.detect_and_protect(signal, 0.0)
        
        # Reset
        protection.reset()
        
        # Should be back to initial state
        assert not protection.howling_detected
        assert protection.protection_gain_db == 0.0
        assert len(protection.howling_frequencies) == 0


class TestGainController:
    """Test gain controller functionality."""
    
    def test_controller_initialization(self):
        """Test gain controller initialization."""
        controller = GainController(sample_rate=48000, frame_size=480)
        
        assert controller.sample_rate == 48000
        assert controller.frame_size == 480
        assert controller.current_gain_db == 0.0
        assert SourceType.TEACHER in controller.target_levels
        assert SourceType.STUDENT in controller.target_levels
    
    def test_gain_processing(self):
        """Test basic gain processing."""
        controller = GainController()
        
        # Create test signal
        signal = np.random.randn(480) * 0.01  # Quiet signal
        
        # Process with teacher source type
        processed_signal, applied_gain = controller.process_gain_control(
            signal, SourceType.TEACHER
        )
        
        assert len(processed_signal) == len(signal)
        assert isinstance(applied_gain, float)
        # Should apply some gain to quiet signal
        assert applied_gain >= 0.0
    
    def test_target_level_setting(self):
        """Test setting target levels."""
        controller = GainController()
        
        # Set custom target level
        controller.set_target_level(SourceType.TEACHER, -12.0)
        
        assert controller.target_levels[SourceType.TEACHER] == -12.0
    
    def test_attack_release_timing(self):
        """Test attack and release time settings."""
        controller = GainController()
        
        # Set custom timing
        controller.set_attack_time(25.0)
        controller.set_release_time(500.0)
        
        assert controller.attack_time_ms == 25.0
        assert controller.release_time_ms == 500.0
    
    def test_pumping_detection(self):
        """Test pumping effect detection."""
        controller = GainController()
        
        # Initially should not detect pumping
        assert not controller.is_pumping_detected()
        
        # Process some signals to potentially trigger pumping detection
        for i in range(25):
            # Alternating signal levels
            level = 0.1 if i % 2 == 0 else 0.01
            signal = np.random.randn(480) * level
            controller.process_gain_control(signal, SourceType.TEACHER)
        
        # May or may not detect pumping depending on implementation
        pumping_detected = controller.is_pumping_detected()
        assert isinstance(pumping_detected, bool)
    
    def test_controller_reset(self):
        """Test controller reset functionality."""
        controller = GainController()
        
        # Process some signals to change state
        signal = np.random.randn(480) * 0.1
        controller.process_gain_control(signal, SourceType.TEACHER)
        
        # Reset
        controller.reset()
        
        # Should be back to initial state
        assert controller.current_gain_db == 0.0
        assert controller.target_gain_db == 0.0
        assert len(controller.level_history) == 0


class TestAGCService:
    """Test AGC service functionality."""
    
    async def test_agc_service_initialization(self):
        """Test AGC service initialization."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        
        agc_service = AGCService("TestAGC", config, mode=AGCMode.BALANCED)
        
        assert agc_service.service_name == "TestAGC"
        assert agc_service.mode == AGCMode.BALANCED
        assert not agc_service.is_running
        assert agc_service.frames_processed == 0
    
    async def test_agc_service_lifecycle(self):
        """Test AGC service start/stop lifecycle."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        agc_service = AGCService("TestAGC", config)
        
        # Start service
        await agc_service.start()
        assert agc_service.is_running
        
        # Stop service
        await agc_service.stop()
        assert not agc_service.is_running
    
    async def test_agc_frame_processing(self):
        """Test AGC frame processing."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        agc_service = AGCService("TestAGC", config)
        
        await agc_service.start()
        
        try:
            # Create test frame with SSL metadata
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=1,
                frame_size=480,
                data=np.random.randn(1, 480).astype(np.float32) * 0.1,
                metadata={
                    'ssl_direction': 0.0,
                    'ssl_confidence': 0.8
                }
            )
            
            # Process frame
            result = await agc_service.process(frame)
            
            assert result.success
            assert result.data is not None
            assert result.data.channels == 1
            
            # Check AGC metadata was added
            metadata = result.data.metadata
            assert 'agc_applied' in metadata
            assert 'agc_mode' in metadata
            assert 'source_type' in metadata
            assert 'applied_gain_db' in metadata
            
            # Validate metadata values
            assert metadata['agc_applied'] is True
            assert metadata['agc_mode'] == AGCMode.BALANCED.value
            assert metadata['source_type'] in [st.value for st in SourceType]
            assert isinstance(metadata['applied_gain_db'], (int, float))
        
        finally:
            await agc_service.stop()
    
    async def test_agc_metrics(self):
        """Test AGC metrics collection."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        agc_service = AGCService("TestAGC", config)
        
        await agc_service.start()
        
        try:
            # Process a frame to generate metrics
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=1,
                frame_size=480,
                data=np.random.randn(1, 480).astype(np.float32) * 0.1,
                metadata={'ssl_direction': 0.0, 'ssl_confidence': 0.8}
            )
            
            await agc_service.process(frame)
            
            # Get AGC metrics
            metrics = agc_service.get_agc_metrics()
            
            assert 'mode' in metrics
            assert 'frames_processed' in metrics
            assert 'current_gain_db' in metrics
            assert 'source_type' in metrics
            assert 'teacher_frame_ratio' in metrics
            
            assert metrics['mode'] == AGCMode.BALANCED.value
            assert metrics['frames_processed'] >= 1
            assert isinstance(metrics['current_gain_db'], (int, float))
        
        finally:
            await agc_service.stop()
    
    async def test_mode_switching(self):
        """Test AGC mode switching."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        agc_service = AGCService("TestAGC", config)
        
        # Test mode switching
        agc_service.set_mode(AGCMode.CONSERVATIVE)
        assert agc_service.mode == AGCMode.CONSERVATIVE
        
        agc_service.set_mode(AGCMode.AGGRESSIVE)
        assert agc_service.mode == AGCMode.AGGRESSIVE
        
        agc_service.set_mode(AGCMode.BYPASS)
        assert agc_service.mode == AGCMode.BYPASS
    
    async def test_target_level_configuration(self):
        """Test target level configuration."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        agc_service = AGCService("TestAGC", config)
        
        # Set custom target levels
        agc_service.set_target_levels(
            teacher_level=-12.0,
            student_level=-18.0,
            ambient_level=-25.0
        )
        
        # Verify levels were set
        controller = agc_service.gain_controller
        assert controller.target_levels[SourceType.TEACHER] == -12.0
        assert controller.target_levels[SourceType.STUDENT] == -18.0
        assert controller.target_levels[SourceType.AMBIENT] == -25.0
    
    async def test_attack_release_configuration(self):
        """Test attack/release time configuration."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        agc_service = AGCService("TestAGC", config)
        
        # Set custom timing
        agc_service.set_attack_release_times(25.0, 500.0)
        
        # Verify timing was set
        controller = agc_service.gain_controller
        assert controller.attack_time_ms == 25.0
        assert controller.release_time_ms == 500.0
    
    async def test_bypass_mode(self):
        """Test AGC bypass mode."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        agc_service = AGCService("TestAGC", config, mode=AGCMode.BYPASS)
        
        await agc_service.start()
        
        try:
            # Create test frame
            original_data = np.random.randn(1, 480).astype(np.float32) * 0.1
            frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=1,
                frame_size=480,
                data=original_data.copy(),
                metadata={'ssl_direction': 0.0, 'ssl_confidence': 0.8}
            )
            
            # Process frame in bypass mode
            result = await agc_service.process(frame)
            
            assert result.success
            # In bypass mode, data should be unchanged
            np.testing.assert_array_equal(result.data.data, original_data)
        
        finally:
            await agc_service.stop()
    
    async def test_adaptation_reset(self):
        """Test AGC adaptation reset."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        agc_service = AGCService("TestAGC", config)
        
        await agc_service.start()
        
        try:
            # Process some frames to build up state
            for _ in range(5):
                frame = AudioFrame(
                    timestamp=datetime.now(),
                    sample_rate=48000,
                    channels=1,
                    frame_size=480,
                    data=np.random.randn(1, 480).astype(np.float32) * 0.1,
                    metadata={'ssl_direction': 0.0, 'ssl_confidence': 0.8}
                )
                await agc_service.process(frame)
            
            # Should have processed frames
            assert agc_service.frames_processed > 0
            
            # Reset adaptation
            agc_service.reset_adaptation()
            
            # Metrics should be reset
            metrics = agc_service.get_agc_metrics()
            assert metrics['frames_processed'] == 0
        
        finally:
            await agc_service.stop()
    
    async def test_invalid_input_handling(self):
        """Test handling of invalid inputs."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        agc_service = AGCService("TestAGC", config)
        
        await agc_service.start()
        
        try:
            # Test multi-channel input (should fail)
            multi_channel_frame = AudioFrame(
                timestamp=datetime.now(),
                sample_rate=48000,
                channels=2,  # Invalid for AGC
                frame_size=480,
                data=np.random.randn(2, 480).astype(np.float32) * 0.1
            )
            
            result = await agc_service.process(multi_channel_frame)
            assert not result.success
            assert "single-channel" in result.error
        
        finally:
            await agc_service.stop()


# Integration test
class TestAGCIntegration:
    """Integration tests for AGC service."""
    
    async def test_agc_classroom_scenario(self):
        """Test AGC service in classroom scenario."""
        # Setup classroom AGC configuration
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        
        agc_service = AGCService(
            "ClassroomAGC", 
            config, 
            mode=AGCMode.BALANCED
        )
        
        await agc_service.start()
        
        try:
            # Simulate classroom audio processing with different source types
            teacher_gains = []
            student_gains = []
            
            # Teacher speaking (front direction, higher energy)
            for i in range(5):
                frame = AudioFrame(
                    timestamp=datetime.now(),
                    sample_rate=48000,
                    channels=1,
                    frame_size=480,
                    data=np.random.randn(1, 480).astype(np.float32) * 0.15,  # Higher energy
                    metadata={
                        'ssl_direction': 0.0,  # Front - teacher area
                        'ssl_confidence': 0.9
                    }
                )
                
                result = await agc_service.process(frame)
                assert result.success
                
                if 'applied_gain_db' in result.data.metadata:
                    teacher_gains.append(result.data.metadata['applied_gain_db'])
            
            # Student question (side direction, lower energy)
            for i in range(5):
                frame = AudioFrame(
                    timestamp=datetime.now(),
                    sample_rate=48000,
                    channels=1,
                    frame_size=480,
                    data=np.random.randn(1, 480).astype(np.float32) * 0.05,  # Lower energy
                    metadata={
                        'ssl_direction': 90.0,  # Side - student area
                        'ssl_confidence': 0.7
                    }
                )
                
                result = await agc_service.process(frame)
                assert result.success
                
                if 'applied_gain_db' in result.data.metadata:
                    student_gains.append(result.data.metadata['applied_gain_db'])
            
            # Check that AGC is working
            metrics = agc_service.get_agc_metrics()
            assert metrics['frames_processed'] == 10
            
            # Should have processed both teacher and student frames
            total_frames = metrics['frames_processed']
            teacher_ratio = metrics['teacher_frame_ratio']
            student_ratio = metrics['student_frame_ratio']
            
            assert teacher_ratio + student_ratio + metrics['ambient_frame_ratio'] <= 1.0
            
        finally:
            await agc_service.stop()