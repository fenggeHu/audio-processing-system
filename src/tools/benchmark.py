"""
Audio Processing Performance Benchmark Suite

Comprehensive benchmarking tools for measuring and optimizing
audio processing performance on embedded systems.
"""

import time
import sys
import platform
import threading
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, asdict
from contextlib import contextmanager
import numpy as np
import json


@dataclass
class BenchmarkResult:
    """Results from a benchmark test."""
    test_name: str
    duration_ms: float
    cpu_usage_percent: float
    memory_mb: float
    throughput_samples_per_sec: float
    latency_ms: float
    success: bool
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class SystemInfo:
    """System information for benchmark context."""
    platform: str
    architecture: str
    cpu_count: int
    total_memory_mb: float
    python_version: str
    numpy_version: str
    
    @classmethod
    def collect(cls) -> 'SystemInfo':
        """Collect current system information."""
        try:
            import psutil
            total_memory = psutil.virtual_memory().total / (1024 * 1024)
        except ImportError:
            total_memory = 0.0
        
        return cls(
            platform=platform.platform(),
            architecture=platform.machine(),
            cpu_count=threading.active_count(),
            total_memory_mb=total_memory,
            python_version=platform.python_version(),
            numpy_version=np.__version__,
        )


class PerformanceMonitor:
    """Monitor system performance during benchmarks."""
    
    def __init__(self):
        self.monitoring = False
        self.monitor_thread = None
        self.metrics = []
        
    def start_monitoring(self, interval_sec: float = 0.1) -> None:
        """Start performance monitoring."""
        if self.monitoring:
            return
        
        self.monitoring = True
        self.metrics.clear()
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval_sec,),
            daemon=True
        )
        self.monitor_thread.start()
    
    def stop_monitoring(self) -> Dict[str, float]:
        """Stop monitoring and return average metrics."""
        if not self.monitoring:
            return {}
        
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1.0)
        
        if not self.metrics:
            return {}
        
        # Calculate averages
        avg_metrics = {}
        for key in self.metrics[0].keys():
            values = [m[key] for m in self.metrics if key in m]
            avg_metrics[key] = sum(values) / len(values) if values else 0.0
        
        return avg_metrics
    
    def _monitor_loop(self, interval_sec: float) -> None:
        """Monitoring loop running in separate thread."""
        try:
            import psutil
            process = psutil.Process()
        except ImportError:
            return
        
        while self.monitoring:
            try:
                cpu_percent = process.cpu_percent()
                memory_info = process.memory_info()
                memory_mb = memory_info.rss / (1024 * 1024)
                
                self.metrics.append({
                    'cpu_percent': cpu_percent,
                    'memory_mb': memory_mb,
                    'timestamp': time.time(),
                })
                
                time.sleep(interval_sec)
            except Exception:
                break


class AudioBenchmarkSuite:
    """Comprehensive audio processing benchmark suite."""
    
    def __init__(self):
        self.monitor = PerformanceMonitor()
        self.results = []
        self.system_info = SystemInfo.collect()
    
    @contextmanager
    def benchmark_context(self, test_name: str):
        """Context manager for benchmarking operations."""
        print(f"Running benchmark: {test_name}")
        
        # Start monitoring
        self.monitor.start_monitoring()
        start_time = time.perf_counter()
        
        success = True
        error_message = None
        
        try:
            yield
        except Exception as e:
            success = False
            error_message = str(e)
            print(f"  Error: {error_message}")
        finally:
            # Stop monitoring and collect metrics
            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000
            
            avg_metrics = self.monitor.stop_monitoring()
            
            result = BenchmarkResult(
                test_name=test_name,
                duration_ms=duration_ms,
                cpu_usage_percent=avg_metrics.get('cpu_percent', 0.0),
                memory_mb=avg_metrics.get('memory_mb', 0.0),
                throughput_samples_per_sec=0.0,  # Will be calculated by specific tests
                latency_ms=duration_ms,  # Default to total duration
                success=success,
                error_message=error_message,
            )
            
            self.results.append(result)
            
            if success:
                print(f"  Duration: {duration_ms:.2f}ms")
                print(f"  CPU: {result.cpu_usage_percent:.1f}%")
                print(f"  Memory: {result.memory_mb:.1f}MB")
            
    def benchmark_numpy_operations(self) -> None:
        """Benchmark basic NumPy operations."""
        sizes = [1024, 4096, 16384, 65536]
        
        for size in sizes:
            with self.benchmark_context(f"numpy_fft_{size}"):
                # Generate test signal
                signal = np.random.randn(size).astype(np.float32)
                
                # Perform FFT operations
                for _ in range(100):
                    fft_result = np.fft.fft(signal)
                    ifft_result = np.fft.ifft(fft_result)
                
                # Calculate throughput
                samples_processed = size * 100 * 2  # FFT + IFFT
                duration_sec = self.results[-1].duration_ms / 1000
                self.results[-1].throughput_samples_per_sec = samples_processed / duration_sec
    
    def benchmark_audio_filtering(self) -> None:
        """Benchmark audio filtering operations."""
        from scipy import signal as scipy_signal
        
        sample_rates = [44100, 48000, 96000]
        filter_orders = [4, 8, 16]
        
        for sr in sample_rates:
            for order in filter_orders:
                test_name = f"filter_sr{sr}_order{order}"
                
                with self.benchmark_context(test_name):
                    # Generate test signal (1 second)
                    duration = 1.0
                    samples = int(sr * duration)
                    test_signal = np.random.randn(samples).astype(np.float32)
                    
                    # Design filter
                    nyquist = sr / 2
                    low_cutoff = 1000 / nyquist
                    high_cutoff = 8000 / nyquist
                    
                    sos = scipy_signal.butter(
                        order, [low_cutoff, high_cutoff], 
                        btype='band', output='sos'
                    )
                    
                    # Apply filter multiple times
                    for _ in range(10):
                        filtered = scipy_signal.sosfilt(sos, test_signal)
                    
                    # Calculate throughput
                    samples_processed = samples * 10
                    duration_sec = self.results[-1].duration_ms / 1000
                    self.results[-1].throughput_samples_per_sec = samples_processed / duration_sec
    
    def benchmark_webrtc_components(self) -> None:
        """Benchmark WebRTC audio processing components."""
        try:
            import webrtcvad
        except ImportError:
            print("WebRTC VAD not available, skipping WebRTC benchmarks")
            return
        
        # VAD benchmark
        with self.benchmark_context("webrtc_vad"):
            vad = webrtcvad.Vad(3)  # Most aggressive mode
            
            # Generate test audio (16kHz, 16-bit)
            sample_rate = 16000
            duration = 10.0  # 10 seconds
            samples = int(sample_rate * duration)
            
            # Create frames (30ms each)
            frame_duration_ms = 30
            frame_samples = int(sample_rate * frame_duration_ms / 1000)
            
            frames_processed = 0
            for i in range(0, samples - frame_samples, frame_samples):
                frame = np.random.randint(-32768, 32767, frame_samples, dtype=np.int16)
                frame_bytes = frame.tobytes()
                
                # Process frame
                is_speech = vad.is_speech(frame_bytes, sample_rate)
                frames_processed += 1
            
            # Calculate throughput
            duration_sec = self.results[-1].duration_ms / 1000
            self.results[-1].throughput_samples_per_sec = (frames_processed * frame_samples) / duration_sec
    
    def benchmark_memory_operations(self) -> None:
        """Benchmark memory-intensive operations."""
        buffer_sizes = [1024, 4096, 16384, 65536]  # In samples
        
        for size in buffer_sizes:
            # Memory allocation benchmark
            with self.benchmark_context(f"memory_alloc_{size}"):
                buffers = []
                for _ in range(1000):
                    buffer = np.zeros(size, dtype=np.float32)
                    buffers.append(buffer)
                
                # Clean up
                del buffers
            
            # Memory copy benchmark
            with self.benchmark_context(f"memory_copy_{size}"):
                source = np.random.randn(size).astype(np.float32)
                
                for _ in range(1000):
                    dest = np.copy(source)
                
                samples_processed = size * 1000
                duration_sec = self.results[-1].duration_ms / 1000
                self.results[-1].throughput_samples_per_sec = samples_processed / duration_sec
    
    def benchmark_threading_performance(self) -> None:
        """Benchmark multi-threading performance."""
        def worker_function(data: np.ndarray, iterations: int):
            """Worker function for threading test."""
            for _ in range(iterations):
                result = np.fft.fft(data)
                result = np.fft.ifft(result)
        
        data_size = 4096
        iterations = 100
        thread_counts = [1, 2, 4, 8]
        
        test_data = np.random.randn(data_size).astype(np.complex64)
        
        for thread_count in thread_counts:
            if thread_count > threading.active_count():
                continue
            
            with self.benchmark_context(f"threading_{thread_count}_threads"):
                threads = []
                
                for _ in range(thread_count):
                    thread = threading.Thread(
                        target=worker_function,
                        args=(test_data, iterations // thread_count)
                    )
                    threads.append(thread)
                
                # Start all threads
                for thread in threads:
                    thread.start()
                
                # Wait for completion
                for thread in threads:
                    thread.join()
                
                # Calculate throughput
                total_samples = data_size * iterations
                duration_sec = self.results[-1].duration_ms / 1000
                self.results[-1].throughput_samples_per_sec = total_samples / duration_sec
    
    def run_all_benchmarks(self) -> None:
        """Run all benchmark tests."""
        print("Starting Audio Processing Benchmark Suite")
        print(f"System: {self.system_info.platform}")
        print(f"Architecture: {self.system_info.architecture}")
        print(f"CPU Count: {self.system_info.cpu_count}")
        print(f"Memory: {self.system_info.total_memory_mb:.0f}MB")
        print("-" * 60)
        
        # Run benchmark categories
        self.benchmark_numpy_operations()
        self.benchmark_audio_filtering()
        self.benchmark_webrtc_components()
        self.benchmark_memory_operations()
        self.benchmark_threading_performance()
        
        print("-" * 60)
        print("Benchmark suite completed")
    
    def generate_report(self, output_file: Optional[Path] = None) -> Dict[str, Any]:
        """Generate comprehensive benchmark report."""
        # Calculate summary statistics
        successful_tests = [r for r in self.results if r.success]
        failed_tests = [r for r in self.results if not r.success]
        
        if successful_tests:
            avg_duration = sum(r.duration_ms for r in successful_tests) / len(successful_tests)
            avg_cpu = sum(r.cpu_usage_percent for r in successful_tests) / len(successful_tests)
            avg_memory = sum(r.memory_mb for r in successful_tests) / len(successful_tests)
            total_throughput = sum(r.throughput_samples_per_sec for r in successful_tests)
        else:
            avg_duration = avg_cpu = avg_memory = total_throughput = 0.0
        
        report = {
            'system_info': asdict(self.system_info),
            'summary': {
                'total_tests': len(self.results),
                'successful_tests': len(successful_tests),
                'failed_tests': len(failed_tests),
                'average_duration_ms': avg_duration,
                'average_cpu_percent': avg_cpu,
                'average_memory_mb': avg_memory,
                'total_throughput_samples_per_sec': total_throughput,
            },
            'detailed_results': [asdict(r) for r in self.results],
            'timestamp': time.time(),
        }
        
        # Save to file if requested
        if output_file:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2)
            print(f"Benchmark report saved to: {output_file}")
        
        return report
    
    def print_summary(self) -> None:
        """Print benchmark summary to console."""
        successful_tests = [r for r in self.results if r.success]
        failed_tests = [r for r in self.results if not r.success]
        
        print("\nBenchmark Summary:")
        print(f"  Total tests: {len(self.results)}")
        print(f"  Successful: {len(successful_tests)}")
        print(f"  Failed: {len(failed_tests)}")
        
        if successful_tests:
            avg_duration = sum(r.duration_ms for r in successful_tests) / len(successful_tests)
            avg_cpu = sum(r.cpu_usage_percent for r in successful_tests) / len(successful_tests)
            avg_memory = sum(r.memory_mb for r in successful_tests) / len(successful_tests)
            
            print(f"  Average duration: {avg_duration:.2f}ms")
            print(f"  Average CPU usage: {avg_cpu:.1f}%")
            print(f"  Average memory usage: {avg_memory:.1f}MB")
        
        if failed_tests:
            print("\nFailed tests:")
            for test in failed_tests:
                print(f"  - {test.test_name}: {test.error_message}")


def main():
    """Main entry point for benchmark tool."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Audio Processing Performance Benchmark")
    parser.add_argument("--output", "-o", type=Path, help="Output file for benchmark report")
    parser.add_argument("--quick", action="store_true", help="Run quick benchmark subset")
    
    args = parser.parse_args()
    
    # Create benchmark suite
    suite = AudioBenchmarkSuite()
    
    try:
        if args.quick:
            # Run subset of benchmarks for quick testing
            suite.benchmark_numpy_operations()
            suite.benchmark_memory_operations()
        else:
            # Run full benchmark suite
            suite.run_all_benchmarks()
        
        # Generate and display results
        suite.print_summary()
        
        # Save report if requested
        if args.output:
            suite.generate_report(args.output)
        
    except KeyboardInterrupt:
        print("\nBenchmark interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Benchmark failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()