"""
Component Visualization and Configuration Management

This module provides visualization interfaces for component tuning,
configuration templates, and visual component interfaces.
"""

import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np
import logging

from ..audio_core.interfaces import IAudioProcessor, IVisualizationProvider
from ..audio_core.models import AudioFrame
from .tuning_platform import BenchmarkResult, TuningSession


class VisualizationType(Enum):
    """Types of visualizations available"""
    WAVEFORM = "waveform"
    SPECTRUM = "spectrum"
    LEVEL_METER = "level_meter"
    PROCESSING_GRAPH = "processing_graph"
    PARAMETER_PLOT = "parameter_plot"
    PERFORMANCE_CHART = "performance_chart"
    COMPARISON_VIEW = "comparison_view"


@dataclass
class VisualizationConfig:
    """Configuration for visualization display"""
    viz_type: VisualizationType
    update_rate_hz: float = 30.0
    buffer_size: int = 1024
    display_duration_ms: int = 1000
    color_scheme: str = "default"
    show_grid: bool = True
    auto_scale: bool = True
    custom_params: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.custom_params is None:
            self.custom_params = {}


@dataclass
class ComponentTemplate:
    """Component configuration template"""
    template_id: str
    name: str
    description: str
    component_type: str
    parameters: Dict[str, Any]
    scenario: str = "default"
    tags: List[str] = None
    created_at: datetime = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.created_at is None:
            self.created_at = datetime.now()


class ComponentVisualizationInterface:
    """
    Visual interface for component input/output comparison and effect display
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.active_visualizations: Dict[str, Dict[str, Any]] = {}
        self.visualization_callbacks: Dict[str, List[Callable]] = {}
        self.data_buffers: Dict[str, List[Any]] = {}
        
    def create_visualization(self, component_id: str, 
                           viz_config: VisualizationConfig) -> str:
        """Create a new visualization for component"""
        viz_id = f"viz_{component_id}_{viz_config.viz_type.value}_{int(time.time())}"
        
        visualization = {
            "viz_id": viz_id,
            "component_id": component_id,
            "config": viz_config,
            "created_at": datetime.now(),
            "last_update": datetime.now(),
            "active": True
        }
        
        self.active_visualizations[viz_id] = visualization
        self.data_buffers[viz_id] = []
        
        self.logger.info(f"Created visualization {viz_id} for component {component_id}")
        return viz_id
    
    def update_visualization_data(self, viz_id: str, 
                                input_data: AudioFrame,
                                output_data: AudioFrame,
                                processing_metrics: Dict[str, float]):
        """Update visualization with new data"""
        if viz_id not in self.active_visualizations:
            return False
        
        viz = self.active_visualizations[viz_id]
        config = viz["config"]
        
        # Prepare visualization data based on type
        viz_data = self._prepare_visualization_data(
            config.viz_type, input_data, output_data, processing_metrics
        )
        
        # Add to buffer
        buffer = self.data_buffers[viz_id]
        buffer.append({
            "timestamp": datetime.now(),
            "input_data": input_data,
            "output_data": output_data,
            "metrics": processing_metrics,
            "viz_data": viz_data
        })
        
        # Maintain buffer size
        max_buffer_size = int(config.update_rate_hz * config.display_duration_ms / 1000)
        if len(buffer) > max_buffer_size:
            buffer.pop(0)
        
        viz["last_update"] = datetime.now()
        
        # Notify callbacks
        self._notify_visualization_callbacks(viz_id, viz_data)
        
        return True
    
    def _prepare_visualization_data(self, viz_type: VisualizationType,
                                  input_data: AudioFrame,
                                  output_data: AudioFrame,
                                  metrics: Dict[str, float]) -> Dict[str, Any]:
        """Prepare data for specific visualization type"""
        
        if viz_type == VisualizationType.WAVEFORM:
            return {
                "input_waveform": input_data.data.tolist(),
                "output_waveform": output_data.data.tolist(),
                "sample_rate": input_data.sample_rate,
                "timestamp": input_data.timestamp.isoformat()
            }
        
        elif viz_type == VisualizationType.SPECTRUM:
            # Calculate FFT for both input and output
            input_fft = np.fft.fft(input_data.data)
            output_fft = np.fft.fft(output_data.data)
            freqs = np.fft.fftfreq(len(input_data.data), 1/input_data.sample_rate)
            
            return {
                "frequencies": freqs[:len(freqs)//2].tolist(),
                "input_magnitude": np.abs(input_fft[:len(input_fft)//2]).tolist(),
                "output_magnitude": np.abs(output_fft[:len(output_fft)//2]).tolist(),
                "input_phase": np.angle(input_fft[:len(input_fft)//2]).tolist(),
                "output_phase": np.angle(output_fft[:len(output_fft)//2]).tolist()
            }
        
        elif viz_type == VisualizationType.LEVEL_METER:
            input_rms = np.sqrt(np.mean(input_data.data ** 2))
            output_rms = np.sqrt(np.mean(output_data.data ** 2))
            input_peak = np.max(np.abs(input_data.data))
            output_peak = np.max(np.abs(output_data.data))
            
            return {
                "input_rms_db": 20 * np.log10(input_rms + 1e-10),
                "output_rms_db": 20 * np.log10(output_rms + 1e-10),
                "input_peak_db": 20 * np.log10(input_peak + 1e-10),
                "output_peak_db": 20 * np.log10(output_peak + 1e-10),
                "gain_db": 20 * np.log10((output_rms + 1e-10) / (input_rms + 1e-10))
            }
        
        elif viz_type == VisualizationType.PERFORMANCE_CHART:
            return {
                "processing_time_ms": metrics.get("processing_time_ms", 0.0),
                "cpu_usage_percent": metrics.get("cpu_usage_percent", 0.0),
                "memory_usage_mb": metrics.get("memory_usage_mb", 0.0),
                "throughput_fps": metrics.get("throughput_fps", 0.0),
                "latency_ms": metrics.get("latency_ms", 0.0)
            }
        
        else:
            return {"raw_metrics": metrics}
    
    def get_visualization_data(self, viz_id: str, 
                             time_range: Optional[Tuple[datetime, datetime]] = None) -> Dict[str, Any]:
        """Get visualization data for display"""
        if viz_id not in self.active_visualizations:
            return {}
        
        viz = self.active_visualizations[viz_id]
        buffer = self.data_buffers[viz_id]
        
        # Filter by time range if specified
        if time_range:
            start_time, end_time = time_range
            filtered_buffer = [
                item for item in buffer
                if start_time <= item["timestamp"] <= end_time
            ]
        else:
            filtered_buffer = buffer
        
        return {
            "visualization_info": {
                "viz_id": viz_id,
                "component_id": viz["component_id"],
                "viz_type": viz["config"].viz_type.value,
                "last_update": viz["last_update"].isoformat(),
                "data_points": len(filtered_buffer)
            },
            "data": [item["viz_data"] for item in filtered_buffer],
            "timestamps": [item["timestamp"].isoformat() for item in filtered_buffer]
        }
    
    def register_visualization_callback(self, viz_id: str, 
                                      callback: Callable[[str, Dict[str, Any]], None]) -> bool:
        """Register callback for visualization updates"""
        if viz_id not in self.visualization_callbacks:
            self.visualization_callbacks[viz_id] = []
        
        self.visualization_callbacks[viz_id].append(callback)
        return True
    
    def _notify_visualization_callbacks(self, viz_id: str, viz_data: Dict[str, Any]):
        """Notify registered callbacks of visualization updates"""
        if viz_id in self.visualization_callbacks:
            for callback in self.visualization_callbacks[viz_id]:
                try:
                    callback(viz_id, viz_data)
                except Exception as e:
                    self.logger.error(f"Visualization callback error: {e}")
    
    def create_comparison_view(self, component_ids: List[str],
                             viz_type: VisualizationType) -> str:
        """Create comparison view for multiple components"""
        comparison_id = f"comparison_{viz_type.value}_{int(time.time())}"
        
        comparison_config = VisualizationConfig(
            viz_type=viz_type,
            custom_params={"component_ids": component_ids, "comparison_mode": True}
        )
        
        comparison = {
            "comparison_id": comparison_id,
            "component_ids": component_ids,
            "config": comparison_config,
            "created_at": datetime.now(),
            "active": True
        }
        
        self.active_visualizations[comparison_id] = comparison
        self.data_buffers[comparison_id] = []
        
        return comparison_id
    
    def stop_visualization(self, viz_id: str) -> bool:
        """Stop and cleanup visualization"""
        if viz_id in self.active_visualizations:
            self.active_visualizations[viz_id]["active"] = False
            
            # Cleanup buffers and callbacks
            if viz_id in self.data_buffers:
                del self.data_buffers[viz_id]
            if viz_id in self.visualization_callbacks:
                del self.visualization_callbacks[viz_id]
            
            return True
        return False
    
    def export_visualization_data(self, viz_id: str, 
                                format: str = "json",
                                file_path: Optional[str] = None) -> str:
        """Export visualization data to file"""
        if viz_id not in self.active_visualizations:
            raise ValueError(f"Visualization {viz_id} not found")
        
        viz_data = self.get_visualization_data(viz_id)
        
        if file_path is None:
            file_path = f"visualization_{viz_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"
        
        if format.lower() == "json":
            with open(file_path, 'w') as f:
                json.dump(viz_data, f, indent=2, default=str)
        else:
            raise ValueError(f"Unsupported export format: {format}")
        
        return file_path


class ComponentConfigurationManager:
    """
    Manager for component configuration templates and presets
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.templates: Dict[str, ComponentTemplate] = {}
        self.template_file_path = "component_templates.json"
        self.load_templates()
    
    def create_template(self, name: str, description: str,
                       component_type: str, parameters: Dict[str, Any],
                       scenario: str = "default", tags: List[str] = None) -> str:
        """Create a new configuration template"""
        template_id = f"template_{component_type}_{int(time.time())}"
        
        template = ComponentTemplate(
            template_id=template_id,
            name=name,
            description=description,
            component_type=component_type,
            parameters=parameters.copy(),
            scenario=scenario,
            tags=tags or []
        )
        
        self.templates[template_id] = template
        self.save_templates()
        
        self.logger.info(f"Created template {template_id}: {name}")
        return template_id
    
    def save_component_configuration(self, component: IAudioProcessor,
                                   template_name: str,
                                   description: str = "",
                                   scenario: str = "default") -> str:
        """Save current component configuration as template"""
        parameters = component.get_parameters()
        component_info = component.get_info()
        
        return self.create_template(
            name=template_name,
            description=description,
            component_type=component_info.component_id,
            parameters=parameters,
            scenario=scenario,
            tags=[component_info.category]
        )
    
    def load_template(self, template_id: str) -> Optional[ComponentTemplate]:
        """Load configuration template"""
        return self.templates.get(template_id)
    
    def apply_template(self, component: IAudioProcessor, template_id: str) -> bool:
        """Apply configuration template to component"""
        template = self.load_template(template_id)
        if not template:
            return False
        
        try:
            success = component.configure(template.parameters)
            if success:
                self.logger.info(f"Applied template {template_id} to component")
            return success
        except Exception as e:
            self.logger.error(f"Failed to apply template {template_id}: {e}")
            return False
    
    def list_templates(self, component_type: Optional[str] = None,
                      scenario: Optional[str] = None,
                      tags: Optional[List[str]] = None) -> List[ComponentTemplate]:
        """List templates with optional filtering"""
        templates = list(self.templates.values())
        
        if component_type:
            templates = [t for t in templates if t.component_type == component_type]
        
        if scenario:
            templates = [t for t in templates if t.scenario == scenario]
        
        if tags:
            templates = [t for t in templates 
                        if any(tag in t.tags for tag in tags)]
        
        return templates
    
    def delete_template(self, template_id: str) -> bool:
        """Delete configuration template"""
        if template_id in self.templates:
            del self.templates[template_id]
            self.save_templates()
            self.logger.info(f"Deleted template {template_id}")
            return True
        return False
    
    def update_template(self, template_id: str, **updates) -> bool:
        """Update existing template"""
        if template_id not in self.templates:
            return False
        
        template = self.templates[template_id]
        
        for key, value in updates.items():
            if hasattr(template, key):
                setattr(template, key, value)
        
        self.save_templates()
        return True
    
    def save_templates(self):
        """Save templates to file"""
        try:
            template_data = {}
            for template_id, template in self.templates.items():
                template_data[template_id] = asdict(template)
            
            with open(self.template_file_path, 'w') as f:
                json.dump(template_data, f, indent=2, default=str)
                
        except Exception as e:
            self.logger.error(f"Failed to save templates: {e}")
    
    def load_templates(self):
        """Load templates from file"""
        try:
            with open(self.template_file_path, 'r') as f:
                template_data = json.load(f)
            
            for template_id, data in template_data.items():
                # Convert datetime strings back to datetime objects
                if 'created_at' in data and isinstance(data['created_at'], str):
                    data['created_at'] = datetime.fromisoformat(data['created_at'])
                
                template = ComponentTemplate(**data)
                self.templates[template_id] = template
                
        except FileNotFoundError:
            self.logger.info("No existing template file found, starting with empty templates")
        except Exception as e:
            self.logger.error(f"Failed to load templates: {e}")
    
    def export_templates(self, file_path: str, template_ids: Optional[List[str]] = None):
        """Export templates to file"""
        if template_ids:
            export_templates = {tid: self.templates[tid] for tid in template_ids 
                              if tid in self.templates}
        else:
            export_templates = self.templates
        
        export_data = {}
        for template_id, template in export_templates.items():
            export_data[template_id] = asdict(template)
        
        with open(file_path, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)
    
    def import_templates(self, file_path: str, overwrite: bool = False):
        """Import templates from file"""
        with open(file_path, 'r') as f:
            import_data = json.load(f)
        
        imported_count = 0
        for template_id, data in import_data.items():
            if template_id in self.templates and not overwrite:
                continue
            
            # Convert datetime strings back to datetime objects
            if 'created_at' in data and isinstance(data['created_at'], str):
                data['created_at'] = datetime.fromisoformat(data['created_at'])
            
            template = ComponentTemplate(**data)
            self.templates[template_id] = template
            imported_count += 1
        
        self.save_templates()
        self.logger.info(f"Imported {imported_count} templates")
        return imported_count


class ComponentPerformanceMonitor:
    """
    Real-time performance monitoring for components
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.performance_data: Dict[str, List[Dict[str, Any]]] = {}
        self.monitoring_active: Dict[str, bool] = {}
        
    def start_monitoring(self, component_id: str) -> bool:
        """Start performance monitoring for component"""
        if component_id not in self.performance_data:
            self.performance_data[component_id] = []
        
        self.monitoring_active[component_id] = True
        self.logger.info(f"Started monitoring component {component_id}")
        return True
    
    def stop_monitoring(self, component_id: str) -> bool:
        """Stop performance monitoring for component"""
        if component_id in self.monitoring_active:
            self.monitoring_active[component_id] = False
            self.logger.info(f"Stopped monitoring component {component_id}")
            return True
        return False
    
    def record_performance_data(self, component_id: str,
                              processing_time_ms: float,
                              cpu_usage_percent: float,
                              memory_usage_mb: float,
                              algorithm_metrics: Dict[str, float]):
        """Record performance data point"""
        if not self.monitoring_active.get(component_id, False):
            return
        
        data_point = {
            "timestamp": datetime.now(),
            "processing_time_ms": processing_time_ms,
            "cpu_usage_percent": cpu_usage_percent,
            "memory_usage_mb": memory_usage_mb,
            "algorithm_metrics": algorithm_metrics.copy()
        }
        
        self.performance_data[component_id].append(data_point)
        
        # Maintain reasonable buffer size (last 1000 data points)
        if len(self.performance_data[component_id]) > 1000:
            self.performance_data[component_id].pop(0)
    
    def get_performance_summary(self, component_id: str,
                              time_window_minutes: int = 5) -> Dict[str, Any]:
        """Get performance summary for component"""
        if component_id not in self.performance_data:
            return {}
        
        cutoff_time = datetime.now() - timedelta(minutes=time_window_minutes)
        recent_data = [
            dp for dp in self.performance_data[component_id]
            if dp["timestamp"] >= cutoff_time
        ]
        
        if not recent_data:
            return {}
        
        # Calculate statistics
        processing_times = [dp["processing_time_ms"] for dp in recent_data]
        cpu_usage = [dp["cpu_usage_percent"] for dp in recent_data]
        memory_usage = [dp["memory_usage_mb"] for dp in recent_data]
        
        summary = {
            "component_id": component_id,
            "time_window_minutes": time_window_minutes,
            "data_points": len(recent_data),
            "processing_time": {
                "avg_ms": np.mean(processing_times),
                "min_ms": np.min(processing_times),
                "max_ms": np.max(processing_times),
                "std_ms": np.std(processing_times)
            },
            "cpu_usage": {
                "avg_percent": np.mean(cpu_usage),
                "min_percent": np.min(cpu_usage),
                "max_percent": np.max(cpu_usage),
                "std_percent": np.std(cpu_usage)
            },
            "memory_usage": {
                "avg_mb": np.mean(memory_usage),
                "min_mb": np.min(memory_usage),
                "max_mb": np.max(memory_usage),
                "std_mb": np.std(memory_usage)
            }
        }
        
        # Add algorithm-specific metrics if available
        if recent_data and "algorithm_metrics" in recent_data[0]:
            algorithm_metrics = {}
            for metric_name in recent_data[0]["algorithm_metrics"]:
                metric_values = [
                    dp["algorithm_metrics"].get(metric_name, 0.0)
                    for dp in recent_data
                ]
                algorithm_metrics[metric_name] = {
                    "avg": np.mean(metric_values),
                    "min": np.min(metric_values),
                    "max": np.max(metric_values),
                    "std": np.std(metric_values)
                }
            summary["algorithm_metrics"] = algorithm_metrics
        
        return summary
    
    def get_performance_trend(self, component_id: str,
                            metric_name: str,
                            time_window_minutes: int = 30) -> List[Tuple[datetime, float]]:
        """Get performance trend for specific metric"""
        if component_id not in self.performance_data:
            return []
        
        cutoff_time = datetime.now() - timedelta(minutes=time_window_minutes)
        recent_data = [
            dp for dp in self.performance_data[component_id]
            if dp["timestamp"] >= cutoff_time
        ]
        
        trend_data = []
        for dp in recent_data:
            if metric_name in dp:
                trend_data.append((dp["timestamp"], dp[metric_name]))
            elif "algorithm_metrics" in dp and metric_name in dp["algorithm_metrics"]:
                trend_data.append((dp["timestamp"], dp["algorithm_metrics"][metric_name]))
        
        return trend_data