"""
Tests for Error Handling System

Basic tests to verify the error classification and handling functionality.
"""

import pytest
import tempfile
import time
from pathlib import Path
from datetime import datetime

from src.audio_core.error_handling import (
    ErrorClassifier, ErrorLogger, ErrorStatistics, ErrorNotifier,
    HardwareErrorHandler, ProcessingErrorHandler, SystemErrorHandler,
    ErrorHandlingSystem, ErrorContext, ErrorType, ErrorSeverity, RecoveryAction,
    initialize_error_handling, handle_error, with_error_handling
)
from src.audio_core.models import AudioDevice, DeviceType, SystemState


class TestErrorClassifier:
    """Test error classification functionality"""
    
    def setup_method(self):
        self.classifier = ErrorClassifier()
        self.context = ErrorContext(
            component_name="test_component",
            operation="test_operation"
        )
    
    def test_hardware_error_classification(self):
        """Test hardware error classification"""
        # Test OSError classification
        error = OSError("Audio device not found")
        error_type, severity = self.classifier.classify_error(error, self.context)
        
        assert error_type == ErrorType.HARDWARE_ERROR
        assert severity in [ErrorSeverity.MEDIUM, ErrorSeverity.HIGH]
    
    def test_processing_error_classification(self):
        """Test processing error classification"""
        # Test ValueError classification
        error = ValueError("Invalid sample rate")
        error_type, severity = self.classifier.classify_error(error, self.context)
        
        assert error_type == ErrorType.PROCESSING_ERROR
        assert severity in [ErrorSeverity.LOW, ErrorSeverity.MEDIUM]
    
    def test_system_error_classification(self):
        """Test system error classification"""
        # Test MemoryError classification
        error = MemoryError("Insufficient memory")
        error_type, severity = self.classifier.classify_error(error, self.context)
        
        assert error_type == ErrorType.SYSTEM_ERROR
        assert severity == ErrorSeverity.CRITICAL
    
    def test_recovery_action_suggestions(self):
        """Test recovery action suggestions"""
        actions = self.classifier.suggest_recovery_actions(
            ErrorType.HARDWARE_ERROR, ErrorSeverity.HIGH, self.context
        )
        
        assert RecoveryAction.RESTART_COMPONENT in actions or RecoveryAction.SWITCH_DEVICE in actions


class TestErrorLogger:
    """Test error logging functionality"""
    
    def setup_method(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.logger = ErrorLogger(self.temp_dir)
        self.context = ErrorContext(
            component_name="test_component",
            operation="test_operation"
        )
    
    def test_error_logging(self):
        """Test basic error logging"""
        from src.audio_core.error_handling import ErrorRecord
        
        error_record = ErrorRecord(
            error_id="TEST_001",
            error_type=ErrorType.HARDWARE_ERROR,
            severity=ErrorSeverity.MEDIUM,
            exception=OSError("Test error"),
            context=self.context,
            error_message="Test error message"
        )
        
        error_id = self.logger.log_error(error_record)
        assert error_id == "TEST_001"
        
        # Verify error can be retrieved
        retrieved_record = self.logger.get_error_record("TEST_001")
        assert retrieved_record is not None
        assert retrieved_record.error_message == "Test error message"
    
    def test_recent_errors_retrieval(self):
        """Test recent errors retrieval"""
        from src.audio_core.error_handling import ErrorRecord
        
        # Log multiple errors
        for i in range(3):
            error_record = ErrorRecord(
                error_id=f"TEST_{i:03d}",
                error_type=ErrorType.PROCESSING_ERROR,
                severity=ErrorSeverity.LOW,
                exception=ValueError(f"Test error {i}"),
                context=self.context,
                error_message=f"Test error message {i}"
            )
            self.logger.log_error(error_record)
        
        recent_errors = self.logger.get_recent_errors(hours=1)
        assert len(recent_errors) == 3


class TestErrorHandlers:
    """Test error handler functionality"""
    
    def setup_method(self):
        self.hardware_handler = HardwareErrorHandler()
        self.processing_handler = ProcessingErrorHandler()
        self.system_handler = SystemErrorHandler()
        
        self.context = ErrorContext(
            component_name="test_component",
            operation="test_operation"
        )
    
    def test_hardware_handler_can_handle(self):
        """Test hardware handler error type detection"""
        from src.audio_core.error_handling import ErrorRecord
        
        error_record = ErrorRecord(
            error_id="TEST_HW_001",
            error_type=ErrorType.HARDWARE_ERROR,
            severity=ErrorSeverity.MEDIUM,
            exception=OSError("Device error"),
            context=self.context,
            error_message="Hardware error"
        )
        
        assert self.hardware_handler.can_handle(error_record)
        assert not self.processing_handler.can_handle(error_record)
        assert not self.system_handler.can_handle(error_record)
    
    def test_processing_handler_can_handle(self):
        """Test processing handler error type detection"""
        from src.audio_core.error_handling import ErrorRecord
        
        error_record = ErrorRecord(
            error_id="TEST_PROC_001",
            error_type=ErrorType.PROCESSING_ERROR,
            severity=ErrorSeverity.MEDIUM,
            exception=ValueError("Processing error"),
            context=self.context,
            error_message="Processing error"
        )
        
        assert self.processing_handler.can_handle(error_record)
        assert not self.hardware_handler.can_handle(error_record)
        assert not self.system_handler.can_handle(error_record)


class TestErrorHandlingSystem:
    """Test complete error handling system"""
    
    def setup_method(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.error_system = ErrorHandlingSystem(self.temp_dir)
        
        # Setup test recovery callbacks
        self.recovery_called = {}
        
        def test_recovery_callback(context):
            action_name = context.get('action', 'unknown')
            self.recovery_called[action_name] = True
            return True
        
        # Register callbacks for testing
        self.error_system.register_recovery_callback(
            ErrorType.HARDWARE_ERROR, RecoveryAction.RETRY, 
            lambda ctx: test_recovery_callback({**ctx, 'action': 'retry'})
        )
    
    def test_complete_error_handling_flow(self):
        """Test complete error handling from exception to recovery"""
        context = ErrorContext(
            component_name="audio_device_manager",
            operation="initialize_device"
        )
        
        # Simulate hardware error
        error = OSError("Audio device not available")
        error_id = self.error_system.handle_error(error, context)
        
        assert error_id != ""
        assert error_id.startswith("ERR_")
        
        # Verify error was logged
        error_record = self.error_system.logger.get_error_record(error_id)
        assert error_record is not None
        assert error_record.error_type == ErrorType.HARDWARE_ERROR
    
    def test_system_health_report(self):
        """Test system health reporting"""
        # Generate some test errors
        for i in range(3):
            context = ErrorContext(
                component_name=f"test_component_{i}",
                operation="test_operation"
            )
            error = ValueError(f"Test error {i}")
            self.error_system.handle_error(error, context)
        
        health_report = self.error_system.get_system_health_report()
        
        assert 'total_errors_handled' in health_report
        assert health_report['total_errors_handled'] >= 3
        assert 'error_frequency' in health_report
        assert 'system_availability' in health_report


class TestConvenienceFunctions:
    """Test convenience functions and decorators"""
    
    def setup_method(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        initialize_error_handling(self.temp_dir)
    
    def test_global_error_handling(self):
        """Test global error handling function"""
        error = ValueError("Test global error")
        error_id = handle_error(error, "test_component", "test_operation")
        
        assert error_id != ""
        assert error_id.startswith("ERR_")
    
    def test_error_handling_decorator(self):
        """Test error handling decorator"""
        @with_error_handling("test_component", "decorated_function")
        def failing_function():
            raise ValueError("Decorated function error")
        
        # Function should still raise the exception, but error should be logged
        with pytest.raises(ValueError):
            failing_function()
        
        # Verify error was handled
        from src.audio_core.error_handling import get_error_system
        error_system = get_error_system()
        assert error_system.error_count > 0


def test_error_context_manager():
    """Test error handling context manager"""
    from src.audio_core.error_handling import ErrorHandlingContext
    
    temp_dir = Path(tempfile.mkdtemp())
    initialize_error_handling(temp_dir)
    
    with pytest.raises(ValueError):
        with ErrorHandlingContext("test_component", "context_test") as ctx:
            raise ValueError("Context manager test error")
    
    # Verify error was handled
    from src.audio_core.error_handling import get_error_system
    error_system = get_error_system()
    assert error_system.error_count > 0


if __name__ == "__main__":
    pytest.main([__file__])