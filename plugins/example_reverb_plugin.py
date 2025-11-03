"""
Example reverb plugin demonstrating the plugin interface.

This plugin adds a simple reverb effect to audio frames.
"""

import numpy as np
from typing import Dict, Any, List
from audio_processing.interfaces import IPluginInterface
from audio_processing.models import AudioConfig, AudioFrame


class SimpleReverbPlugin(IPluginInterface):
    """
    Simple reverb plugin that adds echo effect to audio.
    
    This is an example plugin that demonstrates:
    - Plugin interface implementation
    - Audio processing
    - Configuration handling
    - Resource management
    """
    
    def __init__(self):
        self.config = None
        self.delay_buffer = None
        self.delay_samples = 0
        self.feedback = 0.3
        self.wet_level = 0.2
        self.buffer_index = 0
        self.is_initialized = False
    
    def get_plugin_info(self) -> Dict[str, Any]:
        """Get plugin metadata."""
        return {
            'name': 'SimpleReverb',
            'version': '1.0.0',
            'description': 'Simple reverb effect plugin with configurable delay and feedback',
            'author': 'Audio Processing System',
            'license': 'MIT',
            'categories': ['effects', 'reverb'],
            'keywords': ['reverb', 'echo', 'delay', 'effect'],
            'entry_point': 'SimpleReverbPlugin',
            'min_system_version': '1.0.0'
        }
    
    def get_required_dependencies(self) -> List[str]:
        """Get list of required dependencies."""
        return []  # No dependencies for this simple plugin
    
    async def initialize(self, config: AudioConfig) -> None:
        """
        Initialize the plugin with audio configuration.
        
        Args:
            config: Audio system configuration
        """
        self.config = config
        
        # Calculate delay in samples (100ms delay)
        delay_ms = 100
        self.delay_samples = int((delay_ms / 1000.0) * config.sample_rate)
        
        # Initialize delay buffer for each channel
        self.delay_buffer = np.zeros((config.channels, self.delay_samples))
        self.buffer_index = 0
        
        # Plugin-specific settings (could be configurable)
        self.feedback = 0.3  # 30% feedback
        self.wet_level = 0.2  # 20% wet signal
        
        self.is_initialized = True
        print(f"SimpleReverb plugin initialized: {self.delay_samples} samples delay")
    
    async def cleanup(self) -> None:
        """Clean up plugin resources."""
        self.delay_buffer = None
        self.config = None
        self.is_initialized = False
        print("SimpleReverb plugin cleaned up")
    
    def process_frame(self, frame: AudioFrame) -> AudioFrame:
        """
        Process audio frame with reverb effect.
        
        Args:
            frame: Input audio frame
            
        Returns:
            Processed audio frame with reverb effect
        """
        if not self.is_initialized:
            raise RuntimeError("Plugin not initialized")
        
        # Create output frame
        output_data = frame.data.copy()
        
        # Process each channel
        for ch in range(frame.channels):
            channel_data = frame.data[ch]
            
            # Apply reverb effect
            for i in range(frame.frame_size):
                # Get delayed sample
                delayed_sample = self.delay_buffer[ch, self.buffer_index]
                
                # Calculate output sample (dry + wet)
                dry_sample = channel_data[i]
                wet_sample = delayed_sample * self.wet_level
                output_sample = dry_sample + wet_sample
                
                # Update delay buffer with input + feedback
                feedback_sample = dry_sample + (delayed_sample * self.feedback)
                self.delay_buffer[ch, self.buffer_index] = feedback_sample
                
                # Store output
                output_data[ch, i] = output_sample
                
                # Advance buffer index
                self.buffer_index = (self.buffer_index + 1) % self.delay_samples
        
        # Create output frame
        output_frame = AudioFrame(
            timestamp=frame.timestamp,
            sample_rate=frame.sample_rate,
            channels=frame.channels,
            frame_size=frame.frame_size,
            data=output_data,
            metadata=frame.metadata.copy() if frame.metadata else {}
        )
        
        # Add plugin metadata
        if output_frame.metadata is None:
            output_frame.metadata = {}
        output_frame.metadata['processed_by'] = 'SimpleReverb'
        output_frame.metadata['reverb_settings'] = {
            'delay_ms': (self.delay_samples / self.config.sample_rate) * 1000,
            'feedback': self.feedback,
            'wet_level': self.wet_level
        }
        
        return output_frame
    
    def get_parameters(self) -> Dict[str, Any]:
        """Get current plugin parameters."""
        return {
            'delay_samples': self.delay_samples,
            'feedback': self.feedback,
            'wet_level': self.wet_level,
            'delay_ms': (self.delay_samples / self.config.sample_rate * 1000) if self.config else 0
        }
    
    def set_parameters(self, parameters: Dict[str, Any]) -> None:
        """Set plugin parameters."""
        if 'feedback' in parameters:
            self.feedback = max(0.0, min(0.9, parameters['feedback']))  # Clamp to safe range
        
        if 'wet_level' in parameters:
            self.wet_level = max(0.0, min(1.0, parameters['wet_level']))  # Clamp to 0-1
        
        if 'delay_ms' in parameters and self.config:
            # Recalculate delay samples
            delay_ms = max(10, min(500, parameters['delay_ms']))  # Clamp to reasonable range
            new_delay_samples = int((delay_ms / 1000.0) * self.config.sample_rate)
            
            if new_delay_samples != self.delay_samples:
                # Resize delay buffer
                old_buffer = self.delay_buffer
                self.delay_samples = new_delay_samples
                self.delay_buffer = np.zeros((self.config.channels, self.delay_samples))
                
                # Copy old data if possible
                if old_buffer is not None:
                    copy_samples = min(old_buffer.shape[1], self.delay_samples)
                    self.delay_buffer[:, :copy_samples] = old_buffer[:, :copy_samples]
                
                self.buffer_index = 0


# Plugin factory function (alternative to class-based approach)
def create_plugin() -> IPluginInterface:
    """Factory function to create plugin instance."""
    return SimpleReverbPlugin()


# Plugin metadata for discovery
PLUGIN_METADATA = {
    'name': 'SimpleReverb',
    'version': '1.0.0',
    'description': 'Simple reverb effect plugin',
    'author': 'Audio Processing System',
    'plugin_class': 'SimpleReverbPlugin',
    'factory_function': 'create_plugin'
}