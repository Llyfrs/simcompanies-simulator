"""Simtools - A simulation toolkit for Sim Companies.

This package provides tools for calculating production profits, ROI analysis,
and optimization for the Sim Companies game.
"""

from simtools.api import SimcoAPI
from simtools.calculator import ProfitConfig
from simtools.data_loader import GameData, load_game_data
from simtools.models.building import Building
from simtools.models.resource import Resource

__all__ = [
    "Building",
    "GameData",
    "ProfitConfig",
    "Resource",
    "SimcoAPI",
    "load_game_data",
]

