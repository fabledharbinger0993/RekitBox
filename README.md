# SuperBox
a toolkit companion for RekordBox: worthwhile redundancies, safer tools for relocating and duplicate analysis than tools local to RB, along with file name correction, key reading/tagging, volume normalization and Library structure with path connection tools.
rekordbox-toolkit
Library management for serious DJ libraries


rekordbox-toolkit is a command-line suite for maintaining a Pioneer Rekordbox library at scale. It provides safe batch import, playlist linking, path relocation, BPM/key analysis, loudness normalisation, and duplicate detection — operations that Rekordbox either does not expose or limits to one file at a time.
All write operations enforce two invariants before touching the database: Rekordbox must not be running, and a timestamped backup is created automatically. No operation deletes or modifies a file without a verified replacement in place first.
Requirements


Quick Start




Modules

config.py
Central configuration. All path references and shared constants flow from here. Edit this file before first use.



db_connection.py
Safe database connection wrapper. Every write operation in the toolkit goes through here. Never call Rekordbox6Database directly.

Context managers




cli.py
Single entry point. All module imports are deferred so --help runs instantly without loading heavy dependencies.



audit


Read-only health check. Reports track count, playlist count, cue points, tag coverage (BPM, key, artist, album, genre), file-type breakdown, path integrity, and orphaned files on disk. Safe to run with Rekordbox open. Defaults to MUSIC_ROOT for the orphan scan; pass --root to override.

import


Import all audio files under PATH into the database. Extracts title, artist, album, genre, BPM, key, duration, bitrate, sample rate, bit depth, year, and track number from file tags. Commits in batches of BATCH_SIZE. Skips tracks already in the database.

--dry-run logs what would be imported without writing anything. Use this first.

link


Links tracks already in the database to existing playlists by matching filesystem folder names against playlist names. Walks up each track's path toward MUSIC_ROOT and tries exact match first, then fuzzy match (difflib, threshold 0.85) for folder names four characters or longer.



relocate


Batch-updates FolderPath values in DjmdContent when files have been moved. OLD_ROOT does not need to exist on disk — it is matched as a string prefix against stored paths. Three strategies are tried in order per track:

Exact — same relative path exists under NEW_ROOT
Hash — SHA256 of the first 64 KB matches a file in NEW_ROOT (catches renames with identical content)
Fuzzy — filename stem similarity ≥ 0.90 (catches minor edits, encoding fixes, format changes)

Tracks that cannot be matched are logged as warnings and left unchanged. Run audit afterwards to confirm path integrity.

duplicates


Fingerprints all audio files under PATH using Chromaprint (fpcalc) and groups files that share an identical acoustic fingerprint. Writes a CSV report for human review — it never deletes or moves anything.

Within each duplicate group, files are ranked by the RARP hierarchy to suggest which to keep:

PN — Pioneer Numbered (stem begins with two or more digits and a separator, e.g. 01 - Title)
MIK — Mixed In Key tagged (TKEY/initialkey tag present and non-empty)
RAW — Neither of the above

The CSV contains: group_id, action (KEEP / REVIEW_REMOVE), rank, file_path, file_size_mb, bpm, key, filename.



process


BPM is calculated by librosa beat tracking, which analyzes the actual audio waveform for beat patterns rather than guessing from the filename.


Normalisation target is −8.0 LUFS (DJ standard) with a ±0.5 LUFS tolerance. MP3s are re-encoded at 320 kbps CBR; AIFFs are re-encoded losslessly matching source bit depth. Originals are kept as .bak during the operation and deleted only after the replacement is verified.



Internal Modules

These modules are not called directly. They are imported by the command handlers above.

scanner.py
Filesystem walker and metadata extractor. No database interaction. Returns TrackInfo dataclasses containing all tag fields the importer needs. BPM is returned as a float (not multiplied by 100 — the importer applies ×100 when writing to the DB). Missing fields are None. Errors are captured in TrackInfo.errors rather than raising.

Public interface: scan_directory(root) -> Iterator[TrackInfo],  extract_metadata(path) -> TrackInfo

importer.py
Writes TrackInfo records into DjmdContent. Handles artist get-or-create (DjmdArtist), key resolution (key_mapper), .aif extension workaround (pyrekordbox only recognises .aiff), and batch commits with rollback on failure.

Public interface: import_directory(root, db, dry_run=False) -> ImportReport

key_mapper.py
Resolves any key notation (Camelot, Open Key, standard) to a DjmdKey.ID. Uses a get-or-create pattern: looks up the ScaleName row, creates it if absent, returns its ID. New rows are created with placeholder Seq values.



Public interface: resolve_key_id(raw_key, db) -> str | None,  notation_to_scale_name(raw) -> str | None

audio_processor.py
Analyses and normalises audio files in-place. No database interaction. Existing tags are never overwritten unless force=True. Original files are never deleted until the replacement is verified by soundfile.

Public interface: process_file(path, ...) -> ProcessResult,  process_directory(root, ...) -> list[ProcessResult]

audit.py
Read-only database snapshot and filesystem validation. Three passes: snapshot (entity counts and tag coverage), path validation (checks every FolderPath exists on disk), and orphan detection (finds files on disk with no database row). Safe to run with Rekordbox open.

Public interface: snapshot(db) -> LibrarySnapshot,  validate_paths(db) -> PathReport,  full_audit(db, root) -> AuditReport

playlist_linker.py
Links imported tracks to existing Rekordbox playlists by matching filesystem folder names to playlist names in the database. The 2,190 playlists in this library were built from the folder structure, so folder names correspond directly to playlist names. Fuzzy matching handles minor name differences (threshold 0.85, minimum 4 characters).

Public interface: link_directory(root, db) -> LinkReport

relocator.py
Batch-updates FolderPath values. Builds a hash index (SHA256 of first 64 KB) and a fuzzy stem index over new_root before processing begins — no per-track filesystem walk. Uses pyrekordbox's update_content_path with check_path=True, which refuses to write if the target file does not exist on disk.

Public interface: relocate_directory(old_root, new_root, db) -> list[RelocationResult]

duplicate_detector.py
Chromaprint fingerprinting via fpcalc and pyacoustid. Analyses the first 120 seconds of each file (fpcalc default), groups by identical fingerprint, ranks within each group by the RARP hierarchy, and writes a CSV report. Never modifies files.

Public interface: scan_duplicates(root) -> list[DuplicateGroup],  write_csv_report(groups, output_path)

Design Principles


No write without a backup. write_db() creates a timestamped backup before yielding. If something goes wrong the original is always recoverable.
No write with Rekordbox open. write_db() checks for running Rekordbox processes and refuses if found.
Rollback on exception. All write sessions roll back automatically on unhandled exceptions. Partial imports do not occur.
No silent file loss. audio_processor.py moves the original to .bak before writing the replacement, and only deletes .bak after soundfile confirms the output is valid.
Batch commits. All write operations commit in batches of BATCH_SIZE (default 250). The final tail is committed separately.
Errors are returned, not raised. scanner.py and audio_processor.py capture per-file errors in result objects so a single bad file never aborts a batch.
Read-only operations are always safe. audit, dry-run import, and the duplicate scan never write to the database or modify files.

Recommended Workflow


Run these steps in order when adding new music to the library.

1. Audit first.  Run audit to confirm baseline path integrity before touching anything.



2. Process tags.  Run process with --no-normalize first to detect and write BPM and key tags.



3. Dry-run import.  Verify what will be imported before committing.



4. Import.  Write tracks into the database.



5. Link playlists.  Match imported tracks to their playlists.



6. Audit again.  Confirm path integrity and playlist link counts after the import.



7. Normalise loudness (optional).  Run process again to normalise levels. Ensure files are backed up independently before this step.




rekordbox-toolkit  —  Guthrie Entertainment LLC / Osos Discos
