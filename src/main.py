"""
Main Entry Point for Production Audio Processing System

Command-line interface and application startup.
"""

import sys
import asyncio
import signal
from pathlib import Path
from typing import Optional
import click

# Import configuration and logging
from .config.logging_config import audio_logger, log_system
from .config.embedded_config import embedded_config
from .config.platform_config import platform_config

# Import integrated audio system
from .audio_core.integrated_audio_system import IntegratedProductionAudioSystem


class AudioSystemApp:
    """Main application class for the audio processing system."""
    
    def __init__(self):
        self.running = False
        self.shutdown_event = asyncio.Event()
        
        # Initialize configurations
        self._setup_configurations()
        
        # Setup signal handlers
        self._setup_signal_handlers()
        
        # Initialize integrated audio system
        self.audio_system: Optional[IntegratedProductionAudioSystem] = None
    
    def _setup_configurations(self) -> None:
        """Setup system configurations."""
        log_system("Initializing system configurations")
        
        # Apply embedded optimizations
        embedded_config.apply_runtime_optimizations()
        
        # Apply platform optimizations
        platform_config.apply_platform_optimizations()
        
        log_system("System configurations initialized", 
                  platform=platform_config.platform,
                  memory_mode=embedded_config.config.memory_mode.value,
                  cpu_arch=embedded_config.config.cpu_architecture.value)
    
    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            log_system(f"Received signal {signum}, initiating shutdown")
            self.shutdown()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def start(self) -> None:
        """Start the audio processing system."""
        log_system("Starting Production Audio Processing System")
        
        try:
            self.running = True
            
            # Initialize integrated audio system
            self.audio_system = IntegratedProductionAudioSystem("main_system")
            
            # Create system configuration
            system_config = {
                "sample_rate": 48000,
                "channels": 2,
                "bit_depth": 24,
                "buffer_size": 256,
                "auto_detect_devices": True,
                "enable_all_devices": True,
                "enable_quality_monitoring": True,
                "enable_hot_plug": True,
                "capture_service": {
                    "device_manager": {
                        "scan_interval": 5.0,
                        "enable_hot_plug": True
                    }
                },
                "recovery": {
                    "enable_auto_recovery": True,
                    "max_retry_attempts": 3,
                    "retry_delay_seconds": 2.0
                },
                "dashboard": {
                    "max_history_points": 10000,
                    "input_monitor": {
                        "waveform_buffer_size": 2048,
                        "spectrum_buffer_size": 1024
                    }
                }
            }
            
            # Initialize system
            if not await self.audio_system.initialize_system(system_config):
                raise Exception("Failed to initialize audio system")
            
            log_system("Audio system initialized successfully")
            
            # Start system
            if not await self.audio_system.start_system():
                raise Exception("Failed to start audio system")
            
            log_system("Audio system started successfully")
            
            # Register system callbacks
            self.audio_system.register_state_change_callback(self._on_system_state_change)
            self.audio_system.register_health_change_callback(self._on_system_health_change)
            
            # Wait for shutdown signal
            await self.shutdown_event.wait()
            
        except Exception as e:
            log_system("Error starting audio system", error=str(e))
            raise
        finally:
            await self.cleanup()
    
    def shutdown(self) -> None:
        """Initiate system shutdown."""
        if self.running:
            log_system("Shutting down audio processing system")
            self.running = False
            self.shutdown_event.set()
    
    async def cleanup(self) -> None:
        """Cleanup system resources."""
        log_system("Cleaning up system resources")
        
        # Stop integrated audio system
        if self.audio_system:
            await self.audio_system.stop_system()
            log_system("Audio system stopped")
        
        # Shutdown logging
        audio_logger.shutdown()
        
        log_system("System cleanup completed")
    
    def _on_system_state_change(self, new_state):
        """Handle system state changes"""
        log_system(f"System state changed to: {new_state.value}")
    
    def _on_system_health_change(self, health_status):
        """Handle system health changes"""
        log_system(f"System health: {health_status.overall_health}", 
                  active_components=health_status.active_components,
                  total_components=health_status.total_components,
                  performance_score=health_status.performance_score)


@click.group()
@click.version_option(version="1.0.0")
@click.option("--config", "-c", type=click.Path(exists=True), help="Configuration file path")
@click.option("--log-level", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]), 
              default="INFO", help="Logging level")
@click.option("--embedded", is_flag=True, help="Enable embedded system optimizations")
def cli(config: Optional[str], log_level: str, embedded: bool):
    """Production Audio Processing System CLI."""
    # Configure logging level
    import logging
    logging.getLogger().setLevel(getattr(logging, log_level))
    
    # Enable embedded optimizations if requested
    if embedded:
        embedded_config.config.enable_realtime = True
        embedded_config.config.enable_power_saving = True


@cli.command()
@click.option("--daemon", "-d", is_flag=True, help="Run as daemon")
@click.option("--port", "-p", type=int, default=8080, help="Web interface port")
def start(daemon: bool, port: int):
    """Start the audio processing system."""
    if daemon:
        # TODO: Implement daemon mode
        click.echo("Daemon mode not yet implemented")
        return
    
    # Create and start application
    app = AudioSystemApp()
    
    try:
        asyncio.run(app.start())
    except KeyboardInterrupt:
        click.echo("Interrupted by user")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
def stop():
    """Stop the audio processing system."""
    # For now, just indicate that the system should be stopped via signal
    click.echo("Send SIGTERM or SIGINT to stop the running system")


@cli.command()
def status():
    """Show system status."""
    # This would connect to a running system to get status
    # For now, just show configuration info
    click.echo("System Status:")
    click.echo(f"  Platform: {platform_config.platform}")
    click.echo(f"  Audio Backend: {platform_config.config.primary_backend.value}")
    click.echo(f"  CPU Architecture: {embedded_config.config.cpu_architecture.value}")
    click.echo(f"  Memory Mode: {embedded_config.config.memory_mode.value}")
    click.echo(f"  Real-time Enabled: {embedded_config.config.enable_realtime}")
    click.echo("  Status: Use 'start' command to run the system")


@cli.command()
@click.option("--output", "-o", type=click.Path(), help="Output file for benchmark results")
@click.option("--quick", is_flag=True, help="Run quick benchmark")
def benchmark(output: Optional[str], quick: bool):
    """Run performance benchmarks."""
    from .tools.benchmark import AudioBenchmarkSuite
    
    suite = AudioBenchmarkSuite()
    
    try:
        if quick:
            suite.benchmark_numpy_operations()
            suite.benchmark_memory_operations()
        else:
            suite.run_all_benchmarks()
        
        suite.print_summary()
        
        if output:
            suite.generate_report(Path(output))
            click.echo(f"Benchmark report saved to: {output}")
            
    except Exception as e:
        click.echo(f"Benchmark failed: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--target", help="Cross-compilation target")
@click.option("--list-targets", is_flag=True, help="List available targets")
def cross_compile(target: Optional[str], list_targets: bool):
    """Setup cross-compilation for embedded targets."""
    import subprocess
    
    cmd = [sys.executable, "setup_cross_compile.py"]
    
    if list_targets:
        cmd.append("--list-targets")
    elif target:
        cmd.extend(["--target", target])
    else:
        click.echo("Please specify --target or --list-targets")
        return
    
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        click.echo(f"Cross-compilation setup failed: {e}", err=True)
        sys.exit(1)


@cli.command()
def config_info():
    """Show current system configuration."""
    click.echo("System Configuration:")
    click.echo(f"  Platform: {platform_config.platform}")
    click.echo(f"  Audio Backend: {platform_config.config.primary_backend.value}")
    click.echo(f"  CPU Architecture: {embedded_config.config.cpu_architecture.value}")
    click.echo(f"  Memory Mode: {embedded_config.config.memory_mode.value}")
    click.echo(f"  Real-time Enabled: {embedded_config.config.enable_realtime}")
    click.echo(f"  Thread Count: {embedded_config.config.thread_count}")


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()