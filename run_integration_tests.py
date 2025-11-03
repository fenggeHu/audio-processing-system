#!/usr/bin/env python3
"""
Comprehensive integration test runner for audio processing system.

This script runs all integration tests, performance validation, and
classroom scenario testing to validate the complete system functionality.

Updated to use the new Integration Test Framework.
"""

import asyncio
import sys
import time
import json
from pathlib import Path
from typing import Dict, Any
import subprocess

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from audio_processing.models import AudioConfig
from tests.integration_test_framework import create_integration_test_framework
from run_automated_integration_tests import AutomatedIntegrationTestRunner

# Legacy test result tracking for backward compatibility
class TestResults:
    def __init__(self):
        self.results = {}
        self.start_time = time.time()
        self.total_tests = 0
        self.passed_tests = 0
        self.failed_tests = 0
    
    def add_result(self, test_name: str, status: str, details: Dict[str, Any] = None):
        """Add test result."""
        self.results[test_name] = {
            'status': status,
            'details': details or {},
            'timestamp': time.time()
        }
        
        self.total_tests += 1
        if status == 'PASSED':
            self.passed_tests += 1
        else:
            self.failed_tests += 1
    
    def get_summary(self) -> Dict[str, Any]:
        """Get test summary."""
        duration = time.time() - self.start_time
        
        return {
            'total_tests': self.total_tests,
            'passed_tests': self.passed_tests,
            'failed_tests': self.failed_tests,
            'success_rate': (self.passed_tests / self.total_tests * 100) if self.total_tests > 0 else 0,
            'duration_seconds': duration,
            'results': self.results
        }


async def run_pytest_suite(test_file: str, test_name: str, results: TestResults):
    """Run a pytest test suite."""
    print(f"\n{'='*60}")
    print(f"Running {test_name}")
    print(f"{'='*60}")
    
    try:
        # Run pytest with verbose output
        cmd = [
            sys.executable, '-m', 'pytest', 
            test_file,
            '-v', '--tb=short', '--no-header'
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        # Parse results
        output = stdout.decode() + stderr.decode()
        print(output)
        
        if process.returncode == 0:
            results.add_result(test_name, 'PASSED', {'output': output})
            print(f"✓ {test_name}: PASSED")
        else:
            results.add_result(test_name, 'FAILED', {'output': output, 'error': stderr.decode()})
            print(f"✗ {test_name}: FAILED")
            
    except Exception as e:
        error_msg = f"Failed to run {test_name}: {e}"
        results.add_result(test_name, 'ERROR', {'error': error_msg})
        print(f"✗ {test_name}: ERROR - {e}")


async def run_performance_benchmark(results: TestResults):
    """Run performance benchmark tests."""
    print(f"\n{'='*60}")
    print("Running Performance Benchmark")
    print(f"{'='*60}")
    
    try:
        # Import and run performance tests
        from tests.test_performance_validation import run_performance_benchmark
        
        success = await run_performance_benchmark()
        
        if success:
            results.add_result('Performance Benchmark', 'PASSED')
            print("✓ Performance Benchmark: PASSED")
        else:
            results.add_result('Performance Benchmark', 'FAILED')
            print("✗ Performance Benchmark: FAILED")
            
    except Exception as e:
        results.add_result('Performance Benchmark', 'ERROR', {'error': str(e)})
        print(f"✗ Performance Benchmark: ERROR - {e}")


async def run_classroom_validation(results: TestResults):
    """Run classroom scenario validation."""
    print(f"\n{'='*60}")
    print("Running Classroom Scenario Validation")
    print(f"{'='*60}")
    
    try:
        from tests.test_classroom_scenarios import run_classroom_validation
        
        await run_classroom_validation()
        results.add_result('Classroom Validation', 'PASSED')
        print("✓ Classroom Validation: PASSED")
        
    except Exception as e:
        results.add_result('Classroom Validation', 'FAILED', {'error': str(e)})
        print(f"✗ Classroom Validation: FAILED - {e}")


async def run_system_health_check(results: TestResults):
    """Run basic system health checks."""
    print(f"\n{'='*60}")
    print("Running System Health Check")
    print(f"{'='*60}")
    
    try:
        # Check Python dependencies
        required_packages = [
            'numpy', 'scipy', 'pytest', 'asyncio', 'structlog', 'psutil'
        ]
        
        missing_packages = []
        for package in required_packages:
            try:
                __import__(package)
                print(f"✓ {package}: Available")
            except ImportError:
                missing_packages.append(package)
                print(f"✗ {package}: Missing")
        
        if missing_packages:
            results.add_result('System Health Check', 'FAILED', 
                             {'missing_packages': missing_packages})
            print(f"✗ System Health Check: FAILED - Missing packages: {missing_packages}")
        else:
            results.add_result('System Health Check', 'PASSED')
            print("✓ System Health Check: PASSED")
            
    except Exception as e:
        results.add_result('System Health Check', 'ERROR', {'error': str(e)})
        print(f"✗ System Health Check: ERROR - {e}")


def generate_test_report(results: TestResults):
    """Generate comprehensive test report."""
    summary = results.get_summary()
    
    print(f"\n{'='*80}")
    print("INTEGRATION TEST SUMMARY")
    print(f"{'='*80}")
    
    print(f"Total Tests: {summary['total_tests']}")
    print(f"Passed: {summary['passed_tests']}")
    print(f"Failed: {summary['failed_tests']}")
    print(f"Success Rate: {summary['success_rate']:.1f}%")
    print(f"Duration: {summary['duration_seconds']:.1f} seconds")
    
    print(f"\nDetailed Results:")
    print("-" * 40)
    
    for test_name, result in summary['results'].items():
        status_symbol = "✓" if result['status'] == 'PASSED' else "✗"
        print(f"{status_symbol} {test_name}: {result['status']}")
        
        if result['status'] != 'PASSED' and 'error' in result['details']:
            print(f"    Error: {result['details']['error']}")
    
    # Save detailed report to file
    report_file = Path('integration_test_report.json')
    with open(report_file, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    
    print(f"\nDetailed report saved to: {report_file}")
    
    # Generate recommendations
    print(f"\nRecommendations:")
    print("-" * 20)
    
    if summary['success_rate'] == 100:
        print("🎉 All tests passed! System is ready for deployment.")
    elif summary['success_rate'] >= 90:
        print("⚠️  Most tests passed. Review failed tests before deployment.")
    elif summary['success_rate'] >= 70:
        print("⚠️  Some critical issues found. Address failed tests before deployment.")
    else:
        print("🚨 Multiple test failures. System requires significant fixes.")
    
    return summary['success_rate'] >= 90  # Return True if tests mostly passed


async def main():
    """Main test runner - now uses the new Integration Test Framework."""
    print("Audio Processing System - Integration Test Suite")
    print("=" * 60)
    print("Using new Integration Test Framework")
    
    # Create audio configuration
    config = AudioConfig(
        sample_rate=48000,
        frame_size=480,
        channels=2,
        bit_depth=16
    )
    
    # Create test options
    options = {
        'regression': True,
        'capture_baselines': False,
        'verbose': True,
        'timeout_multiplier': 1.0
    }
    
    try:
        # Use the new automated integration test runner
        runner = AutomatedIntegrationTestRunner(config, options)
        report = await runner.run_complete_test_suite()
        
        # Convert to legacy format for backward compatibility
        results = TestResults()
        
        # Extract results from new framework report
        execution_summary = report.get('execution_summary', {})
        results.total_tests = execution_summary.get('total_tests', 0)
        results.passed_tests = execution_summary.get('passed', 0)
        results.failed_tests = execution_summary.get('failed', 0) + execution_summary.get('errors', 0)
        
        # Add phase results
        phase_summaries = report.get('phase_summaries', {})
        for phase_name, summary in phase_summaries.items():
            if phase_name == 'regression':
                status = 'PASSED' if summary.get('regressions_detected', 0) == 0 else 'FAILED'
                results.add_result(f"Regression Testing", status, summary)
            else:
                status = 'PASSED' if summary.get('success_rate', 0) > 0.9 else 'FAILED'
                results.add_result(phase_name.replace('_', ' ').title(), status, summary)
        
        # Generate legacy report
        success = generate_test_report(results)
        
        # Also save new framework report
        report_file = Path('integration_test_framework_report.json')
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nNew framework report saved to: {report_file}")
        
        # Exit based on overall status
        overall_status = report.get('overall_status', 'ERROR')
        if overall_status == 'PASSED':
            sys.exit(0)
        elif overall_status in ['REGRESSION', 'POOR']:
            sys.exit(1)
        else:
            sys.exit(2)
            
    except Exception as e:
        print(f"\nError running integration tests: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest run interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        sys.exit(1)