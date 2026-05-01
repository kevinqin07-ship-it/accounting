"""Airtable -> accounting sync worker.

Pulls operational records from an Airtable base and posts the financial
side to the accounting HTTP API. One-way; Airtable stays the operational
source of truth.
"""

from accounting.airtable.config import DEFAULT_DRAYAGE_CONFIG, DrayageSyncConfig
from accounting.airtable.sync import SyncReport, run_sync

__all__ = [
    "DEFAULT_DRAYAGE_CONFIG",
    "DrayageSyncConfig",
    "SyncReport",
    "run_sync",
]
