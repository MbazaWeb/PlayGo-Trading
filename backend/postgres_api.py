"""Compatibility entrypoint for existing ``postgres_api:app`` launches."""
import sys

from app import postgres_api as implementation

sys.modules[__name__] = implementation
