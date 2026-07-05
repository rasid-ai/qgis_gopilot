# -*- coding: utf-8 -*-
"""
Dependencies Module

Manages plugin dependencies and virtual environment isolation.
Main entry points:
- DependencyManager: UI dialog for installing dependencies
- venv_manager: Low-level venv and package management utilities
"""

from .dependency_installer import DependencyManager
from . import venv_manager

__all__ = ['DependencyManager', 'venv_manager']
