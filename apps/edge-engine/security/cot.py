"""
Cursor-on-Target (CoT) XML Generator & MIL-STD-2525 Symbology Translator.
Direct module export from src.security.cot.
"""

from src.security.cot import (
    CoTGenerator,
    MIL_STD_2525_MAP,
    MIL_STD_HOSTILE_VEHICLE,
)

__all__ = ["CoTGenerator", "MIL_STD_2525_MAP", "MIL_STD_HOSTILE_VEHICLE"]
