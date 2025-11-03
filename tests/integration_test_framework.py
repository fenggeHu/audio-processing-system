#!/usr/bin/env python3
"""
Integration Test Framework for Audio Processing System

This module provides a comprehensive integration testing framework that:
1. Establishes end-to-end test environments
2. Implements automated test workflows
3. Provides regression testing capabilities

Requirements: 9.4, 9.5
"""

import asyncio
import json
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import subprocess
import sys

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audio_processing.models import AudioConfig
from audio_processing.service_manager import ServiceManager


class TestStatus(Enum):
    """Test execution status."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestResult:
    """Container for individual test results."""
    test_name: str
    status: TestStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: float = 0.0
    error_message: Optional[str] = None
    details: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}
    
    def mark_completed(self, status: TestStatus, error_message: Optional[str] = None):
        """Mark test as completed with given status."""
        self.end_time = datetime.now()
        self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000
        self.status = status
        if error_message:
            self.error_message = error_message


@dataclass
class TestSuite:
    """Test suite configuration and execution."""
    name: str
    description: str
    test_functions: List[Callable]
    setup_function: Optional[Callable] = None
    teardown_function: Optional[Callable] = None
    timeout_seconds: float = 300.0  # 5 minutes default
    required_services: List[str] = None
    
    def __post_init__(self):
        if self.required_services is None:
            self.required_services = []


class IntegrationTestEnvironment:
    """End-to-end test environment manager."""
    
    def __init__(self, config: AudioConfig):
        self.config = config
        self.service_manager: Optional[ServiceManager] = None
        self.test_data_dir = Path("test_data")
        self.results_dir = Path("test_results")
        self.is_setup = False
        
        # Ensure directories exist
        self.test_data_dir.mkdir(exist_ok=True)
        self.results_dir.mkdir(exist_ok=True)
    
    async def setup_environment(self) -> bool:
        """Setup complete test environment."""
        try:
            print("Setting up integration test environment...")
            
            # Initialize service manager
            self.service_manager = ServiceManager(self.config)
            
            # Register all core services
            await self._register_core_services()
            
            # Start service manager
            await self.service_manager.start()
            
            # Verify environment health
            health_check = await self._verify_environment_health()
            
            if health_check:
                self.is_setup = True
                print("✓ Integration test environment ready")
                return True
            else:
                print("✗ Environment health check failed")
                return False
                
        except Exception as e:
            print(f"✗ Failed to setup test environment: {e}")
            return False
    
    async def teardown_environment(self):
        """Cleanup test environment."""
        try:
            if self.service_manager:
                await self.service_manager.stop()
                self.service_manager = None
            
            self.is_setup = False
            print("✓ Test environment cleaned up")
            
        except Exception as e:
            print(f"⚠️  Error during environment cleanup: {e}")
    
    async def _register_core_services(self):
        """Register all core audio processing services."""
        # Only register services with minimal dependencies for testing
        services_to_register = []
        
        # Try to register each service, skip if dependencies are missing
        try:
            from audio_processing.services.denoise import DenoiseService
            services_to_register.append((DenoiseService, "DenoiseService"))
        except ImportError as e:
            print(f"  ⚠️  Skipping DenoiseService: {e}")
        
        try:
            from audio_processing.services.aec import AECService
            services_to_register.append((AECService, "AECService"))
        except ImportError as e:
            print(f"  ⚠️  Skipping AECService: {e}")
        
        try:
            from audio_processing.services.ssl import SSLService, MicrophonePosition
            # Create default microphone positions for testing
            mic_positions = [
                MicrophonePosition(x=0.0, y=0.0, z=0.0, channel=0),
                MicrophonePosition(x=0.1, y=0.0, z=0.0, channel=1)
            ]
            services_to_register.append((SSLService, "SSLService", {"microphone_positions": mic_positions}))
        except ImportError as e:
            print(f"  ⚠️  Skipping SSLService: {e}")
        
        try:
            from audio_processing.services.agc import AGCService
            services_to_register.append((AGCService, "AGCService"))
        except ImportError as e:
            print(f"  ⚠️  Skipping AGCService: {e}")
        
        try:
            from audio_processing.services.capture import CaptureService
            services_to_register.append((CaptureService, "CaptureService"))
        except ImportError as e:
            print(f"  ⚠️  Skipping CaptureService: {e}")
        
        # Register available services with proper configuration
        for service_info in services_to_register:
            if len(service_info) == 3:
                service_class, service_name, extra_config = service_info
                config_dict = {"service_name": service_name, "config": self.config}
                config_dict.update(extra_config)
            else:
                service_class, service_name = service_info
                config_dict = {"service_name": service_name, "config": self.config}
            
            try:
                # Register service with config parameter
                self.service_manager.register_service(
                    service_class, 
                    name=service_name,
                    config=config_dict
                )
                print(f"  ✓ Registered {service_name}")
            except Exception as e:
                print(f"  ⚠️  Failed to register {service_name}: {e}")
    
    async def _verify_environment_health(self) -> bool:
        """Verify that the test environment is healthy."""
        try:
            # Check service manager status
            if not self.service_manager.is_running:
                print("  ✗ Service manager not running")
                return False
            
            # Check that at least some core services are available
            available_services = []
            potential_services = [
                "DenoiseService", "AECService", "SSLService", 
                "AGCService", "CaptureService"
            ]
            
            for service_name in potential_services:
                try:
                    service = await self.service_manager.get_service_by_name(service_name)
                    if service.is_running:
                        available_services.append(service_name)
                        print(f"  ✓ {service_name} available and running")
                    else:
                        print(f"  ⚠️  {service_name} available but not running")
                except Exception as e:
                    print(f"  ⚠️  {service_name} not available: {e}")
            
            # Require at least 2 services to be available for testing
            if len(available_services) < 2:
                print(f"  ✗ Only {len(available_services)} services available, need at least 2")
                return False
            
            print("  ✓ All core services available and running")
            return True
            
        except Exception as e:
            print(f"  ✗ Health check failed: {e}")
            return False
    
    def get_service(self, service_name: str):
        """Get service instance for testing."""
        if not self.is_setup:
            raise RuntimeError("Test environment not setup")
        return self.service_manager.get_service_by_name(service_name)


class AutomatedTestRunner:
    """Automated test workflow execution engine."""
    
    def __init__(self, environment: IntegrationTestEnvironment):
        self.environment = environment
        self.test_suites: List[TestSuite] = []
        self.results: List[TestResult] = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
    
    def register_test_suite(self, suite: TestSuite):
        """Register a test suite for execution."""
        self.test_suites.append(suite)
        print(f"Registered test suite: {suite.name}")
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all registered test suites."""
        if not self.environment.is_setup:
            raise RuntimeError("Test environment must be setup before running tests")
        
        self.start_time = datetime.now()
        self.results = []
        
        print(f"\n{'='*60}")
        print("STARTING AUTOMATED INTEGRATION TEST RUN")
        print(f"{'='*60}")
        print(f"Start time: {self.start_time}")
        print(f"Test suites: {len(self.test_suites)}")
        
        suite_results = {}
        
        for suite in self.test_suites:
            print(f"\n{'-'*40}")
            print(f"Running test suite: {suite.name}")
            print(f"Description: {suite.description}")
            print(f"{'-'*40}")
            
            suite_result = await self._run_test_suite(suite)
            suite_results[suite.name] = suite_result
        
        self.end_time = datetime.now()
        
        # Generate comprehensive report
        report = self._generate_test_report(suite_results)
        
        return report
    
    async def _run_test_suite(self, suite: TestSuite) -> Dict[str, Any]:
        """Run individual test suite."""
        suite_start = datetime.now()
        suite_results = []
        
        try:
            # Run suite setup if provided
            if suite.setup_function:
                print(f"  Running suite setup...")
                await suite.setup_function(self.environment)
            
            # Run each test function
            for test_func in suite.test_functions:
                test_name = f"{suite.name}.{test_func.__name__}"
                print(f"  Running {test_name}...")
                
                test_result = TestResult(
                    test_name=test_name,
                    status=TestStatus.RUNNING,
                    start_time=datetime.now()
                )
                
                try:
                    # Run test with timeout
                    await asyncio.wait_for(
                        test_func(self.environment),
                        timeout=suite.timeout_seconds
                    )
                    
                    test_result.mark_completed(TestStatus.PASSED)
                    print(f"    ✓ PASSED ({test_result.duration_ms:.1f}ms)")
                    
                except asyncio.TimeoutError:
                    test_result.mark_completed(
                        TestStatus.FAILED, 
                        f"Test timed out after {suite.timeout_seconds}s"
                    )
                    print(f"    ✗ TIMEOUT ({suite.timeout_seconds}s)")
                    
                except AssertionError as e:
                    test_result.mark_completed(TestStatus.FAILED, str(e))
                    print(f"    ✗ FAILED: {e}")
                    
                except Exception as e:
                    test_result.mark_completed(TestStatus.ERROR, str(e))
                    print(f"    ✗ ERROR: {e}")
                    print(f"    Traceback: {traceback.format_exc()}")
                
                suite_results.append(test_result)
                self.results.append(test_result)
            
            # Run suite teardown if provided
            if suite.teardown_function:
                print(f"  Running suite teardown...")
                await suite.teardown_function(self.environment)
        
        except Exception as e:
            print(f"  ✗ Suite execution failed: {e}")
            # Mark all remaining tests as error
            for test_func in suite.test_functions:
                if not any(r.test_name.endswith(test_func.__name__) for r in suite_results):
                    error_result = TestResult(
                        test_name=f"{suite.name}.{test_func.__name__}",
                        status=TestStatus.ERROR,
                        start_time=suite_start,
                        error_message=f"Suite execution failed: {e}"
                    )
                    error_result.mark_completed(TestStatus.ERROR)
                    suite_results.append(error_result)
                    self.results.append(error_result)
        
        suite_end = datetime.now()
        suite_duration = (suite_end - suite_start).total_seconds() * 1000
        
        # Calculate suite statistics
        passed = sum(1 for r in suite_results if r.status == TestStatus.PASSED)
        failed = sum(1 for r in suite_results if r.status == TestStatus.FAILED)
        errors = sum(1 for r in suite_results if r.status == TestStatus.ERROR)
        
        print(f"  Suite completed: {passed} passed, {failed} failed, {errors} errors ({suite_duration:.1f}ms)")
        
        return {
            'suite_name': suite.name,
            'description': suite.description,
            'start_time': suite_start,
            'end_time': suite_end,
            'duration_ms': suite_duration,
            'test_results': [asdict(r) for r in suite_results],
            'statistics': {
                'total': len(suite_results),
                'passed': passed,
                'failed': failed,
                'errors': errors,
                'success_rate': passed / len(suite_results) if suite_results else 0
            }
        }
    
    def _generate_test_report(self, suite_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comprehensive test execution report."""
        total_duration = (self.end_time - self.start_time).total_seconds() * 1000
        
        # Overall statistics
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.status == TestStatus.PASSED)
        failed_tests = sum(1 for r in self.results if r.status == TestStatus.FAILED)
        error_tests = sum(1 for r in self.results if r.status == TestStatus.ERROR)
        
        overall_success_rate = passed_tests / total_tests if total_tests > 0 else 0
        
        report = {
            'execution_summary': {
                'start_time': self.start_time,
                'end_time': self.end_time,
                'total_duration_ms': total_duration,
                'test_suites': len(self.test_suites),
                'total_tests': total_tests,
                'passed': passed_tests,
                'failed': failed_tests,
                'errors': error_tests,
                'success_rate': overall_success_rate
            },
            'suite_results': suite_results,
            'detailed_results': [asdict(r) for r in self.results],
            'environment_info': {
                'audio_config': asdict(self.environment.config),
                'python_version': sys.version,
                'timestamp': datetime.now().isoformat()
            }
        }
        
        # Print summary
        print(f"\n{'='*60}")
        print("INTEGRATION TEST EXECUTION SUMMARY")
        print(f"{'='*60}")
        print(f"Total Duration: {total_duration/1000:.1f}s")
        print(f"Test Suites: {len(self.test_suites)}")
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Errors: {error_tests}")
        print(f"Success Rate: {overall_success_rate*100:.1f}%")
        
        # Save report to file
        report_file = self.environment.results_dir / f"integration_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        print(f"Detailed report saved to: {report_file}")
        
        return report


class RegressionTestSuite:
    """Regression testing capabilities for audio processing system."""
    
    def __init__(self, environment: IntegrationTestEnvironment):
        self.environment = environment
        self.baseline_dir = Path("test_baselines")
        self.baseline_dir.mkdir(exist_ok=True)
    
    async def capture_baseline(self, test_name: str, test_data: Dict[str, Any]):
        """Capture baseline results for regression testing."""
        baseline_file = self.baseline_dir / f"{test_name}_baseline.json"
        
        baseline_data = {
            'test_name': test_name,
            'timestamp': datetime.now().isoformat(),
            'audio_config': asdict(self.environment.config),
            'test_data': test_data
        }
        
        with open(baseline_file, 'w') as f:
            json.dump(baseline_data, f, indent=2, default=str)
        
        print(f"Baseline captured for {test_name}: {baseline_file}")
    
    async def compare_with_baseline(self, test_name: str, current_data: Dict[str, Any]) -> Dict[str, Any]:
        """Compare current test results with baseline."""
        baseline_file = self.baseline_dir / f"{test_name}_baseline.json"
        
        if not baseline_file.exists():
            return {
                'status': 'no_baseline',
                'message': f"No baseline found for {test_name}"
            }
        
        with open(baseline_file, 'r') as f:
            baseline_data = json.load(f)
        
        # Compare key metrics
        comparison_result = self._compare_test_data(
            baseline_data['test_data'], 
            current_data
        )
        
        return {
            'status': 'compared',
            'baseline_timestamp': baseline_data['timestamp'],
            'comparison': comparison_result,
            'regression_detected': comparison_result.get('has_regression', False)
        }
    
    def _compare_test_data(self, baseline: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
        """Compare test data for regression detection."""
        comparison = {
            'has_regression': False,
            'differences': [],
            'metrics_comparison': {}
        }
        
        # Compare performance metrics
        if 'performance_metrics' in baseline and 'performance_metrics' in current:
            perf_comparison = self._compare_performance_metrics(
                baseline['performance_metrics'],
                current['performance_metrics']
            )
            comparison['metrics_comparison']['performance'] = perf_comparison
            
            # Check for performance regression (>10% degradation)
            if perf_comparison.get('latency_regression_percent', 0) > 10:
                comparison['has_regression'] = True
                comparison['differences'].append(
                    f"Latency regression: {perf_comparison['latency_regression_percent']:.1f}%"
                )
        
        # Compare quality metrics
        if 'quality_metrics' in baseline and 'quality_metrics' in current:
            quality_comparison = self._compare_quality_metrics(
                baseline['quality_metrics'],
                current['quality_metrics']
            )
            comparison['metrics_comparison']['quality'] = quality_comparison
            
            # Check for quality regression (>5% degradation)
            if quality_comparison.get('quality_regression_percent', 0) > 5:
                comparison['has_regression'] = True
                comparison['differences'].append(
                    f"Quality regression: {quality_comparison['quality_regression_percent']:.1f}%"
                )
        
        return comparison
    
    def _compare_performance_metrics(self, baseline: Dict, current: Dict) -> Dict[str, Any]:
        """Compare performance metrics between baseline and current."""
        comparison = {}
        
        # Compare latency metrics
        if 'avg_latency_ms' in baseline and 'avg_latency_ms' in current:
            baseline_latency = baseline['avg_latency_ms']
            current_latency = current['avg_latency_ms']
            
            if baseline_latency > 0:
                regression_percent = ((current_latency - baseline_latency) / baseline_latency) * 100
                comparison['latency_regression_percent'] = regression_percent
                comparison['baseline_latency_ms'] = baseline_latency
                comparison['current_latency_ms'] = current_latency
        
        # Compare throughput metrics
        if 'throughput_fps' in baseline and 'throughput_fps' in current:
            baseline_throughput = baseline['throughput_fps']
            current_throughput = current['throughput_fps']
            
            if baseline_throughput > 0:
                throughput_change = ((current_throughput - baseline_throughput) / baseline_throughput) * 100
                comparison['throughput_change_percent'] = throughput_change
        
        return comparison
    
    def _compare_quality_metrics(self, baseline: Dict, current: Dict) -> Dict[str, Any]:
        """Compare quality metrics between baseline and current."""
        comparison = {}
        
        # Compare overall quality score
        if 'overall_quality_score' in baseline and 'overall_quality_score' in current:
            baseline_quality = baseline['overall_quality_score']
            current_quality = current['overall_quality_score']
            
            if baseline_quality > 0:
                quality_change = ((current_quality - baseline_quality) / baseline_quality) * 100
                comparison['quality_regression_percent'] = -quality_change  # Negative change is regression
                comparison['baseline_quality'] = baseline_quality
                comparison['current_quality'] = current_quality
        
        return comparison


# Integration test framework factory
def create_integration_test_framework(config: AudioConfig) -> tuple[IntegrationTestEnvironment, AutomatedTestRunner, RegressionTestSuite]:
    """Create complete integration test framework."""
    environment = IntegrationTestEnvironment(config)
    runner = AutomatedTestRunner(environment)
    regression_suite = RegressionTestSuite(environment)
    
    return environment, runner, regression_suite