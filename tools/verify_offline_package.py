#!/usr/bin/env python3
"""
离线包验证工具
Offline Package Verification Tool

用于验证离线部署包的完整性和依赖关系
"""

import os
import sys
import json
import hashlib
import tarfile
import tempfile
import shutil
from pathlib import Path
from typing import List
import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OfflinePackageVerifier:
    """离线包验证器"""
    
    def __init__(self):
        self.temp_dir = None
        self.package_dir = None
        
    def extract_package(self, package_path: str) -> str:
        """解压离线包"""
        logger.info(f"解压离线包: {package_path}")
        
        if not Path(package_path).exists():
            raise FileNotFoundError(f"包文件不存在: {package_path}")
        
        self.temp_dir = Path(tempfile.mkdtemp(prefix="verify_offline_"))
        
        with tarfile.open(package_path, "r:gz") as tar:
            tar.extractall(self.temp_dir)
        
        # 查找包目录
        extracted_dirs = [d for d in self.temp_dir.iterdir() if d.is_dir()]
        if not extracted_dirs:
            raise ValueError("包中未找到目录")
        
        self.package_dir = extracted_dirs[0]
        logger.info(f"包已解压到: {self.package_dir}")
        
        return str(self.package_dir)
    
    def verify_package_structure(self) -> bool:
        """验证包结构"""
        logger.info("验证包结构...")
        
        required_items = [
            "src",  # 源代码
            "config",  # 配置文件
            "requirements-offline.txt",  # 依赖列表
        ]
        
        optional_items = [
            "static",  # 静态文件
            "docs",  # 文档
            "scripts",  # 脚本
            "packages",  # Python包（多架构）
            "python_packages",  # Python包（单架构）
            "manifest.json",  # 清单文件
        ]
        
        missing_required = []
        for item in required_items:
            item_path = self.package_dir / item
            if not item_path.exists():
                missing_required.append(item)
            else:
                logger.info(f"✓ 找到必需项: {item}")
        
        if missing_required:
            logger.error(f"缺少必需项: {missing_required}")
            return False
        
        # 检查可选项
        for item in optional_items:
            item_path = self.package_dir / item
            if item_path.exists():
                logger.info(f"✓ 找到可选项: {item}")
        
        logger.info("包结构验证通过")
        return True
    
    def verify_python_packages(self) -> bool:
        """验证Python包"""
        logger.info("验证Python包...")
        
        # 查找包目录
        packages_dirs = []
        
        # 单架构包
        python_packages_dir = self.package_dir / "python_packages"
        if python_packages_dir.exists():
            for arch_dir in python_packages_dir.iterdir():
                if arch_dir.is_dir():
                    packages_dirs.append(arch_dir)
        
        # 多架构包
        packages_dir = self.package_dir / "packages"
        if packages_dir.exists():
            for arch_dir in packages_dir.iterdir():
                if arch_dir.is_dir():
                    packages_dirs.append(arch_dir)
        
        if not packages_dirs:
            logger.warning("未找到Python包目录")
            return True
        
        total_packages = 0
        total_size = 0
        
        for pkg_dir in packages_dirs:
            logger.info(f"检查目录: {pkg_dir}")
            
            # 统计包文件
            wheel_files = list(pkg_dir.glob("*.whl"))
            tar_files = list(pkg_dir.glob("*.tar.gz"))
            
            dir_packages = len(wheel_files) + len(tar_files)
            total_packages += dir_packages
            
            # 计算大小
            dir_size = sum(f.stat().st_size for f in wheel_files + tar_files)
            total_size += dir_size
            
            logger.info(f"  架构: {pkg_dir.name}")
            logger.info(f"  包数量: {dir_packages}")
            logger.info(f"  大小: {dir_size / 1024 / 1024:.1f} MB")
        
        logger.info(f"总计: {total_packages} 个包, {total_size / 1024 / 1024:.1f} MB")
        
        # 验证清单文件（如果存在）
        manifest_path = self.package_dir / "manifest.json"
        if manifest_path.exists():
            return self._verify_manifest(manifest_path, packages_dirs)
        
        return True
    
    def _verify_manifest(self, manifest_path: Path, packages_dirs: List[Path]) -> bool:
        """验证清单文件"""
        logger.info("验证清单文件...")
        
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
            
            logger.info(f"清单版本: {manifest.get('version', 'unknown')}")
            logger.info(f"创建时间: {manifest.get('created_at', 'unknown')}")
            logger.info(f"Python版本: {manifest.get('python_version', 'unknown')}")
            
            # 验证包校验和
            packages = manifest.get('packages', [])
            failed_packages = []
            
            for pkg_info in packages:
                pkg_name = pkg_info['name']
                expected_checksum = pkg_info['checksum']
                
                # 在所有架构目录中查找包文件
                found = False
                for pkg_dir in packages_dirs:
                    for ext in ['.whl', '.tar.gz']:
                        # 尝试不同的文件名格式
                        possible_names = [
                            f"{pkg_name}-{pkg_info['version']}{ext}",
                            f"{pkg_name}{ext}"
                        ]
                        
                        for name in possible_names:
                            pkg_file = pkg_dir / name
                            if pkg_file.exists():
                                with open(pkg_file, 'rb') as f:
                                    actual_checksum = hashlib.sha256(f.read()).hexdigest()
                                
                                if actual_checksum == expected_checksum:
                                    logger.debug(f"✓ {pkg_name}: 校验和正确")
                                    found = True
                                    break
                                else:
                                    logger.warning(f"✗ {pkg_name}: 校验和不匹配")
                                    failed_packages.append(pkg_name)
                                    found = True
                                    break
                        
                        if found:
                            break
                    if found:
                        break
                
                if not found:
                    logger.warning(f"✗ {pkg_name}: 文件未找到")
                    failed_packages.append(pkg_name)
            
            if failed_packages:
                logger.error(f"校验和验证失败的包: {failed_packages}")
                return False
            else:
                logger.info("所有包校验和验证通过")
                return True
                
        except Exception as e:
            logger.error(f"清单验证失败: {e}")
            return False
    
    def verify_dependencies(self) -> bool:
        """验证依赖关系"""
        logger.info("验证依赖关系...")
        
        requirements_file = self.package_dir / "requirements-offline.txt"
        if not requirements_file.exists():
            logger.warning("未找到requirements-offline.txt文件")
            return True
        
        # 读取依赖列表
        with open(requirements_file) as f:
            requirements = [line.strip() for line in f 
                          if line.strip() and not line.startswith('#')]
        
        logger.info(f"需要验证 {len(requirements)} 个依赖")
        
        # 查找Python包目录
        packages_dirs = []
        python_packages_dir = self.package_dir / "python_packages"
        if python_packages_dir.exists():
            packages_dirs.extend([d for d in python_packages_dir.iterdir() if d.is_dir()])
        
        packages_dir = self.package_dir / "packages"
        if packages_dir.exists():
            packages_dirs.extend([d for d in packages_dir.iterdir() if d.is_dir()])
        
        if not packages_dirs:
            logger.warning("未找到Python包目录，跳过依赖验证")
            return True
        
        # 收集所有可用的包
        available_packages = set()
        for pkg_dir in packages_dirs:
            for pkg_file in pkg_dir.glob("*.whl"):
                # 解析wheel文件名: name-version-python-abi-platform.whl
                name_parts = pkg_file.stem.split('-')
                if len(name_parts) >= 2:
                    pkg_name = name_parts[0].lower().replace('_', '-')
                    available_packages.add(pkg_name)
            
            for pkg_file in pkg_dir.glob("*.tar.gz"):
                # 解析tar.gz文件名: name-version.tar.gz
                name_part = pkg_file.stem.replace('.tar', '')
                if '-' in name_part:
                    pkg_name = name_part.rsplit('-', 1)[0].lower().replace('_', '-')
                    available_packages.add(pkg_name)
        
        logger.info(f"找到 {len(available_packages)} 个可用包")
        
        # 检查依赖是否满足
        missing_deps = []
        for req in requirements:
            # 解析依赖名称（去掉版本约束）
            dep_name = req.split('>=')[0].split('==')[0].split('~=')[0].split('<')[0].split('>')[0].strip()
            dep_name = dep_name.lower().replace('_', '-')
            
            if dep_name not in available_packages:
                missing_deps.append(req)
            else:
                logger.debug(f"✓ 找到依赖: {dep_name}")
        
        if missing_deps:
            logger.error(f"缺少依赖: {missing_deps}")
            return False
        else:
            logger.info("所有依赖验证通过")
            return True
    
    def verify_source_code(self) -> bool:
        """验证源代码"""
        logger.info("验证源代码...")
        
        src_dir = self.package_dir / "src"
        if not src_dir.exists():
            logger.error("未找到src目录")
            return False
        
        # 检查主模块
        main_module = src_dir / "audio_processing"
        if not main_module.exists():
            logger.error("未找到主模块 audio_processing")
            return False
        
        # 检查关键文件
        key_files = [
            "__init__.py",
            "models.py",
            "interfaces.py",
            "base.py",
            "service_manager.py"
        ]
        
        missing_files = []
        for file_name in key_files:
            file_path = main_module / file_name
            if not file_path.exists():
                missing_files.append(file_name)
            else:
                logger.debug(f"✓ 找到文件: {file_name}")
        
        if missing_files:
            logger.warning(f"缺少源文件: {missing_files}")
        
        # 检查服务目录
        services_dir = main_module / "services"
        if services_dir.exists():
            service_files = list(services_dir.glob("*.py"))
            logger.info(f"找到 {len(service_files)} 个服务文件")
        
        logger.info("源代码验证完成")
        return True
    
    def verify_configuration(self) -> bool:
        """验证配置文件"""
        logger.info("验证配置文件...")
        
        config_dir = self.package_dir / "config"
        if not config_dir.exists():
            logger.warning("未找到config目录")
            return True
        
        # 检查配置文件
        config_files = list(config_dir.glob("*.json"))
        if config_files:
            logger.info(f"找到 {len(config_files)} 个配置文件")
            
            # 验证JSON格式
            for config_file in config_files:
                try:
                    with open(config_file) as f:
                        json.load(f)
                    logger.debug(f"✓ 配置文件格式正确: {config_file.name}")
                except json.JSONDecodeError as e:
                    logger.error(f"✗ 配置文件格式错误 {config_file.name}: {e}")
                    return False
        
        logger.info("配置文件验证通过")
        return True
    
    def verify_install_scripts(self) -> bool:
        """验证安装脚本"""
        logger.info("验证安装脚本...")
        
        # 查找安装脚本
        install_scripts = []
        
        # 根目录的安装脚本
        for script_name in ["install_offline.sh", "install_multi_arch.sh"]:
            script_path = self.package_dir / script_name
            if script_path.exists():
                install_scripts.append(script_path)
        
        # scripts目录中的脚本
        scripts_dir = self.package_dir / "scripts"
        if scripts_dir.exists():
            for script_file in scripts_dir.glob("*.sh"):
                install_scripts.append(script_file)
        
        if not install_scripts:
            logger.warning("未找到安装脚本")
            return True
        
        logger.info(f"找到 {len(install_scripts)} 个安装脚本")
        
        # 检查脚本权限
        for script in install_scripts:
            if not os.access(script, os.X_OK):
                logger.warning(f"脚本没有执行权限: {script.name}")
            else:
                logger.debug(f"✓ 脚本权限正确: {script.name}")
        
        logger.info("安装脚本验证完成")
        return True
    
    def run_full_verification(self, package_path: str) -> bool:
        """运行完整验证"""
        logger.info("开始完整验证...")
        
        try:
            # 解压包
            self.extract_package(package_path)
            
            # 运行各项验证
            verifications = [
                ("包结构", self.verify_package_structure),
                ("Python包", self.verify_python_packages),
                ("依赖关系", self.verify_dependencies),
                ("源代码", self.verify_source_code),
                ("配置文件", self.verify_configuration),
                ("安装脚本", self.verify_install_scripts)
            ]
            
            results = {}
            for name, verify_func in verifications:
                try:
                    result = verify_func()
                    results[name] = result
                    if result:
                        logger.info(f"✓ {name}验证通过")
                    else:
                        logger.error(f"✗ {name}验证失败")
                except Exception as e:
                    logger.error(f"✗ {name}验证异常: {e}")
                    results[name] = False
            
            # 汇总结果
            passed = sum(1 for r in results.values() if r)
            total = len(results)
            
            logger.info(f"\n验证结果: {passed}/{total} 项通过")
            
            for name, result in results.items():
                status = "✓" if result else "✗"
                logger.info(f"  {status} {name}")
            
            return all(results.values())
            
        finally:
            # 清理临时目录
            if self.temp_dir and self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)

def main():
    parser = argparse.ArgumentParser(description="离线包验证工具")
    parser.add_argument("package", help="离线包文件路径")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    verifier = OfflinePackageVerifier()
    
    try:
        success = verifier.run_full_verification(args.package)
        
        if success:
            print(f"\n✓ 离线包验证通过: {args.package}")
            print("该包可以安全部署到目标设备")
            sys.exit(0)
        else:
            print(f"\n✗ 离线包验证失败: {args.package}")
            print("请检查包的完整性或重新构建")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"验证过程中发生错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()