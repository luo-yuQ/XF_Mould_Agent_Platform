"""Minimal registered capability boundary for the Runtime Core."""

from runtime.capabilities.core import (
    CapabilityDefinition,
    CapabilityRegistry,
    CapabilityRunner,
)
from runtime.capabilities.demo import DEMO_CAPABILITY_NAME, register_demo_capability

__all__ = [
    "CapabilityDefinition",
    "CapabilityRegistry",
    "CapabilityRunner",
    "DEMO_CAPABILITY_NAME",
    "register_demo_capability",
]
