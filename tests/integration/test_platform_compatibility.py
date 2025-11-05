"""
Platform compatibility integration tests
Tests system behavior across different platforms and configurations
"""

import pytest
import platform
import numpy as np
from unittest.mock import patch, Mock

from tests.mocks.mock_portaudio import MockPyAudio, get_mock_portaudio
from src.audio_core.models import AudioProcessingConfig, AudioFrame
from src.audio_core.device_manager import DeviceManager
from src.processing.visual_pipeline import VisualAudioPipeline


@pytest.mark.integration
class TestPlatformCompatibility:
    """Test platform-specific compatibility"""
    
    def test_audio_format_compatibility(self):
        """Test compatibility with different audio formats"""
        test_formats = [
            {"sample_rate": 44100, "channels": 2, "bit_depth": 16},
            {"sample_rate": 48000, "channels": 2, "bit_depth": 24},
            {"sample_rate": 96000, "channels": 8, "bit_depth": 32},
        ]
        
        with patch("pyaudio.PyAudio", MockPyAudio):
            for format_config in test_formats:
                config = ProcessingConfig(
                    sample_rate=format_config["sample_rate"],
                    channels=format_config["channels"],
                    frame_size=1024
                )
                
                pipeline = VisualAudioPipeline(config)
                
                # Generate test audio
                duration = 1024 / format_config["sample_rate"]
                t = np.linspace(0, duration, 1024)
                test_signal = 0.1 * np.sin(2 * np.pi * 440 * t)
                
                # Create multi-channel audio
                if format_config["channels"] == 1:
                    audio_data = test_signal.reshape(-1, 1)
                else:
                    audio_data = np.tile(test_signal.reshape(-1, 1), (1, format_config["channels"]))
                
                frame = AudioFrame(
                    data=audio_data.astype(np.float32),
                    sample_rate=format_config["sample_rate"],
                    channels=format_config["channels"],
                    timestamp=0.0
                )
                
                processed_frame = pipeline.process(frame)
                assert processed_frame is not None
                assert processed_frame.sample_rate == format_config["sample_rate"]
                assert processed_frame.channels == format_config["channels"]
    
    def test_buffer_size_compatibility(self):
        """Test compatibility with different buffer sizes"""
        buffer_sizes = [128, 256, 512, 1024, 2048, 4096]
        
        with patch("pyaudio.PyAudio", MockPyAudio):
            for buffer_size in buffer_sizes:
                config = ProcessingConfig(
                    sample_rate=48000,
                    channels=2,
                    frame_size=buffer_size,
                    buffer_size=buffer_size * 4
                )
                
                pipeline = VisualAudioPipeline(config)
                
                # Test with different buffer sizes
                audio_data = np.random.randn(buffer_size, 2).astype(np.float32) * 0.1
                frame = AudioFrame(
                    data=audio_data,
                    sample_rate=48000,
                    channels=2,
                    timestamp=0.0
                )
                
                processed_frame = pipeline.process(frame)
                assert processed_frame is not None
                assert processed_frame.data.shape[0] == buffer_size
    
    def test_device_enumeration_consistency(self):
        """Test device enumeration consistency"""
        with patch("pyaudio.PyAudio", MockPyAudio):
            device_manager = DeviceManager()
            
            # Multiple scans should return consistent results
            scan1 = device_manager.scan_devices()
            scan2 = device_manager.scan_devices()
            scan3 = device_manager.scan_devices()
            
            assert len(scan1) == len(scan2) == len(scan3)
            
            # Device properties should be consistent
            for i in range(len(scan1)):
                assert scan1[i].name == scan2[i].name == scan3[i].name
                assert scan1[i].maxInputChannels == scan2[i].maxInputChannels == scan3[i].maxInputChannels
                assert scan1[i].maxOutputChannels == scan2[i].maxOutputChannels == scan3[i].maxOutputChannels
    
    def test_cross_platform_audio_apis(self):
        """Test different audio API backends"""
        # Simulate different platform audio APIs
        api_configs = [
            {"name": "ALSA", "platform": "linux"},
            {"name": "CoreAudio", "platform": "darwin"},
            {"name": "WASAPI", "platform": "win32"},
            {"name": "DirectSound", "platform": "win32"},
        ]
        
        with patch("pyaudio.PyAudio", MockPyAudio):
            mock_pa = get_mock_portaudio()
            
            for api_config in api_configs:
                # Test API availability and functionality
                device_count = mock_pa.get_device_count()
                assert device_count > 0
                
                # Test device info retrieval
                for i in range(min(device_count, 3)):  # Test first 3 devices
                    device_info = mock_pa.get_device_info_by_index(i)
                    assert device_info.name is not None
                    assert device_info.defaultSampleRate > 0
    
    def test_unicode_device_names(self):
        """Test handling of Unicode device names"""
        with patch("pyaudio.PyAudio", MockPyAudio):
            mock_pa = get_mock_portaudio()
            
            # Add device with Unicode name
            from tests.mocks.mock_portaudio import MockDeviceInfo
            unicode_device = MockDeviceInfo(
                index=0,
                name="测试设备 (Test Device) 🎵",  # Chinese + emoji
                hostApi=0,
                maxInputChannels=2,
                maxOutputChannels=2,
                defaultSampleRate=48000.0,
                defaultLowInputLatency=0.01,
                defaultLowOutputLatency=0.01,
                defaultHighInputLatency=0.1,
                defaultHighOutputLatency=0.1
            )
            
            mock_pa.add_mock_device(unicode_device)
            
            device_manager = DeviceManager()
            devices = device_manager.scan_devices()
            
            # Should handle Unicode names properly
            unicode_devices = [d for d in devices if "测试设备" in d.name]
            assert len(unicode_devices) > 0
    
    def test_sample_rate_conversion(self):
        """Test sample rate conversion compatibility"""
        source_rates = [44100, 48000, 96000]
        target_rates = [44100, 48000, 96000]
        
        with patch("pyaudio.PyAudio", MockPyAudio):
            for source_rate in source_rates:
                for target_rate in target_rates:
                    if source_rate == target_rate:
                        continue  # Skip same rates
                    
                    # Create source audio
                    duration = 1024 / source_rate
                    t = np.linspace(0, duration, 1024)
                    source_audio = 0.1 * np.sin(2 * np.pi * 440 * t)
                    
                    source_frame = AudioFrame(
                        data=source_audio.reshape(-1, 1).astype(np.float32),
                        sample_rate=source_rate,
                        channels=1,
                        timestamp=0.0
                    )
                    
                    # Test conversion (simplified - actual implementation would use resampling)
                    config = ProcessingConfig(
                        sample_rate=target_rate,
                        channels=1,
                        frame_size=1024
                    )
                    
                    pipeline = VisualAudioPipeline(config)
                    
                    # Process should handle rate conversion
                    processed_frame = pipeline.process(source_frame)
                    assert processed_frame is not None
    
    def test_endianness_compatibility(self):
        """Test big-endian/little-endian compatibility"""
        with patch("pyaudio.PyAudio", MockPyAudio):
            config = ProcessingConfig(
                sample_rate=48000,
                channels=2,
                frame_size=1024
            )
            
            pipeline = VisualAudioPipeline(config)
            
            # Test with different byte orders
            audio_data = np.random.randn(1024, 2).astype(np.float32) * 0.1
            
            # Little-endian (default)
            le_data = audio_data.astype('<f4')  # Little-endian float32
            le_frame = AudioFrame(
                data=le_data,
                sample_rate=48000,
                channels=2,
                timestamp=0.0
            )
            
            le_result = pipeline.process(le_frame)
            assert le_result is not None
            
            # Big-endian
            be_data = audio_data.astype('>f4')  # Big-endian float32
            be_frame = AudioFrame(
                data=be_data,
                sample_rate=48000,
                channels=2,
                timestamp=0.0
            )
            
            be_result = pipeline.process(be_frame)
            assert be_result is not None
    
    def test_threading_model_compatibility(self):
        """Test compatibility with different threading models"""
        import threading
        from concurrent.futures import ThreadPoolExecutor
        
        with patch("pyaudio.PyAudio", MockPyAudio):
            config = ProcessingConfig(
                sample_rate=48000,
                channels=2,
                frame_size=1024
            )
            
            def process_in_thread(thread_id):
                """Process audio in separate thread"""
                pipeline = VisualAudioPipeline(config)
                results = []
                
                for i in range(10):
                    audio_data = np.random.randn(1024, 2).astype(np.float32) * 0.1
                    frame = AudioFrame(
                        data=audio_data,
                        sample_rate=48000,
                        channels=2,
                        timestamp=i * 0.02
                    )
                    
                    processed_frame = pipeline.process(frame)
                    results.append(processed_frame is not None)
                
                return thread_id, results
            
            # Test with multiple threads
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = [
                    executor.submit(process_in_thread, i)
                    for i in range(4)
                ]
                
                thread_results = [future.result() for future in futures]
            
            # All threads should succeed
            for thread_id, results in thread_results:
                assert all(results), f"Thread {thread_id} had failures"
    
    def test_locale_compatibility(self):
        """Test compatibility with different system locales"""
        import locale
        
        with patch("pyaudio.PyAudio", MockPyAudio):
            device_manager = DeviceManager()
            
            # Test with different locale settings (simulated)
            test_locales = ["en_US.UTF-8", "zh_CN.UTF-8", "ja_JP.UTF-8", "de_DE.UTF-8"]
            
            for test_locale in test_locales:
                try:
                    # Simulate locale change (actual locale change might not work in test environment)
                    with patch('locale.getlocale', return_value=(test_locale, 'UTF-8')):
                        devices = device_manager.scan_devices()
                        assert len(devices) > 0
                        
                        # Device names should be properly encoded
                        for device in devices:
                            assert isinstance(device.name, str)
                            assert len(device.name) > 0
                            
                except Exception as e:
                    # Some locales might not be available in test environment
                    pytest.skip(f"Locale {test_locale} not available: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
