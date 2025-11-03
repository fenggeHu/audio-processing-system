"""
Tests for the ControlService web interface.

This module contains unit tests for the web control interface,
including REST API endpoints, WebSocket functionality, and
integration with the service manager.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect

from audio_processing.models import AudioConfig, AudioMetrics
from audio_processing.services.control import ControlService, ConnectionManager, WebSocketMessage
from audio_processing.service_manager import ServiceManager


class TestConnectionManager:
    """Test WebSocket connection management."""
    
    def test_connection_manager_init(self):
        """Test ConnectionManager initialization."""
        manager = ConnectionManager()
        assert len(manager.active_connections) == 0
        assert len(manager.connection_info) == 0
    
    @pytest.mark.asyncio
    async def test_connect_websocket(self):
        """Test WebSocket connection."""
        manager = ConnectionManager()
        mock_websocket = AsyncMock()
        
        await manager.connect(mock_websocket, {"user": "test"})
        
        mock_websocket.accept.assert_called_once()
        assert mock_websocket in manager.active_connections
        assert manager.connection_info[mock_websocket] == {"user": "test"}
    
    def test_disconnect_websocket(self):
        """Test WebSocket disconnection."""
        manager = ConnectionManager()
        mock_websocket = Mock()
        
        # Add connection first
        manager.active_connections.add(mock_websocket)
        manager.connection_info[mock_websocket] = {"user": "test"}
        
        # Disconnect
        manager.disconnect(mock_websocket)
        
        assert mock_websocket not in manager.active_connections
        assert mock_websocket not in manager.connection_info
    
    @pytest.mark.asyncio
    async def test_broadcast_message(self):
        """Test broadcasting message to all connections."""
        manager = ConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        
        # Add connections
        await manager.connect(mock_ws1)
        await manager.connect(mock_ws2)
        
        # Broadcast message
        message = WebSocketMessage(type="test", data={"value": 123})
        await manager.broadcast(message)
        
        # Verify both connections received the message
        expected_json = message.model_dump_json()
        mock_ws1.send_text.assert_called_once_with(expected_json)
        mock_ws2.send_text.assert_called_once_with(expected_json)
    
    @pytest.mark.asyncio
    async def test_broadcast_handles_disconnected_clients(self):
        """Test that broadcast handles disconnected clients gracefully."""
        manager = ConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        
        # Make one connection fail
        mock_ws1.send_text.side_effect = Exception("Connection lost")
        
        await manager.connect(mock_ws1)
        await manager.connect(mock_ws2)
        
        message = WebSocketMessage(type="test", data={"value": 123})
        await manager.broadcast(message)
        
        # Failed connection should be removed
        assert mock_ws1 not in manager.active_connections
        assert mock_ws2 in manager.active_connections


class TestControlService:
    """Test ControlService functionality."""
    
    @pytest.fixture
    def audio_config(self):
        """Create test audio configuration."""
        return AudioConfig(
            sample_rate=48000,
            frame_size=480,
            channels=4,
            buffer_size=2048
        )
    
    @pytest.fixture
    def mock_service_manager(self):
        """Create mock service manager."""
        manager = Mock(spec=ServiceManager)
        manager.is_running = True
        manager.get_service_status.return_value = {
            "TestService": {
                "running": True,
                "healthy": True,
                "metrics": {}
            }
        }
        manager.get_system_metrics.return_value = {
            "TestService": AudioMetrics(
                processing_latency_ms=5.0,
                cpu_usage_percent=25.0,
                memory_usage_mb=100.0
            )
        }
        return manager
    
    @pytest.fixture
    def control_service(self, audio_config, mock_service_manager):
        """Create ControlService instance for testing."""
        return ControlService(
            config=audio_config,
            service_manager=mock_service_manager,
            host="127.0.0.1",
            port=8081
        )
    
    def test_control_service_init(self, control_service):
        """Test ControlService initialization."""
        assert control_service.service_name == "ControlService"
        assert control_service.host == "127.0.0.1"
        assert control_service.port == 8081
        assert control_service.app is not None
        assert control_service.connection_manager is not None
    
    @pytest.mark.asyncio
    async def test_control_service_lifecycle(self, control_service):
        """Test ControlService start/stop lifecycle."""
        # Test start
        await control_service.start()
        assert control_service.is_running
        assert control_service.start_time is not None
        assert control_service.metrics_task is not None
        
        # Test stop
        await control_service.stop()
        assert not control_service.is_running
    
    def test_get_web_interface_html(self, control_service):
        """Test web interface HTML generation."""
        html = control_service._get_web_interface_html()
        
        assert "<!DOCTYPE html>" in html
        assert "Audio Processing System Control" in html
        assert "WebSocket" in html
        assert "class AudioSystemControl" in html
    
    def test_get_system_metrics_dict(self, control_service):
        """Test system metrics aggregation."""
        metrics = control_service._get_system_metrics_dict()
        
        assert "cpu_usage_percent" in metrics
        assert "memory_usage_mb" in metrics
        assert "processing_latency_ms" in metrics
        assert "frame_drop_rate" in metrics
        assert "service_count" in metrics
        
        assert metrics["service_count"] == 1
        assert metrics["cpu_usage_percent"] == 25.0
        assert metrics["memory_usage_mb"] == 100.0
    
    @pytest.mark.asyncio
    async def test_handle_event(self, control_service):
        """Test event handling and WebSocket broadcasting."""
        # Start service to initialize connection manager
        await control_service.start()
        
        # Mock WebSocket connection
        mock_websocket = AsyncMock()
        await control_service.connection_manager.connect(mock_websocket)
        
        # Handle event
        event_data = {"service_name": "TestService", "status": "healthy"}
        await control_service.handle_event("service_health_changed", event_data)
        
        # Verify WebSocket message was sent
        mock_websocket.send_text.assert_called()
        
        await control_service.stop()


class TestControlServiceAPI:
    """Test ControlService REST API endpoints."""
    
    @pytest.fixture
    def audio_config(self):
        """Create test audio configuration."""
        return AudioConfig(
            sample_rate=48000,
            frame_size=480,
            channels=4,
            buffer_size=2048
        )
    
    @pytest.fixture
    def mock_service_manager(self):
        """Create mock service manager."""
        manager = Mock(spec=ServiceManager)
        manager.is_running = True
        manager.get_service_status.return_value = {
            "TestService": {
                "running": True,
                "healthy": True,
                "metrics": {}
            }
        }
        manager.get_system_metrics.return_value = {}
        manager.update_config = AsyncMock()
        manager.restart_service = AsyncMock()
        return manager
    
    @pytest.fixture
    def test_client(self, audio_config, mock_service_manager):
        """Create test client for API testing."""
        control_service = ControlService(
            config=audio_config,
            service_manager=mock_service_manager,
            host="127.0.0.1",
            port=8081
        )
        return TestClient(control_service.app)
    
    def test_get_root(self, test_client):
        """Test root endpoint returns HTML."""
        response = test_client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Audio Processing System Control" in response.text
    
    def test_get_system_status(self, test_client):
        """Test system status endpoint."""
        response = test_client.get("/api/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "running" in data
        assert "uptime_seconds" in data
        assert "services" in data
        assert "system_metrics" in data
        assert "config_version" in data
    
    def test_get_config(self, test_client):
        """Test configuration retrieval endpoint."""
        response = test_client.get("/api/config")
        assert response.status_code == 200
        
        data = response.json()
        assert "sample_rate" in data
        assert "frame_size" in data
        assert "channels" in data
        assert data["sample_rate"] == 48000
    
    def test_update_config(self, test_client, mock_service_manager):
        """Test configuration update endpoint."""
        new_config = {
            "sample_rate": 44100,
            "frame_size": 441,
            "channels": 2,
            "buffer_size": 1024,
            "enable_ssl": True,
            "enable_beamforming": True,
            "enable_aec": True,
            "enable_denoise": True,
            "enable_agc": True,
            "max_latency_ms": 50.0,
            "cpu_limit_percent": 70.0
        }
        
        response = test_client.post("/api/config", json={
            "config": new_config,
            "description": "Test update",
            "user": "test_user"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        # Verify service manager was called
        mock_service_manager.update_config.assert_called_once()
    
    def test_update_config_invalid(self, test_client):
        """Test configuration update with invalid data."""
        invalid_config = {
            "sample_rate": -1,  # Invalid sample rate
            "frame_size": 480,
            "channels": 2
        }
        
        response = test_client.post("/api/config", json={
            "config": invalid_config
        })
        
        assert response.status_code == 400
    
    def test_get_services(self, test_client):
        """Test services status endpoint."""
        response = test_client.get("/api/services")
        assert response.status_code == 200
        
        data = response.json()
        assert "TestService" in data
        assert data["TestService"]["running"] is True
    
    def test_control_service_restart(self, test_client, mock_service_manager):
        """Test service restart endpoint."""
        response = test_client.post("/api/services/control", json={
            "service_name": "TestService",
            "action": "restart"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        # Verify service manager was called
        mock_service_manager.restart_service.assert_called_once_with("TestService")
    
    def test_control_service_invalid_action(self, test_client):
        """Test service control with invalid action."""
        response = test_client.post("/api/services/control", json={
            "service_name": "TestService",
            "action": "invalid_action"
        })
        
        assert response.status_code == 422  # Validation error
    
    def test_get_metrics(self, test_client):
        """Test metrics endpoint."""
        response = test_client.get("/api/metrics")
        assert response.status_code == 200
        
        # Should return empty dict from mock
        data = response.json()
        assert isinstance(data, dict)


@pytest.mark.asyncio
async def test_websocket_message_model():
    """Test WebSocketMessage model."""
    message = WebSocketMessage(
        type="test_message",
        data={"key": "value", "number": 42}
    )
    
    assert message.type == "test_message"
    assert message.data["key"] == "value"
    assert message.data["number"] == 42
    assert message.timestamp is not None
    
    # Test JSON serialization
    json_str = message.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["type"] == "test_message"
    assert parsed["data"]["key"] == "value"


if __name__ == "__main__":
    pytest.main([__file__])