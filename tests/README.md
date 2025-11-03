# Tests Directory Structure

This directory contains all test-related files and directories for the audio processing system, consolidated into a well-organized structure. All test directories have been migrated from the project root into this centralized location.

## Directory Structure

### Core Test Directories
- **unit/** - Unit tests for individual components and services
  - Contains comprehensive test suite for all audio processing modules
  - Includes test configuration files and utilities
- **integration/** - Integration tests for component interactions
  - End-to-end testing scenarios
  - Multi-service interaction tests

### Supporting Test Infrastructure
- **config/** - Test configuration files and settings
  - `classroom_standard.json` - Standard classroom audio configuration
  - Environment-specific test configurations
- **data/** - Test data files, audio samples, and fixtures
  - Audio test files for processing validation
  - Mock data for testing scenarios
- **baselines/** - Performance baseline data and reference files
  - Performance benchmarks and reference outputs
  - Quality assessment baselines

### Test Results and Artifacts
- **results/** - Test execution results and reports
  - Test run reports and logs
  - Performance test results
- **output/** - Test output artifacts and generated files
  - Generated test files and temporary outputs
  - Processing result validation files

### Specialized Test Areas
- **demo/** - Demo packages and mock data for testing deployments
  - Mock offline packages for deployment testing
  - Portable installer test artifacts
- **power/** - Power management test configurations
  - Power optimization test settings
  - Battery usage test configurations
- **terminal/** - Terminal device configuration tests
  - Device-specific configuration tests
  - Terminal deployment validation

## Running Tests

### Basic Test Execution
```bash
# Run all unit tests
python -m pytest tests/unit/

# Run integration tests
python -m pytest tests/integration/

# Run all tests
python -m pytest tests/

# Run with coverage reporting
python -m pytest tests/ --cov=src/audio_processing
```

### Specialized Test Scripts
```bash
# Run integration tests with custom configuration
python run_integration_tests.py

# Run automated integration test suite
python run_automated_integration_tests.py

# Validate specific service functionality
python validate_control_service.py
python validate_integration_framework.py
```

## Test Organization Guidelines

### Adding New Tests
- **Unit tests**: Place in `tests/unit/test_<module_name>.py`
- **Integration tests**: Place in `tests/integration/test_<feature_name>.py`
- **Test data**: Store in `tests/data/` with descriptive names
- **Test configurations**: Add to `tests/config/` following existing patterns

### Test Data Management
- Use `tests/data/` for all test audio files and fixtures
- Keep test data files small and focused
- Document test data purpose in comments or README files

### Configuration Testing
- Store test-specific configurations in `tests/config/`
- Use environment-specific config files for different test scenarios
- Validate configurations before running tests

## Migration Notes

### Directory Consolidation (Completed)
This test structure was created by consolidating the following root-level directories:
- `test_config/` → `tests/config/`
- `test_data/` → `tests/data/`
- `test_baselines/` → `tests/baselines/`
- `test_results/` → `tests/results/`
- `test_output/` → `tests/output/`
- `test_demo/` → `tests/demo/`
- `test_power/` → `tests/power/`
- `test_terminal/` → `tests/terminal/`

### Updated References
All path references in the following files have been updated:
- `pyproject.toml` - Test discovery configuration
- `run_integration_tests.py` - Test execution scripts
- `run_automated_integration_tests.py` - Automated test runner
- Configuration files in `config/` and `deploy/config/`

### For Team Members
- **Old paths no longer exist**: All `test_*` directories at project root have been moved
- **Update your scripts**: If you have local scripts referencing old paths, update them to use `tests/` subdirectories
- **IDE configuration**: Update your IDE test discovery settings to use the new `tests/` structure
- **Bookmarks**: Update any bookmarks or shortcuts pointing to old test directories

### Backward Compatibility
- All existing functionality is preserved
- Test discovery and execution work the same way
- No changes needed to test writing patterns
- Configuration loading automatically uses new paths

## Troubleshooting

### Common Issues After Migration
1. **Tests not discovered**: Ensure your test runner is configured to look in `tests/` directory
2. **Configuration not found**: Check that config loading uses `tests/config/` path
3. **Test data missing**: Verify test data references point to `tests/data/`
4. **Path errors in scripts**: Update any hardcoded paths in custom scripts

### Getting Help
- Check the main project README.md for general testing information
- Review individual test files for specific testing patterns
- Consult the design document at `.kiro/specs/test-directory-consolidation/design.md` for migration details