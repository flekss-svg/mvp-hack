"""Совместимость: признаки переехали в ml_service/features.py (единственное место, где они считаются)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml_service.features import *  # noqa: E402,F401,F403
