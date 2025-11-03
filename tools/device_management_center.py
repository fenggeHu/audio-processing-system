#!/usr/bin/env python3
"""
设备配置管理中心
Device Configuration Management Center

提供集中化的设备配置管理、批量部署和监控功能
"""

import os
import sys
import json
import time
import asyncio
import sqlite3
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
import argparse
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import subprocess
import socket
import hashlib

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class ManagedDevice:
    """被管理的设备"""
    device_id: str
    hostname: str
    ip_address: str
    device_type: str  # classroom_terminal/server/gateway
    location: str
    status: str  # online/offline/maintenance/error
    last_seen: str
    config_version: str
    hardware_profile: Dict[str, Any]
    current_config: Dict[str, Any]
    deployment_status: str  # deployed/pending/failed
    health_score: float  # 0-100
    alerts_count: int
    tags: List[str]

@dataclass
class DeploymentTask:
    """部署任务"""
    task_id: str
    device_ids: List[str]
    config_template: str
    deployment_type: str  # install/update/rollback
    status: str  # pending/running/completed/failed
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    progress: float  # 0-100
    results: Dict[str, Any]
    error_message: Optional[str]class
 DeviceManagementCenter:
    """设备配置管理中心"""
    
    def __init__(self, data_dir: str = "device_management"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 数据库文件
        self.db_path = self.data_dir / "devices.db"
        
        # 配置模板目录
        self.templates_dir = self.data_dir / "templates"
        self.templates_dir.mkdir(exist_ok=True)
        
        # 部署脚本目录
        self.scripts_dir = self.data_dir / "scripts"
        self.scripts_dir.mkdir(exist_ok=True)
        
        # 日志目录
        self.logs_dir = self.data_dir / "logs"
        self.logs_dir.mkdir(exist_ok=True)
        
        # 初始化数据库
        self._init_database()
        
        # 设备和任务缓存
        self.devices = {}
        self.deployment_tasks = {}
        
        # 监控线程
        self.monitoring_active = False
        self.monitoring_thread = None
    
    def _init_database(self):
        """初始化数据库"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 设备表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    hostname TEXT NOT NULL,
                    ip_address TEXT NOT NULL,
                    device_type TEXT NOT NULL,
                    location TEXT,
                    status TEXT DEFAULT 'unknown',
                    last_seen TEXT,
                    config_version TEXT,
                    hardware_profile TEXT,
                    current_config TEXT,
                    deployment_status TEXT DEFAULT 'pending',
                    health_score REAL DEFAULT 0.0,
                    alerts_count INTEGER DEFAULT 0,
                    tags TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 部署任务表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS deployment_tasks (
                    task_id TEXT PRIMARY KEY,
                    device_ids TEXT NOT NULL,
                    config_template TEXT NOT NULL,
                    deployment_type TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    started_at TEXT,
                    completed_at TEXT,
                    progress REAL DEFAULT 0.0,
                    results TEXT,
                    error_message TEXT
                )
            ''')
            
            # 配置历史表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS config_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    config_version TEXT NOT NULL,
                    config_data TEXT NOT NULL,
                    deployed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    deployed_by TEXT,
                    status TEXT DEFAULT 'active'
                )
            ''')
            
            # 设备日志表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS device_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    log_level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    category TEXT,
                    source TEXT
                )
            ''')
            
            conn.commit()
    
    def register_device(self, device_info: Dict[str, Any]) -> bool:
        """注册新设备"""
        try:
            device = ManagedDevice(
                device_id=device_info['device_id'],
                hostname=device_info['hostname'],
                ip_address=device_info['ip_address'],
                device_type=device_info.get('device_type', 'classroom_terminal'),
                location=device_info.get('location', ''),
                status='online',
                last_seen=datetime.now().isoformat(),
                config_version='',
                hardware_profile=device_info.get('hardware_profile', {}),
                current_config={},
                deployment_status='pending',
                health_score=100.0,
                alerts_count=0,
                tags=device_info.get('tags', [])
            )
            
            # 保存到数据库
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO devices 
                    (device_id, hostname, ip_address, device_type, location, 
                     status, last_seen, hardware_profile, tags)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    device.device_id, device.hostname, device.ip_address,
                    device.device_type, device.location, device.status,
                    device.last_seen, json.dumps(device.hardware_profile),
                    json.dumps(device.tags)
                ))
                conn.commit()
            
            self.devices[device.device_id] = device
            logger.info(f"设备已注册: {device.device_id} ({device.hostname})")
            return True
            
        except Exception as e:
            logger.error(f"设备注册失败: {e}")
            return False
    
    def update_device_status(self, device_id: str, status_data: Dict[str, Any]):
        """更新设备状态"""
        if device_id not in self.devices:
            logger.warning(f"未知设备: {device_id}")
            return
        
        device = self.devices[device_id]
        
        # 更新状态
        device.status = status_data.get('status', device.status)
        device.last_seen = datetime.now().isoformat()
        device.health_score = status_data.get('health_score', device.health_score)
        device.alerts_count = status_data.get('alerts_count', device.alerts_count)
        
        # 更新数据库
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE devices 
                SET status=?, last_seen=?, health_score=?, alerts_count=?, updated_at=?
                WHERE device_id=?
            ''', (
                device.status, device.last_seen, device.health_score,
                device.alerts_count, datetime.now().isoformat(), device_id
            ))
            conn.commit()
    
    def create_config_template(self, template_name: str, 
                             template_data: Dict[str, Any]) -> str:
        """创建配置模板"""
        template_file = self.templates_dir / f"{template_name}.json"
        
        # 添加模板元数据
        template_with_meta = {
            "template_name": template_name,
            "version": "1.0.0",
            "created_at": datetime.now().isoformat(),
            "description": template_data.get("description", ""),
            "target_device_types": template_data.get("target_device_types", ["classroom_terminal"]),
            "config": template_data
        }
        
        with open(template_file, 'w', encoding='utf-8') as f:
            json.dump(template_with_meta, f, indent=2, ensure_ascii=False)
        
        logger.info(f"配置模板已创建: {template_file}")
        return str(template_file)
    
    def get_config_templates(self) -> List[Dict[str, Any]]:
        """获取所有配置模板"""
        templates = []
        
        for template_file in self.templates_dir.glob("*.json"):
            try:
                with open(template_file, 'r', encoding='utf-8') as f:
                    template_data = json.load(f)
                    templates.append({
                        "file": template_file.name,
                        "name": template_data.get("template_name", template_file.stem),
                        "version": template_data.get("version", "unknown"),
                        "description": template_data.get("description", ""),
                        "target_types": template_data.get("target_device_types", [])
                    })
            except Exception as e:
                logger.warning(f"读取模板文件失败 {template_file}: {e}")
        
        return templates