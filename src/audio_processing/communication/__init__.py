"""
Communication framework for the audio processing system.

This module provides the core communication infrastructure including
event bus, message routing, audio data pipelines, and backpressure control.
"""

from .event_bus import EventBus, Event, EventHandler, EventPriority
from .audio_pipeline import (
    AudioPipeline, PipelineNode, BackpressureController, 
    BackpressureStrategy, PipelineState
)
from .message_router import (
    MessageRouter, Message, MessageHandler, MessageType, RoutingStrategy
)
from .shared_memory import SharedMemoryManager, AudioFrameBuffer

__all__ = [
    'EventBus',
    'Event', 
    'EventHandler',
    'EventPriority',
    'AudioPipeline',
    'PipelineNode',
    'BackpressureController',
    'BackpressureStrategy',
    'PipelineState',
    'MessageRouter',
    'Message',
    'MessageHandler',
    'MessageType',
    'RoutingStrategy',
    'SharedMemoryManager',
    'AudioFrameBuffer'
]