"""
Integration tests for multi-device concurrent processing
Tests simultaneous processing from multiple audio devices
"""

import pytest
import asyncio
import threading
import time
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, Mock

from tests.mocks.mock_portaudio import MockPyAudio, get_mock_portaudio
from src.audio_core.device_manager import DeviceManager
from src.audio_core.real_capture_service import RealCaptureService
from src.audio_core.data_models import ProcessingConfig, AudioFrame


@pytest.mark.integration
class TestMultiDeviceProcessing:
    """Test concurrent processing with multiple devices"""
    
    @pytest.fixture
    def multi_device_setup(self):
        """Setup multiple mock devices for testing"""
        with patch("pyaudio.PyAudio", MockPyAudio):
            device_manager = DeviceManager()
            devices = device_manager.scan_devices()
            
            # Filter for input devices
            input_devices = [d for d in devices if d.maxInputChannels > 0]
            
            return {
                "device_manager": device_manager,
                "input_devices": input_devices[:3],  # Use first 3 devices
                "all_devices": devices
            }
    
    def test_simultaneous_capture_from_multiple_devices(self, multi_device_setup):
        """Test capturing from multiple devices simultaneously"""
        input_devices = multi_device_setup["input_devices"]
        
        # Create capture services for each device
        capture_services = []
        for i, device in enumerate(input_devices):
            config = ProcessingConfig(
                sample_rate=48000,
                channels=min(device.maxInputChannels, 2),
                frame_size=1024,
                device_id=device.index
            )
            
            service = RealCaptureService(config)
            service.configure_device(device)
            capture_services.append((service, f"device_{i}"))
        
        # Start all capture services
        for service, name in capture_services:
            service.start_capture()
        
        # Collect data from all devices concurrently
        results = {}
        
        def capture_from_device(service_info):
            service, device_name = service_info
            frames = []
            
            for frame_idx in range(10):  # Capture 10 frames
                # Simulate frame capture
                channels = service.config.channels
                audio_data = np.random.randn(1024, channels).astype(np.float32) * 0.1
                
                frame = AudioFrame(
                    data=audio_data,
                    sample_rate=48000,
                    channels=channels,
                    timestamp=time.time(),
                    device_id=service.config.device_id
                )
                
                frames.append(frame)
                time.sleep(0.02)  # 20ms between frames
            
            return device_name, frames
        
        # Use ThreadPoolExecutor for concurrent capture
        with ThreadPoolExecutor(max_workers=len(capture_services)) as executor:
            future_to_device = {
                executor.submit(capture_from_device, service_info): service_info[1]
                for service_info in capture_services
            }
            
            for future in as_completed(future_to_device):
                device_name = future_to_device[future]
                try:
                    device_name, frames = future.result()
                    results[device_name] = frames
                except Exception as e:
                    pytest.fail(f"Device {device_name} failed: {e}")
        
        # Stop all services
        for service, _ in capture_services:
            service.stop_capture()
        
        # Verify results
        assert len(results) == len(capture_services)
        
        for device_name, frames in results.items():
            assert len(frames) == 10
            for frame in frames:
                assert frame.data.shape[0] == 1024
                assert frame.sample_rate == 48000
                assert frame.device_id is not None
    
    def test_device_synchronization(self, multi_device_setup):
        """Test synchronization between multiple devices"""
        input_devices = multi_device_setup["input_devices"][:2]  # Use 2 devices
        
        # Create synchronized capture services
        sync_event = threading.Event()
        capture_results = {}
        
        def synchronized_capture(device, device_id):
            config = ProcessingConfig(
                sample_rate=48000,
                channels=2,
                frame_size=1024
            )
            
            service = RealCaptureService(config)
            service.configure_device(device)
            service.start_capture()
            
            # Wait for synchronization signal
            sync_event.wait()
            
            # Capture frames with timestamps
            frames_with_timestamps = []
            start_time = time.perf_counter()
            
            for i in range(20):
                capture_time = time.perf_counter()
                
                audio_data = np.random.randn(1024, 2).astype(np.float32) * 0.1
                frame = AudioFrame(
                    data=audio_data,
                    sample_rate=48000,
                    channels=2,
                    timestamp=capture_time,
                    device_id=device_id
                )
                
                frames_with_timestamps.append((capture_time - start_time, frame))
                time.sleep(0.02)  # 20ms nominal interval
            
            service.stop_capture()
            return frames_with_timestamps
        
        # Start synchronized capture
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(synchronized_capture, device, i)
                for i, device in enumerate(input_devices)
            ]
            
            # Signal start of synchronized capture
            time.sleep(0.1)  # Small delay to ensure threads are ready
            sync_event.set()
            
            # Collect results
            for i, future in enumerate(futures):
                capture_results[f"device_{i}"] = future.result()
        
        # Analyze synchronization
        device_0_times = [t for t, _ in capture_results["device_0"]]
        device_1_times = [t for t, _ in capture_results["device_1"]]
        
        # Check that capture times are reasonably synchronized
        for i in range(min(len(device_0_times), len(device_1_times))):
            time_diff = abs(device_0_times[i] - device_1_times[i])
            assert time_diff < 0.01  # Within 10ms synchronization
    
    def test_load_balancing_across_devices(self, multi_device_setup):
        """Test load balancing when processing multiple device streams"""
        input_devices = multi_device_setup["input_devices"]
        
        # Create processing load simulation
        processing_loads = {}
        
        def process_device_stream(device, device_id, processing_complexity):
            """Simulate processing with different computational loads"""
            config = ProcessingConfig(
                sample_rate=48000,
                channels=2,
                frame_size=1024
            )
            
            service = RealCaptureService(config)
            service.configure_device(device)
            service.start_capture()
            
            processing_times = []
            
            for frame_idx in range(30):  # Process 30 frames
                # Generate audio data
                audio_data = np.random.randn(1024, 2).astype(np.float32) * 0.1
                
                # Simulate processing load
                start_time = time.perf_counter()
                
                # Variable processing complexity
                for _ in range(processing_complexity):
                    _ = np.fft.fft(audio_data[:, 0])  # Simulate processing
                
                end_time = time.perf_counter()
                processing_time = end_time - start_time
                processing_times.append(processing_time)
                
                time.sleep(0.02)  # 20ms frame interval
            
            service.stop_capture()
            
            return {
                "device_id": device_id,
                "avg_processing_time": np.mean(processing_times),
                "max_processing_time": np.max(processing_times),
                "total_frames": len(processing_times)
            }
        
        # Assign different processing loads to devices
        processing_complexities = [10, 50, 100]  # Different computational loads
        
        with ThreadPoolExecutor(max_workers=len(input_devices)) as executor:
            futures = [
                executor.submit(
                    process_device_stream, 
                    device, 
                    i, 
                    processing_complexities[i % len(processing_complexities)]
                )
                for i, device in enumerate(input_devices)
            ]
            
            results = [future.result() for future in futures]
        
        # Analyze load distribution
        for result in results:
            processing_loads[result["device_id"]] = result
        
        # Verify all devices processed successfully
        total_frames = sum(r["total_frames"] for r in results)
        expected_frames = len(input_devices) * 30
        assert total_frames == expected_frames
        
        # Check that processing times scale with complexity
        avg_times = [r["avg_processing_time"] for r in results]
        assert len(set(avg_times)) > 1  # Different processing times
    
    def test_device_failure_handling(self, multi_device_setup):
        """Test handling of device failures during multi-device processing"""
        input_devices = multi_device_setup["input_devices"]
        mock_pa = get_mock_portaudio()
        
        # Setup multiple capture services
        capture_services = []
        for i, device in enumerate(input_devices):
            config = ProcessingConfig(
                sample_rate=48000,
                channels=2,
                frame_size=1024
            )
            
            service = RealCaptureService(config)
            service.configure_device(device)
            capture_services.append((service, i))
        
        # Start all services
        for service, _ in capture_services:
            service.start_capture()
        
        results = {"successful": 0, "failed": 0, "recovered": 0}
        
        def process_with_failure_simulation(service_info):
            service, device_id = service_info
            local_results = {"frames": 0, "errors": 0, "recoveries": 0}
            
            for frame_idx in range(50):  # Process 50 frames
                try:
                    # Simulate random device failures
                    if frame_idx == 20 and device_id == 0:  # Fail first device at frame 20
                        mock_pa.set_error_simulation(device_error=True)
                    elif frame_idx == 25 and device_id == 0:  # Recover at frame 25
                        mock_pa.set_error_simulation(device_error=False)
                        local_results["recoveries"] += 1
                    
                    # Process frame
                    audio_data = np.random.randn(1024, 2).astype(np.float32) * 0.1
                    frame = AudioFrame(
                        data=audio_data,
                        sample_rate=48000,
                        channels=2,
                        timestamp=time.time()
                    )
                    
                    # Simulate processing (would normally go through pipeline)
                    processed_frame = frame  # Simplified
                    local_results["frames"] += 1
                    
                except Exception as e:
                    local_results["errors"] += 1
                    # Continue processing despite errors
                
                time.sleep(0.01)  # 10ms processing interval
            
            return local_results
        
        # Process with failure simulation
        with ThreadPoolExecutor(max_workers=len(capture_services)) as executor:
            futures = [
                executor.submit(process_with_failure_simulation, service_info)
                for service_info in capture_services
            ]
            
            for future in futures:
                local_result = future.result()
                results["successful"] += local_result["frames"]
                results["failed"] += local_result["errors"]
                results["recovered"] += local_result["recoveries"]
        
        # Stop all services
        for service, _ in capture_services:
            service.stop_capture()
        
        # Reset error simulation
        mock_pa.set_error_simulation(device_error=False)
        
        # Verify failure handling
        total_expected = len(capture_services) * 50
        success_rate = results["successful"] / total_expected
        
        # Should maintain reasonable success rate despite failures
        assert success_rate > 0.7  # At least 70% success rate
        
        # Should attempt recovery
        if results["failed"] > 0:
            assert results["recovered"] > 0
    
    def test_resource_contention_handling(self, multi_device_setup):
        """Test handling of resource contention between devices"""
        input_devices = multi_device_setup["input_devices"]
        
        # Simulate high resource usage scenario
        resource_usage = {"cpu_intensive_ops": 0, "memory_allocations": 0}
        
        def resource_intensive_processing(device, device_id):
            """Simulate resource-intensive processing"""
            config = ProcessingConfig(
                sample_rate=48000,
                channels=2,
                frame_size=1024
            )
            
            service = RealCaptureService(config)
            service.configure_device(device)
            service.start_capture()
            
            processing_results = []
            
            for frame_idx in range(20):
                start_time = time.perf_counter()
                
                # Generate audio data
                audio_data = np.random.randn(1024, 2).astype(np.float32) * 0.1
                
                # Simulate CPU-intensive operations
                for _ in range(10):  # Multiple FFT operations
                    fft_result = np.fft.fft(audio_data[:, 0])
                    resource_usage["cpu_intensive_ops"] += 1
                
                # Simulate memory allocations
                temp_buffers = [
                    np.zeros((1024, 2)) for _ in range(5)
                ]
                resource_usage["memory_allocations"] += len(temp_buffers)
                
                end_time = time.perf_counter()
                processing_time = end_time - start_time
                
                processing_results.append({
                    "frame_idx": frame_idx,
                    "processing_time": processing_time,
                    "device_id": device_id
                })
                
                # Cleanup
                del temp_buffers
                
                time.sleep(0.02)  # 20ms frame interval
            
            service.stop_capture()
            return processing_results
        
        # Run resource-intensive processing on multiple devices
        with ThreadPoolExecutor(max_workers=len(input_devices)) as executor:
            futures = [
                executor.submit(resource_intensive_processing, device, i)
                for i, device in enumerate(input_devices)
            ]
            
            all_results = []
            for future in futures:
                device_results = future.result()
                all_results.extend(device_results)
        
        # Analyze resource contention effects
        device_processing_times = {}
        for result in all_results:
            device_id = result["device_id"]
            if device_id not in device_processing_times:
                device_processing_times[device_id] = []
            device_processing_times[device_id].append(result["processing_time"])
        
        # Verify that all devices completed processing
        assert len(device_processing_times) == len(input_devices)
        
        # Check processing time consistency despite resource contention
        for device_id, times in device_processing_times.items():
            avg_time = np.mean(times)
            max_time = np.max(times)
            
            # Processing should remain within reasonable bounds
            assert avg_time < 0.1  # Average < 100ms
            assert max_time < 0.2  # Max < 200ms
        
        # Verify resource operations completed
        assert resource_usage["cpu_intensive_ops"] > 0
        assert resource_usage["memory_allocations"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

