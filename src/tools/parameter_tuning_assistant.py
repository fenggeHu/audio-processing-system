"""
Parameter Tuning Assistant

This module provides intelligent parameter adjustment suggestions and effect prediction
for audio processing components.
"""

import json
import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

from ..audio_core.interfaces import IAudioProcessor, ComponentInfo
from ..audio_core.models import AudioFrame, ProcessingMetrics


class TuningStrategy(Enum):
    """Parameter tuning strategies"""
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    CUSTOM = "custom"


@dataclass
class ParameterSuggestion:
    """Parameter adjustment suggestion"""
    parameter_name: str
    current_value: Any
    suggested_value: Any
    confidence: float
    expected_improvement: str
    reasoning: str
    risk_level: str = "low"


@dataclass
class TuningSession:
    """Parameter tuning session data"""
    session_id: str
    component_id: str
    start_time: datetime
    strategy: TuningStrategy
    baseline_metrics: Dict[str, float]
    suggestions: List[ParameterSuggestion]
    applied_changes: List[Dict[str, Any]]
    results: Dict[str, Any]


class ParameterTuningAssistant:
    """Intelligent parameter tuning assistant"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.tuning_sessions: Dict[str, TuningSession] = {}
        self.parameter_history: Dict[str, List[Dict[str, Any]]] = {}
        self.optimization_rules = self._load_optimization_rules()
        
    def analyze_component_parameters(self, component_id: str, 
                                   component: IAudioProcessor,
                                   recent_metrics: List[ProcessingMetrics]) -> Dict[str, Any]:
        """Analyze component parameters and suggest improvements"""
        if not recent_metrics:
            return {"error": "No metrics available for analysis"}
        
        current_params = component.get_parameters()
        component_info = component.get_info()
        
        # Calculate baseline metrics
        baseline_metrics = self._calculate_baseline_metrics(recent_metrics)
        
        # Generate suggestions
        suggestions = self._generate_parameter_suggestions(
            component_id, component_info, current_params, baseline_metrics
        )
        
        analysis = {
            "component_id": component_id,
            "analysis_time": datetime.now(),
            "current_parameters": current_params,
            "baseline_metrics": baseline_metrics,
            "suggestions": [asdict(s) for s in suggestions],
            "optimization_potential": self._assess_optimization_potential(baseline_metrics),
            "recommended_strategy": self._recommend_tuning_strategy(baseline_metrics)
        }
        
        return analysis
    
    def start_tuning_session(self, component_id: str, 
                           component: IAudioProcessor,
                           strategy: TuningStrategy = TuningStrategy.BALANCED) -> str:
        """Start a parameter tuning session"""
        session_id = f"tuning_{component_id}_{int(datetime.now().timestamp())}"
        
        # Get baseline metrics
        current_params = component.get_parameters()
        baseline_metrics = self._get_current_performance_metrics(component_id)
        
        # Generate initial suggestions
        suggestions = self._generate_parameter_suggestions(
            component_id, component.get_info(), current_params, baseline_metrics
        )
        
        session = TuningSession(
            session_id=session_id,
            component_id=component_id,
            start_time=datetime.now(),
            strategy=strategy,
            baseline_metrics=baseline_metrics,
            suggestions=suggestions,
            applied_changes=[],
            results={}
        )
        
        self.tuning_sessions[session_id] = session
        self.logger.info(f"Started tuning session {session_id} for component {component_id}")
        
        return session_id
    
    def apply_suggestion(self, session_id: str, suggestion_index: int,
                        component: IAudioProcessor) -> bool:
        """Apply a parameter suggestion"""
        if session_id not in self.tuning_sessions:
            return False
        
        session = self.tuning_sessions[session_id]
        if suggestion_index >= len(session.suggestions):
            return False
        
        suggestion = session.suggestions[suggestion_index]
        
        try:
            # Apply the parameter change
            success = component.set_parameter(
                suggestion.parameter_name, 
                suggestion.suggested_value
            )
            
            if success:
                # Record the change
                change_record = {
                    "timestamp": datetime.now(),
                    "parameter_name": suggestion.parameter_name,
                    "old_value": suggestion.current_value,
                    "new_value": suggestion.suggested_value,
                    "suggestion_index": suggestion_index
                }
                session.applied_changes.append(change_record)
                
                self.logger.info(f"Applied parameter change: {suggestion.parameter_name} = {suggestion.suggested_value}")
                return True
            
        except Exception as e:
            self.logger.error(f"Failed to apply parameter suggestion: {e}")
        
        return False
    
    def evaluate_tuning_results(self, session_id: str, 
                              new_metrics: List[ProcessingMetrics]) -> Dict[str, Any]:
        """Evaluate the results of parameter tuning"""
        if session_id not in self.tuning_sessions:
            return {"error": "Session not found"}
        
        session = self.tuning_sessions[session_id]
        
        # Calculate new performance metrics
        new_baseline = self._calculate_baseline_metrics(new_metrics)
        
        # Compare with baseline
        improvements = {}
        for metric_name, baseline_value in session.baseline_metrics.items():
            if metric_name in new_baseline:
                new_value = new_baseline[metric_name]
                if baseline_value != 0:
                    improvement_percent = ((new_value - baseline_value) / baseline_value) * 100
                    improvements[metric_name] = {
                        "baseline": baseline_value,
                        "current": new_value,
                        "improvement_percent": improvement_percent,
                        "improved": improvement_percent > 0
                    }
        
        # Overall assessment
        overall_improvement = np.mean([
            imp["improvement_percent"] for imp in improvements.values()
            if imp["improvement_percent"] is not None
        ])
        
        results = {
            "session_id": session_id,
            "evaluation_time": datetime.now(),
            "applied_changes_count": len(session.applied_changes),
            "metric_improvements": improvements,
            "overall_improvement_percent": overall_improvement,
            "success": overall_improvement > 5.0,  # 5% improvement threshold
            "recommendations": self._generate_next_recommendations(session, improvements)
        }
        
        session.results = results
        return results
    
    def get_tuning_history(self, component_id: str) -> List[Dict[str, Any]]:
        """Get parameter tuning history for a component"""
        history = []
        for session in self.tuning_sessions.values():
            if session.component_id == component_id:
                history.append({
                    "session_id": session.session_id,
                    "start_time": session.start_time,
                    "strategy": session.strategy.value,
                    "changes_count": len(session.applied_changes),
                    "results": session.results
                })
        
        return sorted(history, key=lambda x: x["start_time"], reverse=True)
    
    def predict_parameter_effect(self, component_id: str, 
                               parameter_name: str, 
                               new_value: Any) -> Dict[str, Any]:
        """Predict the effect of changing a parameter"""
        # This is a simplified prediction model
        # In a real implementation, this would use ML models or historical data
        
        prediction = {
            "parameter_name": parameter_name,
            "new_value": new_value,
            "predicted_effects": {},
            "confidence": 0.7,
            "risk_assessment": "medium"
        }
        
        # Simple rule-based predictions
        if "gain" in parameter_name.lower():
            if isinstance(new_value, (int, float)):
                if new_value > 1.0:
                    prediction["predicted_effects"]["output_level"] = "increase"
                    prediction["predicted_effects"]["distortion_risk"] = "higher"
                elif new_value < 1.0:
                    prediction["predicted_effects"]["output_level"] = "decrease"
                    prediction["predicted_effects"]["noise_floor"] = "more_visible"
        
        elif "threshold" in parameter_name.lower():
            prediction["predicted_effects"]["processing_sensitivity"] = "modified"
            prediction["predicted_effects"]["cpu_usage"] = "may_change"
        
        elif "frequency" in parameter_name.lower() or "freq" in parameter_name.lower():
            prediction["predicted_effects"]["frequency_response"] = "modified"
            prediction["predicted_effects"]["audio_character"] = "changed"
        
        return prediction
    
    def _calculate_baseline_metrics(self, metrics: List[ProcessingMetrics]) -> Dict[str, float]:
        """Calculate baseline performance metrics"""
        if not metrics:
            return {}
        
        processing_times = [m.processing_time_ms for m in metrics]
        cpu_usage = [m.cpu_usage_percent for m in metrics]
        memory_usage = [m.memory_usage_mb for m in metrics]
        latencies = [m.latency_ms for m in metrics]
        
        return {
            "avg_processing_time_ms": np.mean(processing_times),
            "avg_cpu_usage_percent": np.mean(cpu_usage),
            "avg_memory_usage_mb": np.mean(memory_usage),
            "avg_latency_ms": np.mean(latencies),
            "processing_stability": 1.0 / (np.std(processing_times) + 1e-6)
        }
    
    def _generate_parameter_suggestions(self, component_id: str,
                                      component_info: ComponentInfo,
                                      current_params: Dict[str, Any],
                                      baseline_metrics: Dict[str, float]) -> List[ParameterSuggestion]:
        """Generate parameter adjustment suggestions"""
        suggestions = []
        
        # Check if processing time is high
        if baseline_metrics.get("avg_processing_time_ms", 0) > 20:
            # Suggest reducing quality parameters if available
            for param_name, param_value in current_params.items():
                if "quality" in param_name.lower() and isinstance(param_value, (int, float)):
                    if param_value > 0.5:
                        suggestions.append(ParameterSuggestion(
                            parameter_name=param_name,
                            current_value=param_value,
                            suggested_value=max(0.3, param_value * 0.8),
                            confidence=0.8,
                            expected_improvement="Reduced processing time",
                            reasoning="High processing latency detected, reducing quality parameter may help",
                            risk_level="low"
                        ))
        
        # Check if CPU usage is high
        if baseline_metrics.get("avg_cpu_usage_percent", 0) > 70:
            # Suggest reducing computational complexity
            for param_name, param_value in current_params.items():
                if "size" in param_name.lower() or "length" in param_name.lower():
                    if isinstance(param_value, int) and param_value > 512:
                        suggestions.append(ParameterSuggestion(
                            parameter_name=param_name,
                            current_value=param_value,
                            suggested_value=max(256, int(param_value * 0.75)),
                            confidence=0.7,
                            expected_improvement="Reduced CPU usage",
                            reasoning="High CPU usage detected, reducing buffer/window size may help",
                            risk_level="medium"
                        ))
        
        # Suggest enabling optimizations if available
        for param_name, param_value in current_params.items():
            if "optimization" in param_name.lower() or "fast" in param_name.lower():
                if isinstance(param_value, bool) and not param_value:
                    suggestions.append(ParameterSuggestion(
                        parameter_name=param_name,
                        current_value=param_value,
                        suggested_value=True,
                        confidence=0.9,
                        expected_improvement="Better performance",
                        reasoning="Optimization feature available but not enabled",
                        risk_level="low"
                    ))
        
        return suggestions
    
    def _assess_optimization_potential(self, baseline_metrics: Dict[str, float]) -> str:
        """Assess the optimization potential based on current metrics"""
        issues = 0
        
        if baseline_metrics.get("avg_processing_time_ms", 0) > 30:
            issues += 1
        if baseline_metrics.get("avg_cpu_usage_percent", 0) > 80:
            issues += 1
        if baseline_metrics.get("avg_latency_ms", 0) > 50:
            issues += 1
        
        if issues >= 2:
            return "high"
        elif issues == 1:
            return "medium"
        else:
            return "low"
    
    def _recommend_tuning_strategy(self, baseline_metrics: Dict[str, float]) -> TuningStrategy:
        """Recommend a tuning strategy based on current performance"""
        if baseline_metrics.get("avg_processing_time_ms", 0) > 50:
            return TuningStrategy.AGGRESSIVE
        elif baseline_metrics.get("avg_cpu_usage_percent", 0) > 60:
            return TuningStrategy.BALANCED
        else:
            return TuningStrategy.CONSERVATIVE
    
    def _get_current_performance_metrics(self, component_id: str) -> Dict[str, float]:
        """Get current performance metrics for a component"""
        # This would integrate with the performance monitoring system
        # For now, return simulated metrics
        return {
            "avg_processing_time_ms": 15.0 + np.random.random() * 10,
            "avg_cpu_usage_percent": 45.0 + np.random.random() * 20,
            "avg_memory_usage_mb": 50.0 + np.random.random() * 30,
            "avg_latency_ms": 12.0 + np.random.random() * 8,
            "processing_stability": 0.8 + np.random.random() * 0.2
        }
    
    def _generate_next_recommendations(self, session: TuningSession, 
                                     improvements: Dict[str, Any]) -> List[str]:
        """Generate recommendations for next steps"""
        recommendations = []
        
        overall_improvement = np.mean([
            imp["improvement_percent"] for imp in improvements.values()
            if imp["improvement_percent"] is not None
        ])
        
        if overall_improvement > 10:
            recommendations.append("Excellent results! Consider saving this configuration as a preset.")
        elif overall_improvement > 5:
            recommendations.append("Good improvement achieved. Monitor stability over time.")
        elif overall_improvement > 0:
            recommendations.append("Modest improvement. Consider trying additional adjustments.")
        else:
            recommendations.append("No significant improvement. Consider reverting changes.")
            recommendations.append("Try a different tuning strategy or consult documentation.")
        
        return recommendations
    
    def _load_optimization_rules(self) -> Dict[str, Any]:
        """Load optimization rules and patterns"""
        # This would load from a configuration file or database
        return {
            "performance_thresholds": {
                "processing_time_ms": 20.0,
                "cpu_usage_percent": 70.0,
                "memory_usage_mb": 100.0,
                "latency_ms": 30.0
            },
            "parameter_patterns": {
                "gain_parameters": ["gain", "level", "amplitude"],
                "quality_parameters": ["quality", "resolution", "precision"],
                "size_parameters": ["size", "length", "window", "buffer"],
                "optimization_parameters": ["fast", "optimization", "efficient"]
            }
        }