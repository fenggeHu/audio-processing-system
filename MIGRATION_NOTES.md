# Test Directory Consolidation - Migration Notes

## Overview

The audio processing system project has undergone a test directory consolidation to improve project organization and maintainability. All scattered `test_*` directories at the project root have been consolidated into a well-organized structure under the main `tests/` directory.

## What Changed

### Directory Migration
The following directories have been moved:

| Old Location | New Location | Purpose |
|--------------|--------------|---------|
| `test_config/` | `tests/config/` | Test configuration files |
| `test_data/` | `tests/data/` | Test data and audio fixtures |
| `test_baselines/` | `tests/baselines/` | Performance baseline data |
| `test_results/` | `tests/results/` | Test execution results |
| `test_output/` | `tests/output/` | Test output artifacts |
| `test_demo/` | `tests/demo/` | Demo packages and mock data |
| `test_power/` | `tests/power/` | Power management test configs |
| `test_terminal/` | `tests/terminal/` | Terminal device test configs |
| `tests/` | `tests/unit/` | Existing unit tests moved to subdirectory |

### Updated Files
The following project files have been automatically updated to use the new paths:
- `pyproject.toml` - Test discovery configuration
- `run_integration_tests.py` - Integration test runner
- `run_automated_integration_tests.py` - Automated test suite
- Various configuration files in `config/` and `deploy/config/`

## Action Items for Team Members

### Immediate Actions Required
1. **Pull the latest changes** from the main branch
2. **Update local scripts** that reference old `test_*` directories
3. **Update IDE settings** for test discovery if configured manually
4. **Update bookmarks** or shortcuts pointing to old test directories

### IDE Configuration Updates

#### VS Code
If you have custom test discovery settings in `.vscode/settings.json`:
```json
{
    "python.testing.pytestArgs": [
        "tests"
    ],
    "python.testing.unittestArgs": [
        "-v",
        "-s",
        "./tests",
        "-p",
        "test_*.py"
    ]
}
```

#### PyCharm
- Update test configurations to point to `tests/` directory
- Refresh project structure if test directories don't appear correctly

### Script Updates
If you have local development scripts that reference old paths, update them:

```bash
# Old (will not work)
python -m pytest test_config/
cat test_data/sample.wav

# New (correct)
python -m pytest tests/config/
cat tests/data/sample.wav
```

### Git Workflow
- The old `test_*` directories have been removed from the repository
- If you have uncommitted changes in old directories, you'll need to move them manually
- Use `git status` to check for any orphaned files

## Benefits of the New Structure

### Improved Organization
- All test-related files are now in one place
- Clear separation between different types of tests and test data
- Follows Python project conventions

### Better Navigation
- Easier to find test files and related resources
- Reduced clutter in project root directory
- Logical grouping of test assets

### Enhanced Maintainability
- Simplified CI/CD configuration
- Easier to manage test dependencies
- Clear documentation of test structure

## Troubleshooting

### Common Issues

#### "No tests found" or "Test discovery failed"
- Ensure your test runner is looking in the `tests/` directory
- Check that pytest is configured correctly in `pyproject.toml`
- Verify your IDE test discovery settings

#### "Configuration file not found"
- Update any hardcoded paths in your code to use `tests/config/`
- Check that configuration loading logic uses the new paths

#### "Test data missing"
- Update test file references to use `tests/data/`
- Verify that test data files were moved correctly

#### Local scripts failing
- Update any custom scripts to use the new directory structure
- Replace `test_*` paths with `tests/*` equivalents

### Getting Help
- Check `tests/README.md` for detailed information about the new structure
- Review the design document at `.kiro/specs/test-directory-consolidation/design.md`
- Ask questions in team channels if you encounter issues

## Rollback Information

If critical issues arise, the migration can be rolled back using the backup created during the consolidation process. Contact the project maintainer if rollback is necessary.

## Timeline

- **Migration completed**: [Date of migration]
- **Old directory cleanup**: Completed automatically
- **Documentation updates**: Completed
- **Team notification**: [Date of team notification]

---

*This migration improves project organization while maintaining all existing functionality. No test behavior or capabilities have changed - only the file locations.*