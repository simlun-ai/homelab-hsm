"""Authenticated wrapped records. Imports do not access hardware or change process state."""
from .wrapping import wrap, unwrap

__all__ = ["wrap", "unwrap"]
