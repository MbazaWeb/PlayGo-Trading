"""Compatibility entrypoint for existing ``main:app`` launches."""
import sys

from app import main as implementation

sys.modules[__name__] = implementation
