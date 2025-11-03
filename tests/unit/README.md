# Audio Processing System Unit Tests

This directory contains comprehensive unit tests for the audio processing system, focusing on core functionality and performance validation.

## Test Structure

### Core Model Tests
- `test_models.py` - Tests for AudioFrame, AudioConfig, ProcessingResult, and AudioMetrics data models

### Service Tests
- `test_agc_service.py` - Tests for Automatic Gain Control service including source identification, howling protection, and gain control
- `test_beamformer_service.py` - Tests for beamforming services (DAS and MVDR algorithms)
- `test_mixer_service.py` - Tests for classroom mixer service with dual-path processing
- `test_ssl_service.py` - Tests for Sound Source Localization service (existing)
- `test_aec_service.py` - Tests for Acoustic Echo Cancellation service (existing)
- Other existing service tests...

### Test Utilities
- `test_audio_mock_generator.py` - Mock audio data generator for creating realistic test signals
- `test_performance_benchmarks.py` - Performance benchmarks and stress tests

## Mock Audio Generator

The `MockAudioGenerator` class provides realistic test audio data including:

### Signal Types
- **Silence** - Pure silence for baseline testing
- **White Noise** - Random noise for general testing
- **Pink Noise** - 1/f spectrum noise for more realistic testing
- **Sine Wave** - Pure tones for frequency-specific testing
- **Speech-like** - Synthetic speech with formants and modulation
- **Teacher Voice** - Projected, clear speech characteristics
- **Student Voice** - Quieter, more hesitant speech patterns
- **Classroom Ambient** - Background noise including HVAC and paper rustling
- **Howling** - Feedback signals for testing anti-howling systems

### Features
- Configurable sample rates, frame sizes, and channel counts
- Realistic spatial simulation for multichannel testing
- SSL metadata generation for direction-dependent testing
- Classroom scenario generation with multiple speakers
- Sequence generation for temporal testing

## Performance Benchmarks

The performance benchmark suite tests:

### Individual Service Performance
- Processing latency (target: <40ms P95)
- Real-time factor (target: >1.0x)
- Throughput (frames per second)
- Memory stability over time

### Full Pipeline Performance
- End-to-end latency through multiple services
- Concurrent processing capabilities
- Sustained load testing (30+ seconds)

### Stress Tests
- High frame rate processing
- Memory leak detection
- Concurrent stream processing
- Error recovery testing

## Running Tests

### Run All Tests
```bash
python -m pytest tests/ -v
```

### Run Specific Test Categories
```bash
# Core models
python -m pytest tests/test_models.py -v

# Mock generator
python -m pytest tests/test_audio_mock_generator.py -v

# Service tests
python -m pytest tests/test_agc_service.py -v
python -m pytest tests/test_beamformer_service.py -v
python -m pytest tests/test_mixer_service.py -v

# Performance benchmarks
python -m pytest tests/test_performance_benchmarks.py -v
```

### Run Performance Benchmarks
```bash
# Run benchmarks and see detailed results
python tests/test_performance_benchmarks.py
```

## Test Coverage

The unit test suite covers:

### Core Functionality
- ✅ Data model validation and operations
- ✅ Audio frame processing and conversion
- ✅ Configuration management and validation
- ✅ Processing result handling

### Service Testing
- ✅ AGC service with source identification and howling protection
- ✅ Beamformer service with DAS and MVDR algorithms
- ✅ Mixer service with dual-path processing
- ✅ SSL service (existing comprehensive tests)
- ✅ AEC service (existing comprehensive tests)
- ✅ Other services (existing tests)

### Performance Validation
- ✅ Real-time processing requirements (<40ms latency)
- ✅ Throughput requirements (>1.0x real-time factor)
- ✅ Memory stability over extended periods
- ✅ Concurrent processing capabilities

### Integration Scenarios
- ✅ Classroom audio processing scenarios
- ✅ Multi-service pipeline processing
- ✅ Error handling and recovery
- ✅ Configuration changes during operation

## Key Testing Principles

1. **Minimal Test Solutions** - Tests focus on core functionality without over-testing edge cases
2. **Real Functionality Validation** - No mocks for core logic, tests validate actual behavior
3. **Performance Focus** - All tests include performance validation against real-time requirements
4. **Classroom Scenarios** - Tests include realistic classroom audio processing scenarios
5. **Error Handling** - Tests validate proper error handling and recovery mechanisms

## Test Data Generation

The mock audio generator creates realistic test data that:
- Simulates actual classroom acoustics
- Includes spatial characteristics for multichannel testing
- Provides consistent, reproducible test signals
- Supports various audio processing scenarios
- Generates appropriate metadata for service testing

This comprehensive test suite ensures the audio processing system meets its real-time performance requirements while maintaining high audio quality in classroom environments.
</content>
</invoke>