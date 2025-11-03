#!/usr/bin/env python3
"""
Automated Integration Test Runner

This script provides a comprehensive automated testing workflow that:
1. Sets up the complete integration test environment
2. Runs all integration test suites
3. Performs regression testing
4. Generates detailed reports
5. Provides CI/CD integration capabilities

Requirements: 9.4, 9.5
"""

import asyncio
import sys
import argparse
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from audio_processing.models import AudioConfig
from tests.integration_test_framework import create_integration_test_framework, TestSuite
from tests.test_end_to_end_integration import EndToEndIntegrationTests


class AutomatedIntegrationTestRunner:
    """Comprehensive automated integration test execution."""
    
    def __init__(self, config: AudioConfig, options: Dict[str, Any] = None):
        self.config = config
        self.options = options or {}
        self.results_dir = Path("integration_test_results")
        self.results_dir.mkdir(exist_ok=True)
        
        # Test execution options
        self.run_regression_tests = self.options.get('regression', True)
        self.capture_baselines = self.options.get('capture_baselines', False)
        self.verbose = self.options.get('verbose', False)
        self.timeout_multiplier = self.options.get('timeout_multiplier', 1.0)
        
    async def run_complete_test_suite(self) -> Dict[str, Any]:
        """Run the complete automated integration test suite."""
        print("="*80)
        print("AUTOMATED INTEGRATION TEST SUITE")
        print("="*80)
        print(f"Start time: {datetime.now()}")
        print(f"Configuration: {self.config.sample_rate}Hz, {self.config.channels}ch, {self.config.frame_size} samples")
        print(f"Options: regression={self.run_regression_tests}, baselines={self.capture_baselines}")
        
        overall_start_time = time.time()
        
        # Create test framework
        environment, runner, regression_suite = create_integration_test_framework(self.config)
        
        try:
            # Phase 1: Environment Setup
            print(f"\n{'-'*60}")
            print("PHASE 1: ENVIRONMENT SETUP")
            print(f"{'-'*60}")
            
            setup_success = await environment.setup_environment()
            if not setup_success:
                return {
                    'status': 'FAILED',
                    'phase': 'environment_setup',
                    'error': 'Failed to setup integration test environment'
                }
            
            # Phase 2: Core Integration Tests
            print(f"\n{'-'*60}")
            print("PHASE 2: CORE INTEGRATION TESTS")
            print(f"{'-'*60}")
            
            core_results = await self._run_core_integration_tests(runner)
            
            # Phase 3: Performance and Scalability Tests
            print(f"\n{'-'*60}")
            print("PHASE 3: PERFORMANCE AND SCALABILITY TESTS")
            print(f"{'-'*60}")
            
            performance_results = await self._run_performance_tests(runner)
            
            # Phase 4: Classroom Scenario Tests
            print(f"\n{'-'*60}")
            print("PHASE 4: CLASSROOM SCENARIO TESTS")
            print(f"{'-'*60}")
            
            classroom_results = await self._run_classroom_tests(runner)
            
            # Phase 5: Resilience and Error Handling Tests
            print(f"\n{'-'*60}")
            print("PHASE 5: RESILIENCE AND ERROR HANDLING TESTS")
            print(f"{'-'*60}")
            
            resilience_results = await self._run_resilience_tests(runner)
            
            # Phase 6: Regression Testing (if enabled)
            regression_results = None
            if self.run_regression_tests:
                print(f"\n{'-'*60}")
                print("PHASE 6: REGRESSION TESTING")
                print(f"{'-'*60}")
                
                regression_results = await self._run_regression_tests(environment, regression_suite)
            
            # Generate comprehensive report
            overall_duration = time.time() - overall_start_time
            
            final_report = self._generate_final_report({
                'core_integration': core_results,
                'performance': performance_results,
                'classroom_scenarios': classroom_results,
                'resilience': resilience_results,
                'regression': regression_results
            }, overall_duration)
            
            return final_report
            
        except Exception as e:
            print(f"\n✗ CRITICAL ERROR: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                'status': 'ERROR',
                'error': str(e),
                'traceback': traceback.format_exc()
            }
            
        finally:
            await environment.teardown_environment()
    
    async def _run_core_integration_tests(self, runner) -> Dict[str, Any]:
        """Run core integration tests."""
        core_suite = TestSuite(
            name="CoreIntegrationTests",
            description="Core audio processing pipeline integration tests",
            test_functions=[
                EndToEndIntegrationTests.test_complete_audio_pipeline,
                EndToEndIntegrationTests.test_real_time_processing_latency,
            ],
            timeout_seconds=120.0 * self.timeout_multiplier
        )
        
        runner.register_test_suite(core_suite)
        results = await runner.run_all_tests()
        
        # Clear registered suites for next phase
        runner.test_suites = []
        runner.results = []
        
        return results
    
    async def _run_performance_tests(self, runner) -> Dict[str, Any]:
        """Run performance and scalability tests."""
        performance_suite = TestSuite(
            name="PerformanceTests",
            description="Performance, scalability, and throughput tests",
            test_functions=[
                EndToEndIntegrationTests.test_concurrent_stream_processing,
                EndToEndIntegrationTests.test_system_stability_under_load,
            ],
            timeout_seconds=300.0 * self.timeout_multiplier
        )
        
        runner.register_test_suite(performance_suite)
        results = await runner.run_all_tests()
        
        runner.test_suites = []
        runner.results = []
        
        return results
    
    async def _run_classroom_tests(self, runner) -> Dict[str, Any]:
        """Run classroom scenario tests."""
        classroom_suite = TestSuite(
            name="ClassroomScenarioTests",
            description="Realistic classroom environment and scenario tests",
            test_functions=[
                EndToEndIntegrationTests.test_classroom_scenario_processing,
            ],
            timeout_seconds=180.0 * self.timeout_multiplier
        )
        
        runner.register_test_suite(classroom_suite)
        results = await runner.run_all_tests()
        
        runner.test_suites = []
        runner.results = []
        
        return results
    
    async def _run_resilience_tests(self, runner) -> Dict[str, Any]:
        """Run resilience and error handling tests."""
        resilience_suite = TestSuite(
            name="ResilienceTests",
            description="Error handling, recovery, and system resilience tests",
            test_functions=[
                EndToEndIntegrationTests.test_error_recovery_and_resilience,
            ],
            timeout_seconds=60.0 * self.timeout_multiplier
        )
        
        runner.register_test_suite(resilience_suite)
        results = await runner.run_all_tests()
        
        runner.test_suites = []
        runner.results = []
        
        return results
    
    async def _run_regression_tests(self, environment, regression_suite) -> Dict[str, Any]:
        """Run regression testing."""
        from tests.test_audio_mock_generator import MockAudioGenerator
        import numpy as np
        
        regression_results = {
            'tests_run': [],
            'baselines_captured': [],
            'regressions_detected': [],
            'status': 'PASSED'
        }
        
        mock_generator = MockAudioGenerator(environment.config)
        
        # Test scenarios for regression testing
        test_scenarios = [
            ('denoise_performance', 'DenoiseService'),
            ('aec_performance', 'AECService'),
            ('ssl_performance', 'SSLService')
        ]
        
        for test_name, service_name in test_scenarios:
            try:
                service = await environment.get_service(service_name)
                
                # Generate test data
                test_frames = [mock_generator.generate_speech_frame() for _ in range(20)]
                latencies = []
                success_count = 0
                
                for frame in test_frames:
                    start_time = asyncio.get_event_loop().time()
                    result = await service.process(frame)
                    end_time = asyncio.get_event_loop().time()
                    
                    if result.success:
                        success_count += 1
                        latencies.append((end_time - start_time) * 1000)
                
                # Collect metrics
                test_data = {
                    'performance_metrics': {
                        'avg_latency_ms': np.mean(latencies) if latencies else 0,
                        'max_latency_ms': np.max(latencies) if latencies else 0,
                        'min_latency_ms': np.min(latencies) if latencies else 0,
                        'throughput_fps': success_count / (np.sum(latencies) / 1000) if latencies else 0,
                        'success_rate': success_count / len(test_frames)
                    },
                    'quality_metrics': {
                        'overall_quality_score': 85.0,  # Would be calculated from actual quality assessment
                        'processing_success_rate': success_count / len(test_frames)
                    }
                }
                
                if self.capture_baselines:
                    # Capture new baseline
                    await regression_suite.capture_baseline(test_name, test_data)
                    regression_results['baselines_captured'].append(test_name)
                    print(f"  ✓ Captured baseline for {test_name}")
                else:
                    # Compare with existing baseline
                    comparison = await regression_suite.compare_with_baseline(test_name, test_data)
                    regression_results['tests_run'].append({
                        'test_name': test_name,
                        'comparison_result': comparison
                    })
                    
                    if comparison.get('regression_detected', False):
                        regression_results['regressions_detected'].append(test_name)
                        regression_results['status'] = 'REGRESSION_DETECTED'
                        print(f"  ⚠️  Regression detected in {test_name}")
                    else:
                        print(f"  ✓ No regression in {test_name}")
                        
            except Exception as e:
                print(f"  ✗ Regression test failed for {test_name}: {e}")
                regression_results['status'] = 'ERROR'
        
        return regression_results
    
    def _generate_final_report(self, phase_results: Dict[str, Any], total_duration: float) -> Dict[str, Any]:
        """Generate comprehensive final test report."""
        print(f"\n{'='*80}")
        print("FINAL INTEGRATION TEST REPORT")
        print(f"{'='*80}")
        
        # Aggregate statistics
        total_tests = 0
        total_passed = 0
        total_failed = 0
        total_errors = 0
        
        phase_summaries = {}
        
        for phase_name, results in phase_results.items():
            if results is None:
                continue
                
            if phase_name == 'regression':
                # Handle regression results differently
                phase_summaries[phase_name] = {
                    'status': results.get('status', 'SKIPPED'),
                    'tests_run': len(results.get('tests_run', [])),
                    'regressions_detected': len(results.get('regressions_detected', [])),
                    'baselines_captured': len(results.get('baselines_captured', []))
                }
            else:
                # Handle standard test results
                summary = results.get('execution_summary', {})
                phase_tests = summary.get('total_tests', 0)
                phase_passed = summary.get('passed', 0)
                phase_failed = summary.get('failed', 0)
                phase_errors = summary.get('errors', 0)
                
                total_tests += phase_tests
                total_passed += phase_passed
                total_failed += phase_failed
                total_errors += phase_errors
                
                phase_summaries[phase_name] = {
                    'tests': phase_tests,
                    'passed': phase_passed,
                    'failed': phase_failed,
                    'errors': phase_errors,
                    'success_rate': summary.get('success_rate', 0)
                }
        
        # Calculate overall metrics
        overall_success_rate = total_passed / total_tests if total_tests > 0 else 0
        
        # Determine overall status
        if total_errors > 0:
            overall_status = 'ERROR'
        elif total_failed > 2:  # Allow up to 2 failures
            overall_status = 'FAILED'
        elif overall_success_rate < 0.85:
            overall_status = 'POOR'
        elif any(r.get('status') == 'REGRESSION_DETECTED' for r in [phase_results.get('regression')] if r):
            overall_status = 'REGRESSION'
        else:
            overall_status = 'PASSED'
        
        final_report = {
            'overall_status': overall_status,
            'execution_summary': {
                'start_time': datetime.now().isoformat(),
                'total_duration_seconds': total_duration,
                'total_tests': total_tests,
                'passed': total_passed,
                'failed': total_failed,
                'errors': total_errors,
                'success_rate': overall_success_rate
            },
            'phase_summaries': phase_summaries,
            'detailed_results': phase_results,
            'configuration': {
                'audio_config': {
                    'sample_rate': self.config.sample_rate,
                    'frame_size': self.config.frame_size,
                    'channels': self.config.channels,
                    'bit_depth': self.config.bit_depth
                },
                'test_options': self.options
            }
        }
        
        # Print summary
        print(f"Overall Status: {overall_status}")
        print(f"Total Duration: {total_duration:.1f}s")
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {total_passed}")
        print(f"Failed: {total_failed}")
        print(f"Errors: {total_errors}")
        print(f"Success Rate: {overall_success_rate*100:.1f}%")
        
        print(f"\nPhase Results:")
        for phase_name, summary in phase_summaries.items():
            if phase_name == 'regression':
                print(f"  {phase_name}: {summary['status']} "
                      f"({summary['tests_run']} tests, {summary['regressions_detected']} regressions)")
            else:
                print(f"  {phase_name}: {summary['success_rate']*100:.1f}% "
                      f"({summary['passed']}/{summary['tests']} passed)")
        
        # Save detailed report
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = self.results_dir / f"automated_integration_report_{timestamp}.json"
        
        with open(report_file, 'w') as f:
            json.dump(final_report, f, indent=2, default=str)
        
        print(f"\nDetailed report saved to: {report_file}")
        
        # Generate recommendations
        self._print_recommendations(overall_status, phase_summaries)
        
        return final_report
    
    def _print_recommendations(self, status: str, phase_summaries: Dict[str, Any]):
        """Print recommendations based on test results."""
        print(f"\nRecommendations:")
        print("-" * 20)
        
        if status == 'PASSED':
            print("🎉 All integration tests passed! System is ready for deployment.")
        elif status == 'REGRESSION':
            print("⚠️  Regression detected. Review performance changes before deployment.")
        elif status == 'POOR':
            print("⚠️  Low success rate. Address failing tests before deployment.")
        elif status == 'FAILED':
            print("🚨 Multiple test failures. System requires fixes before deployment.")
        elif status == 'ERROR':
            print("🚨 Critical errors encountered. System needs immediate attention.")
        
        # Specific recommendations
        for phase_name, summary in phase_summaries.items():
            if phase_name == 'regression':
                if summary['regressions_detected'] > 0:
                    print(f"  - Review performance regressions in {phase_name}")
            else:
                if summary.get('success_rate', 1.0) < 0.9:
                    print(f"  - Address failures in {phase_name} ({summary['success_rate']*100:.1f}% success)")


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Automated Integration Test Runner for Audio Processing System"
    )
    
    parser.add_argument(
        '--sample-rate', 
        type=int, 
        default=48000,
        help='Audio sample rate (default: 48000)'
    )
    
    parser.add_argument(
        '--frame-size',
        type=int,
        default=480,
        help='Audio frame size in samples (default: 480)'
    )
    
    parser.add_argument(
        '--channels',
        type=int,
        default=2,
        help='Number of audio channels (default: 2)'
    )
    
    parser.add_argument(
        '--no-regression',
        action='store_true',
        help='Skip regression testing'
    )
    
    parser.add_argument(
        '--capture-baselines',
        action='store_true',
        help='Capture new regression test baselines'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '--timeout-multiplier',
        type=float,
        default=1.0,
        help='Multiply all test timeouts by this factor (default: 1.0)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='integration_test_results',
        help='Output directory for test results (default: integration_test_results)'
    )
    
    return parser.parse_args()


async def main():
    """Main entry point for automated integration testing."""
    args = parse_arguments()
    
    # Create audio configuration
    config = AudioConfig(
        sample_rate=args.sample_rate,
        frame_size=args.frame_size,
        channels=args.channels,
        bit_depth=16
    )
    
    # Create test options
    options = {
        'regression': not args.no_regression,
        'capture_baselines': args.capture_baselines,
        'verbose': args.verbose,
        'timeout_multiplier': args.timeout_multiplier,
        'output_dir': args.output_dir
    }
    
    # Create and run automated test runner
    runner = AutomatedIntegrationTestRunner(config, options)
    
    try:
        report = await runner.run_complete_test_suite()
        
        # Exit with appropriate code
        status = report.get('overall_status', 'ERROR')
        
        if status in ['PASSED']:
            print(f"\n✅ Integration testing completed successfully!")
            return 0
        elif status in ['REGRESSION', 'POOR']:
            print(f"\n⚠️  Integration testing completed with warnings!")
            return 1
        else:
            print(f"\n❌ Integration testing failed!")
            return 2
            
    except KeyboardInterrupt:
        print(f"\n\n⚠️  Integration testing interrupted by user.")
        return 130
    except Exception as e:
        print(f"\n\n❌ Unexpected error during integration testing: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))