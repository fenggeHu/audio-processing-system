"""
Fault Diagnosis Tool

This module provides automated fault detection and diagnosis capabilities including:
- Common problem detection
- Solution suggestions
- System health checks
- Automated fixes for known issues
- Diagnostic reports
"""

import logging
import psutil
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum

from ..visualization.system_diagnostics import SystemStatusMonitor, DiagnosticLevel, DiagnosticIssue


class FaultCategory(Enum):
    """Categories of system faults"""
    PERFORMANCE = "performance"
    RESOURCE = "resource"
    AUDIO = "audio"
    CONFIGURATION = "configuration"
    HARDWARE = "hardware"
    NETWORK = "network"


class FaultSeverity(Enum):
    """Fault severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class DiagnosticRule:
    """Diagnostic rule definition"""
    rule_id: str
    name: str
    description: str
    category: FaultCategory
    severity: FaultSeverity
    check_function: Callable[[], bool]
    suggested_actions: List[str]
    auto_fix_function: Optional[Callable[[], bool]] = None


@dataclass
class DiagnosticReport:
    """Comprehensive diagnostic report"""
    report_id: str
    timestamp: datetime
    system_status: Dict[str, Any]
    detected_issues: List[DiagnosticIssue]
    resolved_issues: List[DiagnosticIssue]
    recommendations: List[str]
    overall_health_score: float


class FaultDiagnosisTool:
    """Automated fault detection and diagnosis tool"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.system_monitor = SystemStatusMonitor()
        self.diagnostic_rules: List[DiagnosticRule] = []
        self.diagnostic_history: List[DiagnosticReport] = []
        
        # Initialize diagnostic rules
        self._initialize_diagnostic_rules()
        
    def run_comprehensive_diagnosis(self, auto_fix: bool = False) -> DiagnosticReport:
        """Run comprehensive system diagnosis"""
        report_id = f"diagnosis_{int(datetime.now().timestamp())}"
        
        # Get current system status
        system_status = self.system_monitor.get_health_assessment()
        
        # Run all diagnostic rules
        detected_issues = []
        resolved_issues = []
        
        for rule in self.diagnostic_rules:
            try:
                if rule.check_function():
                    issue = DiagnosticIssue(
                        issue_id=f"{rule.rule_id}_{int(time.time())}",
                        timestamp=datetime.now(),
                        level=self._severity_to_diagnostic_level(rule.severity),
                        category=rule.category.value,
                        title=rule.name,
                        description=rule.description,
                        suggested_actions=rule.suggested_actions,
                        auto_fixable=rule.auto_fix_function is not None
                    )
                    
                    detected_issues.append(issue)
                    
                    # Attempt auto-fix if enabled and available
                    if auto_fix and rule.auto_fix_function:
                        try:
                            if rule.auto_fix_function():
                                resolved_issues.append(issue)
                                self.logger.info(f"Auto-fixed issue: {rule.name}")
                        except Exception as e:
                            self.logger.error(f"Auto-fix failed for {rule.name}: {e}")
                            
            except Exception as e:
                self.logger.error(f"Error running diagnostic rule {rule.rule_id}: {e}")
        
        # Generate recommendations
        recommendations = self._generate_recommendations(detected_issues, system_status)
        
        # Calculate overall health score
        health_score = self._calculate_health_score(detected_issues, system_status)
        
        # Create report
        report = DiagnosticReport(
            report_id=report_id,
            timestamp=datetime.now(),
            system_status=system_status,
            detected_issues=detected_issues,
            resolved_issues=resolved_issues,
            recommendations=recommendations,
            overall_health_score=health_score
        )
        
        self.diagnostic_history.append(report)
        return report
    
    def check_specific_issue(self, category: FaultCategory) -> List[DiagnosticIssue]:
        """Check for issues in a specific category"""
        issues = []
        
        for rule in self.diagnostic_rules:
            if rule.category == category:
                try:
                    if rule.check_function():
                        issue = DiagnosticIssue(
                            issue_id=f"{rule.rule_id}_{int(time.time())}",
                            timestamp=datetime.now(),
                            level=self._severity_to_diagnostic_level(rule.severity),
                            category=rule.category.value,
                            title=rule.name,
                            description=rule.description,
                            suggested_actions=rule.suggested_actions,
                            auto_fixable=rule.auto_fix_function is not None
                        )
                        issues.append(issue)
                        
                except Exception as e:
                    self.logger.error(f"Error checking rule {rule.rule_id}: {e}")
        
        return issues
    
    def get_diagnostic_history(self, days: int = 7) -> List[DiagnosticReport]:
        """Get diagnostic history for the specified number of days"""
        cutoff_date = datetime.now() - timedelta(days=days)
        return [report for report in self.diagnostic_history if report.timestamp >= cutoff_date]
    
    def _initialize_diagnostic_rules(self):
        """Initialize built-in diagnostic rules"""
        
        # High CPU usage rule
        self.diagnostic_rules.append(DiagnosticRule(
            rule_id="high_cpu_usage",
            name="High CPU Usage",
            description="System CPU usage is consistently high",
            category=FaultCategory.PERFORMANCE,
            severity=FaultSeverity.HIGH,
            check_function=self._check_high_cpu_usage,
            suggested_actions=[
                "Check for runaway processes",
                "Reduce audio processing quality settings",
                "Close unnecessary applications",
                "Consider upgrading hardware"
            ]
        ))
        
        # High memory usage rule
        self.diagnostic_rules.append(DiagnosticRule(
            rule_id="high_memory_usage",
            name="High Memory Usage",
            description="System memory usage is critically high",
            category=FaultCategory.RESOURCE,
            severity=FaultSeverity.HIGH,
            check_function=self._check_high_memory_usage,
            suggested_actions=[
                "Close unnecessary applications",
                "Reduce buffer sizes",
                "Check for memory leaks",
                "Add more RAM"
            ]
        ))
        
        # Low disk space rule
        self.diagnostic_rules.append(DiagnosticRule(
            rule_id="low_disk_space",
            name="Low Disk Space",
            description="Available disk space is running low",
            category=FaultCategory.RESOURCE,
            severity=FaultSeverity.MEDIUM,
            check_function=self._check_low_disk_space,
            suggested_actions=[
                "Clean up temporary files",
                "Archive old recordings",
                "Delete unnecessary files",
                "Add more storage"
            ],
            auto_fix_function=self._auto_fix_disk_space
        ))
        
        # Audio device issues rule
        self.diagnostic_rules.append(DiagnosticRule(
            rule_id="audio_device_issues",
            name="Audio Device Issues",
            description="Audio devices are not responding properly",
            category=FaultCategory.AUDIO,
            severity=FaultSeverity.CRITICAL,
            check_function=self._check_audio_device_issues,
            suggested_actions=[
                "Check audio device connections",
                "Restart audio services",
                "Update audio drivers",
                "Check device permissions"
            ]
        ))
        
        # High system temperature rule
        self.diagnostic_rules.append(DiagnosticRule(
            rule_id="high_temperature",
            name="High System Temperature",
            description="System temperature is above safe operating levels",
            category=FaultCategory.HARDWARE,
            severity=FaultSeverity.HIGH,
            check_function=self._check_high_temperature,
            suggested_actions=[
                "Check cooling system",
                "Clean dust from fans",
                "Reduce processing load",
                "Improve ventilation"
            ]
        ))
        
        # Configuration issues rule
        self.diagnostic_rules.append(DiagnosticRule(
            rule_id="config_issues",
            name="Configuration Issues",
            description="System configuration has potential issues",
            category=FaultCategory.CONFIGURATION,
            severity=FaultSeverity.MEDIUM,
            check_function=self._check_config_issues,
            suggested_actions=[
                "Validate configuration files",
                "Reset to default settings",
                "Check parameter ranges",
                "Restore from backup"
            ]
        ))
    
    def _check_high_cpu_usage(self) -> bool:
        """Check for high CPU usage"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            return cpu_percent > 85.0
        except:
            return False
    
    def _check_high_memory_usage(self) -> bool:
        """Check for high memory usage"""
        try:
            memory = psutil.virtual_memory()
            return memory.percent > 90.0
        except:
            return False
    
    def _check_low_disk_space(self) -> bool:
        """Check for low disk space"""
        try:
            disk = psutil.disk_usage('/')
            usage_percent = (disk.used / disk.total) * 100
            return usage_percent > 90.0
        except:
            return False
    
    def _check_audio_device_issues(self) -> bool:
        """Check for audio device issues"""
        # This is a simplified check - in a real implementation,
        # this would check actual audio device status
        try:
            # Simulate audio device check
            import random
            return random.random() < 0.1  # 10% chance of audio issues
        except:
            return False
    
    def _check_high_temperature(self) -> bool:
        """Check for high system temperature"""
        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if temps:
                    for sensor_name, sensor_list in temps.items():
                        for sensor in sensor_list:
                            if sensor.current and sensor.current > 80.0:
                                return True
            return False
        except:
            return False
    
    def _check_config_issues(self) -> bool:
        """Check for configuration issues"""
        # This is a simplified check - in a real implementation,
        # this would validate actual configuration files
        try:
            # Simulate configuration validation
            import random
            return random.random() < 0.05  # 5% chance of config issues
        except:
            return False
    
    def _auto_fix_disk_space(self) -> bool:
        """Auto-fix disk space issues by cleaning temporary files"""
        try:
            import tempfile
            import shutil
            
            # Clean temporary directory
            temp_dir = tempfile.gettempdir()
            for item in os.listdir(temp_dir):
                item_path = os.path.join(temp_dir, item)
                try:
                    if os.path.isfile(item_path):
                        # Only delete files older than 1 day
                        if time.time() - os.path.getmtime(item_path) > 86400:
                            os.remove(item_path)
                    elif os.path.isdir(item_path):
                        # Only delete empty directories
                        if not os.listdir(item_path):
                            os.rmdir(item_path)
                except:
                    continue
            
            self.logger.info("Cleaned temporary files to free disk space")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to auto-fix disk space: {e}")
            return False
    
    def _generate_recommendations(self, issues: List[DiagnosticIssue], 
                                system_status: Dict[str, Any]) -> List[str]:
        """Generate system recommendations based on detected issues"""
        recommendations = []
        
        # Performance recommendations
        performance_issues = [i for i in issues if i.category == FaultCategory.PERFORMANCE.value]
        if performance_issues:
            recommendations.append("Consider optimizing audio processing parameters")
            recommendations.append("Monitor system performance regularly")
        
        # Resource recommendations
        resource_issues = [i for i in issues if i.category == FaultCategory.RESOURCE.value]
        if resource_issues:
            recommendations.append("Review system resource allocation")
            recommendations.append("Consider hardware upgrades if issues persist")
        
        # Audio recommendations
        audio_issues = [i for i in issues if i.category == FaultCategory.AUDIO.value]
        if audio_issues:
            recommendations.append("Verify audio device configurations")
            recommendations.append("Test audio devices with external tools")
        
        # General recommendations
        if len(issues) > 5:
            recommendations.append("System has multiple issues - consider comprehensive maintenance")
        
        if system_status.get("health_score", 100) < 70:
            recommendations.append("System health is below optimal - schedule maintenance")
        
        return recommendations
    
    def _calculate_health_score(self, issues: List[DiagnosticIssue], 
                              system_status: Dict[str, Any]) -> float:
        """Calculate overall system health score"""
        base_score = system_status.get("health_score", 100.0)
        
        # Deduct points for each issue based on severity
        severity_penalties = {
            DiagnosticLevel.CRITICAL: 20.0,
            DiagnosticLevel.ERROR: 15.0,
            DiagnosticLevel.WARNING: 10.0,
            DiagnosticLevel.INFO: 5.0
        }
        
        for issue in issues:
            penalty = severity_penalties.get(issue.level, 5.0)
            base_score -= penalty
        
        return max(0.0, min(100.0, base_score))
    
    def _severity_to_diagnostic_level(self, severity: FaultSeverity) -> DiagnosticLevel:
        """Convert fault severity to diagnostic level"""
        mapping = {
            FaultSeverity.LOW: DiagnosticLevel.INFO,
            FaultSeverity.MEDIUM: DiagnosticLevel.WARNING,
            FaultSeverity.HIGH: DiagnosticLevel.ERROR,
            FaultSeverity.CRITICAL: DiagnosticLevel.CRITICAL
        }
        return mapping.get(severity, DiagnosticLevel.INFO)
