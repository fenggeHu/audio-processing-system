#!/usr/bin/env python3
"""
Simple validation script for the ControlService implementation.

This script tests the basic functionality of the web control interface
without requiring the full system setup.
"""

import sys
import asyncio
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from audio_processing.models import AudioConfig
from audio_processing.services.control import ConnectionManager, WebSocketMessage, ControlService
from unittest.mock import Mock, AsyncMock


async def test_connection_manager():
    """Test ConnectionManager basic functionality."""
    print("Testing ConnectionManager...")
    
    manager = ConnectionManager()
    assert len(manager.active_connections) == 0
    assert len(manager.connection_info) == 0
    
    # Test WebSocket message creation
    message = WebSocketMessage(type="test", data={"key": "value"})
    assert message.type == "test"
    assert message.data["key"] == "value"
    
    print("✓ ConnectionManager tests passed")


async def test_control_service_basic():
    """Test ControlService basic functionality."""
    print("Testing ControlService...")
    
    # Create mock service manager
    mock_service_manager = Mock()
    mock_service_manager.is_running = True
    mock_service_manager.get_service_status.return_value = {
        "TestService": {"running": True, "healthy": True, "metrics": {}}
    }
    mock_service_manager.get_system_metrics.return_value = {}
    
    # Create audio config
    config = AudioConfig(
        sample_rate=48000,
        frame_size=480,
        channels=4,
        buffer_size=2048
    )
    
    # Create control service
    control_service = ControlService(
        config=config,
        service_manager=mock_service_manager,
        host="127.0.0.1",
        port=8081
    )
    
    # Test basic properties
    assert control_service.service_name == "ControlService"
    assert control_service.host == "127.0.0.1"
    assert control_service.port == 8081
    assert control_service.app is not None
    
    # Test HTML generation
    html = control_service._get_web_interface_html()
    assert "<!DOCTYPE html>" in html
    assert "Audio Processing System Control" in html
    
    # Test metrics aggregation
    metrics = control_service._get_system_metrics_dict()
    assert "cpu_usage_percent" in metrics
    assert "memory_usage_mb" in metrics
    assert "processing_latency_ms" in metrics
    
    print("✓ ControlService basic tests passed")


async def test_fastapi_app():
    """Test FastAPI application setup."""
    print("Testing FastAPI application...")
    
    from fastapi.testclient import TestClient
    
    # Create mock service manager
    mock_service_manager = Mock()
    mock_service_manager.is_running = True
    mock_service_manager.get_service_status.return_value = {}
    mock_service_manager.get_system_metrics.return_value = {}
    
    config = AudioConfig()
    
    control_service = ControlService(
        config=config,
        service_manager=mock_service_manager
    )
    
    # Create test client
    client = TestClient(control_service.app)
    
    # Test root endpoint
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    
    # Test API status endpoint
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "running" in data
    assert "services" in data
    
    # Test config endpoint
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "sample_rate" in data
    
    print("✓ FastAPI application tests passed")


async def main():
    """Run all validation tests."""
    print("🎵 Validating ControlService Implementation 🎵")
    print("=" * 50)
    
    try:
        await test_connection_manager()
        await test_control_service_basic()
        await test_fastapi_app()
        
        print("=" * 50)
        print("✅ All validation tests passed!")
        print("✅ ControlService implementation is working correctly")
        print("=" * 50)
        
        return True
        
    except Exception as e:
        print("=" * 50)
        print(f"❌ Validation failed: {e}")
        print("=" * 50)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)