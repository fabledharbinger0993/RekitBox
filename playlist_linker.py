"""
rekordbox-toolkit / playlist_linker.py

Links imported tracks to existing Rekordbox playlists by matching
filesystem folder names to playlist names already in the database.

The 2,190 playlists in this DB were created from the folder structure —
artist folders, label folders, VA compilations — so their names correspond
directly to directory names on DJMT PRIMARY.

Matching strategy per track:
  1. Walk up the path (from immediate parent toward MUSIC_ROOT)
  2. For each folder name, try exact match against playlist names
  3. If no exact match and name is long enough, try fuzzy match (difflib, 0.85)
  4. Link to all matched playlists at each level (a track can appear in multiple)
  5. Stop walking up when MUSIC_ROOT is reached

Public interface:
    link_directory(root, db) -> LinkReport
    link_track(track_path, content_row, db, index, playlist_names_lower) -> TrackLinkResult
    build_playlist_index(db) -> dict[str, ...]             # name → playlist obj
"""

import difflib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from pyrekordbox import Rekordbox6Database

from SuperBox.config import BATCH_SIZE, MUSIC_ROOT, SKIP_DIRS, SKIP_PREFIXES, AUDIO_EXTENSIONS

if TYPE_CHECKING:
    # DjmdPlaylist and DjmdContent are ORM row types from pyrekordbox's SQLAlchemy
    # models. They aren't cleanly importable at runtime in all pyrekordbox versions,
    # so we reference them under TYPE_CHECKING only for static analysis.
    from pyrekordbox.db6.tables import DjmdPlaylist, DjmdContent

log = logging.getLogger(__name__)

# Minimum folder name length to attempt fuzzy matching.
# Short names (e.g. "DJ", "UK") are too ambiguous for the 0.85 threshold.
_FUZZY_MIN_LEN: int = 4
_FUZZY_CUTOFF: float = 0.85
# Maximum fuzzy matches per folder name. Multiple matches are intentional —
# a track in .../Kerri Chandler/... can legitimately belong to several
# similarly-named playlists (e.g. a label and an artist share a close name).
# Reviewers should verify the sample output and tighten this if false positives
# appear in practice.
_FUZZY_MAX_MATCHES: int = 3


# ─── Result types ─────────────────────────────────────────────────────────────

@dataclass
class TrackLinkResult:
    path: Path
    content_id: str
    playlist_ids_linked: list[str] = field(default_factory=list)
    unmatched_folders: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def was_linked(self) -> bool:
        """True if at least one playlist link was created for this track."""
        return len(self.playlist_ids_linked) > 0


@dataclass
class LinkReport:
    linked: int = 0           # tracks that matched at least one playlist
    unmatched: int = 0        # tracks with no playlist match at any folder level
    total_links: int = 0      # total DjmdSongPlaylist rows created
    failed: int = 0           # tracks that errored during linking
    results: list[TrackLinkResult] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "═══ PLAYLIST LINK REPORT ═══",
            f"  Tracks linked      : {self.linked}",
            f"  Tracks unmatched   : {self.unmatched}",
            f"  Total links created: {self.total_links}",
            f"  Errors             : {self.failed}",
        ]
        if self.unmatched > 0:
            lines.append("\n  Unmatched folders (sample):")
            seen: set[str] = set()
            count = 0
            for r in self.results:
                for folder in r.unmatched_folders:
                    if folder not in seen:
                        seen.add(folder)
                        lines.append(f"    {folder!r}")
                        count += 1
                        if count >= 10:
                            break
                if count >= 10:
                    break
        lines.append("═════════════════════════════")
        return "\n".join(lines)


# ─── Playlist index ───────────────────────────────────────────────────────────

def build_playlist_index(db: Rekordbox6Database) -> dict[str, object]:
    """
    Build a dict mapping lowercase playlist name → DjmdPlaylist object.
    Called once per session — avoids repeated DB queries during linking.

    Returns
    -------
    dict[str, DjmdPlaylist]
        Keys are lowercased for case-insensitive matching.
        If two playlists share a name (case-insensitively), the last one wins.
        In practice Rekordbox names are unique.
    """
    index: dict[str, object] = {}
    for playlist in db.get_playlist().all():
        if playlist.Name:
            index[playlist.Name.lower()] = playlist
    log.info("Playlist index built: %d playlists", len(index))
    return index


# ─── Matching logic ───────────────────────────────────────────────────────────

def _match_folder(
    folder_name: str,
    index: dict[str, object],
    playlist_names_lower: list[str],
) -> list[object]:
    """
    Attempt to match folder_name against the playlist index.
    Returns a list of matching DjmdPlaylist objects (may be empty).

    Tries exact match first (case-insensitive), then fuzzy if name is long enough.
    Fuzzy can return up to _FUZZY_MAX_MATCHES results — see module-level note
    on _FUZZY_MAX_MATCHES about false-positive risk.
    """
    key = folder_name.lower()

    # Exact match (case-insensitive)
    if key in index:
        return [index[key]]

    # Fuzzy match — only for names long enough to be unambiguous
    if len(folder_name) >= _FUZZY_MIN_LEN:
        close = difflib.get_close_matches(
            key,
            playlist_names_lower,
            n=_FUZZY_MAX_MATCHES,
            cutoff=_FUZZY_CUTOFF,
        )
        if close:
            matches = [index[name] for name in close if name in index]
            if matches:
                log.debug(
                    "Fuzzy matched %r → %s",
                    folder_name,
                    [m.Name for m in matches],
                )
            return matches

    return []


# ─── Single track linking ─────────────────────────────────────────────────────

def link_track(
    track_path: Path,
    content_row: object,
    db: Rekordbox6Database,
    index: dict[str, object],
    playlist_names_lower: list[str],
    music_root: Path = MUSIC_ROOT,
) -> TrackLinkResult:
    """
    Link a single track to all matching playlists by walking up its path.

    Parameters
    ----------
    track_path : Path
        Absolute path to the audio file.
    content_row : DjmdContent
        The already-fetched ORM row for this track. Passed in by link_directory
        to avoid a redundant per-track DB lookup.
    db : Rekordbox6Database
        Open write session.
    index : dict
        Pre-built playlist name index from build_playlist_index().
    playlist_names_lower : list[str]
        Pre-built list of lowercased playlist names for difflib.
    music_root : Path
        Walk stops here — we don't try to match the root folder itself.

    Returns
    -------
    TrackLinkResult
    """
    content_id = str(content_row.ID)
    result = TrackLinkResult(path=track_path, content_id=content_id)

    # Walk up from immediate parent toward music_root
    current = track_path.parent
    visited_folders: set[str] = set()

    while True:
        # Stop at or above music_root
        try:
            current.relative_to(music_root)
        except ValueError:
            break  # current is above music_root

        if current == music_root:
            break

        folder_name = current.name
        if folder_name in visited_folders:
            current = current.parent
            continue
        visited_folders.add(folder_name)

        matches = _match_folder(folder_name, index, playlist_names_lower)

        if matches:
            for playlist in matches:
                try:
                    # PRE-PRODUCTION VERIFICATION REQUIRED:
                    # Confirm db.add_to_playlist(playlist, content_row, track_no=None)
                    # works against the installed pyrekordbox version BEFORE a live run.
                    # If track_no=None raises TypeError, try track_no=0 or omit it.
                    # Silent failures here produce a LinkReport showing zero links
                    # with only WARNING-level log messages — easy to miss.
                    # Verify by reading DjmdSongPlaylist rows with read_db() after a
                    # test link pass on a single known track.
                    db.add_to_playlist(playlist, content_row, track_no=None)
                    result.playlist_ids_linked.append(str(playlist.ID))
                    log.debug(
                        "Linked %s → playlist %r (ID=%s)",
                        track_path.name, playlist.Name, playlist.ID,
                    )
                except Exception as e:
                    # Already linked or other non-fatal error — log and continue.
                    log.warning(
                        "Could not link %s to playlist %r: %s",
                        track_path.name, playlist.Name, e,
                    )
        else:
            result.unmatched_folders.append(folder_name)

        current = current.parent

    return result


# ─── Directory linker ─────────────────────────────────────────────────────────

def link_directory(
    root: Path,
    db: Rekordbox6Database,
    *,
    music_root: Path = MUSIC_ROOT,
) -> LinkReport:
    """
    Link all tracks under root to their matching playlists.

    Queries the DB for DjmdContent rows whose FolderPath falls under root,
    then calls link_track() for each. Does NOT re-scan the filesystem —
    only links tracks already in the database. Import first, link second.

    Parameters
    ----------
    root : Path
        Directory whose tracks should be linked.
    db : Rekordbox6Database
        Open write session (write_db()).
    music_root : Path
        Folder walk upper bound. Defaults to MUSIC_ROOT from config.

    Returns
    -------
    LinkReport
    """
    report = LinkReport()
    root_str = str(root)

    # Build playlist index once for the session
    index = build_playlist_index(db)
    playlist_names_lower = list(index.keys())

    # Find all content rows under root — these are guaranteed to have IDs
    try:
        all_content = db.get_content().all()
        under_root = [
            c for c in all_content
            if c.FolderPath and c.FolderPath.startswith(root_str)
        ]
    except Exception as e:
        log.error("Failed to fetch content rows: %s", e)
        return report

    log.info("Linking %d tracks under %s", len(under_root), root)

    batch_count = 0

    for content_row in under_root:
        track_path = Path(content_row.FolderPath)

        try:
            # Pass the already-fetched content_row directly — no redundant DB lookup
            result = link_track(
                track_path=track_path,
                content_row=content_row,
                db=db,
                index=index,
                playlist_names_lower=playlist_names_lower,
                music_root=music_root,
            )
        except Exception as e:
            log.exception("Unexpected error linking %s", track_path.name)
            r = TrackLinkResult(
                path=track_path,
                content_id=str(content_row.ID),
                error=str(e),
            )
            report.results.append(r)
            report.failed += 1
            continue

        report.results.append(result)

        if result.error:
            report.failed += 1
        elif result.was_linked:
            report.linked += 1
            report.total_links += len(result.playlist_ids_linked)
            batch_count += len(result.playlist_ids_linked)
        else:
            report.unmatched += 1
            log.warning("No playlist match for: %s", track_path.name)

        # Batch commit
        if batch_count >= BATCH_SIZE:
            try:
                db.commit()
                log.info("Committed batch (%d links)", batch_count)
                batch_count = 0
            except Exception:
                log.exception("Batch commit failed — rolling back")
                db.rollback()
                raise

    # Final commit for remaining tail
    if batch_count > 0:
        try:
            db.commit()
            log.info("Final commit: %d links", batch_count)
        except Exception:
            log.exception("Final commit failed — rolling back")
            db.rollback()
            raise

    return report


# ─── Smoke test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")
    sys.path.insert(0, ".")

    from config import DJMT_DB, MUSIC_ROOT
    from db_connection import read_db

    # ── Part 1: playlist index inspection (no writes) ──
    print("=== Playlist index (read-only) ===")
    with read_db(DJMT_DB) as db:
        index = build_playlist_index(db)
        names_lower = list(index.keys())
        print(f"  Total playlists indexed: {len(index)}")
        for name, pl in list(index.items())[:10]:
            print(f"    {pl.Name!r:40} ID={pl.ID}")

        # ── Part 2: matching dry run against known folder names ──
        print("\n=== Matching test (no writes) ===")
        test_folders = [
            "Kerri Chandler",
            "Blaze",
            "Moodymann",
            "kerri chandler",           # lowercase — should still match
            "Kerri Chandlr",            # typo — should fuzzy match
            "XYZ_DEFINITELY_NO_MATCH",
            "DJ",                       # too short for fuzzy — exact only
        ]
        for folder in test_folders:
            matches = _match_folder(folder, index, names_lower)
            if matches:
                print(f"  ✓ {folder!r:30} → {[m.Name for m in matches]}")
            else:
                print(f"  ✗ {folder!r:30} → no match")

    print("\nSmoke test complete — no writes performed.")
    print("To run a real link pass: link_directory(root, db) inside a write_db() session.")
