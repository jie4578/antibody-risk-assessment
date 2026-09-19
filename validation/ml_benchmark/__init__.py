"""Phase 5A leakage-safe benchmark specification and split utilities."""

from .similarity import global_identity
from .split import assign_component_splits, build_leakage_components

__all__ = ["global_identity", "assign_component_splits", "build_leakage_components"]
