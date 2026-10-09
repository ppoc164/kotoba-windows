"""Portable storage beside the executable, never in the bundle's _internal."""
import os
import sys
from pathlib import Path


def data_root():
    base = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    return base / 'data'


def configure_caches():
    root = data_root()
    os.environ['HF_HOME'] = str(root / 'cache' / 'huggingface')
    os.environ['HF_HUB_CACHE'] = str(root / 'cache' / 'huggingface' / 'hub')
    os.environ['HF_XET_CACHE'] = str(root / 'cache' / 'huggingface' / 'xet')
