"""
Full-Chain Visual Audio Processing Pipeline

This module implements the FullChainVisualAudioPipeline class for complete
"audio input → processing components → audio output" visualization pipeline
with dynamic topology graphs, drag-and-drop configuration, and real-time monitoring.
"""

import asyncio
import json
import time
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Callable, Union
from enum import Enum
import numpy as np
import logging
from concurrent.futures import ThreadPoolExecutor
from collections import deque

from ..audio_core.interfaces import IAudioProcessor, ComponentInfo, ProcessingMetrics
from ..audio_core.models import AudioFrame
from .component_visualization import ComponentVisualizationInterface, VisualizationType


class PipelineNodeType(Enum):
    """Types of nodes in the processing pipeline"""
    INPUT = "input"
    PROCESSOR = "processor"
    OUTPUT = "output"
    SPLITTER = "splitter"
    MIXER = "mixer"


class ConnectionType(Enum):
    """Types of connections between nodes"""
    AUDIO = "audio"
    CONTROL = "control"
    SIDECHAIN = "sidechain"


@dataclass
class PipelineNode:
    """Node in the processing pipeline"""
    node_id: str
    name: str
    node_type: PipelineNodeType
    component: Optional[IAudioProcessor] = None
    position: Tuple[float, float] = (0.0, 0.0)
    enabled: bool = True
    bypass: bool = False
    parameters: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}


@dataclass
class PipelineConnection:
    """Connection between pipeline nodes"""
    connection_id: str
    source_node_id: str
    target_node_id: str
    connection_type: ConnectionType = ConnectionType.AUDIO
    enabled: bool = True
    gain: float = 1.0
    delay_ms: float = 0.0


@dataclass
class PipelineTemplate:
    """Template for pipeline configuration"""
    template_id: str
    name: str
    description: str
    nodes: List[PipelineNode]
    connections: List[PipelineConnection]
    scenario: str = "default"
    tags: List[str] = None
    created_at: datetime = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.created_at is None:
            self.created_at = datetime.now()


@dataclass
class ProcessingMetrics:
    """Real-time processing metrics"""
    node_id: str
    timestamp: datetime
    processing_time_ms: float
    cpu_usage_percent: float
    memory_usage_mb: float
    input_level_db: float
    output_level_db: float
    latency_ms: float
    quality_metrics: Dict[str, float] = None
    
    def __post_init__(self):
        if self.quality_metrics is None:
            self.quality_metrics = {}


class FullChainVisualAudioPipeline:
    """
    Complete visual audio processing pipeline with real-time monitoring
    and drag-and-drop configuration
    """
    
    def __init__(self, pipeline_id: str, name: str = ""):
        self.pipeline_id = pipeline_id
        self.name = name or f"Pipeline_{pipeline_id}"
        self.logger = logging.getLogger(__name__)
        
        # Pipeline structure
        self.nodes: Dict[str, PipelineNode] = {}
        self.connections: Dict[str, PipelineConnection] = {}
        self.processing_order: List[str] = []
        
        # Runtime state
        self.running = False
        self.paused = False
        self.start_time: Optional[datetime] = None
        
        # Monitoring and visualization
        self.visualization_interface = ComponentVisualizationInterface()
        self.metrics_history: Dict[str, deque] = {}
        self.data_flow_monitor = DataFlowMonitor()
        
        # Performance analysis
        self.performance_analyzer = PipelinePerformanceAnalyzer()
        self.quality_evaluator = PipelineQualityEvaluator()
        
        # Template management
        self.template_manager = PipelineTemplateManager()
        
        # Multi-path processing support
        self.parallel_paths: Dict[str, List[str]] = {}
        self.cross_processing_configs: Dict[str, Dict[str, Any]] = {}
        
        # Callbacks
        self.update_callbacks: List[Callable] = []
        
    def add_node(self, node: PipelineNode) -> bool:
        """Add a node to the pipeline"""
        if node.node_id in self.nodes:
            self.logger.warning(f"Node {node.node_id} already exists")
            return False
        
        self.nodes[node.node_id] = node
        self.metrics_history[node.node_id] = deque(maxlen=1000)
        
        # Create visualization for the node if it has a component
        if node.component:
            viz_config = self._create_node_visualization_config(node)
            self.visualization_interface.create_visualization(node.node_id, viz_config)
        
        self._update_processing_order()
        self._notify_callbacks("node_added", {"node_id": node.node_id})
        
        self.logger.info(f"Added node {node.node_id} to pipeline")
        return True
    
    def remove_node(self, node_id: str) -> bool:
        """Remove a node from the pipeline"""
        if node_id not in self.nodes:
            return False
        
        # Remove all connections involving this node
        connections_to_remove = [
            conn_id for conn_id, conn in self.connections.items()
            if conn.source_node_id == node_id or conn.target_node_id == node_id
        ]
        
        for conn_id in connections_to_remove:
            self.remove_connection(conn_id)
        
        # Remove node
        del self.nodes[node_id]
        if node_id in self.metrics_history:
            del self.metrics_history[node_id]
        
        # Stop visualization
        self.visualization_interface.stop_visualization(node_id)
        
        self._update_processing_order()
        self._notify_callbacks("node_removed", {"node_id": node_id})
        
        self.logger.info(f"Removed node {node_id} from pipeline")
        return True
    
    def add_connection(self, connection: PipelineConnection) -> bool:
        """Add a connection between nodes"""
        if connection.connection_id in self.connections:
            return False
        
        # Validate nodes exist
        if (connection.source_node_id not in self.nodes or 
            connection.target_node_id not in self.nodes):
            return False
        
        # Check for cycles (simplified check)
        if self._would_create_cycle(connection):
            self.logger.warning(f"Connection would create cycle: {connection.connection_id}")
            return False
        
        self.connections[connection.connection_id] = connection
        self._update_processing_order()
        self._notify_callbacks("connection_added", {"connection_id": connection.connection_id})
        
        self.logger.info(f"Added connection {connection.connection_id}")
        return True
    
    def remove_connection(self, connection_id: str) -> bool:
        """Remove a connection"""
        if connection_id not in self.connections:
            return False
        
        del self.connections[connection_id]
        self._update_processing_order()
        self._notify_callbacks("connection_removed", {"connection_id": connection_id})
        
        self.logger.info(f"Removed connection {connection_id}")
        return True
    
    def start_pipeline(self) -> bool:
        """Start the processing pipeline"""
        if self.running:
            return False
        
        if not self._validate_pipeline():
            self.logger.error("Pipeline validation failed")
            return False
        
        self.running = True
        self.paused = False
        self.start_time = datetime.now()
        
        # Start monitoring
        self.data_flow_monitor.start_monitoring(self.pipeline_id)
        
        self._notify_callbacks("pipeline_started", {"pipeline_id": self.pipeline_id})
        self.logger.info(f"Started pipeline {self.pipeline_id}")
        return True
    
    def stop_pipeline(self) -> bool:
        """Stop the processing pipeline"""
        if not self.running:
            return False
        
        self.running = False
        self.paused = False
        
        # Stop monitoring
        self.data_flow_monitor.stop_monitoring(self.pipeline_id)
        
        self._notify_callbacks("pipeline_stopped", {"pipeline_id": self.pipeline_id})
        self.logger.info(f"Stopped pipeline {self.pipeline_id}")
        return True
    
    def pause_pipeline(self) -> bool:
        """Pause the processing pipeline"""
        if not self.running or self.paused:
            return False
        
        self.paused = True
        self._notify_callbacks("pipeline_paused", {"pipeline_id": self.pipeline_id})
        return True
    
    def resume_pipeline(self) -> bool:
        """Resume the processing pipeline"""
        if not self.running or not self.paused:
            return False
        
        self.paused = False
        self._notify_callbacks("pipeline_resumed", {"pipeline_id": self.pipeline_id})
        return True
    
    def process_audio(self, input_audio: AudioFrame, input_node_id: str = None) -> Dict[str, AudioFrame]:
        """Process audio through the pipeline"""
        if not self.running or self.paused:
            return {}
        
        # Find input nodes if not specified
        if input_node_id is None:
            input_nodes = [node_id for node_id, node in self.nodes.items() 
                          if node.node_type == PipelineNodeType.INPUT]
            if not input_nodes:
                return {}
            input_node_id = input_nodes[0]
        
        # Process through pipeline
        processing_context = {
            "audio_data": {input_node_id: input_audio},
            "metrics": {},
            "start_time": time.time()
        }
        
        # Execute processing order
        for node_id in self.processing_order:
            if node_id not in self.nodes:
                continue
            
            node = self.nodes[node_id]
            if not node.enabled or node.bypass:
                continue
            
            # Get input audio for this node
            input_data = self._get_node_input_audio(node_id, processing_context)
            if input_data is None:
                continue
            
            # Process audio
            start_time = time.time()
            try:
                if node.component:
                    output_data = node.component.process(input_data)
                else:
                    output_data = input_data  # Pass-through
                
                processing_time = (time.time() - start_time) * 1000
                
                # Store output
                processing_context["audio_data"][node_id] = output_data
                
                # Record metrics
                metrics = self._calculate_node_metrics(node_id, input_data, output_data, processing_time)
                processing_context["metrics"][node_id] = metrics
                self.metrics_history[node_id].append(metrics)
                
                # Update visualization
                if node.component:
                    self.visualization_interface.update_visualization_data(
                        node_id, input_data, output_data, asdict(metrics)
                    )
                
            except Exception as e:
                self.logger.error(f"Error processing node {node_id}: {e}")
                continue
        
        # Return output audio from output nodes
        output_audio = {}
        for node_id, node in self.nodes.items():
            if node.node_type == PipelineNodeType.OUTPUT and node_id in processing_context["audio_data"]:
                output_audio[node_id] = processing_context["audio_data"][node_id]
        
        return output_audio
    
    def get_topology_graph(self) -> Dict[str, Any]:
        """Get dynamic topology graph representation"""
        graph = {
            "nodes": [],
            "connections": [],
            "metadata": {
                "pipeline_id": self.pipeline_id,
                "name": self.name,
                "running": self.running,
                "paused": self.paused,
                "node_count": len(self.nodes),
                "connection_count": len(self.connections)
            }
        }
        
        # Add nodes
        for node_id, node in self.nodes.items():
            node_data = {
                "id": node_id,
                "name": node.name,
                "type": node.node_type.value,
                "position": node.position,
                "enabled": node.enabled,
                "bypass": node.bypass,
                "parameters": node.parameters
            }
            
            # Add component info if available
            if node.component:
                component_info = node.component.get_info()
                node_data["component_info"] = asdict(component_info)
            
            # Add recent metrics
            if node_id in self.metrics_history and self.metrics_history[node_id]:
                latest_metrics = self.metrics_history[node_id][-1]
                node_data["latest_metrics"] = asdict(latest_metrics)
            
            graph["nodes"].append(node_data)
        
        # Add connections
        for conn_id, conn in self.connections.items():
            conn_data = {
                "id": conn_id,
                "source": conn.source_node_id,
                "target": conn.target_node_id,
                "type": conn.connection_type.value,
                "enabled": conn.enabled,
                "gain": conn.gain,
                "delay_ms": conn.delay_ms
            }
            graph["connections"].append(conn_data)
        
        return graph
    
    def update_node_position(self, node_id: str, position: Tuple[float, float]) -> bool:
        """Update node position for drag-and-drop interface"""
        if node_id not in self.nodes:
            return False
        
        self.nodes[node_id].position = position
        self._notify_callbacks("node_moved", {"node_id": node_id, "position": position})
        return True
    
    def reconfigure_pipeline(self, new_topology: Dict[str, Any]) -> bool:
        """Reconfigure pipeline from topology data"""
        try:
            # Validate topology
            if not self._validate_topology(new_topology):
                return False
            
            # Stop pipeline if running
            was_running = self.running
            if was_running:
                self.stop_pipeline()
            
            # Clear current configuration
            self.nodes.clear()
            self.connections.clear()
            
            # Load new configuration
            for node_data in new_topology.get("nodes", []):
                node = PipelineNode(
                    node_id=node_data["id"],
                    name=node_data["name"],
                    node_type=PipelineNodeType(node_data["type"]),
                    position=tuple(node_data.get("position", (0.0, 0.0))),
                    enabled=node_data.get("enabled", True),
                    bypass=node_data.get("bypass", False),
                    parameters=node_data.get("parameters", {})
                )
                self.add_node(node)
            
            for conn_data in new_topology.get("connections", []):
                connection = PipelineConnection(
                    connection_id=conn_data["id"],
                    source_node_id=conn_data["source"],
                    target_node_id=conn_data["target"],
                    connection_type=ConnectionType(conn_data.get("type", "audio")),
                    enabled=conn_data.get("enabled", True),
                    gain=conn_data.get("gain", 1.0),
                    delay_ms=conn_data.get("delay_ms", 0.0)
                )
                self.add_connection(connection)
            
            # Restart if was running
            if was_running:
                self.start_pipeline()
            
            self._notify_callbacks("pipeline_reconfigured", {"topology": new_topology})
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to reconfigure pipeline: {e}")
            return False
    
    def save_template(self, template_name: str, description: str = "", 
                     scenario: str = "default", tags: List[str] = None) -> str:
        """Save current pipeline configuration as template"""
        template = PipelineTemplate(
            template_id=f"template_{self.pipeline_id}_{int(time.time())}",
            name=template_name,
            description=description,
            nodes=list(self.nodes.values()),
            connections=list(self.connections.values()),
            scenario=scenario,
            tags=tags or []
        )
        
        return self.template_manager.save_template(template)
    
    def load_template(self, template_id: str) -> bool:
        """Load pipeline configuration from template"""
        template = self.template_manager.load_template(template_id)
        if not template:
            return False
        
        # Convert template to topology format
        topology = {
            "nodes": [asdict(node) for node in template.nodes],
            "connections": [asdict(conn) for conn in template.connections]
        }
        
        return self.reconfigure_pipeline(topology)
    
    def get_performance_analysis(self, time_window_minutes: int = 5) -> Dict[str, Any]:
        """Get comprehensive performance analysis"""
        return self.performance_analyzer.analyze_pipeline_performance(
            self.pipeline_id, self.metrics_history, time_window_minutes
        )
    
    def get_quality_assessment(self) -> Dict[str, Any]:
        """Get end-to-end quality assessment"""
        return self.quality_evaluator.evaluate_pipeline_quality(
            self.pipeline_id, self.metrics_history
        )
    
    def register_update_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """Register callback for pipeline updates"""
        self.update_callbacks.append(callback)
    
    def _create_node_visualization_config(self, node: PipelineNode):
        """Create visualization configuration for node"""
        from .component_visualization import VisualizationConfig
        
        if node.node_type == PipelineNodeType.PROCESSOR:
            viz_type = VisualizationType.PROCESSING_GRAPH
        elif node.node_type in [PipelineNodeType.INPUT, PipelineNodeType.OUTPUT]:
            viz_type = VisualizationType.LEVEL_METER
        else:
            viz_type = VisualizationType.WAVEFORM
        
        return VisualizationConfig(
            viz_type=viz_type,
            update_rate_hz=30.0,
            display_duration_ms=1000
        )
    
    def _update_processing_order(self):
        """Update processing order based on topology"""
        # Simple topological sort
        self.processing_order = []
        visited = set()
        temp_visited = set()
        
        def visit(node_id):
            if node_id in temp_visited:
                return  # Cycle detected, skip
            if node_id in visited:
                return
            
            temp_visited.add(node_id)
            
            # Visit dependencies (nodes that feed into this one)
            for conn in self.connections.values():
                if conn.target_node_id == node_id and conn.enabled:
                    visit(conn.source_node_id)
            
            temp_visited.remove(node_id)
            visited.add(node_id)
            self.processing_order.append(node_id)
        
        # Start with input nodes
        for node_id, node in self.nodes.items():
            if node.node_type == PipelineNodeType.INPUT:
                visit(node_id)
        
        # Visit remaining nodes
        for node_id in self.nodes:
            if node_id not in visited:
                visit(node_id)
    
    def _would_create_cycle(self, new_connection: PipelineConnection) -> bool:
        """Check if adding connection would create a cycle"""
        # Simple cycle detection - check if target can reach source
        def can_reach(start_id, target_id, visited=None):
            if visited is None:
                visited = set()
            
            if start_id == target_id:
                return True
            
            if start_id in visited:
                return False
            
            visited.add(start_id)
            
            for conn in self.connections.values():
                if conn.source_node_id == start_id and conn.enabled:
                    if can_reach(conn.target_node_id, target_id, visited):
                        return True
            
            return False
        
        return can_reach(new_connection.target_node_id, new_connection.source_node_id)
    
    def _validate_pipeline(self) -> bool:
        """Validate pipeline configuration"""
        # If pipeline is empty, it's valid (will be configured later)
        if not self.nodes:
            return True
        
        # Check for at least one input and one output
        has_input = any(node.node_type == PipelineNodeType.INPUT for node in self.nodes.values())
        has_output = any(node.node_type == PipelineNodeType.OUTPUT for node in self.nodes.values())
        
        if not has_input or not has_output:
            return False
        
        # Check for disconnected nodes (optional warning)
        connected_nodes = set()
        for conn in self.connections.values():
            if conn.enabled:
                connected_nodes.add(conn.source_node_id)
                connected_nodes.add(conn.target_node_id)
        
        disconnected = set(self.nodes.keys()) - connected_nodes
        if disconnected:
            self.logger.warning(f"Disconnected nodes: {disconnected}")
        
        return True
    
    def _validate_topology(self, topology: Dict[str, Any]) -> bool:
        """Validate topology configuration"""
        try:
            # Check required fields
            if "nodes" not in topology or "connections" not in topology:
                return False
            
            # Validate nodes
            node_ids = set()
            for node_data in topology["nodes"]:
                if "id" not in node_data or "name" not in node_data or "type" not in node_data:
                    return False
                node_ids.add(node_data["id"])
            
            # Validate connections
            for conn_data in topology["connections"]:
                if ("id" not in conn_data or "source" not in conn_data or 
                    "target" not in conn_data):
                    return False
                
                if (conn_data["source"] not in node_ids or 
                    conn_data["target"] not in node_ids):
                    return False
            
            return True
            
        except Exception:
            return False
    
    def _get_node_input_audio(self, node_id: str, context: Dict[str, Any]) -> Optional[AudioFrame]:
        """Get input audio for a node from processing context"""
        # Find connections that feed into this node
        input_connections = [
            conn for conn in self.connections.values()
            if conn.target_node_id == node_id and conn.enabled
        ]
        
        if not input_connections:
            # No input connections, check if it's an input node
            node = self.nodes[node_id]
            if node.node_type == PipelineNodeType.INPUT:
                return context["audio_data"].get(node_id)
            return None
        
        # For now, use the first input connection
        # In a full implementation, would handle mixing multiple inputs
        source_node_id = input_connections[0].source_node_id
        return context["audio_data"].get(source_node_id)
    
    def _calculate_node_metrics(self, node_id: str, input_audio: AudioFrame, 
                              output_audio: AudioFrame, processing_time_ms: float) -> ProcessingMetrics:
        """Calculate processing metrics for a node"""
        # Calculate audio levels
        input_rms = np.sqrt(np.mean(input_audio.data ** 2))
        output_rms = np.sqrt(np.mean(output_audio.data ** 2))
        
        input_level_db = 20 * np.log10(input_rms + 1e-10)
        output_level_db = 20 * np.log10(output_rms + 1e-10)
        
        # Simulate other metrics
        cpu_usage = 10.0 + 20.0 * np.random.random()
        memory_usage = 20.0 + 10.0 * np.random.random()
        latency_ms = processing_time_ms + 1.0 * np.random.random()
        
        return ProcessingMetrics(
            node_id=node_id,
            timestamp=datetime.now(),
            processing_time_ms=processing_time_ms,
            cpu_usage_percent=cpu_usage,
            memory_usage_mb=memory_usage,
            input_level_db=input_level_db,
            output_level_db=output_level_db,
            latency_ms=latency_ms,
            quality_metrics={
                "snr_db": 40.0 + 20.0 * np.random.random(),
                "thd_percent": 0.01 + 0.02 * np.random.random()
            }
        )
    
    def _notify_callbacks(self, event_type: str, data: Dict[str, Any]):
        """Notify registered callbacks of pipeline events"""
        for callback in self.update_callbacks:
            try:
                callback(event_type, data)
            except Exception as e:
                self.logger.error(f"Callback error: {e}")


class DataFlowMonitor:
    """Monitor data flow through the pipeline"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.monitoring_active: Dict[str, bool] = {}
        self.flow_data: Dict[str, List[Dict[str, Any]]] = {}
    
    def start_monitoring(self, pipeline_id: str):
        """Start monitoring data flow for pipeline"""
        self.monitoring_active[pipeline_id] = True
        self.flow_data[pipeline_id] = []
        self.logger.info(f"Started data flow monitoring for {pipeline_id}")
    
    def stop_monitoring(self, pipeline_id: str):
        """Stop monitoring data flow for pipeline"""
        self.monitoring_active[pipeline_id] = False
        self.logger.info(f"Stopped data flow monitoring for {pipeline_id}")
    
    def record_flow_data(self, pipeline_id: str, node_id: str, 
                        audio_data: AudioFrame, metrics: Dict[str, Any]):
        """Record data flow information"""
        if not self.monitoring_active.get(pipeline_id, False):
            return
        
        flow_record = {
            "timestamp": datetime.now(),
            "node_id": node_id,
            "audio_info": {
                "sample_rate": audio_data.sample_rate,
                "channels": audio_data.channels,
                "frame_size": len(audio_data.data),
                "rms_level": float(np.sqrt(np.mean(audio_data.data ** 2)))
            },
            "metrics": metrics
        }
        
        self.flow_data[pipeline_id].append(flow_record)
        
        # Maintain buffer size
        if len(self.flow_data[pipeline_id]) > 10000:
            self.flow_data[pipeline_id] = self.flow_data[pipeline_id][-5000:]


class PipelinePerformanceAnalyzer:
    """Analyze pipeline performance metrics"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def analyze_pipeline_performance(self, pipeline_id: str, 
                                   metrics_history: Dict[str, deque],
                                   time_window_minutes: int = 5) -> Dict[str, Any]:
        """Analyze overall pipeline performance"""
        cutoff_time = datetime.now() - timedelta(minutes=time_window_minutes)
        
        analysis = {
            "pipeline_id": pipeline_id,
            "analysis_time": datetime.now(),
            "time_window_minutes": time_window_minutes,
            "node_analysis": {},
            "overall_metrics": {}
        }
        
        all_processing_times = []
        all_cpu_usage = []
        all_memory_usage = []
        all_latencies = []
        
        # Analyze each node
        for node_id, metrics_deque in metrics_history.items():
            recent_metrics = [
                m for m in metrics_deque 
                if m.timestamp >= cutoff_time
            ]
            
            if not recent_metrics:
                continue
            
            processing_times = [m.processing_time_ms for m in recent_metrics]
            cpu_usage = [m.cpu_usage_percent for m in recent_metrics]
            memory_usage = [m.memory_usage_mb for m in recent_metrics]
            latencies = [m.latency_ms for m in recent_metrics]
            
            node_analysis = {
                "data_points": len(recent_metrics),
                "processing_time": {
                    "avg_ms": np.mean(processing_times),
                    "max_ms": np.max(processing_times),
                    "min_ms": np.min(processing_times),
                    "std_ms": np.std(processing_times)
                },
                "cpu_usage": {
                    "avg_percent": np.mean(cpu_usage),
                    "max_percent": np.max(cpu_usage),
                    "min_percent": np.min(cpu_usage)
                },
                "memory_usage": {
                    "avg_mb": np.mean(memory_usage),
                    "max_mb": np.max(memory_usage),
                    "min_mb": np.min(memory_usage)
                },
                "latency": {
                    "avg_ms": np.mean(latencies),
                    "max_ms": np.max(latencies),
                    "min_ms": np.min(latencies)
                }
            }
            
            analysis["node_analysis"][node_id] = node_analysis
            
            # Collect for overall analysis
            all_processing_times.extend(processing_times)
            all_cpu_usage.extend(cpu_usage)
            all_memory_usage.extend(memory_usage)
            all_latencies.extend(latencies)
        
        # Overall pipeline metrics
        if all_processing_times:
            analysis["overall_metrics"] = {
                "total_processing_time_ms": np.sum(all_processing_times),
                "avg_processing_time_ms": np.mean(all_processing_times),
                "max_processing_time_ms": np.max(all_processing_times),
                "total_cpu_usage_percent": np.mean(all_cpu_usage),
                "total_memory_usage_mb": np.sum(all_memory_usage),
                "end_to_end_latency_ms": np.sum(all_latencies),
                "throughput_estimate_fps": 1000.0 / (np.mean(all_processing_times) + 1e-6)
            }
        
        return analysis


class PipelineQualityEvaluator:
    """Evaluate end-to-end pipeline quality"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def evaluate_pipeline_quality(self, pipeline_id: str, 
                                metrics_history: Dict[str, deque]) -> Dict[str, Any]:
        """Evaluate overall pipeline quality metrics"""
        evaluation = {
            "pipeline_id": pipeline_id,
            "evaluation_time": datetime.now(),
            "quality_metrics": {},
            "node_quality": {}
        }
        
        all_quality_metrics = []
        
        # Collect quality metrics from all nodes
        for node_id, metrics_deque in metrics_history.items():
            if not metrics_deque:
                continue
            
            recent_metrics = list(metrics_deque)[-100:]  # Last 100 samples
            
            node_quality = {}
            for metric in recent_metrics:
                if metric.quality_metrics:
                    for quality_name, quality_value in metric.quality_metrics.items():
                        if quality_name not in node_quality:
                            node_quality[quality_name] = []
                        node_quality[quality_name].append(quality_value)
            
            # Calculate averages for this node
            node_avg_quality = {}
            for quality_name, values in node_quality.items():
                node_avg_quality[quality_name] = {
                    "avg": np.mean(values),
                    "min": np.min(values),
                    "max": np.max(values),
                    "std": np.std(values)
                }
            
            evaluation["node_quality"][node_id] = node_avg_quality
            all_quality_metrics.append(node_avg_quality)
        
        # Calculate overall quality score
        if all_quality_metrics:
            overall_snr = []
            overall_thd = []
            
            for node_metrics in all_quality_metrics:
                if "snr_db" in node_metrics:
                    overall_snr.append(node_metrics["snr_db"]["avg"])
                if "thd_percent" in node_metrics:
                    overall_thd.append(node_metrics["thd_percent"]["avg"])
            
            if overall_snr and overall_thd:
                # Calculate composite quality score
                avg_snr = np.mean(overall_snr)
                avg_thd = np.mean(overall_thd)
                
                # Normalize and combine (higher SNR is better, lower THD is better)
                snr_score = min(1.0, avg_snr / 60.0)  # Normalize to 60dB
                thd_score = max(0.0, 1.0 - avg_thd / 1.0)  # Normalize to 1% THD
                
                overall_quality_score = (snr_score * 0.6 + thd_score * 0.4)
                
                evaluation["quality_metrics"] = {
                    "overall_quality_score": overall_quality_score,
                    "avg_snr_db": avg_snr,
                    "avg_thd_percent": avg_thd,
                    "quality_grade": self._get_quality_grade(overall_quality_score)
                }
        
        return evaluation
    
    def _get_quality_grade(self, score: float) -> str:
        """Convert quality score to grade"""
        if score >= 0.9:
            return "Excellent"
        elif score >= 0.8:
            return "Very Good"
        elif score >= 0.7:
            return "Good"
        elif score >= 0.6:
            return "Fair"
        else:
            return "Poor"


class PipelineTemplateManager:
    """Manage pipeline configuration templates"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.templates: Dict[str, PipelineTemplate] = {}
        self.template_file = "pipeline_templates.json"
        self.load_templates()
    
    def save_template(self, template: PipelineTemplate) -> str:
        """Save pipeline template"""
        self.templates[template.template_id] = template
        self._save_templates_to_file()
        self.logger.info(f"Saved template {template.template_id}")
        return template.template_id
    
    def load_template(self, template_id: str) -> Optional[PipelineTemplate]:
        """Load pipeline template"""
        return self.templates.get(template_id)
    
    def list_templates(self, scenario: Optional[str] = None, 
                      tags: Optional[List[str]] = None) -> List[PipelineTemplate]:
        """List available templates with optional filtering"""
        templates = list(self.templates.values())
        
        if scenario:
            templates = [t for t in templates if t.scenario == scenario]
        
        if tags:
            templates = [t for t in templates 
                        if any(tag in t.tags for tag in tags)]
        
        return templates
    
    def delete_template(self, template_id: str) -> bool:
        """Delete template"""
        if template_id in self.templates:
            del self.templates[template_id]
            self._save_templates_to_file()
            return True
        return False
    
    def load_templates(self):
        """Load templates from file"""
        try:
            with open(self.template_file, 'r') as f:
                template_data = json.load(f)
            
            for template_id, data in template_data.items():
                # Reconstruct template object
                nodes = [PipelineNode(**node_data) for node_data in data["nodes"]]
                connections = [PipelineConnection(**conn_data) for conn_data in data["connections"]]
                
                template = PipelineTemplate(
                    template_id=template_id,
                    name=data["name"],
                    description=data["description"],
                    nodes=nodes,
                    connections=connections,
                    scenario=data.get("scenario", "default"),
                    tags=data.get("tags", []),
                    created_at=datetime.fromisoformat(data["created_at"])
                )
                
                self.templates[template_id] = template
                
        except FileNotFoundError:
            self.logger.info("No template file found, starting with empty templates")
        except Exception as e:
            self.logger.error(f"Failed to load templates: {e}")
    
    def _save_templates_to_file(self):
        """Save templates to file"""
        try:
            template_data = {}
            for template_id, template in self.templates.items():
                template_data[template_id] = {
                    "name": template.name,
                    "description": template.description,
                    "nodes": [asdict(node) for node in template.nodes],
                    "connections": [asdict(conn) for conn in template.connections],
                    "scenario": template.scenario,
                    "tags": template.tags,
                    "created_at": template.created_at.isoformat()
                }
            
            with open(self.template_file, 'w') as f:
                json.dump(template_data, f, indent=2, default=str)
                
        except Exception as e:
            self.logger.error(f"Failed to save templates: {e}")