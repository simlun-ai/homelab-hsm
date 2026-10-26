"""Authenticated wrapped records. Imports do not access hardware or change process state."""

from .wrapping import unwrap, wrap

__all__ = ["wrap", "unwrap"]
