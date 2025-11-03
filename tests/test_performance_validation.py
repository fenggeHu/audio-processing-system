"""
Performance validation test suite for audio processing system.

This module provides comprehensive performance testing including
latency measurements, throughput analysis, and resource utilization
monitoring for real-time audio processing requirements.
"""

import pytest
import asyncio
import time
import psutil
import numpy as np
from datetime import datetime
from typing import List, Dict, Tuple
import statistics
import json

from audio_processing.models import AudioFrame, AudioConfig, ProcessingResult
from audio_processing.service_manager import ServiceManager
from audio_processing.services.denoise import DenoiseService
from audio_processing.services.aec import AECService
from audio_processing.services.ssl import SSLService


class PerformanceMetrics:
    """Container for performance measurement data."""
    
    def __init__(self):
        self.latencies: List[float] = []
        self.cpu_usage: List[float] = []
        self.memory_usage: List[float] = []
        self.throughput: float = 0.0
        self.frame_drops: int = 0
        self.total_frames: int = 0
    
    def add_latency(self, latency_ms: float):
        """Add latency measurement."""
        self.latencies.append(latency_ms)
    
    def add_system_metrics(self, cpu_percent: float, memory_mb: float):
        """Add system resource usage metrics."""
        self.cpu_usage.append(cpu_percent)
        self.memory_usage.append(memory_mb)
    
    def calculate_statistics(self) -> Dict[str, float]:
        """Calculate performance statistics."""
        if not self.latencies:
            return {}
        
        return {
            'latency_avg_ms': statistics.mean(self.latencies),
            'latency_min_ms': min(self.latencies),
            'latency_max_ms': max(self.latencies),
            'latency_p50_ms': np.percentile(self.latencies, 50),
            'latency_p95_ms': np.percentile(self.latencies, 95),
            'latency_p99_ms': np.percentile(self.latencies, 99),
            'latency_std_ms': statistics.stdev(self.latencies) if len(self.latencies) > 1 else 0,
            'cpu_avg_percent': statistics.mean(self.cpu_usage) if self.cpu_usage else 0,
            'cpu_max_percent': max(self.cpu_usage) if self.cpu_usage else 0,
            'memory_avg_mb': statistics.mean(self.memory_usage) if self.memory_usage else 0,
            'memory_max_mb': max(self.memory_usage) if self.memory_usage else 0,
            'throughput_fps': self.throughput,
            'frame_drop_rate': self.frame_drops / self.total_frames if self.total_frames > 0 else 0
        }


class TestLatencyPerformance:
    """Comprehensive latency performance testing."""
    
    @pytest.fixture
    async def performance_config(self):
        """Audio configuration for performance testing."""
        return AudioConfig(
            sample_rate=48000,
            frame_size=480,  # 10ms frames for real-time processing
            channels=2,
            bit_depth=16
        )
    
    @pytest.fixture
    async def performance_manager(self, performance_config):
        """Service manager optimized for performance testing."""
        manager = ServiceManager(performance_config)
        
        # Register services with performance monitoring
        manager.register_service(DenoiseService, name="DenoiseService")
        manager.register_service(AECService, name="AECService")
        manager.register_service(SSLService, name="SSLService")
        
        await manager.start()
        yield manager
        await manager.stop()
    
    async def test_single_service_latency(self, performance_manager, performance_config):
        """Test latency of individual services."""
        services = {
            'DenoiseService': await performance_manager.get_service_by_name("DenoiseService"),
            'AECService': await performance_manager.get_service_by_name("AECService"),
            'SSLService': await performance_manager.get_service_by_name("SSLService")
        }
        
        results = {}
        
        for service_name, service in services.items():
            metrics = PerformanceMetrics()
            
            # Test 100 frames for statistical significance
            for i in range(100):
                frame = self._create_performance_test_frame(performance_config)
                
                start_time = time.perf_counter()
                result = await service.process(frame)
                end_time = time.perf_counter()
                
                assert result.success, f"{service_name} processing failed"
                
                latency_ms = (end_time - start_time) * 1000
                metrics.add_latency(latency_ms)
                
                # Add small delay to prevent overwhelming the system
                await asyncio.sleep(0.001)
            
            stats = metrics.calculate_statistics()
            results[service_name] = stats
            
            # Performance requirements for real-time audio
            assert stats['latency_avg_ms'] < 3.0, f"{service_name} avg latency {stats['latency_avg_ms']:.2f}ms exceeds 3ms"
            assert stats['latency_p95_ms'] < 5.0, f"{service_name} P95 latency {stats['latency_p95_ms']:.2f}ms exceeds 5ms"
            assert stats['latency_max_ms'] < 10.0, f"{service_name} max latency {stats['latency_max_ms']:.2f}ms exceeds 10ms"
        
        # Print detailed results
        print("\nSingle Service Latency Results:")
        for service_name, stats in results.items():
            print(f"  {service_name}:")
            print(f"    Average: {stats['latency_avg_ms']:.2f}ms")
            print(f"    P95: {stats['latency_p95_ms']:.2f}ms")
            print(f"    Max: {stats['latency_max_ms']:.2f}ms")
    
    async def test_pipeline_end_to_end_latency(self, performance_manager, performance_config):
        """Test end-to-end pipeline latency."""
        services = [
            await performance_manager.get_service_by_name("DenoiseService"),
            await performance_manager.get_service_by_name("AECService"),
            await performance_manager.get_service_by_name("SSLService")
        ]
        
        metrics = PerformanceMetrics()
        
        # Test pipeline latency with 200 frames
        for i in range(200):
            frame = self._create_performance_test_frame(performance_config)
            
            start_time = time.perf_counter()
            
            # Process through entire pipeline
            current_frame = frame
            for service in services:
                result = await service.process(current_frame)
                assert result.success, "Pipeline processing failed"
                current_frame = result.data
            
            end_time = time.perf_counter()
            
            pipeline_latency_ms = (end_time - start_time) * 1000
            metrics.add_latency(pipeline_latency_ms)
            
            # Simulate real-time frame rate (10ms intervals)
            await asyncio.sleep(0.01)
        
        stats = metrics.calculate_statistics()
        
        # Real-time processing requirements
        assert stats['latency_avg_ms'] < 8.0, f"Pipeline avg latency {stats['latency_avg_ms']:.2f}ms exceeds 8ms"
        assert stats['latency_p95_ms'] < 12.0, f"Pipeline P95 latency {stats['latency_p95_ms']:.2f}ms exceeds 12ms"
        assert stats['latency_max_ms'] < 20.0, f"Pipeline max latency {stats['latency_max_ms']:.2f}ms exceeds 20ms"
        
        print(f"\nPipeline End-to-End Latency:")
        print(f"  Average: {stats['latency_avg_ms']:.2f}ms")
        print(f"  P50: {stats['latency_p50_ms']:.2f}ms")
        print(f"  P95: {stats['latency_p95_ms']:.2f}ms")
        print(f"  P99: {stats['latency_p99_ms']:.2f}ms")
        print(f"  Max: {stats['latency_max_ms']:.2f}ms")
        print(f"  Std Dev: {stats['latency_std_ms']:.2f}ms")
    
    async def test_sustained_load_performance(self, performance_manager, performance_config):
        """Test performance under sustained processing load."""
        denoise_service = await performance_manager.get_service_by_name("DenoiseService")
        
        metrics = PerformanceMetrics()
        process = psutil.Process()
        
        # Run sustained load for 60 seconds
        duration = 60.0
        start_time = time.time()
        frame_count = 0
        
        while (time.time() - start_time) < duration:
            frame = self._create_performance_test_frame(performance_config)
            
            # Measure processing latency
            proc_start = time.perf_counter()
            result = await denoise_service.process(frame)
            proc_end = time.perf_counter()
            
            if result.success:
                latency_ms = (proc_end - proc_start) * 1000
                metrics.add_latency(latency_ms)
                frame_count += 1
            else:
                metrics.frame_drops += 1
            
            metrics.total_frames += 1
            
            # Collect system metrics every 100 frames
            if frame_count % 100 == 0:
                cpu_percent = process.cpu_percent()
                memory_mb = process.memory_info().rss / 1024 / 1024
                metrics.add_system_metrics(cpu_percent, memory_mb)
            
            # Maintain real-time frame rate
            await asyncio.sleep(0.01)
        
        # Calculate throughput
        actual_duration = time.time() - start_time
        metrics.throughput = frame_count / actual_duration
        
        stats = metrics.calculate_statistics()
        
        # Performance requirements for sustained operation
        assert stats['frame_drop_rate'] < 0.01, f"Frame drop rate {stats['frame_drop_rate']:.3f} exceeds 1%"
        assert stats['throughput_fps'] > 80.0, f"Throughput {stats['throughput_fps']:.1f} fps below 80 fps"
        assert stats['latency_avg_ms'] < 5.0, f"Sustained avg latency {stats['latency_avg_ms']:.2f}ms exceeds 5ms"
        assert stats['cpu_avg_percent'] < 50.0, f"Average CPU usage {stats['cpu_avg_percent']:.1f}% exceeds 50%"
        
        print(f"\nSustained Load Performance (60s):")
        print(f"  Throughput: {stats['throughput_fps']:.1f} fps")
        print(f"  Frame drop rate: {stats['frame_drop_rate']:.4f}")
        print(f"  Average latency: {stats['latency_avg_ms']:.2f}ms")
        print(f"  Average CPU: {stats['cpu_avg_percent']:.1f}%")
        print(f"  Peak CPU: {stats['cpu_max_percent']:.1f}%")
        print(f"  Average Memory: {stats['memory_avg_mb']:.1f} MB")
        print(f"  Peak Memory: {stats['memory_max_mb']:.1f} MB")
    
    async def test_burst_load_handling(self, performance_manager, performance_config):
        """Test system response to burst processing loads."""
        services = [
            await performance_manager.get_service_by_name("DenoiseService"),
            await performance_manager.get_service_by_name("AECService")
        ]
        
        # Test different burst sizes
        burst_sizes = [10, 50, 100]
        results = {}
        
        for burst_size in burst_sizes:
            metrics = PerformanceMetrics()
            
            # Create burst of frames
            frames = [
                self._create_performance_test_frame(performance_config)
                for _ in range(burst_size)
            ]
            
            # Process burst as quickly as possible
            start_time = time.perf_counter()
            
            for frame in frames:
                current_frame = frame
                for service in services:
                    proc_start = time.perf_counter()
                    result = await service.process(current_frame)
                    proc_end = time.perf_counter()
                    
                    if result.success:
                        latency_ms = (proc_end - proc_start) * 1000
                        metrics.add_latency(latency_ms)
                        current_frame = result.data
                    else:
                        metrics.frame_drops += 1
                
                metrics.total_frames += 1
            
            end_time = time.perf_counter()
            
            # Calculate burst processing metrics
            total_time = end_time - start_time
            metrics.throughput = burst_size / total_time
            
            stats = metrics.calculate_statistics()
            results[burst_size] = stats
            
            # Burst processing should maintain reasonable latency
            assert stats['latency_avg_ms'] < 10.0, f"Burst {burst_size} avg latency {stats['latency_avg_ms']:.2f}ms too high"
            assert stats['frame_drop_rate'] < 0.05, f"Burst {burst_size} drop rate {stats['frame_drop_rate']:.3f} too high"
        
        print(f"\nBurst Load Handling Results:")
        for burst_size, stats in results.items():
            print(f"  Burst size {burst_size}:")
            print(f"    Throughput: {stats['throughput_fps']:.1f} fps")
            print(f"    Avg latency: {stats['latency_avg_ms']:.2f}ms")
            print(f"    Drop rate: {stats['frame_drop_rate']:.4f}")
    
    def _create_performance_test_frame(self, config: AudioConfig) -> AudioFrame:
        """Create standardized test frame for performance testing."""
        # Use deterministic signal for consistent performance testing
        duration = config.frame_size / config.sample_rate
        t = np.linspace(0, duration, config.frame_size)
        
        # Simple sine wave with some harmonics
        signal = (
            0.5 * np.sin(2 * np.pi * 440 * t) +  # A4 note
            0.3 * np.sin(2 * np.pi * 880 * t) +  # A5 note
            0.1 * np.random.normal(0, 0.05, config.frame_size)  # Small amount of noise
        )
        
        # Create multi-channel data
        if config.channels == 2:
            data = np.array([signal, signal * 0.8])
        else:
            data = signal.reshape(1, -1)
        
        return AudioFrame(
            timestamp=datetime.now(),
            sample_rate=config.sample_rate,
            channels=config.channels,
            frame_size=config.frame_size,
            data=data
        )


class TestThroughputAnalysis:
    """Throughput and capacity analysis tests."""
    
    @pytest.fixture
    async def throughput_config(self):
        """Configuration for throughput testing."""
        return AudioConfig(
            sample_rate=48000,
            frame_size=480,
            channels=2,
            bit_depth=16
        )
    
    async def test_maximum_throughput_capacity(self, throughput_config):
        """Determine maximum sustainable throughput."""
        from audio_processing.services.denoise import DenoiseService
        
        config = throughput_config
        service = DenoiseService("ThroughputTest", config)
        await service.start()
        
        try:
            # Test increasing frame rates to find maximum capacity
            frame_rates = [50, 100, 200, 500, 1000]  # fps
            max_sustainable_fps = 0
            
            for target_fps in frame_rates:
                frame_interval = 1.0 / target_fps
                success_count = 0
                total_frames = 100
                
                start_time = time.time()
                
                for i in range(total_frames):
                    frame = self._create_test_frame(config)
                    
                    result = await service.process(frame)
                    if result.success:
                        success_count += 1
                    
                    # Try to maintain target frame rate
                    elapsed = time.time() - start_time
                    target_time = (i + 1) * frame_interval
                    if elapsed < target_time:
                        await asyncio.sleep(target_time - elapsed)
                
                success_rate = success_count / total_frames
                actual_fps = total_frames / (time.time() - start_time)
                
                print(f"Target: {target_fps} fps, Actual: {actual_fps:.1f} fps, Success: {success_rate:.3f}")
                
                # Consider sustainable if >95% success rate and actual fps within 10% of target
                if success_rate > 0.95 and actual_fps > target_fps * 0.9:
                    max_sustainable_fps = target_fps
                else:
                    break
            
            assert max_sustainable_fps >= 100, f"Max sustainable throughput {max_sustainable_fps} fps below minimum 100 fps"
            
            print(f"\nMaximum Sustainable Throughput: {max_sustainable_fps} fps")
            
        finally:
            await service.stop()
    
    async def test_concurrent_stream_capacity(self, throughput_config):
        """Test capacity for processing multiple concurrent audio streams."""
        from audio_processing.services.denoise import DenoiseService
        
        config = throughput_config
        
        # Test with increasing number of concurrent streams
        stream_counts = [1, 2, 4, 8]
        results = {}
        
        for stream_count in stream_counts:
            # Create multiple service instances to simulate concurrent streams
            services = []
            for i in range(stream_count):
                service = DenoiseService(f"Stream{i}", config)
                await service.start()
                services.append(service)
            
            try:
                # Process frames concurrently across all streams
                async def process_stream(service, stream_id):
                    latencies = []
                    success_count = 0
                    
                    for i in range(50):  # 50 frames per stream
                        frame = self._create_test_frame(config)
                        
                        start_time = time.perf_counter()
                        result = await service.process(frame)
                        end_time = time.perf_counter()
                        
                        if result.success:
                            success_count += 1
                            latencies.append((end_time - start_time) * 1000)
                        
                        await asyncio.sleep(0.01)  # 100 fps per stream
                    
                    return stream_id, success_count, latencies
                
                # Run all streams concurrently
                start_time = time.time()
                tasks = [process_stream(service, i) for i, service in enumerate(services)]
                stream_results = await asyncio.gather(*tasks)
                total_time = time.time() - start_time
                
                # Analyze results
                total_success = sum(result[1] for result in stream_results)
                all_latencies = []
                for result in stream_results:
                    all_latencies.extend(result[2])
                
                avg_latency = statistics.mean(all_latencies) if all_latencies else 0
                total_throughput = total_success / total_time
                
                results[stream_count] = {
                    'throughput_fps': total_throughput,
                    'avg_latency_ms': avg_latency,
                    'success_rate': total_success / (stream_count * 50)
                }
                
                # Performance requirements scale with stream count
                min_throughput = stream_count * 80  # 80 fps per stream minimum
                assert total_throughput > min_throughput, f"{stream_count} streams: throughput {total_throughput:.1f} < {min_throughput}"
                assert avg_latency < 10.0, f"{stream_count} streams: avg latency {avg_latency:.2f}ms exceeds 10ms"
                
            finally:
                for service in services:
                    await service.stop()
        
        print(f"\nConcurrent Stream Capacity Results:")
        for stream_count, stats in results.items():
            print(f"  {stream_count} streams:")
            print(f"    Total throughput: {stats['throughput_fps']:.1f} fps")
            print(f"    Avg latency: {stats['avg_latency_ms']:.2f}ms")
            print(f"    Success rate: {stats['success_rate']:.3f}")
    
    def _create_test_frame(self, config: AudioConfig) -> AudioFrame:
        """Create test frame for throughput testing."""
        # Simple deterministic signal for consistent testing
        signal = np.sin(2 * np.pi * 440 * np.linspace(0, config.frame_size / config.sample_rate, config.frame_size))
        
        if config.channels == 2:
            data = np.array([signal, signal])
        else:
            data = signal.reshape(1, -1)
        
        return AudioFrame(
            timestamp=datetime.now(),
            sample_rate=config.sample_rate,
            channels=config.channels,
            frame_size=config.frame_size,
            data=data
        )


# Performance test runner utility
async def run_performance_benchmark():
    """Run complete performance benchmark suite."""
    print("Starting Audio Processing Performance Benchmark...")
    
    # Run pytest with performance tests
    import subprocess
    result = subprocess.run([
        'python', '-m', 'pytest', 
        'tests/test_performance_validation.py',
        '-v', '--tb=short'
    ], capture_output=True, text=True)
    
    print("Performance Benchmark Results:")
    print(result.stdout)
    if result.stderr:
        print("Errors:")
        print(result.stderr)
    
    return result.returncode == 0


if __name__ == "__main__":
    # Allow running performance tests directly
    asyncio.run(run_performance_benchmark())