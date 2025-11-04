#!/usr/bin/env python3
"""
离线包构建验证报告生成器
生成详细的测试报告和包分析
"""

import json
import tarfile
import hashlib
import subprocess
import sys
from pathlib import Path
from datetime import datetime
import tempfile
import shutil

def get_system_info():
    """获取系统信息"""
    try:
        import platform
        return {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation()
        }
    except Exception as e:
        return {"error": str(e)}

def get_pip_info():
    """获取pip信息"""
    try:
        result = subprocess.run([sys.executable, "-m", "pip", "--version"], 
                              capture_output=True, text=True)
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e}"

def analyze_package(package_path):
    """分析离线包内容"""
    analysis = {
        "path": str(package_path),
        "exists": package_path.exists(),
        "size_mb": 0,
        "checksum": "",
        "contents": [],
        "python_packages": [],
        "scripts": [],
        "config_files": [],
        "manifest": {}
    }
    
    if not package_path.exists():
        return analysis
    
    # 计算大小和校验和
    stat = package_path.stat()
    analysis["size_mb"] = round(stat.st_size / 1024 / 1024, 2)
    
    with open(package_path, "rb") as f:
        analysis["checksum"] = hashlib.sha256(f.read()).hexdigest()
    
    # 分析包内容
    try:
        with tarfile.open(package_path, "r:gz") as tar:
            members = tar.getnames()
            analysis["contents"] = members[:20]  # 只显示前20个文件
            
            # 分类文件
            for member in members:
                if member.endswith(('.whl', '.tar.gz')) and 'python_packages' in member:
                    analysis["python_packages"].append(Path(member).name)
                elif member.endswith('.sh') and 'scripts' in member:
                    analysis["scripts"].append(Path(member).name)
                elif member.endswith(('.json', '.yaml', '.yml', '.toml')) and 'config' in member:
                    analysis["config_files"].append(Path(member).name)
            
            # 读取清单文件
            try:
                manifest_member = None
                for member in members:
                    if member.endswith('manifest.json'):
                        manifest_member = member
                        break
                
                if manifest_member:
                    manifest_file = tar.extractfile(manifest_member)
                    if manifest_file:
                        analysis["manifest"] = json.loads(manifest_file.read().decode())
            except Exception as e:
                analysis["manifest"] = {"error": str(e)}
                
    except Exception as e:
        analysis["error"] = str(e)
    
    return analysis

def test_package_extraction(package_path):
    """测试包解压和基本验证"""
    test_results = {
        "extraction_success": False,
        "scripts_executable": False,
        "manifest_valid": False,
        "python_packages_count": 0,
        "key_files_present": []
    }
    
    if not package_path.exists():
        return test_results
    
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # 解压包
            with tarfile.open(package_path, "r:gz") as tar:
                tar.extractall(temp_dir)
            test_results["extraction_success"] = True
            
            # 查找解压后的目录
            extracted_dirs = [d for d in Path(temp_dir).iterdir() if d.is_dir()]
            if not extracted_dirs:
                return test_results
            
            extracted_dir = extracted_dirs[0]
            
            # 检查关键文件
            key_files = [
                "scripts/install_offline.sh",
                "scripts/install_system_deps.sh",
                "manifest.json",
                "requirements.txt"
            ]
            
            for key_file in key_files:
                file_path = extracted_dir / key_file
                if file_path.exists():
                    test_results["key_files_present"].append(key_file)
                    
                    # 检查脚本是否可执行
                    if key_file.endswith('.sh') and file_path.stat().st_mode & 0o111:
                        test_results["scripts_executable"] = True
            
            # 验证清单文件
            manifest_path = extracted_dir / "manifest.json"
            if manifest_path.exists():
                try:
                    with open(manifest_path) as f:
                        json.load(f)
                    test_results["manifest_valid"] = True
                except:
                    pass
            
            # 统计Python包数量
            python_packages_dir = extracted_dir / "python_packages"
            if python_packages_dir.exists():
                whl_files = list(python_packages_dir.rglob("*.whl"))
                test_results["python_packages_count"] = len(whl_files)
                
        except Exception as e:
            test_results["error"] = str(e)
    
    return test_results

def run_build_test():
    """运行构建测试"""
    print("运行构建测试...")
    
    test_output_dir = Path("dist/test-report")
    test_output_dir.mkdir(parents=True, exist_ok=True)
    
    # 测试单架构构建
    single_arch_result = subprocess.run([
        sys.executable, "tools/offline_packager.py",
        "--output", str(test_output_dir / "single"),
        "--verbose"
    ], capture_output=True, text=True)
    
    # 测试多架构构建
    multi_arch_result = subprocess.run([
        sys.executable, "tools/build_multi_arch.py",
        "--output", str(test_output_dir / "multi"),
        "--verbose"
    ], capture_output=True, text=True)
    
    return {
        "single_arch": {
            "success": single_arch_result.returncode == 0,
            "stdout": single_arch_result.stdout,
            "stderr": single_arch_result.stderr
        },
        "multi_arch": {
            "success": multi_arch_result.returncode == 0,
            "stdout": multi_arch_result.stdout,
            "stderr": multi_arch_result.stderr
        }
    }

def generate_report():
    """生成完整的验证报告"""
    print("生成离线包构建验证报告...")
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "system_info": get_system_info(),
        "pip_info": get_pip_info(),
        "build_tests": {},
        "package_analysis": {},
        "extraction_tests": {},
        "summary": {}
    }
    
    # 运行构建测试
    report["build_tests"] = run_build_test()
    
    # 分析生成的包
    test_output_dir = Path("dist/test-report")
    
    # 查找生成的包文件
    single_packages = list((test_output_dir / "single").glob("*.tar.gz"))
    multi_packages = list((test_output_dir / "multi").glob("*.tar.gz"))
    
    # 分析单架构包
    if single_packages:
        package_path = single_packages[0]
        report["package_analysis"]["single_arch"] = analyze_package(package_path)
        report["extraction_tests"]["single_arch"] = test_package_extraction(package_path)
    
    # 分析多架构包
    if multi_packages:
        package_path = multi_packages[0]
        report["package_analysis"]["multi_arch"] = analyze_package(package_path)
        report["extraction_tests"]["multi_arch"] = test_package_extraction(package_path)
    
    # 生成摘要
    summary = {
        "single_arch_build_success": report["build_tests"]["single_arch"]["success"],
        "multi_arch_build_success": report["build_tests"]["multi_arch"]["success"],
        "packages_generated": len(single_packages) + len(multi_packages),
        "total_size_mb": 0,
        "all_tests_passed": True
    }
    
    # 计算总大小
    for analysis in report["package_analysis"].values():
        if "size_mb" in analysis:
            summary["total_size_mb"] += analysis["size_mb"]
    
    # 检查是否所有测试都通过
    for test_result in report["extraction_tests"].values():
        if not test_result.get("extraction_success", False):
            summary["all_tests_passed"] = False
            break
    
    report["summary"] = summary
    
    # 保存报告
    report_file = Path("test_report.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"报告已保存到: {report_file}")
    
    # 打印摘要
    print("\n" + "="*50)
    print("验证报告摘要")
    print("="*50)
    print(f"时间: {report['timestamp']}")
    print(f"系统: {report['system_info'].get('system', 'Unknown')} {report['system_info'].get('machine', '')}")
    print(f"Python: {report['system_info'].get('python_version', 'Unknown')}")
    print(f"单架构构建: {'✓' if summary['single_arch_build_success'] else '✗'}")
    print(f"多架构构建: {'✓' if summary['multi_arch_build_success'] else '✗'}")
    print(f"生成包数量: {summary['packages_generated']}")
    print(f"总包大小: {summary['total_size_mb']:.1f} MB")
    print(f"所有测试: {'✓ 通过' if summary['all_tests_passed'] else '✗ 失败'}")
    
    # 显示包详情
    for pkg_type, analysis in report["package_analysis"].items():
        if "size_mb" in analysis:
            print(f"\n{pkg_type.replace('_', ' ').title()}包:")
            print(f"  大小: {analysis['size_mb']} MB")
            print(f"  Python包数量: {len(analysis.get('python_packages', []))}")
            print(f"  脚本数量: {len(analysis.get('scripts', []))}")
    
    # 清理测试文件
    if test_output_dir.exists():
        shutil.rmtree(test_output_dir)
    
    return summary["all_tests_passed"]

if __name__ == "__main__":
    success = generate_report()
    sys.exit(0 if success else 1)