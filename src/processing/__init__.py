"""
Audio Processing Module

High-level audio processing components including algorithms,
filters, and processing pipelines.
"""

__version__ = "1.0.0"
__author__ = "Production Audio System Team"

from .processing_chain import ProcessingChain
from .components import ComponentRegistry
from .pipeline import AudioPipeline

__all__ = [
    "ProcessingChain",
    "ComponentRegistry",
    "AudioPipeline"
]