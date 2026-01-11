# Debugging Guide for Snapchat Memories Downloader

This guide helps you diagnose and fix issues with video conversion, file validation, and failed downloads.

## Quick Diagnostics

### Check Conversion Tools

Run these commands in PowerShell to verify ffmpeg and VLC are available:

```powershell
# Check ffmpeg
ffmpeg -version

# Check VLC (adjust path if installed elsewhere)
& "C:\\Program Files\\VideoLAN\\VLC\\vlc.exe" --version
```

### Inspect Video Files

Use ffprobe to check video file properties:

```powershell
# Get video duration and streams
ffprobe -v error -show_entries format=duration -show_entries stream=codec_name,codec_type "path\\to\\video.mp4"

# Get detailed format information
ffprobe -v error -show_format -show_streams "path\\to\\video.mp4"

# Check for HEVC/H.265 codec (needs conversion)
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of default=noprint_wrappers=1:nokey=1 "path\\to\\video.mp4"
```

### Check Debug Logs

The application logs detailed information to `debug.log` in the application directory:

```powershell
# View last 50 lines
Get-Content debug.log -Tail 50

# Search for errors
Select-String -Path debug.log -Pattern "ERROR|CRITICAL|Failed"

# Find conversion attempts for a specific file
Select-String -Path debug.log -Pattern "20240115_143022"
```

## Common Issues

### Issue: Videos have trailing "}" in filename

**Symptoms:** Files named like `20240115_143022.mp4}` or similar

**Cause:** VLC command-line parameter not properly quoted, causing format string artifacts

**Fix Applied:** 
- `video_utils.py`: Added `sanitize_path()` function that strips trailing braces and invalid characters
- All path returns now use `Path.resolve()` for normalization
- VLC --sout parameter properly escapes paths

**Verify Fix:**
```python
from video_utils import sanitize_path
result = sanitize_path("test.mp4}")
print(result)  # Should not end with }
```

### Issue: Playable videos marked as "failed conversion"

**Symptoms:** Video plays fine but is in `downloads/failed_conversions/`

**Cause:** Conversion tool returned non-zero exit code but produced valid output

**Fix Applied:**
- Added `validate_video_file()` that uses ffprobe to verify:
  - Duration > 0
  - Has video stream
  - File size > minimum threshold
- Conversion only fails if validation fails, not just on exit code

**Debug:**
```powershell
# Check if video is actually playable
ffprobe "downloads\\failed_conversions\\video.mp4"

# If it shows valid duration and streams, it's a false failure
```

### Issue: Conversion creates incomplete files

**Symptoms:** Small files (< 1KB) or 1-second videos instead of full length

**Cause:** VLC or ffmpeg didn't properly loop overlay image for full video duration

**Fix Applied:**
- Video overlay merge now uses ffmpeg `-loop 1` and `shortest=1` parameters
- Added validation step that checks output duration matches input
- Atomic replacement: temp file validated before replacing original

**Debug:**
```powershell
# Compare durations
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "original.mp4"
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "converted.mp4"
```

### Issue: Resume mode doesn't detect existing files

**Symptoms:** Files re-downloaded even though they exist

**Cause:** Filename patterns don't match due to timezone differences or merge suffixes

**Debug:**
Look for files with these patterns:
- `YYYYMMDD_HHMMSS_index.mp4` (normal download)
- `YYYYMMDD_HHMMSS.mp4` (merged overlay, no index)
- `YYYYMMDD_HHMMSS_1.mp4` (collision resolved)

Check `debug.log` for lines like:
```
[idx/total] ✓ File already exists (resume): path\\to\\file.mp4
```

## Interpreting Debug Logs

### Conversion Log Format

Each conversion attempt is logged with a unique ID:

```
[filename_timestamp_attempt] Attempt 1: Opening input video: path\\to\\input.mp4
[filename_timestamp_attempt] Creating temp output: path\\to\\output.temp.mp4
[filename_timestamp_attempt] Validating converted file...
[filename_timestamp_attempt] Validation passed, performing atomic replace...
```

### Validation Log Format

```
Video validation passed: path\\to\\file.mp4 - duration=15.5s, codec=h264
```

or on failure:

```
Validation failed: No video stream found
Validation failed: Duration too short: 0.5s
```

### Failed Conversion Logs

When conversion completely fails:

```
Saved error log: downloads\\failed_conversions\\filename_error_timestamp.log
Copied failed file to: downloads\\failed_conversions\\filename.mp4
```

Check the error log for full stdout/stderr from VLC/ffmpeg.

## Testing Changes

Run unit tests to verify fixes:

```powershell
# Install pytest if not already installed
pip install pytest

# Run all tests
python -m pytest tests\\ -v

# Run specific test file
python -m pytest tests\\test_filename_sanitization.py -v

# Run with more detail
python -m pytest tests\\ -v --tb=short
```

## Manual Testing Procedure

1. **Test filename sanitation:**
   ```python
   from video_utils import sanitize_path
   paths = ["test.mp4}", "path/file.mp4  ", "video.mp4{ }"]
   for p in paths:
       result = sanitize_path(p)
       print(f"{p} -> {result}")
       assert not str(result).endswith('}')
   ```

2. **Test validation:**
   ```python
   from video_utils import validate_video_file
   from pathlib import Path
   
   is_valid, info = validate_video_file(Path("path/to/test.mp4"))
   print(f"Valid: {is_valid}")
   print(f"Info: {info}")
   ```

3. **Test atomic replacement:**
   - Look for `.temp.mp4` files during conversion
   - They should disappear after successful conversion
   - If they remain, check debug.log for validation failures

## Reporting Issues

When reporting bugs, include:

1. Relevant section from `debug.log` (include conversion ID lines)
2. Output of `ffprobe` on the problematic file
3. Whether ffmpeg/VLC are installed (`ffmpeg -version`, `vlc --version`)
4. Steps to reproduce
5. Expected vs actual filename/behavior

## Additional Tools

### Check Video Codec

```powershell
# Quick codec check
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of default=noprint_wrappers=1:nokey=1 "video.mp4"

# If output is "hevc" or "h265", it needs conversion for Windows compatibility
```

### Manually Convert HEVC to H.264

```powershell
ffmpeg -i "input_hevc.mp4" -c:v libx264 -crf 23 -preset medium -c:a copy "output_h264.mp4"
```

### Validate MP4 Structure

```powershell
# Check for corruption
ffmpeg -v error -i "video.mp4" -f null - 2>&1

# If output is empty, file is structurally sound
# If errors appear, file may be corrupted
```

## Performance Optimization

### Conversion Speed Settings

In `video_utils.py`, conversion uses these presets:

- PyAV: Default encoder settings
- VLC: `preset=medium, profile=main`
- ffmpeg overlay: `preset=veryfast, crf=18`

To speed up (lower quality):
- Change `veryfast` to `ultrafast`
- Increase CRF from 18 to 23-28 (higher = smaller/faster/lower quality)

To improve quality (slower):
- Change `veryfast` to `slow` or `medium`
- Decrease CRF from 18 to 15 (lower = larger/slower/higher quality)

## Environment Variables

None currently used. Tools are detected at runtime via `shutil.which()`.
