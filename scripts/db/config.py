#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database configuration loader for scripts/db/
Reads .env from the same directory.
"""

import os
from pathlib import Path

# Load .env from the directory where this file resides
PROJECT_ROOT = Path(__file__).parent.parent.parent
_db_dir = PROJECT_ROOT / "data/db"
_dotenv_path = PROJECT_ROOT / ".env"


def load_env_file(filepath: Path):
    """手动解析 .env 文件，不依赖 python-dotenv"""
    if not filepath.exists():
        return
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()


load_env_file(_dotenv_path)

DB_PATH = os.getenv("DB_PATH", str(_db_dir / "ittf.db"))
SCHEMA_PATH = os.getenv("SCHEMA_PATH", str(PROJECT_ROOT / "scripts" / "db" / "schema.sql"))

# Project root for deriving other paths
