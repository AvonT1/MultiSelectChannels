#!/usr/bin/env python3
"""
Test configuration loading without running the full bot.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

try:
    from src.config.settings import settings
    print("Configuration loaded successfully!")
    print(
        f"API_ID: {settings.api_id if hasattr(settings, 'api_id') else 'Not set'}"
    )
    print(f"Database URL: {settings.database_url[:20]}..." if hasattr(
        settings, 'database_url') else 'Not set')
    print(
        f"Admin IDs: {settings.admin_ids if hasattr(settings, 'admin_ids') else 'Not set'}"
    )
except Exception as e:
    print(f"Configuration failed: {e}")
    sys.exit(1)
