"""Read-only external result contracts; never import external scientific engines."""

from .adapters import inspect_biolab, inspect_literature
from .common import IntegrationError, ResultSummary

__all__ = ["IntegrationError", "ResultSummary", "inspect_biolab", "inspect_literature"]
