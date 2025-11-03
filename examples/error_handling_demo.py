"""
Demonstration of the error handling and fault tolerance system.

This example shows how to integrate and use the comprehensive
error handling, fault tolerance, and recovery mechanisms.
"""

import asyncio
import time
from typing import Dict, Any

from src.audio_processing.error_recovery_integration import create_error_recovery_system
from src.audio_processing.classroom_failsafe import FailsafeConfig
from src.audio_processing.retry_mechanism import RetryConfig, RetryStrategy
from src.audio_processing.models import AudioConfig
from src.audio_processing.exceptions import ServiceError, ProcessingError, DeviceError


class MockService:
    """Mock service for demonstration purposes."""
    
    def __init__(self, name: str, failure_rate: float = 0.0):
        self.name = name
        self.failure_rate = failure_rate
        self.is_running = True
        self.call_count = 0
    
    async def process(self, data: Any) -> Any:
        """Simulate processing with potential failures."""
        self.call_count += 1
        
        # Simulate failure based on failure rate
        import random
        if random.random() < self.failure_rate:
            if self.call_count % 3 == 0:
                raise DeviceError("Simulated device failure", self.name)
            elif self.call_count % 2 == 0:
                raise ServiceError("Simulated service error", self.name)
            else:
                raise ProcessingError("Simulated processing error", self.name)
        
        # Simulate processing delay
        await asyncio.sleep(0.1)
        return f"Processed by {self.name}: {data}"
    
    async def start(self) -> None:
        """Start the service."""
        self.is_running = True
    
    async def stop(self) -> None:
        """Stop the service."""
        self.is_running = False


class MockServiceManager:
    """Mock service manager for demonstration."""
    
    def __init__(self):
        self.services: Dict[str, MockService] = {}
        self.event_handlers: Dict[str, list] = {}
    
    def add_service(self, name: str, service: MockService) -> None:
        """Add a service to the manager."""
        self.services[name] = service
    
    async def restart_service(self, service_name: str) -> None:
        """Restart a service."""
        if service_name in self.services:
            service = self.services[service_name]
            await service.stop()
            await asyncio.sleep(0.5)  # Simulate restart delay
            await service.start()
            print(f"Service {service_name} restarted")
        else:
            raise ServiceError(f"Service {service_name} not found")
    
    def get_service_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all services."""
        return {
            name: {
                "running": service.is_running,
                "healthy": service.is_running,
                "call_count": service.call_count
            }
            for name, service in self.services.items()
        }
    
    def subscribe_to_events(self, event_type: str, handler) -> None:
        """Subscribe to events."""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)


async def demonstrate_error_handling():
    """Demonstrate the error handling and recovery system."""
    print("=== Audio Processing Error Handling Demo ===\n")
    
    # Create audio configuration
    audio_config = AudioConfig(
        sample_rate=48000,
        frame_size=1024,
        channels=2
    )
    
    # Create failsafe configuration
    failsafe_config = FailsafeConfig(
        emergency_volume_reduction_db=12.0,
        max_feedback_threshold_dbfs=-3.0,
        auto_recovery_enabled=True,
        degradation_timeout_s=60.0
    )
    
    # Create error recovery system
    print("1. Creating error recovery system...")
    recovery_system = create_error_recovery_system(audio_config, failsafe_config)
    
    # Create mock service manager and services
    service_manager = MockServiceManager()
    
    # Create mock services with different failure rates
    services = {
        "CaptureService": MockService("CaptureService", failure_rate=0.1),
        "AECService": MockService("AECService", failure_rate=0.2),
        "BeamformerService": MockService("BeamformerService", failure_rate=0.15),
        "SSLService": MockService("SSLService", failure_rate=0.1),
        "AGCService": MockService("AGCService", failure_rate=0.05)
    }
    
    for name, service in services.items():
        service_manager.add_service(name, service)
    
    # Initialize recovery system
    print("2. Initializing error recovery system...")
    await recovery_system.initialize(service_manager)
    
    # Register services with custom retry configurations
    print("3. Registering services...")
    
    # AEC service with aggressive retry
    aec_retry_config = RetryConfig(
        max_attempts=5,
        base_delay=0.1,
        strategy=RetryStrategy.EXPONENTIAL_BACKOFF
    )
    recovery_system.register_service("AECService", services["AECService"], aec_retry_config)
    
    # Other services with default configs
    for name, service in services.items():
        if name != "AECService":
            recovery_system.register_service(name, service)
    
    # Start monitoring
    print("4. Starting monitoring...")
    for service_name in services.keys():
        await recovery_system.start_monitoring(service_name)
    
    print("\n=== Running Simulation ===\n")
    
    # Simulate processing with errors
    print("5. Simulating audio processing with errors...")
    
    for i in range(20):
        print(f"\nProcessing cycle {i + 1}:")
        
        # Try to process data through each service
        for service_name, service in services.items():
            try:
                result = await recovery_system.handle_error(
                    ProcessingError("Simulated processing issue"),
                    service_name,
                    {"cycle": i + 1, "timestamp": time.time()}
                )
                
                if result:
                    print(f"  ✓ {service_name}: Error handled successfully")
                else:
                    print(f"  ✗ {service_name}: Error handling failed")
                    
            except Exception as e:
                print(f"  ✗ {service_name}: Unhandled error - {e}")
        
        # Simulate some processing delay
        await asyncio.sleep(0.5)
        
        # Show system status every 5 cycles
        if (i + 1) % 5 == 0:
            print(f"\n--- System Status (Cycle {i + 1}) ---")
            status = recovery_system.get_system_status()
            
            print(f"System Health: {status['fault_tolerance']['system_health']}")
            print(f"Operation Mode: {status['fault_tolerance']['failsafe_status']['operation_mode']}")
            print(f"Failed Services: {status['fault_tolerance']['failsafe_status']['failed_services']}")
            
            # Show retry statistics
            recovery_stats = status['auto_recovery']['retry_statistics']
            for service_name, stats in recovery_stats.items():
                active_retries = len(stats['active_retries'])
                if active_retries > 0:
                    print(f"  {service_name}: {active_retries} active retries")
    
    # Demonstrate emergency procedures
    print("\n=== Testing Emergency Procedures ===\n")
    
    print("6. Triggering emergency procedures...")
    await recovery_system.trigger_emergency("Demonstration of emergency response")
    
    # Show final status
    print("\n7. Final system status:")
    final_status = recovery_system.get_system_status()
    print(f"System Health: {final_status['fault_tolerance']['system_health']}")
    print(f"Operation Mode: {final_status['fault_tolerance']['failsafe_status']['operation_mode']}")
    print(f"Emergency Active: {final_status['fault_tolerance']['failsafe_status']['emergency_active']}")
    
    # Test manual recovery
    print("\n8. Testing manual service recovery...")
    for service_name in ["AECService", "BeamformerService"]:
        success = await recovery_system.recover_service(service_name, "Manual recovery test")
        print(f"  {service_name} recovery: {'✓ Success' if success else '✗ Failed'}")
    
    # Cleanup
    print("\n9. Shutting down error recovery system...")
    await recovery_system.shutdown()
    
    print("\n=== Demo Complete ===")


async def demonstrate_retry_mechanisms():
    """Demonstrate retry mechanisms in isolation."""
    print("\n=== Retry Mechanism Demo ===\n")
    
    from src.audio_processing.retry_mechanism import RetryMechanism, RetryConfig, RetryStrategy
    
    # Create retry mechanism with exponential backoff
    retry_config = RetryConfig(
        max_attempts=4,
        base_delay=0.5,
        strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
        backoff_multiplier=2.0
    )
    
    retry_mechanism = RetryMechanism(retry_config)
    
    # Function that fails a few times then succeeds
    attempt_count = 0
    
    async def flaky_function(data: str) -> str:
        nonlocal attempt_count
        attempt_count += 1
        
        print(f"  Attempt {attempt_count}: Processing '{data}'")
        
        if attempt_count < 3:
            raise ServiceError(f"Simulated failure on attempt {attempt_count}")
        
        return f"Success on attempt {attempt_count}: {data}"
    
    print("Testing retry mechanism with flaky function...")
    
    try:
        result = await retry_mechanism.execute_with_retry(
            flaky_function,
            "test data",
            operation_id="demo_operation"
        )
        print(f"Final result: {result}")
        
    except Exception as e:
        print(f"Operation failed: {e}")
    
    # Show retry statistics
    stats = retry_mechanism.get_retry_statistics()
    print(f"\nRetry statistics: {stats}")


if __name__ == "__main__":
    async def main():
        await demonstrate_error_handling()
        await demonstrate_retry_mechanisms()
    
    asyncio.run(main())