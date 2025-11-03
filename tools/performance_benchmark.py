#!/usr/bin/env python3
"""
音频处理系统性能基准测试工具
Audio Processing System Performance Benchmark Tool
"""

import time
import json
import asyncio
import argparse
import statistics
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
import concurrent.futures

@dataclass
class BenchmarkResult:
    """基准测试结果数据类"""
    test_name: str
    duration_seconds: float
    throughput_mbps: Optional[float] = None
    latency_ms: Optional[float] = None
    cpu_usage_percent: Optional[float] = None
    memory_usage_mb: Optional[float] = None
    success: bool = True
    error_message: Optional[str] = None
    metadata: Optional[Dict] = None

class AudioProcessingBenchmark:
    """音频处理性能基准测试类"""
    
    def __init__(self, config_path: str = "config/classroom_environments.yaml"):
        self.config_path = config_path
        self.results: List[BenchmarkResult] = []
        self.test_data_dir = Path("test_data")
        self.test_data_dir.mkdir(exist_ok=True)
        
    def run_all_benchmarks(self) -> Dict:
        """运行所有基准测试"""
        print("🚀 开始音频处理系统性能基准测试")
        print("=" * 60)
        
        # 基础性能测试
        self._run_basic_performance_tests()
        
        # 音频处理测试
        self._run_audio_processing_tests()
        
        # 并发性能测试
        asyncio.run(self._run_concurrent_tests())
        
        # 网络性能测试
        self._run_network_tests()
        
        # 内存性能测试
        self._run_memory_tests()
        
        # 生成报告
        return self._generate_report()
    
    def _run_basic_performance_tests(self):
        """运行基础性能测试"""
        print("\n📊 基础性能测试")
        print("-" * 30)
        
        # CPU计算性能测试
        self._test_cpu_performance()
        
        # 内存访问性能测试
        self._test_memory_performance()
        
        # 磁盘I/O性能测试
        self._test_disk_performance()
    
    def _test_cpu_performance(self):
        """CPU性能测试"""
        print("🔄 CPU性能测试...")
        
        start_time = time.time()
        
        # 计算密集型任务
        result = 0
        for i in range(1000000):
            result += i * i
        
        end_time = time.time()
        duration = end_time - start_time
        
        # 计算每秒操作数
        operations_per_second = 1000000 / duration
        
        benchmark_result = BenchmarkResult(
            test_name="CPU计算性能",
            duration_seconds=duration,
            throughput_mbps=operations_per_second / 1000000,  # 转换为M ops/s
            success=True,
            metadata={"operations": 1000000, "ops_per_second": operations_per_second}
        )
        
        self.results.append(benchmark_result)
        print(f"  ✅ 完成 - 耗时: {duration:.3f}s, 性能: {operations_per_second:.0f} ops/s")
    
    def _test_memory_performance(self):
        """内存性能测试"""
        print("🔄 内存性能测试...")
        
        # 测试不同大小的内存分配和访问
        sizes = [1024, 10240, 102400, 1024000]  # 1KB, 10KB, 100KB, 1MB
        
        for size in sizes:
            start_time = time.time()
            
            # 分配内存
            data = bytearray(size)
            
            # 写入数据
            for i in range(0, size, 4):
                if i + 3 < size:
                    data[i:i+4] = (i % 256).to_bytes(4, 'little')
            
            # 读取数据
            checksum = 0
            for i in range(0, size, 4):
                if i + 3 < size:
                    checksum += int.from_bytes(data[i:i+4], 'little')
            
            end_time = time.time()
            duration = end_time - start_time
            
            throughput = (size * 2) / (1024 * 1024) / duration  # MB/s (读+写)
            
            benchmark_result = BenchmarkResult(
                test_name=f"内存性能_{size//1024}KB",
                duration_seconds=duration,
                throughput_mbps=throughput,
                success=True,
                metadata={"size_bytes": size, "checksum": checksum}
            )
            
            self.results.append(benchmark_result)
            print(f"  ✅ {size//1024}KB - 耗时: {duration:.4f}s, 吞吐量: {throughput:.1f} MB/s")
    
    def _test_disk_performance(self):
        """磁盘I/O性能测试"""
        print("🔄 磁盘I/O性能测试...")
        
        test_file = self.test_data_dir / "disk_test.bin"
        test_size = 10 * 1024 * 1024  # 10MB
        
        try:
            # 写入测试
            start_time = time.time()
            with open(test_file, 'wb') as f:
                data = b'A' * 1024  # 1KB块
                for _ in range(test_size // 1024):
                    f.write(data)
                f.flush()
                f.fsync()  # 强制写入磁盘
            write_time = time.time() - start_time
            
            # 读取测试
            start_time = time.time()
            with open(test_file, 'rb') as f:
                while f.read(1024):
                    pass
            read_time = time.time() - start_time
            
            write_throughput = (test_size / (1024 * 1024)) / write_time
            read_throughput = (test_size / (1024 * 1024)) / read_time
            
            # 写入性能
            self.results.append(BenchmarkResult(
                test_name="磁盘写入性能",
                duration_seconds=write_time,
                throughput_mbps=write_throughput,
                success=True,
                metadata={"size_mb": test_size // (1024 * 1024)}
            ))
            
            # 读取性能
            self.results.append(BenchmarkResult(
                test_name="磁盘读取性能",
                duration_seconds=read_time,
                throughput_mbps=read_throughput,
                success=True,
                metadata={"size_mb": test_size // (1024 * 1024)}
            ))
            
            print(f"  ✅ 写入 - 耗时: {write_time:.3f}s, 吞吐量: {write_throughput:.1f} MB/s")
            print(f"  ✅ 读取 - 耗时: {read_time:.3f}s, 吞吐量: {read_throughput:.1f} MB/s")
            
        except Exception as e:
            self.results.append(BenchmarkResult(
                test_name="磁盘I/O性能",
                duration_seconds=0,
                success=False,
                error_message=str(e)
            ))
            print(f"  ❌ 磁盘测试失败: {e}")
        
        finally:
            # 清理测试文件
            if test_file.exists():
                test_file.unlink()
    
    def _run_audio_processing_tests(self):
        """运行音频处理测试"""
        print("\n🎵 音频处理性能测试")
        print("-" * 30)
        
        # FFT性能测试
        self._test_fft_performance()
        
        # 音频滤波性能测试
        self._test_audio_filtering()
        
        # 实时处理延迟测试
        self._test_realtime_latency()
    
    def _test_fft_performance(self):
        """FFT性能测试"""
        print("🔄 FFT性能测试...")
        
        # 测试不同大小的FFT
        sizes = [256, 512, 1024, 2048, 4096]
        
        for size in sizes:
            # 生成测试数据
            test_data = np.random.randn(size).astype(np.float32)
            
            start_time = time.time()
            
            # 执行多次FFT
            iterations = 1000
            for _ in range(iterations):
                fft_result = np.fft.fft(test_data)
            
            end_time = time.time()
            duration = end_time - start_time
            
            ffts_per_second = iterations / duration
            
            benchmark_result = BenchmarkResult(
                test_name=f"FFT性能_{size}点",
                duration_seconds=duration,
                throughput_mbps=ffts_per_second / 1000,  # K FFTs/s
                success=True,
                metadata={
                    "fft_size": size,
                    "iterations": iterations,
                    "ffts_per_second": ffts_per_second
                }
            )
            
            self.results.append(benchmark_result)
            print(f"  ✅ {size}点FFT - {ffts_per_second:.0f} FFTs/s")
    
    def _test_audio_filtering(self):
        """音频滤波性能测试"""
        print("🔄 音频滤波性能测试...")
        
        # 生成测试音频数据 (1秒，48kHz)
        sample_rate = 48000
        duration = 1.0
        samples = int(sample_rate * duration)
        test_audio = np.random.randn(samples).astype(np.float32)
        
        start_time = time.time()
        
        # 简单的低通滤波器
        from scipy import signal
        b, a = signal.butter(4, 1000, 'low', fs=sample_rate)
        
        # 执行滤波
        iterations = 10
        for _ in range(iterations):
            filtered_audio = signal.filtfilt(b, a, test_audio)
        
        end_time = time.time()
        duration_total = end_time - start_time
        
        # 计算实时倍数
        audio_duration = duration * iterations
        real_time_factor = audio_duration / duration_total
        
        benchmark_result = BenchmarkResult(
            test_name="音频滤波性能",
            duration_seconds=duration_total,
            success=True,
            metadata={
                "audio_duration_seconds": audio_duration,
                "real_time_factor": real_time_factor,
                "sample_rate": sample_rate,
                "iterations": iterations
            }
        )
        
        self.results.append(benchmark_result)
        print(f"  ✅ 滤波性能 - 实时倍数: {real_time_factor:.2f}x")
    
    def _test_realtime_latency(self):
        """实时处理延迟测试"""
        print("🔄 实时处理延迟测试...")
        
        # 模拟音频缓冲区处理
        buffer_sizes = [64, 128, 256, 512, 1024]
        sample_rate = 48000
        
        for buffer_size in buffer_sizes:
            latencies = []
            
            # 多次测试取平均值
            for _ in range(100):
                # 生成音频缓冲区
                audio_buffer = np.random.randn(buffer_size).astype(np.float32)
                
                start_time = time.perf_counter()
                
                # 模拟音频处理 (简单的增益调整)
                processed_buffer = audio_buffer * 0.8
                
                end_time = time.perf_counter()
                
                processing_time = (end_time - start_time) * 1000  # 转换为毫秒
                latencies.append(processing_time)
            
            avg_latency = statistics.mean(latencies)
            max_latency = max(latencies)
            min_latency = min(latencies)
            
            # 理论最小延迟 (缓冲区大小决定)
            theoretical_latency = (buffer_size / sample_rate) * 1000
            
            benchmark_result = BenchmarkResult(
                test_name=f"实时延迟_{buffer_size}样本",
                duration_seconds=0,
                latency_ms=avg_latency,
                success=True,
                metadata={
                    "buffer_size": buffer_size,
                    "avg_latency_ms": avg_latency,
                    "max_latency_ms": max_latency,
                    "min_latency_ms": min_latency,
                    "theoretical_latency_ms": theoretical_latency,
                    "sample_rate": sample_rate
                }
            )
            
            self.results.append(benchmark_result)
            print(f"  ✅ {buffer_size}样本 - 平均延迟: {avg_latency:.3f}ms (理论: {theoretical_latency:.1f}ms)")
    
    async def _run_concurrent_tests(self):
        """运行并发性能测试"""
        print("\n⚡ 并发性能测试")
        print("-" * 30)
        
        await self._test_concurrent_processing()
        await self._test_thread_scaling()
    
    async def _test_concurrent_processing(self):
        """并发处理测试"""
        print("🔄 并发处理测试...")
        
        async def process_audio_stream(stream_id: int, duration: float = 1.0):
            """模拟音频流处理"""
            sample_rate = 48000
            samples = int(sample_rate * duration)
            
            start_time = time.time()
            
            # 生成和处理音频数据
            for _ in range(10):  # 处理10个缓冲区
                audio_data = np.random.randn(samples // 10).astype(np.float32)
                # 简单处理
                processed = audio_data * 0.8
                await asyncio.sleep(0.001)  # 模拟I/O等待
            
            end_time = time.time()
            return {
                'stream_id': stream_id,
                'duration': end_time - start_time,
                'success': True
            }
        
        # 测试不同数量的并发流
        concurrent_counts = [1, 2, 4, 8, 16]
        
        for count in concurrent_counts:
            start_time = time.time()
            
            # 创建并发任务
            tasks = [process_audio_stream(i) for i in range(count)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            end_time = time.time()
            total_duration = end_time - start_time
            
            # 统计成功的任务
            successful_tasks = [r for r in results if isinstance(r, dict) and r.get('success')]
            success_rate = len(successful_tasks) / len(results)
            
            benchmark_result = BenchmarkResult(
                test_name=f"并发处理_{count}流",
                duration_seconds=total_duration,
                success=success_rate > 0.9,
                metadata={
                    "concurrent_streams": count,
                    "success_rate": success_rate,
                    "successful_tasks": len(successful_tasks),
                    "total_tasks": len(results)
                }
            )
            
            self.results.append(benchmark_result)
            print(f"  ✅ {count}并发流 - 耗时: {total_duration:.3f}s, 成功率: {success_rate:.1%}")
    
    async def _test_thread_scaling(self):
        """线程扩展性测试"""
        print("🔄 线程扩展性测试...")
        
        def cpu_intensive_task(iterations: int = 100000):
            """CPU密集型任务"""
            result = 0
            for i in range(iterations):
                result += i * i
            return result
        
        # 测试不同线程数
        thread_counts = [1, 2, 4, 8]
        
        for thread_count in thread_counts:
            start_time = time.time()
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
                # 提交任务
                futures = [executor.submit(cpu_intensive_task) for _ in range(thread_count * 2)]
                
                # 等待完成
                results = [future.result() for future in concurrent.futures.as_completed(futures)]
            
            end_time = time.time()
            duration = end_time - start_time
            
            throughput = len(futures) / duration
            
            benchmark_result = BenchmarkResult(
                test_name=f"线程扩展_{thread_count}线程",
                duration_seconds=duration,
                throughput_mbps=throughput,
                success=True,
                metadata={
                    "thread_count": thread_count,
                    "task_count": len(futures),
                    "tasks_per_second": throughput
                }
            )
            
            self.results.append(benchmark_result)
            print(f"  ✅ {thread_count}线程 - 吞吐量: {throughput:.1f} tasks/s")
    
    def _run_network_tests(self):
        """运行网络性能测试"""
        print("\n🌐 网络性能测试")
        print("-" * 30)
        
        self._test_network_throughput()
        self._test_network_latency()
    
    def _test_network_throughput(self):
        """网络吞吐量测试"""
        print("🔄 网络吞吐量测试...")
        
        # 模拟网络数据传输
        data_sizes = [1024, 10240, 102400, 1024000]  # 1KB to 1MB
        
        for size in data_sizes:
            # 生成测试数据
            test_data = b'A' * size
            
            start_time = time.time()
            
            # 模拟网络传输 (序列化/反序列化)
            iterations = 100
            for _ in range(iterations):
                # 模拟发送 (序列化)
                serialized = test_data
                
                # 模拟接收 (反序列化)
                received = serialized
            
            end_time = time.time()
            duration = end_time - start_time
            
            total_bytes = size * iterations * 2  # 发送+接收
            throughput = (total_bytes / (1024 * 1024)) / duration  # MB/s
            
            benchmark_result = BenchmarkResult(
                test_name=f"网络吞吐量_{size//1024}KB",
                duration_seconds=duration,
                throughput_mbps=throughput,
                success=True,
                metadata={
                    "packet_size_bytes": size,
                    "iterations": iterations,
                    "total_bytes": total_bytes
                }
            )
            
            self.results.append(benchmark_result)
            print(f"  ✅ {size//1024}KB包 - 吞吐量: {throughput:.1f} MB/s")
    
    def _test_network_latency(self):
        """网络延迟测试"""
        print("🔄 网络延迟测试...")
        
        import subprocess
        
        try:
            # 测试本地回环延迟
            result = subprocess.run(
                ['ping', '-c', '10', '127.0.0.1'],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode == 0:
                # 解析ping结果
                lines = result.stdout.split('\n')
                latencies = []
                
                for line in lines:
                    if 'time=' in line:
                        try:
                            time_part = line.split('time=')[1].split()[0]
                            latency = float(time_part)
                            latencies.append(latency)
                        except (IndexError, ValueError):
                            continue
                
                if latencies:
                    avg_latency = statistics.mean(latencies)
                    min_latency = min(latencies)
                    max_latency = max(latencies)
                    
                    benchmark_result = BenchmarkResult(
                        test_name="网络延迟_本地回环",
                        duration_seconds=0,
                        latency_ms=avg_latency,
                        success=True,
                        metadata={
                            "avg_latency_ms": avg_latency,
                            "min_latency_ms": min_latency,
                            "max_latency_ms": max_latency,
                            "packet_count": len(latencies)
                        }
                    )
                    
                    self.results.append(benchmark_result)
                    print(f"  ✅ 本地回环 - 平均延迟: {avg_latency:.2f}ms")
                else:
                    raise ValueError("无法解析ping结果")
            else:
                raise subprocess.CalledProcessError(result.returncode, "ping")
        
        except Exception as e:
            benchmark_result = BenchmarkResult(
                test_name="网络延迟测试",
                duration_seconds=0,
                success=False,
                error_message=str(e)
            )
            
            self.results.append(benchmark_result)
            print(f"  ❌ 网络延迟测试失败: {e}")
    
    def _run_memory_tests(self):
        """运行内存性能测试"""
        print("\n💾 内存性能测试")
        print("-" * 30)
        
        self._test_memory_allocation()
        self._test_memory_bandwidth()
    
    def _test_memory_allocation(self):
        """内存分配性能测试"""
        print("🔄 内存分配性能测试...")
        
        allocation_sizes = [1024, 10240, 102400, 1024000]  # 1KB to 1MB
        
        for size in allocation_sizes:
            start_time = time.time()
            
            # 大量内存分配和释放
            allocations = []
            iterations = 1000
            
            for _ in range(iterations):
                data = bytearray(size)
                allocations.append(data)
            
            # 清理
            allocations.clear()
            
            end_time = time.time()
            duration = end_time - start_time
            
            allocations_per_second = iterations / duration
            
            benchmark_result = BenchmarkResult(
                test_name=f"内存分配_{size//1024}KB",
                duration_seconds=duration,
                throughput_mbps=allocations_per_second / 1000,  # K allocs/s
                success=True,
                metadata={
                    "allocation_size_bytes": size,
                    "iterations": iterations,
                    "allocations_per_second": allocations_per_second
                }
            )
            
            self.results.append(benchmark_result)
            print(f"  ✅ {size//1024}KB - {allocations_per_second:.0f} allocs/s")
    
    def _test_memory_bandwidth(self):
        """内存带宽测试"""
        print("🔄 内存带宽测试...")
        
        # 大块内存复制测试
        size = 10 * 1024 * 1024  # 10MB
        source = bytearray(size)
        
        # 填充源数据
        for i in range(0, size, 4):
            if i + 3 < size:
                source[i:i+4] = (i % 256).to_bytes(4, 'little')
        
        start_time = time.time()
        
        # 执行多次内存复制
        iterations = 100
        for _ in range(iterations):
            destination = bytearray(source)
        
        end_time = time.time()
        duration = end_time - start_time
        
        total_bytes = size * iterations
        bandwidth = (total_bytes / (1024 * 1024)) / duration  # MB/s
        
        benchmark_result = BenchmarkResult(
            test_name="内存带宽",
            duration_seconds=duration,
            throughput_mbps=bandwidth,
            success=True,
            metadata={
                "block_size_mb": size // (1024 * 1024),
                "iterations": iterations,
                "total_mb": total_bytes // (1024 * 1024)
            }
        )
        
        self.results.append(benchmark_result)
        print(f"  ✅ 内存带宽 - {bandwidth:.1f} MB/s")
    
    def _generate_report(self) -> Dict:
        """生成基准测试报告"""
        print("\n📋 生成基准测试报告...")
        
        # 统计结果
        total_tests = len(self.results)
        successful_tests = len([r for r in self.results if r.success])
        failed_tests = total_tests - successful_tests
        
        # 分类结果
        categories = {}
        for result in self.results:
            category = result.test_name.split('_')[0] if '_' in result.test_name else result.test_name.split('性能')[0]
            if category not in categories:
                categories[category] = []
            categories[category].append(result)
        
        # 生成报告
        report = {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_tests': total_tests,
                'successful_tests': successful_tests,
                'failed_tests': failed_tests,
                'success_rate': successful_tests / total_tests if total_tests > 0 else 0
            },
            'categories': {},
            'detailed_results': [asdict(r) for r in self.results],
            'recommendations': self._generate_recommendations()
        }
        
        # 按类别统计
        for category, results in categories.items():
            successful = len([r for r in results if r.success])
            report['categories'][category] = {
                'total': len(results),
                'successful': successful,
                'failed': len(results) - successful
            }
        
        # 保存报告
        report_file = Path(f"benchmark_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"📄 基准测试报告已保存到: {report_file}")
        
        # 显示摘要
        print(f"\n📊 测试摘要:")
        print(f"  总测试数: {total_tests}")
        print(f"  成功: {successful_tests}")
        print(f"  失败: {failed_tests}")
        print(f"  成功率: {report['summary']['success_rate']:.1%}")
        
        return report
    
    def _generate_recommendations(self) -> List[str]:
        """生成性能优化建议"""
        recommendations = []
        
        # 分析结果并生成建议
        for result in self.results:
            if not result.success:
                recommendations.append(f"修复失败的测试: {result.test_name}")
                continue
            
            # CPU性能建议
            if "CPU" in result.test_name and result.metadata:
                ops_per_second = result.metadata.get('ops_per_second', 0)
                if ops_per_second < 1000000:  # 低于100万ops/s
                    recommendations.append("CPU性能较低，建议升级处理器或启用性能模式")
            
            # 内存性能建议
            if "内存" in result.test_name and result.throughput_mbps:
                if result.throughput_mbps < 1000:  # 低于1GB/s
                    recommendations.append("内存带宽较低，建议升级到更快的内存")
            
            # 磁盘性能建议
            if "磁盘" in result.test_name and result.throughput_mbps:
                if result.throughput_mbps < 100:  # 低于100MB/s
                    recommendations.append("磁盘I/O性能较低，建议使用SSD存储")
            
            # 实时延迟建议
            if "实时延迟" in result.test_name and result.latency_ms:
                if result.latency_ms > 10:  # 高于10ms
                    recommendations.append("音频处理延迟较高，建议优化算法或减小缓冲区")
        
        if not recommendations:
            recommendations.append("系统性能良好，无需特殊优化")
        
        return list(set(recommendations))  # 去重

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='音频处理系统性能基准测试')
    parser.add_argument('--config', default='config/classroom_environments.yaml',
                       help='配置文件路径')
    parser.add_argument('--output', help='输出报告文件路径')
    parser.add_argument('--category', choices=['basic', 'audio', 'concurrent', 'network', 'memory', 'all'],
                       default='all', help='测试类别')
    
    args = parser.parse_args()
    
    benchmark = AudioProcessingBenchmark(args.config)
    
    # 根据类别运行测试
    if args.category == 'all':
        report = benchmark.run_all_benchmarks()
    else:
        # 运行特定类别的测试
        print(f"🚀 运行 {args.category} 类别测试")
        if args.category == 'basic':
            benchmark._run_basic_performance_tests()
        elif args.category == 'audio':
            benchmark._run_audio_processing_tests()
        elif args.category == 'concurrent':
            asyncio.run(benchmark._run_concurrent_tests())
        elif args.category == 'network':
            benchmark._run_network_tests()
        elif args.category == 'memory':
            benchmark._run_memory_tests()
        
        report = benchmark._generate_report()
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"📄 报告已保存到: {args.output}")

if __name__ == "__main__":
    main()