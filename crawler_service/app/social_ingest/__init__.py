"""Bounded, HTTP-only POI ingestion for public web sources (OC-050).

This package is intentionally separate from :mod:`crawler_service.app.acquisition`:
it performs the network-facing *collection* step (guarded public HTTP + raw
capture + deterministic extraction), writes a normalized export, and then hands
that export to the existing offline acquisition pipeline through the
``web_poi`` adapter. It never writes to the graph and never imports data.

Only the Python standard library is used. There is no browser automation, login,
cookie, proxy, CAPTCHA handling or third-party crawler framework.
"""

from __future__ import annotations

SCHEMA_VERSION = 1

__all__ = ["SCHEMA_VERSION"]
