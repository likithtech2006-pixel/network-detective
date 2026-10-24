"""Network simulation, topology emulation, and fault injection subsystem.

Provides virtualized network devices and links for offline testing, chaos engineering,
and automated self-healing validation without requiring physical testbeds.
"""

from src.simulation.failure_injector import FailureInjector
from src.simulation.virtual_network import SimulatedResponse, VirtualNetwork

__all__ = [
    "VirtualNetwork",
    "FailureInjector",
    "SimulatedResponse",
]
