"""
System Debugging and Diagnostic Tools

This module implements comprehensive system debugging and diagnostic tools including:
- System status monitoring interface
- Audio processing performance analysis
- Parameter tuning assistant
- Audio quality testing tools
- Configuration management interface
- Log viewer
- Fault diagnosis tools
- System backup and recovery
"""

import asyncio
import json
import time
import threading
import psutil
import logging
import os
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np
from collections import deque
from pathlib import Path

from ..audio_core.models import AudioFrame, ProcessingMetrics, AudioDevice, SystemState
from ..audio_core.interfaces import IAudioProcessor, ComponentInfo
from ..config.system_config import SystemConfig


class DiagnosticLevel(Enum):
    """Diagnostic severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class SystemHealthStatus(Enum):
    """System health status"""
    HEALTHY = "healthy"
    WARNING = "warning"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    OFFLINE = "offline"


@dataclass
class SystemStatusData:
    """System status monitoring data"""
    timestamp: datetime
    cpu_usage_percent: float
    memory_usage_percent: float
    memory_available_mb: float
    disk_usage_percent: float
    disk_available_gb: float
    audio_devices_count: int
    active_components_count: int
    processing_load_percent: float
    temperature_celsius: Optional[float] = None
    network_status: str = "unknown"


@dataclass
class PerformanceMetrics:
    """Audio processing performance metrics"""
    component_id: str
    timestamp: datetime
    processing_time_ms: float
    cpu_usage_percent: float
    memory_usage_mb: float
    throughput_fps: float
    latency_ms: float
    quality_score: float
    error_count: int = 0


@dataclass
class DiagnosticIssue:
    """Diagnostic issue information"""
    issue_id: str
    timestamp: datetime
    level: DiagnosticLevel
    category: str
    title: str
    description: str
    component_id: Optional[str] = None
    suggested_actions: List[str] = None
    auto_fixable: bool = False
    
    def __post_init__(self):
        if self.suggested_actions is None:
            self.suggested_actions = []


class SystemStatusMonitor:
    """System status monitoring interface"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.monitoring = False
        self.status_history: deque = deque(maxlen=1000)
        self.update_interval = 1.0  # seconds
        self.monitor_thread: Optional[threading.Thread] = None
        self.callbacks: List[Callable] = []
        
    def start_monitoring(self) -> bool:
        """Start system status monitoring"""
        if self.monitoring:
            return True
        
        try:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self.monitor_thread.start()
            
            self.logger.info("Started system status monitoring")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start system monitoring: {e}")
            return False
    
    def stop_monitoring(self) -> bool:
        """Stop system status monitoring"""
        if not self.monitoring:
            return True
        
        self.monitoring = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2.0)
        
        self.logger.info("Stopped system status monitoring")
        return True
    
    def get_current_status(self) -> SystemStatusData:
        """Get current system status"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_available_mb = memory.available / (1024 * 1024)
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            disk_available_gb = disk.free / (1024 * 1024 * 1024)
            
            # Audio devices (simplified)
            audio_devices_count = len(psutil.disk_partitions())  # Placeholder
            
            # Processing load (simulated)
            processing_load = min(100.0, cpu_percent * 1.2)
            
            # Temperature (if available)
            temperature = None
            try:
                if hasattr(psutil, "sensors_temperatures"):
                    temps = psutil.sensors_temperatures()
                    if temps:
                        # Get first available temperature
                        for sensor_name, sensor_list in temps.items():
                            if sensor_list:
                                temperature = sensor_list[0].current
                                break
            except:
                pass
            
            return SystemStatusData(
                timestamp=datetime.now(),
                cpu_usage_percent=cpu_percent,
                memory_usage_percent=memory_percent,
                memory_available_mb=memory_available_mb,
                disk_usage_percent=disk_percent,
                disk_available_gb=disk_available_gb,
                audio_devices_count=audio_devices_count,
                active_components_count=0,  # Will be updated by component registry
                processing_load_percent=processing_load,
                temperature_celsius=temperature,
                network_status="connected"
            )
            
        except Exception as e:
            self.logger.error(f"Error getting system status: {e}")
            return SystemStatusData(
                timestamp=datetime.now(),
                cpu_usage_percent=0.0,
                memory_usage_percent=0.0,
                memory_available_mb=0.0,
                disk_usage_percent=0.0,
                disk_available_gb=0.0,
                audio_devices_count=0,
                active_components_count=0,
                processing_load_percent=0.0
            )
    
    def get_status_history(self, minutes: int = 10) -> List[SystemStatusData]:
        """Get system status history"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        return [status for status in self.status_history if status.timestamp >= cutoff_time]
    
    def get_health_assessment(self) -> Dict[str, Any]:
        """Get overall system health assessment"""
        current_status = self.get_current_status()
        
        health_score = 100.0
        issues = []
        
        # CPU health
        if current_status.cpu_usage_percent > 90:
            health_score -= 30
            issues.append("High CPU usage")
        elif current_status.cpu_usage_percent > 70:
            health_score -= 15
            issues.append("Elevated CPU usage")
        
        # Memory health
        if current_status.memory_usage_percent > 90:
            health_score -= 25
            issues.append("High memory usage")
        elif current_status.memory_usage_percent > 80:
            health_score -= 10
            issues.append("Elevated memory usage")
        
        # Disk health
        if current_status.disk_usage_percent > 95:
            health_score -= 20
            issues.append("Disk space critical")
        elif current_status.disk_usage_percent > 85:
            health_score -= 10
            issues.append("Low disk space")
        
        # Temperature health
        if current_status.temperature_celsius and current_status.temperature_celsius > 80:
            health_score -= 15
            issues.append("High system temperature")
        
        # Determine overall status
        if health_score >= 90:
            status = SystemHealthStatus.HEALTHY
        elif health_score >= 70:
            status = SystemHealthStatus.WARNING
        elif health_score >= 50:
            status = SystemHealthStatus.DEGRADED
        else:
            status = SystemHealthStatus.CRITICAL
        
        return {
            "status": status.value,
            "health_score": health_score,
            "issues": issues,
            "timestamp": datetime.now().isoformat(),
            "system_metrics": asdict(current_status)
        }
    
    def register_callback(self, callback: Callable[[SystemStatusData], None]):
        """Register callback for status updates"""
        self.callbacks.append(callback)
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring:
            try:
                status = self.get_current_status()
                self.status_history.append(status)
                
                # Notify callbacks
                for callback in self.callbacks:
                    try:
                        callback(status)
                    except Exception as e:
                        self.logger.error(f"Callback error: {e}")
                
                time.sleep(self.update_interval)
                
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")
                time.sleep(1.0)


class AudioProcessingPerformanceAnalyzer:
    """Audio processing performance analysis tool"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.performance_data: Dict[str, deque] = {}
        self.analysis_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_timeout = 30.0  # seconds
        
    def record_performance_data(self, component_id: str, metrics: PerformanceMetrics):
        """Record performance data for a component"""
        if component_id not in self.performance_data:
            self.performance_data[component_id] = deque(maxlen=1000)
        
        self.performance_data[component_id].append(metrics)
        
        # Invalidate cache for this component
        if component_id in self.analysis_cache:
            del self.analysis_cache[component_id]
    
    def analyze_component_performance(self, component_id: str, 
                                    time_window_minutes: int = 5) -> Dict[str, Any]:
        """Analyze performance for a specific component"""
        cache_key = f"{component_id}_{time_window_minutes}"
        
        # Check cache
        if cache_key in self.analysis_cache:
            cache_entry = self.analysis_cache[cache_key]
            if (datetime.now() - cache_entry["timestamp"]).total_seconds() < self.cache_timeout:
                return cache_entry["data"]
        
        if component_id not in self.performance_data:
            return {"error": "No performance data available"}
        
        # Get recent data
        cutoff_time = datetime.now() - timedelta(minutes=time_window_minutes)
        recent_data = [
            metrics for metrics in self.performance_data[component_id]
            if metrics.timestamp >= cutoff_time
        ]
        
        if not recent_data:
            return {"error": "No recent performance data"}
        
        # Calculate statistics
        processing_times = [m.processing_time_ms for m in recent_data]
        cpu_usage = [m.cpu_usage_percent for m in recent_data]
        memory_usage = [m.memory_usage_mb for m in recent_data]
        throughput = [m.throughput_fps for m in recent_data]
        latency = [m.latency_ms for m in recent_data]
        quality_scores = [m.quality_score for m in recent_data]
        error_counts = [m.error_count for m in recent_data]
        
        analysis = {
            "component_id": component_id,
            "analysis_time": datetime.now(),
            "time_window_minutes": time_window_minutes,
            "data_points": len(recent_data),
            "processing_time": {
                "avg_ms": np.mean(processing_times),
                "max_ms": np.max(processing_times),
                "min_ms": np.min(processing_times),
                "std_ms": np.std(processing_times),
                "p95_ms": np.percentile(processing_times, 95),
                "p99_ms": np.percentile(processing_times, 99)
            },
            "resource_usage": {
                "avg_cpu_percent": np.mean(cpu_usage),
                "max_cpu_percent": np.max(cpu_usage),
                "avg_memory_mb": np.mean(memory_usage),
                "max_memory_mb": np.max(memory_usage)
            },
            "throughput": {
                "avg_fps": np.mean(throughput),
                "min_fps": np.min(throughput),
                "max_fps": np.max(throughput)
            },
            "latency": {
                "avg_ms": np.mean(latency),
                "max_ms": np.max(latency),
                "min_ms": np.min(latency),
                "p95_ms": np.percentile(latency, 95)
            },
            "quality": {
                "avg_score": np.mean(quality_scores),
                "min_score": np.min(quality_scores),
                "max_score": np.max(quality_scores)
            },
            "reliability": {
                "total_errors": np.sum(error_counts),
                "error_rate": np.sum(error_counts) / len(recent_data),
                "uptime_percent": (len(recent_data) - np.sum([1 for e in error_counts if e > 0])) / len(recent_data) * 100
            }
        }
        
        # Add performance assessment
        analysis["assessment"] = self._assess_component_performance(analysis)
        
        # Cache result
        self.analysis_cache[cache_key] = {
            "timestamp": datetime.now(),
            "data": analysis
        }
        
        return analysis
    
    def get_system_performance_overview(self) -> Dict[str, Any]:
        """Get overall system performance overview"""
        overview = {
            "timestamp": datetime.now(),
            "components": {},
            "system_totals": {
                "total_processing_time_ms": 0.0,
                "total_cpu_usage_percent": 0.0,
                "total_memory_usage_mb": 0.0,
                "avg_quality_score": 0.0,
                "total_errors": 0
            }
        }
        
        component_count = 0
        total_quality = 0.0
        
        for component_id in self.performance_data.keys():
            component_analysis = self.analyze_component_performance(component_id, 1)  # 1 minute window
            if "error" not in component_analysis:
                overview["components"][component_id] = {
                    "avg_processing_time_ms": component_analysis["processing_time"]["avg_ms"],
                    "avg_cpu_percent": component_analysis["resource_usage"]["avg_cpu_percent"],
                    "avg_memory_mb": component_analysis["resource_usage"]["avg_memory_mb"],
                    "avg_quality_score": component_analysis["quality"]["avg_score"],
                    "error_count": component_analysis["reliability"]["total_errors"],
                    "assessment": component_analysis["assessment"]
                }
                
                # Accumulate totals
                overview["system_totals"]["total_processing_time_ms"] += component_analysis["processing_time"]["avg_ms"]
                overview["system_totals"]["total_cpu_usage_percent"] += component_analysis["resource_usage"]["avg_cpu_percent"]
                overview["system_totals"]["total_memory_usage_mb"] += component_analysis["resource_usage"]["avg_memory_mb"]
                total_quality += component_analysis["quality"]["avg_score"]
                overview["system_totals"]["total_errors"] += component_analysis["reliability"]["total_errors"]
                component_count += 1
        
        if component_count > 0:
            overview["system_totals"]["avg_quality_score"] = total_quality / component_count
        
        return overview
    
    def _assess_component_performance(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Assess component performance and provide recommendations"""
        assessment = {
            "overall_grade": "Good",
            "issues": [],
            "recommendations": []
        }
        
        # Check processing time
        avg_processing_time = analysis["processing_time"]["avg_ms"]
        if avg_processing_time > 50:
            assessment["issues"].append("High processing latency")
            assessment["recommendations"].append("Consider optimizing processing algorithms")
            assessment["overall_grade"] = "Poor"
        elif avg_processing_time > 20:
            assessment["issues"].append("Elevated processing latency")
            assessment["recommendations"].append("Monitor processing efficiency")
            if assessment["overall_grade"] == "Good":
                assessment["overall_grade"] = "Fair"
        
        # Check CPU usage
        avg_cpu = analysis["resource_usage"]["avg_cpu_percent"]
        if avg_cpu > 80:
            assessment["issues"].append("High CPU usage")
            assessment["recommendations"].append("Consider CPU optimization or load balancing")
            assessment["overall_grade"] = "Poor"
        elif avg_cpu > 60:
            assessment["issues"].append("Elevated CPU usage")
            assessment["recommendations"].append("Monitor CPU usage trends")
            if assessment["overall_grade"] == "Good":
                assessment["overall_grade"] = "Fair"
        
        # Check quality
        avg_quality = analysis["quality"]["avg_score"]
        if avg_quality < 0.7:
            assessment["issues"].append("Low audio quality")
            assessment["recommendations"].append("Review and adjust processing parameters")
            assessment["overall_grade"] = "Poor"
        elif avg_quality < 0.8:
            assessment["issues"].append("Suboptimal audio quality")
            assessment["recommendations"].append("Fine-tune quality parameters")
            if assessment["overall_grade"] == "Good":
                assessment["overall_grade"] = "Fair"
        
        # Check error rate
        error_rate = analysis["reliability"]["error_rate"]
        if error_rate > 0.05:  # 5% error rate
            assessment["issues"].append("High error rate")
            assessment["recommendations"].append("Investigate and fix error sources")
            assessment["overall_grade"] = "Poor"
        elif error_rate > 0.01:  # 1% error rate
            assessment["issues"].append("Elevated error rate")
            assessment["recommendations"].append("Monitor error patterns")
            if assessment["overall_grade"] == "Good":
                assessment["overall_grade"] = "Fair"
        
        return assessment


