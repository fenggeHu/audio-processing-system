#!/usr/bin/env python3
"""
Audio Processing System - Main Demo Runner

This script provides multiple ways to run and test the audio processing system:
1. Web Interface Demo - Interactive web control panel
2. Integration Tests - Comprehensive system testing
3. Performance Benchmarks - System performance evaluation
4. Troubleshooting Tools - System diagnostics
"""

import sys
import asyncio
import argparse
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

def main():
    parser = argparse.ArgumentParser(
        description="Audio Processing System Demo Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_demo.py web                    # Start web interface demo
  python run_demo.py test                   # Run integration tests
  python run_demo.py benchmark              # Run performance benchmarks
  python run_demo.py troubleshoot           # Run system diagnostics
  python run_demo.py validate               # Validate system components
        """
    )
    
    parser.add_argument(
        'mode',
        choices=['web', 'test', 'benchmark', 'troubleshoot', 'validate'],
        help='Demo mode to run'
    )
    
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Host for web interface (default: 127.0.0.1)'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=8080,
        help='Port for web interface (default: 8080)'
    )
    
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    args = parser.parse_args()
    
    print("🎵 Audio Processing System Demo Runner 🎵")
    print("=" * 50)
    
    if args.mode == 'web':
        print("🚀 Starting Real Audio Processing System...")
        print(f"📱 Will be available at: http://{args.host}:{args.port}")
        print("=" * 50)
        
        # Import and run the real audio processing system
        from audio_system import main as audio_main
        try:
            asyncio.run(audio_main())
        except KeyboardInterrupt:
            print("\n✅ Audio system stopped by user")
        except Exception as e:
            print(f"❌ Audio system failed: {e}")
            sys.exit(1)
    
    elif args.mode == 'test':
        print("🧪 Running Integration Tests...")
        print("=" * 50)
        
        # Import and run integration tests
        from run_integration_tests import main as test_main
        try:
            asyncio.run(test_main())
        except Exception as e:
            print(f"❌ Integration tests failed: {e}")
            sys.exit(1)
    
    elif args.mode == 'benchmark':
        print("📊 Running Performance Benchmarks...")
        print("=" * 50)
        
        # Import and run benchmarks
        try:
            from tools.performance_benchmark import main as benchmark_main
            benchmark_main()
        except ImportError:
            print("❌ Benchmark tools not found. Please ensure all files are in place.")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Benchmarks failed: {e}")
            sys.exit(1)
    
    elif args.mode == 'troubleshoot':
        print("🔍 Running System Diagnostics...")
        print("=" * 50)
        
        # Import and run troubleshooting
        try:
            from tools.troubleshooting_toolkit import main as troubleshoot_main
            troubleshoot_main()
        except ImportError:
            print("❌ Troubleshooting tools not found. Please ensure all files are in place.")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Diagnostics failed: {e}")
            sys.exit(1)
    
    elif args.mode == 'validate':
        print("✅ Validating System Components...")
        print("=" * 50)
        
        # Import and run validation
        from validate_integration_framework import main as validate_main
        try:
            exit_code = asyncio.run(validate_main())
            sys.exit(exit_code)
        except Exception as e:
            print(f"❌ Validation failed: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()