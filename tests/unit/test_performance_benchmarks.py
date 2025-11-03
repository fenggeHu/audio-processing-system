"""
Performance Benchmark Tests for Audio Processing System.

This module provides performance benchmarks and stress tests for
the audio processing services to ensure they meet real-time requirements.
"""

import pytest
import asyncio
import time
import statistics
import numpy as np
from datetime import datetime
from typing import List, Dict, Any

from src.audio_processing.models import AudioConfig, AudioFrame, AudioMetrics
from src.audio_processing.services.aec import AECService, AECMode
from src.audio_processing.services.ssl import SSLService, create_linear_array
from src.audio_processing.services.agc import AGCService, AGCMode
from src.audio_processing.services.beamformer import BeamformerService, BeamformingAlgorithm
from src.audio_processing.services.mixer import ClassroomMixerService
from tests.unit.test_audio_mock_generator import MockAudioGenerator, SignalType


class PerformanceBenchmark:
    """Performance benchmark utilities."""
    
    def __init__(self):
        self.results = {}
    
    async def benchmark_service(self, service, frames: List[AudioFrame],
                              service_name: str) -> Dict[str, float]:
        """
        Benchmark a service with a sequence of frames.
        
        Args:
            service: Audio service to benchmark
            frames: List of audio frames to process
            service_name: Name for reporting
            
        Returns:
            Dictionary with performance metrics
        """
        latencies = []
        processing_times = []
        
        await service.start()
        
        try:
            total_start = time.time()
            
            for frame in frames:
                frame_start = time.time()
                
                result = await service.process(frame)
                
                frame_end = time.time()
                processing_time = (frame_end - frame_start) * 1000  # ms
                
                if result.success:
                    latencies.append(processing_time)
                    processing_times.append(result.processing_time_ms)
            
            total_end = time.time()
            total_time = total_end - total_start
            
            # Calculate statistics
            if latencies:
                metrics = {
                    'service_name': service_name,
                    'frames_processed': len(latencies),
                    'total_time_seconds': total_time,
                    'throughput_fps': len(frames) / total_time,
                    'avg_latency_ms': statistics.mean(latencies),
                    'max_latency_ms': max(latencies),
                    'min_latency_ms': min(latencies),
                    'p95_latency_ms': np.percentile(latencies, 95),
                    'p99_latency_ms': np.percentile(latencies, 99),
                    'latency_std_ms': statistics.stdev(latencies) if len(latencies) > 1 else 0.0,
                    'real_time_factor': (len(frames) * 0.01) / total_time  # Assuming 10ms frames
                }
                
                self.results[service_name] = metrics
                return metrics
            else:
                return {'error': 'No successful frames processed'}
        
        finally:
            await service.stop()
    
    def print_results(self):
        """Print benchmark results in a readable format."""
        print("\n" + "="*80)
        print("AUDIO PROCESSING PERFORMANCE BENCHMARK RESULTS")
        print("="*80)
        
        for service_name, metrics in self.results.items():
            if 'error' in metrics:
                print(f"\n{service_name}: {metrics['error']}")
                continue
            
            print(f"\n{service_name}:")
            print(f"  Frames Processed: {metrics['frames_processed']}")
            print(f"  Total Time: {metrics['total_time_seconds']:.3f}s")
            print(f"  Throughput: {metrics['throughput_fps']:.1f} fps")
            print(f"  Real-time Factor: {metrics['real_time_factor']:.2f}x")
            print(f"  Average Latency: {metrics['avg_latency_ms']:.2f}ms")
            print(f"  Max Latency: {metrics['max_latency_ms']:.2f}ms")
            print(f"  P95 Latency: {metrics['p95_latency_ms']:.2f}ms")
            print(f"  P99 Latency: {metrics['p99_latency_ms']:.2f}ms")
            print(f"  Latency Std Dev: {metrics['latency_std_ms']:.2f}ms")
            
            # Performance assessment
            real_time_ok = metrics['real_time_factor'] >= 1.0
            latency_ok = metrics['p95_latency_ms'] <= 40.0  # 40ms requirement
            
            status = "✓ PASS" if (real_time_ok and latency_ok) else "✗ FAIL"
            print(f"  Status: {status}")
            
            if not real_time_ok:
                print(f"    WARNING: Real-time factor {metrics['real_time_factor']:.2f}x < 1.0")
            if not latency_ok:
                print(f"    WARNING: P95 latency {metrics['p95_latency_ms']:.2f}ms > 40ms")


class TestPerformanceBenchmarks:
    """Performance benchmark tests."""
    
    @pytest.fixture
    def benchmark(self):
        """Create benchmark instance."""
        return PerformanceBenchmark()
    
    @pytest.fixture
    def test_frames(self):
        """Generate test frames for benchmarking."""
        generator = MockAudioGenerator(sample_rate=48000, seed=42)
        
        # Generate 5 seconds of audio (500 frames at 10ms each)
        frames = []
        for i in range(500):
            frame = generator.generate_frame(
                SignalType.SPEECH_LIKE,
                frame_size=480,
                channels=1,
                level_dbfs=-20.0
            )
            frames.append(frame)
        
        return frames
    
    @pytest.fixture
    def multichannel_test_frames(self):
        """Generate multichannel test frames."""
        generator = MockAudioGenerator(sample_rate=48000, seed=42)
        
        # Generate 3 seconds of 8-channel audio
        frames = []
        for i in range(300):
            frame = generator.generate_frame(
                SignalType.SPEECH_LIKE,
                frame_size=480,
                channels=8,
                level_dbfs=-20.0
            )
            # Add SSL metadata
            frame.metadata.update({
                'ssl_azimuth': np.sin(i * 0.1) * 30.0,  # Varying direction
                'ssl_elevation': 0.0,
                'ssl_confidence': 0.8
            })
            frames.append(frame)
        
        return frames
    
    async def test_aec_service_performance(self, benchmark, test_frames):
        """Benchmark AEC service performance."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        aec_service = AECService("BenchmarkAEC", config)
        aec_service.mode = AECMode.FULL_DUPLEX
        
        # Enable test reference for benchmarking
        aec_service._enable_test_reference(True)
        
        metrics = await benchmark.benchmark_service(
            aec_service, test_frames, "AEC Service"
        )
        
        # Performance assertions
        assert metrics['real_time_factor'] >= 1.0, "AEC should run faster than real-time"
        assert metrics['p95_latency_ms'] <= 40.0, "AEC P95 latency should be ≤ 40ms"
        assert metrics['avg_latency_ms'] <= 20.0, "AEC average latency should be ≤ 20ms"
    
    async def test_ssl_service_performance(self, benchmark, multichannel_test_frames):
        """Benchmark SSL service performance."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=8)
        mic_array = create_linear_array(8, spacing=0.05)
        ssl_service = SSLService("BenchmarkSSL", config, mic_array)
        
        metrics = await benchmark.benchmark_service(
            ssl_service, multichannel_test_frames, "SSL Service"
        )
        
        # Performance assertions
        assert metrics['real_time_factor'] >= 1.0, "SSL should run faster than real-time"
        assert metrics['p95_latency_ms'] <= 40.0, "SSL P95 latency should be ≤ 40ms"
    
    async def test_agc_service_performance(self, benchmark, test_frames):
        """Benchmark AGC service performance."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        agc_service = AGCService("BenchmarkAGC", config, mode=AGCMode.BALANCED)
        
        # Add SSL metadata to frames for AGC
        for frame in test_frames:
            frame.metadata.update({
                'ssl_direction': 0.0,
                'ssl_confidence': 0.8
            })
        
        metrics = await benchmark.benchmark_service(
            agc_service, test_frames, "AGC Service"
        )
        
        # Performance assertions
        assert metrics['real_time_factor'] >= 1.0, "AGC should run faster than real-time"
        assert metrics['p95_latency_ms'] <= 40.0, "AGC P95 latency should be ≤ 40ms"
        assert metrics['avg_latency_ms'] <= 15.0, "AGC average latency should be ≤ 15ms"
    
    async def test_beamformer_service_performance(self, benchmark, multichannel_test_frames):
        """Benchmark Beamformer service performance."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=8)
        mic_array = create_linear_array(8, spacing=0.05)
        beamformer_service = BeamformerService(
            "BenchmarkBeamformer", config, mic_array,
            algorithm=BeamformingAlgorithm.DAS
        )
        
        metrics = await benchmark.benchmark_service(
            beamformer_service, multichannel_test_frames, "Beamformer Service (DAS)"
        )
        
        # Performance assertions
        assert metrics['real_time_factor'] >= 1.0, "Beamformer should run faster than real-time"
        assert metrics['p95_latency_ms'] <= 40.0, "Beamformer P95 latency should be ≤ 40ms"
    
    async def test_mixer_service_performance(self, benchmark, test_frames):
        """Benchmark Mixer service performance."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        mixer_service = ClassroomMixerService("BenchmarkMixer", config)
        
        metrics = await benchmark.benchmark_service(
            mixer_service, test_frames, "Mixer Service"
        )
        
        # Performance assertions
        assert metrics['real_time_factor'] >= 1.0, "Mixer should run faster than real-time"
        assert metrics['p95_latency_ms'] <= 40.0, "Mixer P95 latency should be ≤ 40ms"
        assert metrics['avg_latency_ms'] <= 10.0, "Mixer average latency should be ≤ 10ms"
    
    async def test_full_pipeline_performance(self, benchmark):
        """Benchmark full audio processing pipeline."""
        # This is a simplified pipeline test
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=8)
        
        # Create services
        mic_array = create_linear_array(8, spacing=0.05)
        ssl_service = SSLService("PipelineSSL", config, mic_array)
        
        beamformer_config = AudioConfig(sample_rate=48000, frame_size=480, channels=8)
        beamformer_service = BeamformerService(
            "PipelineBeamformer", beamformer_config, mic_array
        )
        
        agc_config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        agc_service = AGCService("PipelineAGC", agc_config)
        
        # Generate test data
        generator = MockAudioGenerator(sample_rate=48000, seed=42)
        frames = []
        for i in range(200):  # 2 seconds
            frame = generator.generate_frame(
                SignalType.TEACHER_VOICE,
                frame_size=480,
                channels=8,
                level_dbfs=-25.0
            )
            frames.append(frame)
        
        # Benchmark pipeline processing
        pipeline_latencies = []
        
        await ssl_service.start()
        await beamformer_service.start()
        await agc_service.start()
        
        try:
            total_start = time.time()
            
            for frame in frames:
                pipeline_start = time.time()
                
                # SSL processing
                ssl_result = await ssl_service.process(frame)
                if not ssl_result.success:
                    continue
                
                # Beamforming
                bf_result = await beamformer_service.process(ssl_result.data)
                if not bf_result.success:
                    continue
                
                # AGC processing
                agc_result = await agc_service.process(bf_result.data)
                if not agc_result.success:
                    continue
                
                pipeline_end = time.time()
                pipeline_latency = (pipeline_end - pipeline_start) * 1000
                pipeline_latencies.append(pipeline_latency)
            
            total_end = time.time()
            total_time = total_end - total_start
            
            # Calculate pipeline metrics
            if pipeline_latencies:
                pipeline_metrics = {
                    'service_name': 'Full Pipeline (SSL+Beamformer+AGC)',
                    'frames_processed': len(pipeline_latencies),
                    'total_time_seconds': total_time,
                    'throughput_fps': len(frames) / total_time,
                    'avg_latency_ms': statistics.mean(pipeline_latencies),
                    'max_latency_ms': max(pipeline_latencies),
                    'p95_latency_ms': np.percentile(pipeline_latencies, 95),
                    'p99_latency_ms': np.percentile(pipeline_latencies, 99),
                    'real_time_factor': (len(frames) * 0.01) / total_time
                }
                
                benchmark.results['Full Pipeline'] = pipeline_metrics
                
                # Performance assertions for full pipeline
                assert pipeline_metrics['real_time_factor'] >= 1.0, \
                    "Full pipeline should run faster than real-time"
                assert pipeline_metrics['p95_latency_ms'] <= 40.0, \
                    "Full pipeline P95 latency should be ≤ 40ms"
                assert pipeline_metrics['avg_latency_ms'] <= 30.0, \
                    "Full pipeline average latency should be ≤ 30ms"
        
        finally:
            await ssl_service.stop()
            await beamformer_service.stop()
            await agc_service.stop()


class TestStressTests:
    """Stress tests for audio processing services."""
    
    async def test_sustained_load(self):
        """Test services under sustained load."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        agc_service = AGCService("StressAGC", config)
        
        generator = MockAudioGenerator(sample_rate=48000, seed=42)
        
        await agc_service.start()
        
        try:
            # Run for 30 seconds of audio (3000 frames)
            start_time = time.time()
            successful_frames = 0
            failed_frames = 0
            
            for i in range(3000):
                frame = generator.generate_frame(
                    SignalType.SPEECH_LIKE,
                    frame_size=480,
                    channels=1,
                    level_dbfs=-20.0
                )
                frame.metadata.update({
                    'ssl_direction': 0.0,
                    'ssl_confidence': 0.8
                })
                
                result = await agc_service.process(frame)
                
                if result.success:
                    successful_frames += 1
                else:
                    failed_frames += 1
                
                # Brief pause to simulate real-time processing
                if i % 100 == 0:  # Every second
                    await asyncio.sleep(0.001)
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Assertions
            success_rate = successful_frames / (successful_frames + failed_frames)
            assert success_rate >= 0.99, f"Success rate {success_rate:.3f} should be ≥ 99%"
            
            # Should process faster than real-time
            real_time_factor = 30.0 / processing_time  # 30 seconds of audio
            assert real_time_factor >= 1.0, \
                f"Real-time factor {real_time_factor:.2f} should be ≥ 1.0"
        
        finally:
            await agc_service.stop()
    
    async def test_memory_stability(self):
        """Test memory usage stability over time."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=8)
        mic_array = create_linear_array(8, spacing=0.05)
        ssl_service = SSLService("MemorySSL", config, mic_array)
        
        generator = MockAudioGenerator(sample_rate=48000, seed=42)
        
        await ssl_service.start()
        
        try:
            # Process frames and check that service doesn't accumulate state
            initial_metrics = ssl_service.get_ssl_metrics()
            
            # Process 1000 frames
            for i in range(1000):
                frame = generator.generate_frame(
                    SignalType.SPEECH_LIKE,
                    frame_size=480,
                    channels=8,
                    level_dbfs=-20.0
                )
                
                result = await ssl_service.process(frame)
                assert result.success
            
            # Check metrics haven't grown unbounded
            final_metrics = ssl_service.get_ssl_metrics()
            
            # Directions estimated should have increased
            assert final_metrics['directions_estimated'] > initial_metrics['directions_estimated']
            
            # But should be reasonable (not accumulating unbounded state)
            assert final_metrics['directions_estimated'] <= 1000
        
        finally:
            await ssl_service.stop()
    
    async def test_concurrent_processing(self):
        """Test concurrent processing of multiple streams."""
        config = AudioConfig(sample_rate=48000, frame_size=480, channels=1)
        
        # Create multiple AGC services
        services = []
        for i in range(4):
            service = AGCService(f"ConcurrentAGC_{i}", config)
            services.append(service)
        
        generator = MockAudioGenerator(sample_rate=48000, seed=42)
        
        # Start all services
        for service in services:
            await service.start()
        
        try:
            async def process_stream(service, stream_id):
                """Process frames for one stream."""
                successful = 0
                failed = 0
                
                for i in range(100):  # 1 second of audio per stream
                    frame = generator.generate_frame(
                        SignalType.SPEECH_LIKE,
                        frame_size=480,
                        channels=1,
                        level_dbfs=-20.0
                    )
                    frame.metadata.update({
                        'ssl_direction': stream_id * 45.0,  # Different directions
                        'ssl_confidence': 0.8
                    })
                    
                    result = await service.process(frame)
                    
                    if result.success:
                        successful += 1
                    else:
                        failed += 1
                
                return successful, failed
            
            # Process all streams concurrently
            tasks = []
            for i, service in enumerate(services):
                task = asyncio.create_task(process_stream(service, i))
                tasks.append(task)
            
            # Wait for all streams to complete
            results = await asyncio.gather(*tasks)
            
            # Check that all streams processed successfully
            for i, (successful, failed) in enumerate(results):
                success_rate = successful / (successful + failed)
                assert success_rate >= 0.95, \
                    f"Stream {i} success rate {success_rate:.3f} should be ≥ 95%"
        
        finally:
            # Stop all services
            for service in services:
                await service.stop()


# Utility function to run all benchmarks
async def run_all_benchmarks():
    """Run all performance benchmarks and print results."""
    benchmark = PerformanceBenchmark()
    test_instance = TestPerformanceBenchmarks()
    
    # Generate test data
    generator = MockAudioGenerator(sample_rate=48000, seed=42)
    
    # Single channel frames
    test_frames = []
    for i in range(500):
        frame = generator.generate_frame(
            SignalType.SPEECH_LIKE,
            frame_size=480,
            channels=1,
            level_dbfs=-20.0
        )
        frame.metadata.update({
            'ssl_direction': 0.0,
            'ssl_confidence': 0.8
        })
        test_frames.append(frame)
    
    # Multi-channel frames
    multichannel_frames = []
    for i in range(300):
        frame = generator.generate_frame(
            SignalType.SPEECH_LIKE,
            frame_size=480,
            channels=8,
            level_dbfs=-20.0
        )
        frame.metadata.update({
            'ssl_azimuth': np.sin(i * 0.1) * 30.0,
            'ssl_elevation': 0.0,
            'ssl_confidence': 0.8
        })
        multichannel_frames.append(frame)
    
    print("Running Audio Processing Performance Benchmarks...")
    
    # Run individual service benchmarks
    await test_instance.test_aec_service_performance(benchmark, test_frames)
    await test_instance.test_ssl_service_performance(benchmark, multichannel_frames)
    await test_instance.test_agc_service_performance(benchmark, test_frames)
    await test_instance.test_beamformer_service_performance(benchmark, multichannel_frames)
    await test_instance.test_mixer_service_performance(benchmark, test_frames)
    
    # Run full pipeline benchmark
    await test_instance.test_full_pipeline_performance(benchmark)
    
    # Print results
    benchmark.print_results()


if __name__ == "__main__":
    # Run benchmarks directly
    asyncio.run(run_all_benchmarks())