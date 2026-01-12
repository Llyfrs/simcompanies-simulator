"""Data models for simtools.

This module provides the core data models for representing game entities:
- Resource: Producible items with production characteristics
- Building: Production facilities that create resources
- ResourceInput: Input materials required for production
- ProfitData: TypedDict for profit calculation results
"""

from simtools.models.building import Building, build_resource_to_building_map
from simtools.models.resource import ProfitData, Resource, ResourceInput

__all__ = [
    "Building",
    "ProfitData",
    "Resource",
    "ResourceInput",
    "build_resource_to_building_map",
]

