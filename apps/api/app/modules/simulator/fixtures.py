"""Authored source examples. These are drafts, never approved foundation policy."""
import json
from pathlib import Path

def authored_drafts():
    return json.loads(Path(__file__).with_name('source_drafts.json').read_text())
