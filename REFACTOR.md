Refactor summary

What's changed
- Large monolithic script `download_snapchat_memories_gui.py` was split into smaller modules for maintainability:
  - `snap_utils.py` - date/location helpers, validation, timestamps, file extension helpers
  - `exif_utils.py` - image EXIF writing logic
  - `video_utils.py` - video conversion, ffmpeg/vlc helpers, metadata writing
  - `zip_utils.py` - ZIP extraction and merging overlay logic
  - `downloader.py` - download logic (with retry, ZIP handling, and progress callback)

Compatibility
- The main script `download_snapchat_memories_gui.py` keeps the same public API and CLI entrypoint. Functions are now delegated to the new modules, so existing behaviour and `build_exe.bat` should continue to work unchanged.

Notes & next steps
- If you use a virtualenv or PyInstaller, ensure required packages (Pillow, piexif, mutagen, av, python-vlc, ffmpeg) are available or included as hidden imports.
- I ran a quick import and smoke tests (parse_date, check_ffmpeg, get_file_extension) locally — all good.
