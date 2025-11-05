"""
Full Process Visualization Dashboard

Implements FullProcessVisualizationDashboard for complete "audio input → processing components → audio output" 
full-chain visualization with real-time monitoring and control.
"""

import asyncio
import json
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np
import logging
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from ..audio_core.models import AudioFrame, ProcessingMetrics, AudioDevice, SystemState
from ..audio_core.interfaces import IAudioProcessor, ComponentInfo
from ..processing.visual_pipeline import FullChainVisualAudioPipeline, PipelineNode, PipelineConnection


class DashboardState(Enum):
    """Dashboard operational states"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class InputMonitorData:
    """Data structure for input monitoring"""
    device_id: str
    device_name: str
    is_active: bool
    level_db: float
    peak_db: float
    waveform_data: np.ndarray
    spectrum_data: np.ndarray
    quality_score: float
    sample_rate: int
    channels: int
    timestamp: datetime


@dataclass
class ProcessingChainStatus:
    """Status of processing chain visualization"""
    chain_id: str
    chain_name: str
    nodes: List[Dict[str, Any]]
    connections: List[Dict[str, Any]]
    data_flow_active: bool
    total_latency_ms: float
    throughput_fps: float


@dataclass
class OutputQualityData:
    """Output quality monitoring data"""
    output_id: str
    output_name: str
    quality_score: float
    latency_ms: float
    stability_index: float
    level_db: float
    thd_percent: float
    snr_db: float
    timestamp: datetime


class FullProcessVisualizationDashboard:
    """
    Main control console for complete "audio input → processing components → audio output" 
    full-chain visualization and control
    """
    
    def __init__(self, dashboard_id: str = "main_dashboard"):
        self.dashboard_id = dashboard_id
        self.logger = logging.getLogger(__name__)
        
        # Dashboard state
        self.state = DashboardState.STOPPED
        self.start_time: Optional[datetime] = None
        
        # Core components
        self.multi_input_monitor = MultiInputMonitorPanel()
        self.processing_chain_viz = ProcessingChainVisualization()
        self.component_control_matrix = ComponentControlMatrix()
        self.data_flow_monitor = RealTimeDataFlowMonitor()
        self.output_quality_dashboard = OutputQualityDashboard()
        self.system_status_overview = SystemStatusOverview()
        self.interactive_control_panel = InteractiveControlPanel()
        
        # Data storage
        self.input_data_history: Dict[str, deque] = {}
        self.processing_metrics_history: Dict[str, deque] = {}
        self.output_quality_history: Dict[str, deque] = {}
        self.system_events: deque = deque(maxlen=1000)
        
        # Update callbacks
        self.update_callbacks: List[Callable] = []
        
        # Threading
        self.update_thread: Optional[threading.Thread] = None
        self.update_interval = 0.033  # 30 FPS
        self.running = False
        
    def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize the dashboard with configuration"""
        try:
            self.state = DashboardState.STARTING
            
            # Initialize all components
            self.multi_input_monitor.initialize(config.get("input_monitor", {}))
            self.processing_chain_viz.initialize(config.get("processing_viz", {}))
            self.component_control_matrix.initialize(config.get("component_control", {}))
            self.data_flow_monitor.initialize(config.get("data_flow", {}))
            self.output_quality_dashboard.initialize(config.get("output_quality", {}))
            self.system_status_overview.initialize(config.get("system_status", {}))
            self.interactive_control_panel.initialize(config.get("interactive_control", {}))
            
            # Setup data history
            max_history = config.get("max_history_points", 10000)
            for component in ["input", "processing", "output"]:
                if component not in self.input_data_history:
                    self.input_data_history[component] = deque(maxlen=max_history)
                if component not in self.processing_metrics_history:
                    self.processing_metrics_history[component] = deque(maxlen=max_history)
                if component not in self.output_quality_history:
                    self.output_quality_history[component] = deque(maxlen=max_history)
            
            self.state = DashboardState.STOPPED
            self.logger.info(f"Dashboard {self.dashboard_id} initialized successfully")
            return True
            
        except Exception as e:
            self.state = DashboardState.ERROR
            self.logger.error(f"Failed to initialize dashboard: {e}")
            return False
    
    def start_dashboard(self) -> bool:
        """Start the full process visualization dashboard"""
        if self.state == DashboardState.RUNNING:
            return True
        
        try:
            self.state = DashboardState.STARTING
            
            # Start all monitoring components
            self.multi_input_monitor.start_monitoring()
            self.processing_chain_viz.start_visualization()
            self.component_control_matrix.start_control()
            self.data_flow_monitor.start_monitoring()
            self.output_quality_dashboard.start_monitoring()
            self.system_status_overview.start_monitoring()
            
            # Start update thread
            self.running = True
            self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
            self.update_thread.start()
            
            self.state = DashboardState.RUNNING
            self.start_time = datetime.now()
            
            self._log_event("Dashboard started", "info")
            self.logger.info(f"Dashboard {self.dashboard_id} started successfully")
            return True
            
        except Exception as e:
            self.state = DashboardState.ERROR
            self.logger.error(f"Failed to start dashboard: {e}")
            return False
    
    def stop_dashboard(self) -> bool:
        """Stop the dashboard"""
        if self.state == DashboardState.STOPPED:
            return True
        
        try:
            # Stop update thread
            self.running = False
            if self.update_thread and self.update_thread.is_alive():
                self.update_thread.join(timeout=1.0)
            
            # Stop all components
            self.multi_input_monitor.stop_monitoring()
            self.processing_chain_viz.stop_visualization()
            self.component_control_matrix.stop_control()
            self.data_flow_monitor.stop_monitoring()
            self.output_quality_dashboard.stop_monitoring()
            self.system_status_overview.stop_monitoring()
            
            self.state = DashboardState.STOPPED
            self._log_event("Dashboard stopped", "info")
            self.logger.info(f"Dashboard {self.dashboard_id} stopped")
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping dashboard: {e}")
            return False
    
    def pause_dashboard(self) -> bool:
        """Pause dashboard updates"""
        if self.state == DashboardState.RUNNING:
            self.state = DashboardState.PAUSED
            self._log_event("Dashboard paused", "info")
            return True
        return False
    
    def resume_dashboard(self) -> bool:
        """Resume dashboard updates"""
        if self.state == DashboardState.PAUSED:
            self.state = DashboardState.RUNNING
            self._log_event("Dashboard resumed", "info")
            return True
        return False
    
    def get_full_chain_status(self) -> Dict[str, Any]:
        """Get complete full-chain status"""
        return {
            "dashboard_id": self.dashboard_id,
            "state": self.state.value,
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds() if self.start_time else 0,
            "input_status": self.multi_input_monitor.get_status(),
            "processing_status": self.processing_chain_viz.get_status(),
            "component_control": self.component_control_matrix.get_status(),
            "data_flow": self.data_flow_monitor.get_status(),
            "output_quality": self.output_quality_dashboard.get_status(),
            "system_overview": self.system_status_overview.get_status(),
            "timestamp": datetime.now().isoformat()
        }
    
    def update_input_data(self, device_id: str, audio_frame: AudioFrame, metrics: Dict[str, Any]):
        """Update input monitoring data"""
        self.multi_input_monitor.update_input_data(device_id, audio_frame, metrics)
        
        # Store in history
        input_data = InputMonitorData(
            device_id=device_id,
            device_name=metrics.get("device_name", device_id),
            is_active=True,
            level_db=metrics.get("level_db", -60.0),
            peak_db=metrics.get("peak_db", -60.0),
            waveform_data=audio_frame.data[:1024] if hasattr(audio_frame, 'data') else np.zeros(1024),
            spectrum_data=np.abs(np.fft.fft(audio_frame.data[:1024])) if hasattr(audio_frame, 'data') else np.zeros(512),
            quality_score=metrics.get("quality_score", 0.8),
            sample_rate=audio_frame.sample_rate,
            channels=audio_frame.channels,
            timestamp=datetime.now()
        )
        
        if device_id not in self.input_data_history:
            self.input_data_history[device_id] = deque(maxlen=1000)
        self.input_data_history[device_id].append(input_data)
    
    def update_processing_metrics(self, component_id: str, metrics: ProcessingMetrics):
        """Update processing component metrics"""
        self.processing_chain_viz.update_component_metrics(component_id, metrics)
        self.component_control_matrix.update_component_status(component_id, metrics)
        
        # Store in history
        if component_id not in self.processing_metrics_history:
            self.processing_metrics_history[component_id] = deque(maxlen=1000)
        self.processing_metrics_history[component_id].append(metrics)
    
    def update_output_quality(self, output_id: str, quality_data: Dict[str, Any]):
        """Update output quality data"""
        self.output_quality_dashboard.update_quality_data(output_id, quality_data)
        
        # Store in history
        output_data = OutputQualityData(
            output_id=output_id,
            output_name=quality_data.get("output_name", output_id),
            quality_score=quality_data.get("quality_score", 0.8),
            latency_ms=quality_data.get("latency_ms", 10.0),
            stability_index=quality_data.get("stability_index", 0.9),
            level_db=quality_data.get("level_db", -20.0),
            thd_percent=quality_data.get("thd_percent", 0.01),
            snr_db=quality_data.get("snr_db", 60.0),
            timestamp=datetime.now()
        )
        
        if output_id not in self.output_quality_history:
            self.output_quality_history[output_id] = deque(maxlen=1000)
        self.output_quality_history[output_id].append(output_data)
    
    def register_update_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Register callback for dashboard updates"""
        self.update_callbacks.append(callback)
    
    def _update_loop(self):
        """Main update loop for dashboard"""
        while self.running:
            try:
                if self.state == DashboardState.RUNNING:
                    # Update all components
                    self.multi_input_monitor.update()
                    self.processing_chain_viz.update()
                    self.component_control_matrix.update()
                    self.data_flow_monitor.update()
                    self.output_quality_dashboard.update()
                    self.system_status_overview.update()
                    
                    # Notify callbacks
                    status = self.get_full_chain_status()
                    for callback in self.update_callbacks:
                        try:
                            callback(status)
                        except Exception as e:
                            self.logger.error(f"Callback error: {e}")
                
                time.sleep(self.update_interval)
                
            except Exception as e:
                self.logger.error(f"Update loop error: {e}")
                time.sleep(0.1)
    
    def _log_event(self, message: str, level: str = "info"):
        """Log system event"""
        event = {
            "timestamp": datetime.now(),
            "level": level,
            "message": message,
            "dashboard_id": self.dashboard_id
        }
        self.system_events.append(event)


class MultiInputMonitorPanel:
    """Multi-input monitoring panel for 1~n audio inputs with real-time status, waveform, spectrum, quality metrics"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.monitoring = False
        self.input_devices: Dict[str, Dict[str, Any]] = {}
        self.waveform_buffers: Dict[str, deque] = {}
        self.spectrum_buffers: Dict[str, deque] = {}
        self.quality_metrics: Dict[str, Dict[str, float]] = {}
        
    def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize input monitoring"""
        try:
            self.waveform_buffer_size = config.get("waveform_buffer_size", 2048)
            self.spectrum_buffer_size = config.get("spectrum_buffer_size", 1024)
            self.quality_update_interval = config.get("quality_update_interval", 0.1)
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize input monitor: {e}")
            return False
    
    def start_monitoring(self) -> bool:
        """Start input monitoring"""
        self.monitoring = True
        self.logger.info("Started multi-input monitoring")
        return True
    
    def stop_monitoring(self) -> bool:
        """Stop input monitoring"""
        self.monitoring = False
        self.logger.info("Stopped multi-input monitoring")
        return True
    
    def add_input_device(self, device_id: str, device_info: Dict[str, Any]) -> bool:
        """Add input device to monitoring"""
        self.input_devices[device_id] = {
            "device_info": device_info,
            "is_active": False,
            "last_update": datetime.now(),
            "level_db": -60.0,
            "peak_db": -60.0,
            "quality_score": 0.0
        }
        
        self.waveform_buffers[device_id] = deque(maxlen=self.waveform_buffer_size)
        self.spectrum_buffers[device_id] = deque(maxlen=self.spectrum_buffer_size)
        self.quality_metrics[device_id] = {}
        
        self.logger.info(f"Added input device {device_id} to monitoring")
        return True
    
    def remove_input_device(self, device_id: str) -> bool:
        """Remove input device from monitoring"""
        if device_id in self.input_devices:
            del self.input_devices[device_id]
            del self.waveform_buffers[device_id]
            del self.spectrum_buffers[device_id]
            del self.quality_metrics[device_id]
            return True
        return False
    
    def update_input_data(self, device_id: str, audio_frame: AudioFrame, metrics: Dict[str, Any]):
        """Update input data for device"""
        if not self.monitoring or device_id not in self.input_devices:
            return
        
        # Update device status
        self.input_devices[device_id].update({
            "is_active": True,
            "last_update": datetime.now(),
            "level_db": metrics.get("level_db", -60.0),
            "peak_db": metrics.get("peak_db", -60.0),
            "quality_score": metrics.get("quality_score", 0.0)
        })
        
        # Update waveform buffer
        if hasattr(audio_frame, 'data') and audio_frame.data is not None:
            waveform_chunk = audio_frame.data[:512]  # Take first 512 samples
            self.waveform_buffers[device_id].extend(waveform_chunk)
            
            # Calculate spectrum
            if len(waveform_chunk) >= 512:
                spectrum = np.abs(np.fft.fft(waveform_chunk))[:256]
                self.spectrum_buffers[device_id].append(spectrum)
        
        # Update quality metrics
        self.quality_metrics[device_id].update(metrics.get("quality_metrics", {}))
    
    def get_status(self) -> Dict[str, Any]:
        """Get input monitoring status"""
        return {
            "monitoring": self.monitoring,
            "device_count": len(self.input_devices),
            "active_devices": sum(1 for dev in self.input_devices.values() if dev["is_active"]),
            "devices": self.input_devices.copy(),
            "timestamp": datetime.now().isoformat()
        }
    
    def get_waveform_data(self, device_id: str, samples: int = 1024) -> Optional[np.ndarray]:
        """Get waveform data for device"""
        if device_id not in self.waveform_buffers:
            return None
        
        buffer = list(self.waveform_buffers[device_id])
        if len(buffer) < samples:
            return np.array(buffer + [0.0] * (samples - len(buffer)))
        return np.array(buffer[-samples:])
    
    def get_spectrum_data(self, device_id: str) -> Optional[np.ndarray]:
        """Get spectrum data for device"""
        if device_id not in self.spectrum_buffers or not self.spectrum_buffers[device_id]:
            return None
        return self.spectrum_buffers[device_id][-1]
    
    def update(self):
        """Update monitoring (called from main loop)"""
        if not self.monitoring:
            return
        
        # Check for inactive devices
        current_time = datetime.now()
        for device_id, device_data in self.input_devices.items():
            if (current_time - device_data["last_update"]).total_seconds() > 1.0:
                device_data["is_active"] = False
                device_data["level_db"] = -60.0
                device_data["peak_db"] = -60.0

class ProcessingChainVisualization:
    """Processing chain visualization component"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.active = False
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        return True
    
    def start_visualization(self) -> bool:
        self.active = True
        return True
    
    def stop_visualization(self) -> bool:
        self.active = False
        return True
    
    def update(self):
        pass
    
    def update_component_metrics(self, component_id: str, metrics):
        pass
    
    def get_status(self) -> Dict[str, Any]:
        return {"active": self.active}


class ComponentControlMatrix:
    """Component control matrix"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.active = False
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        return True
    
    def start_control(self) -> bool:
        self.active = True
        return True
    
    def stop_control(self) -> bool:
        self.active = False
        return True
    
    def update(self):
        pass
    
    def update_component_status(self, component_id: str, metrics):
        pass
    
    def get_status(self) -> Dict[str, Any]:
        return {"active": self.active}


class RealTimeDataFlowMonitor:
    """Real-time data flow monitor"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.active = False
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        return True
    
    def start_monitoring(self) -> bool:
        self.active = True
        return True
    
    def stop_monitoring(self) -> bool:
        self.active = False
        return True
    
    def update(self):
        pass
    
    def get_status(self) -> Dict[str, Any]:
        return {"active": self.active}


class OutputQualityDashboard:
    """Output quality dashboard"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.active = False
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        return True
    
    def start_monitoring(self) -> bool:
        self.active = True
        return True
    
    def stop_monitoring(self) -> bool:
        self.active = False
        return True
    
    def update(self):
        pass
    
    def update_quality_data(self, output_id: str, quality_data: Dict[str, Any]):
        pass
    
    def get_status(self) -> Dict[str, Any]:
        return {"active": self.active}


class SystemStatusOverview:
    """System status overview"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.active = False
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        return True
    
    def start_monitoring(self) -> bool:
        self.active = True
        return True
    
    def stop_monitoring(self) -> bool:
        self.active = False
        return True
    
    def update(self):
        pass
    
    def get_status(self) -> Dict[str, Any]:
        return {"active": self.active}


class InteractiveControlPanel:
    """Interactive control panel"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.active = False
    
    def initialize(self, config: Dict[str, Any]) -> bool:
        return True
    
    def get_status(self) -> Dict[str, Any]:
        return {"active": self.active}