"""HTTP API (FastAPI). Phase 2 exposes status, health and audit verification only.

No trading endpoints exist yet. Every response states the environment, halt state and
live-authority status so no consumer can mistake this build for a live trading system.
"""

from nexus.api.app import create_app

__all__ = ["create_app"]
