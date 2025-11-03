#!/usr/bin/env python3
"""
部署验证脚本
Deployment Validation Script
"""

import requests
import subprocess
import sys
import time
import json
from pathlib import Path

class DeploymentValidator:
    def __init__(self):
        self.base_url = "http://localhost"
        self.api_url = f"{self.base_url}:8000"
        self.checks_passed = 0
        self.checks_total = 0
        
    def run_check(self, name, check_func):
        """运行单个检查"""
        self.checks_total += 1
        print(f"检查 {self.checks_total}: {name}...", end=" ")
        
        try:
            result = check_func()
            if result:
                print("✓ 通过")
                self.checks_passed += 1
                return True
            else:
                print("✗ 失败")
                return False
        except Exception as e:
            print(f"✗ 异常: {e}")
            return False
    
    def check_web_interface(self):
        """检查Web界面"""
        try:
            response = requests.get(self.base_url, timeout=10)
            return response.status_code == 200
        except:
            return False
    
    def check_api_health(self):
        """检查API健康状态"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def check_api_docs(self):
        """检查API文档"""
        try:
            response = requests.get(f"{self.base_url}/docs", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def check_system_services(self):
        """检查系统服务状态"""
        services = ["audio-processing", "audio-processing-web", "nginx"]
        
        for service in services:
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", service],
                    capture_output=True,
                    text=True
                )
                if result.stdout.strip() != "active":
                    return False
            except:
                return False
        return True
    
    def check_docker_services(self):
        """检查Docker服务状态"""
        try:
            result = subprocess.run(
                ["docker-compose", "-f", "deploy/docker-compose.yml", "ps"],
                capture_output=True,
                text=True
            )
            return "Up" in result.stdout
        except:
            return False
    
    def check_audio_devices(self):
        """检查音频设备"""
        try:
            result = subprocess.run(
                ["arecord", "-l"],
                capture_output=True,
                text=True
            )
            return "card" in result.stdout.lower()
        except:
            return False
    
    def check_config_files(self):
        """检查配置文件"""
        config_files = [
            "/opt/audio-processing-system/config/production.json",
            "deploy/config/production.json"
        ]
        
        for config_file in config_files:
            if Path(config_file).exists():
                try:
                    with open(config_file, 'r') as f:
                        json.load(f)
                    return True
                except:
                    continue
        return False
    
    def check_log_files(self):
        """检查日志文件"""
        log_paths = [
            "/opt/audio-processing-system/logs",
            "/var/log/nginx"
        ]
        
        for log_path in log_paths:
            if Path(log_path).exists():
                return True
        return False
    
    def check_storage_permissions(self):
        """检查存储权限"""
        storage_paths = [
            "/opt/audio-processing-system/recordings",
            "/opt/audio-processing-system/logs"
        ]
        
        for storage_path in storage_paths:
            path = Path(storage_path)
            if path.exists():
                try:
                    # 尝试创建测试文件
                    test_file = path / "test_write.tmp"
                    test_file.write_text("test")
                    test_file.unlink()
                    return True
                except:
                    continue
        return False
    
    def check_network_ports(self):
        """检查网络端口"""
        try:
            result = subprocess.run(
                ["netstat", "-tlnp"],
                capture_output=True,
                text=True
            )
            
            required_ports = [":80", ":8000"]
            for port in required_ports:
                if port not in result.stdout:
                    return False
            return True
        except:
            return False
    
    def validate_deployment(self):
        """执行完整的部署验证"""
        print("=" * 50)
        print("音频处理系统部署验证")
        print("Audio Processing System Deployment Validation")
        print("=" * 50)
        
        # 基础检查
        print("\n基础服务检查:")
        self.run_check("Web界面访问", self.check_web_interface)
        self.run_check("API健康检查", self.check_api_health)
        self.run_check("API文档访问", self.check_api_docs)
        
        # 服务状态检查
        print("\n服务状态检查:")
        if Path("/etc/systemd/system/audio-processing.service").exists():
            self.run_check("系统服务状态", self.check_system_services)
        else:
            self.run_check("Docker服务状态", self.check_docker_services)
        
        # 系统资源检查
        print("\n系统资源检查:")
        self.run_check("音频设备检测", self.check_audio_devices)
        self.run_check("配置文件验证", self.check_config_files)
        self.run_check("日志文件检查", self.check_log_files)
        self.run_check("存储权限检查", self.check_storage_permissions)
        self.run_check("网络端口检查", self.check_network_ports)
        
        # 输出结果
        print("\n" + "=" * 50)
        print(f"验证结果: {self.checks_passed}/{self.checks_total} 项检查通过")
        
        if self.checks_passed == self.checks_total:
            print("🎉 部署验证成功！系统已准备就绪。")
            print(f"Web界面: {self.base_url}")
            print(f"API文档: {self.base_url}/docs")
            return True
        else:
            print("⚠️  部署验证发现问题，请检查失败的项目。")
            return False

def main():
    validator = DeploymentValidator()
    success = validator.validate_deployment()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()