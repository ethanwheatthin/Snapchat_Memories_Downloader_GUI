# Copilot / AI Agent Quick Instructions

Purpose: Short, actionable guidance to help an AI agent be productive immediately in this repository.

## Big picture
- Single Windows-only desktop app with a Tkinter GUI: entrypoint is `download_snapchat_memories_gui.py`.
- Main responsibilities are split into small modules (see `REFACTOR.md`):
  - `snap_utils.py` — date parsing, location parsing, file extension helpers, timestamp setting, file validation
  - `exif_utils.py` — writes EXIF to JPEGs (uses `piexif` + `Pillow` when available)
  - `video_utils.py` — video conversion (PyAV, VLC, ffmpeg fallbacks), metadata writing (`mutagen`)
  - `zip_utils.py` — ZIP handling and merge logic for `-main`/`-overlay` pairs
  - `downloader.py` — network download logic with retries and ZIP handling

## Developer workflows (run / build / debug)
- Run from source (development):
  - pip install -r requirements.txt
  - python download_snapchat_memories_gui.py
- Build distributable for Windows (provided):
  - `build_exe.bat` runs PyInstaller with hidden imports (see command inside the batch file). Use this on Windows.
- Important local tools (not installed by pip):
  - FFmpeg (required for some video operations)
  - VLC (optional but recommended for video conversion)
- Debugging tips:
  - Check `debug.log` (logging is configured at DEBUG level) for stack traces and progress logs
  - Many features fall back gracefully if optional deps are missing, so check `HAS_*` checks in modules

## Project-specific patterns & conventions
- ZIP overlay pattern: look for `-main` and `-overlay` members inside ZIPs; `zip_utils.process_zip_overlay` merges these into `-merged` files.
- Output naming: merged and downloaded files are renamed to `YYYYMMDD_HHMMSS.ext` (see `zip_utils.py` and `download_snapchat_memories_gui.py`).
- Download validation: files < ~100 bytes or unrecognized magic headers are treated as failures (see `snap_utils.validate_downloaded_file`).
- `downloader.download_media(url, output_path, progress_callback=None, date_obj=None)`
  - Retries with exponential backoff; returns `(True, None)`, `(True, [merged_files])`, or `(False, None)` depending on outcome.
- Optional dependencies guarded by `HAS_*` flags (e.g., `HAS_PIEXIF`, `HAS_PYAV`, `HAS_VLC`, `HAS_MUTAGEN`). Code should handle their absence.
- Temp/backup conventions: rotated or converted files get suffixes like `.rotated`, `.temp.mp4`, `.backup` or moved into `downloads/failed_conversions` when necessary.

## Integration & packaging notes
- PyInstaller needs explicit hidden imports for `av`, `mutagen`, `piexif`, `PIL` and `--collect-all=av` (the `build_exe.bat` already includes these flags).
- Native tools (ffmpeg, VLC) are not packaged by PyInstaller — document pre-installation in the installer or README and detect at runtime.
- Windows-specific paths: `video_utils.find_vlc_executable()` checks common Program Files locations; use that for tests or to stub VLC in CI.

## Helpful files to inspect when changing code
- `download_snapchat_memories_gui.py` — primary UI + coordinator; has wrappers delegating to the smaller modules
- `REFACTOR.md` — rationale and module split notes
- `zip_utils.py`, `video_utils.py`, `downloader.py`, `snap_utils.py`, `exif_utils.py` — core behavior examples
- `build_exe.bat` and `requirements.txt` — build & dependency guidance

## Example quick tasks an agent may be asked to do
- Add unit smoke tests: run `parse_date(date_string)`, `snap_utils.get_file_extension('Video')`, `video_utils.check_ffmpeg()` in a small script.
- Improve robustness: when adding features that touch FFmpeg/VLC, add explicit runtime detection and informative messages to the GUI/log.
- Packaging changes: update `build_exe.bat` if you add a new binary dependency or a new hidden import.

---
If anything here is unclear or you'd like more strict style/PR guidance (tests, commit message templates, CI), tell me what to add and I'll iterate on this file. 
