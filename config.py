"""
rekordbox-toolkit / config.py
Central configuration: paths, constants, key mappings.
All path references in the toolkit flow from here.
"""

import os
import sys
from pathlib import Path

# Require Python 3.12+ — Path.walk() was added in 3.12
if sys.version_info < (3, 12):
    raise RuntimeError(
        f"rekordbox-toolkit requires Python 3.12 or later "
        f"(found {sys.version_info.major}.{sys.version_info.minor}). "
        "Path.walk() is used throughout — upgrade Python or replace with os.walk()."
    )

# ─── Database paths ───────────────────────────────────────────────────────────

# Primary Rekordbox database (what the Mac app reads/writes)
LOCAL_DB = Path.home() / "Library/Pioneer/rekordbox/master.db"

# Device database on DJMT (exported for CDJ playback)
DJMT_DB = Path("/Volumes/DJMT/PIONEER/Master/master.db")

# Music library root on the drive
MUSIC_ROOT = Path("/Volumes/DJMT/DJMT PRIMARY")

# Backup directory (created automatically before any write)
BACKUP_DIR = Path.home() / "rekordbox-toolkit/backups"

# Supported audio file extensions (lowercase)
AUDIO_EXTENSIONS = {".mp3", ".aiff", ".aif", ".wav", ".flac", ".m4a", ".ogg", ".opus"}

# Files to skip when scanning (macOS metadata, hidden files)
SKIP_PREFIXES = ("._", ".")
SKIP_DIRS = {"PIONEER", "__MACOSX", ".Spotlight-V100", ".fseventsd"}

# Batch size for database commits — one commit per N tracks
BATCH_SIZE: int = 250

# BPM sanity-check range — shared by scanner and audio_processor
BPM_MIN: float = 30.0
BPM_MAX: float = 300.0


# ─── Camelot / Musical Key → Rekordbox ScaleName mapping ─────────────────────
#
# Rekordbox stores key as a foreign key (KeyID) pointing to a DjmdKey row
# with a ScaleName field. The ScaleName format uses standard notation:
# major keys as plain note names (e.g. "C", "G#"), minor keys suffixed with "m"
# (e.g. "Am", "F#m").
#
# Sources that tag keys use various notations. We normalize all of them here.

# Camelot → Rekordbox ScaleName
CAMELOT_TO_RB = {
    "1A": "Am",   "2A": "Em",   "3A": "Bm",   "4A": "F#m",
    "5A": "C#m",  "6A": "Abm",  "7A": "Ebm",  "8A": "Bbm",
    "9A": "Fm",   "10A": "Cm",  "11A": "Gm",  "12A": "Dm",
    "1B": "C",    "2B": "G",    "3B": "D",    "4B": "A",
    "5B": "E",    "6B": "B",    "7B": "F#",   "8B": "Db",
    "9B": "Ab",   "10B": "Eb",  "11B": "Bb",  "12B": "F",
}

# Open Key → Rekordbox ScaleName
OPENKEY_TO_RB = {
    "1m": "Am",   "2m": "Em",   "3m": "Bm",   "4m": "F#m",
    "5m": "C#m",  "6m": "Abm",  "7m": "Ebm",  "8m": "Bbm",
    "9m": "Fm",   "10m": "Cm",  "11m": "Gm",  "12m": "Dm",
    "1d": "C",    "2d": "G",    "3d": "D",    "4d": "A",
    "5d": "E",    "6d": "B",    "7d": "F#",   "8d": "Db",
    "9d": "Ab",   "10d": "Eb",  "11d": "Bb",  "12d": "F",
}

# Standard notation aliases → canonical Rekordbox ScaleName
# Covers enharmonic equivalents and common alternate spellings
STANDARD_KEY_ALIASES = {
    # Major
    "C": "C",       "Cmaj": "C",    "CM": "C",
    "Db": "Db",     "C#": "Db",     "Dbmaj": "Db",  "C#maj": "Db",
    "D": "D",       "Dmaj": "D",    "DM": "D",
    "Eb": "Eb",     "D#": "Eb",     "Ebmaj": "Eb",
    "E": "E",       "Emaj": "E",    "EM": "E",
    "F": "F",       "Fmaj": "F",    "FM": "F",
    "F#": "F#",     "Gb": "F#",     "F#maj": "F#",  "Gbmaj": "F#",
    "G": "G",       "Gmaj": "G",    "GM": "G",
    "Ab": "Ab",     "G#": "Ab",     "Abmaj": "Ab",  "G#maj": "Ab",
    "A": "A",       "Amaj": "A",    "AM": "A",
    "Bb": "Bb",     "A#": "Bb",     "Bbmaj": "Bb",  "A#maj": "Bb",
    "B": "B",       "Bmaj": "B",    "BM": "B",
    # Minor
    "Am": "Am",     "Amin": "Am",   "A minor": "Am",
    "Bbm": "Bbm",   "A#m": "Bbm",   "Bbmin": "Bbm",
    "Bm": "Bm",     "Bmin": "Bm",
    "Cm": "Cm",     "Cmin": "Cm",
    "C#m": "C#m",   "Dbm": "C#m",   "C#min": "C#m", "Dbmin": "C#m",
    "Dm": "Dm",     "Dmin": "Dm",
    "Ebm": "Ebm",   "D#m": "Ebm",   "Ebmin": "Ebm",
    "Em": "Em",     "Emin": "Em",
    "Fm": "Fm",     "Fmin": "Fm",
    "F#m": "F#m",   "Gbm": "F#m",   "F#min": "F#m",
    "Gm": "Gm",     "Gmin": "Gm",
    "Abm": "Abm",   "G#m": "Abm",   "Abmin": "Abm", "G#min": "Abm",
}
