"""
Control service for web-based system management and monitoring.

This module provides the ControlService that implements REST API endpoints
and WebSocket connections for real-time system control and monitoring.
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
from pathlib import Path
import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import uvicorn

from ..base import BaseAudioProcessor
from ..models import AudioConfig
from ..interfaces import IEventHandler
from ..service_manager import ServiceManager

logger = structlog.get_logger(__name__)


class SystemStatus(BaseModel):
    """System status response model."""
    running: bool
    uptime_seconds: float
    services: Dict[str, Dict[str, Any]]
    system_metrics: Dict[str, Any]
    config_version: int


class ConfigUpdateRequest(BaseModel):
    """Configuration update request model."""
    config: Dict[str, Any]
    description: Optional[str] = None
    user: Optional[str] = None


class ServiceControlRequest(BaseModel):
    """Service control request model."""
    action: str = Field(..., pattern="^(start|stop|restart)$")
    service_name: str


class WebSocketMessage(BaseModel):
    """WebSocket message model."""
    type: str
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.connection_info: Dict[WebSocket, Dict[str, Any]] = {}
    
    async def connect(self, websocket: WebSocket, client_info: Dict[str, Any] = None):
        """Accept new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        self.connection_info[websocket] = client_info or {}
        
        logger.info("WebSocket client connected", 
                   client_count=len(self.active_connections))
    
    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection."""
        self.active_connections.discard(websocket)
        self.connection_info.pop(websocket, None)
        
        logger.info("WebSocket client disconnected", 
                   client_count=len(self.active_connections))
    
    async def send_personal_message(self, message: WebSocketMessage, websocket: WebSocket):
        """Send message to specific client."""
        try:
            await websocket.send_text(message.model_dump_json())
        except Exception as e:
            logger.error("Failed to send personal message", error=str(e))
            self.disconnect(websocket)
    
    async def broadcast(self, message: WebSocketMessage):
        """Broadcast message to all connected clients."""
        if not self.active_connections:
            return
        
        message_json = message.model_dump_json()
        disconnected = set()
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.error("Failed to broadcast message", error=str(e))
                disconnected.add(connection)
        
        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)


class ControlService(BaseAudioProcessor, IEventHandler):
    """
    Web-based control service for system management and monitoring.
    
    Provides:
    - REST API for system control and configuration
    - WebSocket connections for real-time monitoring
    - Web interface for parameter adjustment
    - Service management endpoints
    """
    
    def __init__(self, config: AudioConfig, service_manager: ServiceManager,
                 host: str = "0.0.0.0", port: int = 8080):
        """
        Initialize ControlService.
        
        Args:
            config: Audio system configuration
            service_manager: Service manager instance
            host: Web server host address
            port: Web server port
        """
        super().__init__("ControlService", config)
        self.service_manager = service_manager
        self.host = host
        self.port = port
        
        # Web application setup
        self.app = FastAPI(
            title="Audio Processing System Control",
            description="Web interface for audio processing system control and monitoring",
            version="1.0.0"
        )
        
        # WebSocket connection manager
        self.connection_manager = ConnectionManager()
        
        # Server state
        self.server = None
        self.start_time = None
        self.metrics_task = None
        
        # Setup routes
        self._setup_routes()
        self._setup_static_files()
    
    @property
    def service_name(self) -> str:
        """Get service name."""
        return "ControlService"
    
    async def _initialize(self) -> None:
        """Initialize the control service."""
        self.start_time = datetime.now()
        
        # Subscribe to system events
        self.service_manager.subscribe_to_events('service_health_changed', self)
        self.service_manager.subscribe_to_events('config_updated', self)
        self.service_manager.subscribe_to_events('service_restarted', self)
        
        # Start metrics broadcasting task
        self.metrics_task = asyncio.create_task(self._metrics_broadcast_loop())
        
        logger.info("Control service initialized", host=self.host, port=self.port)
    
    async def _cleanup(self) -> None:
        """Cleanup control service resources."""
        if self.metrics_task:
            self.metrics_task.cancel()
            try:
                await self.metrics_task
            except asyncio.CancelledError:
                pass
        
        if self.server:
            self.server.should_exit = True
        
        logger.info("Control service cleaned up")
    
    async def _process_frame(self, frame) -> Any:
        """Control service doesn't process audio frames."""
        return frame
    
    def _setup_routes(self) -> None:
        """Setup FastAPI routes."""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def get_web_interface():
            """Serve main web interface."""
            return self._get_web_interface_html()
        
        @self.app.get("/api/status", response_model=SystemStatus)
        async def get_system_status():
            """Get current system status."""
            uptime = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
            
            return SystemStatus(
                running=self.service_manager.is_running,
                uptime_seconds=uptime,
                services=self.service_manager.get_service_status(),
                system_metrics=self._get_system_metrics_dict(),
                config_version=self._get_config_version()
            )
        
        @self.app.get("/api/config")
        async def get_config():
            """Get current system configuration."""
            return self._audio_config.model_dump()
        
        @self.app.post("/api/config")
        async def update_config(request: ConfigUpdateRequest):
            """Update system configuration."""
            try:
                # Validate configuration
                new_config = AudioConfig(**request.config)
                
                # Apply through service manager
                await self.service_manager.update_config(new_config)
                
                # Broadcast config change
                await self.connection_manager.broadcast(
                    WebSocketMessage(
                        type="config_updated",
                        data={
                            "config": new_config.model_dump(),
                            "description": request.description,
                            "user": request.user
                        }
                    )
                )
                
                return {"success": True, "message": "Configuration updated successfully"}
                
            except Exception as e:
                logger.error("Failed to update configuration", error=str(e))
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.get("/api/services")
        async def get_services():
            """Get list of all services and their status."""
            return self.service_manager.get_service_status()
        
        @self.app.post("/api/services/control")
        async def control_service(request: ServiceControlRequest):
            """Control service (start/stop/restart)."""
            try:
                if request.action == "restart":
                    await self.service_manager.restart_service(request.service_name)
                elif request.action == "start":
                    service = await self.service_manager.get_service_by_name(request.service_name)
                    await service.start()
                elif request.action == "stop":
                    service = await self.service_manager.get_service_by_name(request.service_name)
                    await service.stop()
                
                return {"success": True, "message": f"Service {request.action} completed"}
                
            except Exception as e:
                logger.error("Service control failed", 
                           service=request.service_name, 
                           action=request.action, 
                           error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/metrics")
        async def get_metrics():
            """Get current system metrics."""
            return self.service_manager.get_system_metrics()
        
        @self.app.get("/api/metrics/{service_name}")
        async def get_service_metrics(service_name: str):
            """Get metrics for specific service."""
            try:
                service = await self.service_manager.get_service_by_name(service_name)
                return service.get_metrics().model_dump()
            except Exception:
                raise HTTPException(status_code=404, detail=f"Service not found: {service_name}")
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time updates."""
            await self.connection_manager.connect(websocket)
            
            try:
                # Send initial status
                status = await get_system_status()
                await self.connection_manager.send_personal_message(
                    WebSocketMessage(type="initial_status", data=status.model_dump()),
                    websocket
                )
                
                # Handle incoming messages
                while True:
                    data = await websocket.receive_text()
                    message = json.loads(data)
                    
                    # Handle client requests
                    await self._handle_websocket_message(message, websocket)
                    
            except WebSocketDisconnect:
                self.connection_manager.disconnect(websocket)
            except Exception as e:
                logger.error("WebSocket error", error=str(e))
                self.connection_manager.disconnect(websocket)
    
    def _setup_static_files(self) -> None:
        """Setup static file serving for web interface."""
        # Create static directory if it doesn't exist
        static_dir = Path(__file__).parent.parent.parent.parent / "static"
        static_dir.mkdir(exist_ok=True)
        
        # Mount static files
        self.app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    
    def _get_web_interface_html(self) -> str:
        """Generate main web interface HTML."""
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Audio Processing System Control</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            text-align: center;
        }
        .status-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px 20px;
            background: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
        }
        .status-indicator {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #28a745;
        }
        .status-dot.error {
            background: #dc3545;
        }
        .tabs {
            display: flex;
            border-bottom: 1px solid #dee2e6;
        }
        .tab {
            padding: 15px 25px;
            cursor: pointer;
            border-bottom: 3px solid transparent;
            transition: all 0.3s;
        }
        .tab.active {
            border-bottom-color: #667eea;
            background: #f8f9fa;
        }
        .tab-content {
            padding: 20px;
            display: none;
        }
        .tab-content.active {
            display: block;
        }
        .services-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        .service-card {
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 15px;
            background: white;
        }
        .service-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .service-name {
            font-weight: bold;
            font-size: 16px;
        }
        .service-status {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        }
        .service-status.running {
            background: #d4edda;
            color: #155724;
        }
        .service-status.stopped {
            background: #f8d7da;
            color: #721c24;
        }
        .config-form {
            display: grid;
            gap: 15px;
        }
        .form-group {
            display: flex;
            flex-direction: column;
            gap: 5px;
        }
        .form-group label {
            font-weight: bold;
            color: #495057;
        }
        .form-group input, .form-group select {
            padding: 8px 12px;
            border: 1px solid #ced4da;
            border-radius: 4px;
            font-size: 14px;
        }
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            font-weight: bold;
            transition: all 0.3s;
        }
        .btn-primary {
            background: #667eea;
            color: white;
        }
        .btn-primary:hover {
            background: #5a6fd8;
        }
        .btn-danger {
            background: #dc3545;
            color: white;
        }
        .btn-danger:hover {
            background: #c82333;
        }
        .btn-success {
            background: #28a745;
            color: white;
        }
        .btn-success:hover {
            background: #218838;
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }
        .metric-card {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }
        .metric-value {
            font-size: 24px;
            font-weight: bold;
            color: #667eea;
        }
        .metric-label {
            font-size: 12px;
            color: #6c757d;
            margin-top: 5px;
        }
        .log-container {
            background: #2d3748;
            color: #e2e8f0;
            padding: 15px;
            border-radius: 8px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            height: 300px;
            overflow-y: auto;
        }
        .log-entry {
            margin-bottom: 5px;
            padding: 2px 0;
        }
        .log-timestamp {
            color: #a0aec0;
        }
        .log-level-info {
            color: #63b3ed;
        }
        .log-level-error {
            color: #f56565;
        }
        .log-level-warning {
            color: #ed8936;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Audio Processing System Control</h1>
            <p>Real-time monitoring and configuration interface</p>
        </div>
        
        <div class="status-bar">
            <div class="status-indicator">
                <div class="status-dot" id="systemStatus"></div>
                <span id="systemStatusText">System Status</span>
            </div>
            <div>
                <span>Uptime: <span id="uptime">--</span></span>
                <span style="margin-left: 20px;">Version: <span id="configVersion">--</span></span>
            </div>
        </div>
        
        <div class="tabs">
            <div class="tab active" onclick="showTab('overview')">Overview</div>
            <div class="tab" onclick="showTab('services')">Services</div>
            <div class="tab" onclick="showTab('config')">Configuration</div>
            <div class="tab" onclick="showTab('metrics')">Metrics</div>
            <div class="tab" onclick="showTab('logs')">Logs</div>
        </div>
        
        <div id="overview" class="tab-content active">
            <h3>System Overview</h3>
            <div class="metrics-grid" id="overviewMetrics">
                <!-- Metrics will be populated by JavaScript -->
            </div>
        </div>
        
        <div id="services" class="tab-content">
            <h3>Service Management</h3>
            <div class="services-grid" id="servicesGrid">
                <!-- Services will be populated by JavaScript -->
            </div>
        </div>
        
        <div id="config" class="tab-content">
            <h3>System Configuration</h3>
            <form class="config-form" id="configForm">
                <!-- Configuration form will be populated by JavaScript -->
            </form>
        </div>
        
        <div id="metrics" class="tab-content">
            <h3>Performance Metrics</h3>
            <div id="metricsContent">
                <!-- Detailed metrics will be populated by JavaScript -->
            </div>
        </div>
        
        <div id="logs" class="tab-content">
            <h3>System Logs</h3>
            <div class="log-container" id="logContainer">
                <!-- Logs will be populated by JavaScript -->
            </div>
        </div>
    </div>

    <script>
        class AudioSystemControl {
            constructor() {
                this.ws = null;
                this.reconnectAttempts = 0;
                this.maxReconnectAttempts = 5;
                this.reconnectDelay = 1000;
                
                this.initWebSocket();
                this.loadInitialData();
            }
            
            initWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws`;
                
                this.ws = new WebSocket(wsUrl);
                
                this.ws.onopen = () => {
                    console.log('WebSocket connected');
                    this.reconnectAttempts = 0;
                    this.updateConnectionStatus(true);
                };
                
                this.ws.onmessage = (event) => {
                    const message = JSON.parse(event.data);
                    this.handleWebSocketMessage(message);
                };
                
                this.ws.onclose = () => {
                    console.log('WebSocket disconnected');
                    this.updateConnectionStatus(false);
                    this.attemptReconnect();
                };
                
                this.ws.onerror = (error) => {
                    console.error('WebSocket error:', error);
                };
            }
            
            attemptReconnect() {
                if (this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.reconnectAttempts++;
                    setTimeout(() => {
                        console.log(`Reconnection attempt ${this.reconnectAttempts}`);
                        this.initWebSocket();
                    }, this.reconnectDelay * this.reconnectAttempts);
                }
            }
            
            handleWebSocketMessage(message) {
                switch (message.type) {
                    case 'initial_status':
                        this.updateSystemStatus(message.data);
                        break;
                    case 'metrics_update':
                        this.updateMetrics(message.data);
                        break;
                    case 'service_status_changed':
                        this.updateServiceStatus(message.data);
                        break;
                    case 'config_updated':
                        this.updateConfiguration(message.data);
                        break;
                    case 'log_entry':
                        this.addLogEntry(message.data);
                        break;
                }
            }
            
            async loadInitialData() {
                try {
                    const [status, config, services] = await Promise.all([
                        fetch('/api/status').then(r => r.json()),
                        fetch('/api/config').then(r => r.json()),
                        fetch('/api/services').then(r => r.json())
                    ]);
                    
                    this.updateSystemStatus(status);
                    this.populateConfigForm(config);
                    this.updateServicesGrid(services);
                } catch (error) {
                    console.error('Failed to load initial data:', error);
                }
            }
            
            updateSystemStatus(status) {
                const statusDot = document.getElementById('systemStatus');
                const statusText = document.getElementById('systemStatusText');
                const uptime = document.getElementById('uptime');
                const configVersion = document.getElementById('configVersion');
                
                statusDot.className = status.running ? 'status-dot' : 'status-dot error';
                statusText.textContent = status.running ? 'System Running' : 'System Stopped';
                uptime.textContent = this.formatUptime(status.uptime_seconds);
                configVersion.textContent = status.config_version;
                
                this.updateOverviewMetrics(status.system_metrics);
            }
            
            updateOverviewMetrics(metrics) {
                const container = document.getElementById('overviewMetrics');
                container.innerHTML = '';
                
                const metricCards = [
                    { label: 'CPU Usage', value: `${metrics.cpu_usage_percent?.toFixed(1) || 0}%` },
                    { label: 'Memory Usage', value: `${metrics.memory_usage_mb?.toFixed(0) || 0} MB` },
                    { label: 'Latency', value: `${metrics.processing_latency_ms?.toFixed(1) || 0} ms` },
                    { label: 'Frame Drop Rate', value: `${metrics.frame_drop_rate?.toFixed(2) || 0}%` }
                ];
                
                metricCards.forEach(metric => {
                    const card = document.createElement('div');
                    card.className = 'metric-card';
                    card.innerHTML = `
                        <div class="metric-value">${metric.value}</div>
                        <div class="metric-label">${metric.label}</div>
                    `;
                    container.appendChild(card);
                });
            }
            
            updateServicesGrid(services) {
                const grid = document.getElementById('servicesGrid');
                grid.innerHTML = '';
                
                Object.entries(services).forEach(([name, service]) => {
                    const card = document.createElement('div');
                    card.className = 'service-card';
                    card.innerHTML = `
                        <div class="service-header">
                            <div class="service-name">${name}</div>
                            <div class="service-status ${service.running ? 'running' : 'stopped'}">
                                ${service.running ? 'Running' : 'Stopped'}
                            </div>
                        </div>
                        <div class="service-controls">
                            <button class="btn btn-success" onclick="controlService('${name}', 'start')" 
                                    ${service.running ? 'disabled' : ''}>Start</button>
                            <button class="btn btn-danger" onclick="controlService('${name}', 'stop')" 
                                    ${!service.running ? 'disabled' : ''}>Stop</button>
                            <button class="btn btn-primary" onclick="controlService('${name}', 'restart')">Restart</button>
                        </div>
                    `;
                    grid.appendChild(card);
                });
            }
            
            populateConfigForm(config) {
                const form = document.getElementById('configForm');
                form.innerHTML = '';
                
                const configFields = [
                    { key: 'sample_rate', label: 'Sample Rate (Hz)', type: 'number' },
                    { key: 'frame_size', label: 'Frame Size', type: 'number' },
                    { key: 'channels', label: 'Channels', type: 'number' },
                    { key: 'buffer_size', label: 'Buffer Size', type: 'number' },
                    { key: 'enable_ssl', label: 'Enable SSL', type: 'checkbox' },
                    { key: 'enable_beamforming', label: 'Enable Beamforming', type: 'checkbox' },
                    { key: 'enable_aec', label: 'Enable AEC', type: 'checkbox' },
                    { key: 'enable_denoise', label: 'Enable Denoise', type: 'checkbox' },
                    { key: 'enable_agc', label: 'Enable AGC', type: 'checkbox' },
                    { key: 'max_latency_ms', label: 'Max Latency (ms)', type: 'number', step: '0.1' },
                    { key: 'cpu_limit_percent', label: 'CPU Limit (%)', type: 'number', step: '0.1' }
                ];
                
                configFields.forEach(field => {
                    const group = document.createElement('div');
                    group.className = 'form-group';
                    
                    const label = document.createElement('label');
                    label.textContent = field.label;
                    
                    const input = document.createElement('input');
                    input.type = field.type;
                    input.name = field.key;
                    input.id = field.key;
                    
                    if (field.step) input.step = field.step;
                    
                    if (field.type === 'checkbox') {
                        input.checked = config[field.key];
                    } else {
                        input.value = config[field.key];
                    }
                    
                    group.appendChild(label);
                    group.appendChild(input);
                    form.appendChild(group);
                });
                
                const submitButton = document.createElement('button');
                submitButton.type = 'button';
                submitButton.className = 'btn btn-primary';
                submitButton.textContent = 'Update Configuration';
                submitButton.onclick = () => this.updateConfig();
                
                form.appendChild(submitButton);
            }
            
            async updateConfig() {
                const form = document.getElementById('configForm');
                const formData = new FormData(form);
                const config = {};
                
                for (const [key, value] of formData.entries()) {
                    const input = form.querySelector(`[name="${key}"]`);
                    if (input.type === 'checkbox') {
                        config[key] = input.checked;
                    } else if (input.type === 'number') {
                        config[key] = parseFloat(value);
                    } else {
                        config[key] = value;
                    }
                }
                
                try {
                    const response = await fetch('/api/config', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            config: config,
                            description: 'Updated via web interface',
                            user: 'web_user'
                        })
                    });
                    
                    if (response.ok) {
                        alert('Configuration updated successfully');
                    } else {
                        const error = await response.json();
                        alert(`Failed to update configuration: ${error.detail}`);
                    }
                } catch (error) {
                    alert(`Error updating configuration: ${error.message}`);
                }
            }
            
            updateConnectionStatus(connected) {
                // Update UI to show connection status
            }
            
            formatUptime(seconds) {
                const hours = Math.floor(seconds / 3600);
                const minutes = Math.floor((seconds % 3600) / 60);
                const secs = Math.floor(seconds % 60);
                return `${hours}h ${minutes}m ${secs}s`;
            }
            
            addLogEntry(logData) {
                const container = document.getElementById('logContainer');
                const entry = document.createElement('div');
                entry.className = 'log-entry';
                entry.innerHTML = `
                    <span class="log-timestamp">${new Date(logData.timestamp).toLocaleTimeString()}</span>
                    <span class="log-level-${logData.level}">[${logData.level.toUpperCase()}]</span>
                    <span>${logData.message}</span>
                `;
                container.appendChild(entry);
                container.scrollTop = container.scrollHeight;
            }
        }
        
        function showTab(tabName) {
            // Hide all tab contents
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });
            
            // Remove active class from all tabs
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // Show selected tab content
            document.getElementById(tabName).classList.add('active');
            
            // Add active class to clicked tab
            event.target.classList.add('active');
        }
        
        async function controlService(serviceName, action) {
            try {
                const response = await fetch('/api/services/control', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        service_name: serviceName,
                        action: action
                    })
                });
                
                if (response.ok) {
                    const result = await response.json();
                    alert(result.message);
                    // Refresh services grid
                    const services = await fetch('/api/services').then(r => r.json());
                    app.updateServicesGrid(services);
                } else {
                    const error = await response.json();
                    alert(`Failed to ${action} service: ${error.detail}`);
                }
            } catch (error) {
                alert(`Error controlling service: ${error.message}`);
            }
        }
        
        // Initialize the application
        const app = new AudioSystemControl();
    </script>
</body>
</html>
        """
    
    async def _handle_websocket_message(self, message: Dict[str, Any], websocket: WebSocket) -> None:
        """Handle incoming WebSocket messages from clients."""
        message_type = message.get('type')
        
        if message_type == 'get_metrics':
            # Send current metrics
            metrics = self.service_manager.get_system_metrics()
            await self.connection_manager.send_personal_message(
                WebSocketMessage(type="metrics_update", data=metrics),
                websocket
            )
        
        elif message_type == 'subscribe_logs':
            # Add client to log subscribers (implementation depends on logging system)
            pass
    
    async def _metrics_broadcast_loop(self) -> None:
        """Background task to broadcast metrics updates."""
        while self.is_running:
            try:
                # Get current metrics
                metrics = self._get_system_metrics_dict()
                
                # Broadcast to all connected clients
                await self.connection_manager.broadcast(
                    WebSocketMessage(type="metrics_update", data=metrics)
                )
                
                await asyncio.sleep(2.0)  # Update every 2 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Metrics broadcast failed", error=str(e))
                await asyncio.sleep(1.0)
    
    def _get_system_metrics_dict(self) -> Dict[str, Any]:
        """Get system metrics as dictionary."""
        system_metrics = self.service_manager.get_system_metrics()
        
        # Aggregate metrics across all services
        aggregated = {
            'cpu_usage_percent': 0.0,
            'memory_usage_mb': 0.0,
            'processing_latency_ms': 0.0,
            'frame_drop_rate': 0.0,
            'service_count': len(system_metrics)
        }
        
        if system_metrics:
            for service_metrics in system_metrics.values():
                if hasattr(service_metrics, 'model_dump'):
                    metrics_dict = service_metrics.model_dump()
                else:
                    metrics_dict = service_metrics
                
                aggregated['cpu_usage_percent'] += metrics_dict.get('cpu_usage_percent', 0)
                aggregated['memory_usage_mb'] += metrics_dict.get('memory_usage_mb', 0)
                aggregated['processing_latency_ms'] = max(
                    aggregated['processing_latency_ms'],
                    metrics_dict.get('processing_latency_ms', 0)
                )
                
                # Calculate frame drop rate
                frames_processed = metrics_dict.get('frames_processed', 0)
                frames_dropped = metrics_dict.get('frames_dropped', 0)
                if frames_processed + frames_dropped > 0:
                    drop_rate = (frames_dropped / (frames_processed + frames_dropped)) * 100
                    aggregated['frame_drop_rate'] = max(aggregated['frame_drop_rate'], drop_rate)
        
        return aggregated
    
    def _get_config_version(self) -> int:
        """Get current configuration version."""
        # This would typically come from ConfigManager
        return 1
    
    async def handle_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Handle system events and broadcast to WebSocket clients."""
        # Broadcast system events to connected clients
        await self.connection_manager.broadcast(
            WebSocketMessage(
                type=f"system_event_{event_type}",
                data=event_data
            )
        )
    
    def get_supported_events(self) -> List[str]:
        """Get supported event types."""
        return [
            'service_health_changed',
            'config_updated',
            'service_restarted'
        ]
    
    async def start_server(self) -> None:
        """Start the web server."""
        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
        
        self.server = uvicorn.Server(config)
        
        logger.info("Starting web server", host=self.host, port=self.port)
        await self.server.serve()
    
    def get_server_url(self) -> str:
        """Get the server URL."""
        return f"http://{self.host}:{self.port}"