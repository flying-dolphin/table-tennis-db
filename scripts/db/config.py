#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database configuration loader for scripts/db/
Reads .env from the same directory.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError as e:
    raise ImportError(
        "python-dotenv is required. Install it via: pip install python-dotenv"
    ) from e

# Load .env from the directory where this file resides
PROJECT_ROOT = Path(__file__).parent.parent.parent
_db_dir = PROJECT_ROOT / "data/db"
_dotenv_path = PROJECT_ROOT /  ".env"

if _dotenv_path.exists():
    load_dotenv(dotenv_path=str(_dotenv_path), override=True)


DB_PATH = os.getenv("DB_PATH", str(_db_dir / "ittf.db"))
SCHEMA_PATH = os.getenv("SCHEMA_PATH", str(PROJECT_ROOT / "scripts" / "db" / "schema.sql"))

# Project root for deriving other paths
