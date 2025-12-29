import json
import os
import requests
from datetime import datetime
from pathlib import Path
import platform
import subprocess
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import logging
import zipfile
import tempfile
import re
import webbrowser

# For PIL and piexif: detect availability separately
HAS_PIEXIF = False
HAS_PIL = False
try:
    # Try to import PIL.Image independently so we can use it even if piexif is missing
    from PIL import Image as PILImage
    HAS_PIL = True
except Exception:
    HAS_PIL = False

try:
    # piexif is optional and required only for writing EXIF
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    import piexif
    HAS_PIEXIF = True
except Exception:
    HAS_PIEXIF = False

# For setting video metadata without ffmpeg
try:
    from mutagen.mp4 import MP4
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False

# For video conversion (HEVC to H.264)
try:
    import av
    HAS_PYAV = True
except ImportError:
    HAS_PYAV = False

# For VLC-based video conversion
try:
    import vlc
    HAS_VLC = True
except (ImportError, FileNotFoundError, OSError):
    HAS_VLC = False

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG for verbose logging
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("debug.log"),  # Log to a file
        logging.StreamHandler()  # Log to console
    ]
)

# ==================== Core Functions (from original script) ====================

# --- Delegated to refactored utility module ---
import snap_utils, exif_utils, video_utils, zip_utils, downloader

def parse_date(date_str):
    """Parse date string from JSON format to datetime object. Delegates to snap_utils."""
    return snap_utils.parse_date(date_str)

def parse_location(location_str):
    """Parse location string to get latitude and longitude. Delegates to snap_utils."""
    return snap_utils.parse_location(location_str)

def decimal_to_dms(decimal):
    """Convert decimal degrees to degrees, minutes, seconds format for EXIF. Delegates to snap_utils."""
    return snap_utils.decimal_to_dms(decimal)


def set_image_exif_metadata(file_path, date_obj, latitude, longitude):
    """Set EXIF metadata for image files. Delegates to exif_utils."""
    return exif_utils.set_image_exif_metadata(file_path, date_obj, latitude, longitude)

def check_ffmpeg():
    """Check if ffmpeg is available on the system. Delegates to video_utils."""
    return video_utils.check_ffmpeg()

def check_vlc():
    """Check if VLC Python bindings are available. Delegates to video_utils."""
    return video_utils.check_vlc()

def find_vlc_executable():
    """Find VLC executable on the system. Delegates to video_utils."""
    return video_utils.find_vlc_executable()

def convert_with_vlc(input_path, output_path=None):
    """Convert video using VLC - delegated to video_utils."""
    return video_utils.convert_with_vlc(input_path, output_path)

def convert_with_vlc_python(input_path, output_path):
    """Convert video using VLC Python bindings - delegated to video_utils."""
    return video_utils.convert_with_vlc_python(input_path, output_path)

def convert_with_vlc_subprocess(input_path, output_path):
    """Convert video using VLC command-line interface via subprocess."""
    vlc_path = find_vlc_executable()
    if not vlc_path:
        logging.error("VLC executable not found on system")
        return False, "VLC not installed"
    
    try:
        logging.info(f"Converting with VLC (subprocess): {input_path}")
        
        # VLC command-line conversion
        # This matches the VLC GUI profile: Video - H.264 + MP3 (MP4)
        cmd = [
            vlc_path,
            "-I", "dummy",  # No interface
            "--no-repeat",
            "--no-loop",
            input_path,
            "--sout", (
                f"#transcode{{"
                f"vcodec=h264,"
                f"venc=x264{{"
                    f"preset=medium,"
                    f"profile=main"
                f"}},"
                f"acodec=mp3,"
                f"ab=192,"
                f"channels=2,"
                f"samplerate=44100"
                f"}}:"
                f"standard{{"
                    f"access=file,"
                    f"mux=mp4,"
                    f"dst={output_path}"
                f"}}"
            ),
            "vlc://quit"
        ]
        
        logging.debug(f"VLC command: {' '.join(cmd)}")
        
        # Run VLC conversion
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        # Check if output file was created
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            logging.info(f"VLC subprocess conversion successful: {output_path}")
            return True, output_path
        else:
            logging.error(f"VLC subprocess conversion failed - output file not created or too small")
            if os.path.exists(output_path):
                os.remove(output_path)
            return False, "VLC subprocess conversion failed"
            
    except subprocess.TimeoutExpired:
        logging.error("VLC subprocess conversion timed out")
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass
        return video_utils.convert_with_vlc_subprocess(input_path, output_path)
    except Exception as e:
        logging.error(f"VLC subprocess conversion error: {e}", exc_info=True)
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass
        return video_utils.convert_with_vlc_subprocess(input_path, output_path)

def set_video_metadata(file_path, date_obj, latitude, longitude):
    """Set metadata for video files. Delegates to video_utils."""
    return video_utils.set_video_metadata(file_path, date_obj, latitude, longitude)

def set_video_metadata_ffmpeg(file_path, date_obj, latitude, longitude):
    """Set video metadata using ffmpeg if available. Delegates to video_utils."""
    return video_utils.set_video_metadata_ffmpeg(file_path, date_obj, latitude, longitude)

def set_file_timestamps(file_path, date_obj):
    """Set file modification and access times. Delegates to snap_utils."""
    return snap_utils.set_file_timestamps(file_path, date_obj)


def enforce_portrait_video(file_path, timeout=300):
    """Ensure the video is portrait (height >= width). Delegates to video_utils."""
    return video_utils.enforce_portrait_video(file_path, timeout)

def convert_hevc_to_h264(input_path, output_path=None, max_attempts=3, failed_dir_path="downloads/failed_conversions"):
    """Convert any video to H.264 for better compatibility. Delegates to video_utils."""
    return video_utils.convert_hevc_to_h264(input_path, output_path, max_attempts, failed_dir_path)

def extract_media_from_zip(zip_path, output_path):
    """Extract media file from ZIP archive. Delegates to zip_utils."""
    return zip_utils.extract_media_from_zip(zip_path, output_path)

def merge_images(main_img_path, overlay_img_path, output_path):
    """Merge overlay image on top of main image and save to output_path. Delegates to zip_utils."""
    return zip_utils.merge_images(main_img_path, overlay_img_path, output_path)

def merge_video_overlay(main_video_path, overlay_image_path, output_path):
    """Overlay an image on top of a video using ffmpeg. Delegates to zip_utils."""
    return zip_utils.merge_video_overlay(main_video_path, overlay_image_path, output_path)

def merge_images(main_img_path, overlay_img_path, output_path):
    """Merge overlay image on top of main image and save to output_path.

    - Resizes overlay to match main if sizes differ.
    - Preserves alpha channel if present by converting to RGBA.
    """
    if not HAS_PIL:
        logging.error("Pillow is not installed; cannot merge images")
        return False, "Pillow not installed"

    try:
        main = PILImage.open(main_img_path).convert('RGBA')
        overlay = PILImage.open(overlay_img_path).convert('RGBA')

        if overlay.size != main.size:
            overlay = overlay.resize(main.size, PILImage.LANCZOS)

        merged = PILImage.alpha_composite(main, overlay)

        # Determine output format from output_path extension
        ext = Path(output_path).suffix.lower()
        if ext in ['.jpg', '.jpeg']:
            # JPEG doesn't support alpha; flatten against white background
            bg = PILImage.new('RGB', merged.size, (255, 255, 255))
            bg.paste(merged, mask=merged.split()[3])
            bg.save(output_path, quality=95)
        else:
            # PNG or other formats supporting alpha
            merged.save(output_path)

        return True, output_path

    except Exception as e:
        logging.error(f"Error merging images: {e}", exc_info=True)
        return False, str(e)


def merge_video_overlay(main_video_path, overlay_image_path, output_path):
    """Overlay an image on top of a video using ffmpeg.

    Returns (True, output_path) on success or (False, error_message).
    """
    try:
        if not check_ffmpeg():
            logging.warning("ffmpeg not found; cannot merge video overlay")
            return False, "ffmpeg not found"

        # Build ffmpeg command to overlay image onto video (overlay at 0,0)
        # Keep audio stream, encode video with libx264 for compatibility
        cmd = [
            'ffmpeg', '-y',
            '-i', str(main_video_path),
            '-i', str(overlay_image_path),
            '-filter_complex', 'overlay=0:0',
            '-c:a', 'copy',
            '-c:v', 'libx264', '-crf', '18', '-preset', 'veryfast',
            str(output_path)
        ]

        logging.info(f"Running ffmpeg to merge video overlay: {' '.join(cmd)}")
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            logging.error(f"ffmpeg failed: {proc.stderr}")
            return False, proc.stderr

        # Verify output exists and has reasonable size
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return True, str(output_path)
        else:
            return False, "ffmpeg did not produce output file"

    except subprocess.TimeoutExpired:
        return False, "ffmpeg timeout"
    except Exception as e:
        logging.error(f"Error merging video overlay: {e}", exc_info=True)
        return False, str(e)


def process_zip_overlay(zip_path, output_dir, date_obj=None):
    """Extract ZIP to a temp directory, find -main/-overlay pairs, merge them, and save -merged files to output_dir.

    Args:
        zip_path: Path to the ZIP file
        output_dir: Directory to save merged files
        date_obj: Optional datetime object from memories_history.json for accurate filenames

    Returns a list of merged file paths.
    """
    merged_files = []
    temp_dir = None
    try:
        logging.info(f"Processing ZIP for overlays: {zip_path}")
        temp_dir = Path(tempfile.mkdtemp(prefix="zip_extract_"))

        with zipfile.ZipFile(zip_path, 'r') as z:
            # Inspect zip member names (this looks deep into nested folders)
            namelist = [n for n in z.namelist() if not n.endswith('/')]
            z.extractall(temp_dir)

            # Build map by base name from zip members (ignore differing extensions)
            pattern_main = re.compile(r'(?P<base>.+)-main(?P<ext>\.[^.]+)$', re.IGNORECASE)
            pattern_overlay = re.compile(r'(?P<base>.+)-overlay(?P<ext>\.[^.]+)$', re.IGNORECASE)

            # Map basenames to lists of files: {base: {"main": path, "overlay": path}}
            pairs = {}
            for member_name in namelist:
                m_main = pattern_main.search(member_name)
                m_overlay = pattern_overlay.search(member_name)

                if m_main:
                    base = m_main.group('base')
                    if base not in pairs:
                        pairs[base] = {}
                    pairs[base]['main'] = member_name
                elif m_overlay:
                    base = m_overlay.group('base')
                    if base not in pairs:
                        pairs[base] = {}
                    pairs[base]['overlay'] = member_name

        # Now merge pairs
        for base, files in pairs.items():
            main_file = files.get('main')
            overlay_file = files.get('overlay')

            # Only merge if we have both
            if not main_file or not overlay_file:
                continue

            main_path = temp_dir / main_file
            overlay_path = temp_dir / overlay_file

            # Determine type and merge
            # For images: use merge_images
            # For videos: use merge_video_overlay
            ext = Path(main_file).suffix.lower()
            is_video = ext in ['.mp4', '.mov', '.m4v', '.avi', '.mkv']

            # Build output name: replace -main with -merged
            output_name = Path(main_file).name.replace('-main', '-merged')
            output_path = Path(output_dir) / output_name

            if is_video:
                success, result = merge_video_overlay(str(main_path), str(overlay_path), str(output_path))
                if success:
                    # Attempt to ensure merged video is portrait before renaming
                    try:
                        rot_ok, rot_msg = enforce_portrait_video(str(output_path))
                        if rot_ok:
                            logging.info(f"Ensured portrait orientation for merged video: {output_path}")
                        else:
                            logging.warning(f"Could not enforce portrait orientation for {output_path}: {rot_msg}")
                    except Exception as rot_err:
                        logging.debug(f"Error enforcing portrait orientation for merged video: {rot_err}", exc_info=True)

                    # Rename merged file to standard date/time format and remove originals
                    try:
                        # Use date from memories_history.json if available, otherwise use file modification time
                        if date_obj:
                            ts = date_obj
                        else:
                            try:
                                ts = datetime.fromtimestamp(main_path.stat().st_mtime)
                            except Exception:
                                ts = datetime.now()
                        date_name = ts.strftime("%Y%m%d_%H%M%S")
                        new_name = f"{date_name}{output_path.suffix}"
                        new_path = Path(output_dir) / new_name

                        # Ensure uniqueness
                        count = 1
                        while new_path.exists():
                            new_path = Path(output_dir) / f"{date_name}_{count}{output_path.suffix}"
                            count += 1

                        os.rename(output_path, new_path)
                        merged_files.append(str(new_path))
                        logging.info(f"Merged video: {new_path}")

                        # Try to remove the original files if present in output dir (safety) or temp dir
                        try:
                            orig_in_out = Path(output_dir) / Path(main_file).name
                            if orig_in_out.exists() and orig_in_out != new_path:
                                os.remove(orig_in_out)
                                logging.info(f"Removed original main file from output dir: {orig_in_out}")
                        except Exception as rm_err:
                            logging.debug(f"Could not remove original main in output dir: {rm_err}")

                        try:
                            # main_path and overlay_path are in temp dir; attempt removal
                            if main_path.exists():
                                main_path.unlink()
                            if overlay_path.exists():
                                overlay_path.unlink()
                        except Exception:
                            pass

                    except Exception as rename_err:
                        logging.warning(f"Merged but could not rename video {base}: {rename_err}")
                        merged_files.append(str(output_path))
                else:
                    logging.warning(f"Failed to merge video {base}: {result}")
            else:
                # Image
                success, result = merge_images(str(main_path), str(overlay_path), str(output_path))
                if success:
                    try:
                        # Use date from memories_history.json if available, otherwise use file modification time
                        if date_obj:
                            ts = date_obj
                        else:
                            try:
                                ts = datetime.fromtimestamp(main_path.stat().st_mtime)
                            except Exception:
                                ts = datetime.now()
                        date_name = ts.strftime("%Y%m%d_%H%M%S")
                        new_name = f"{date_name}{output_path.suffix}"
                        new_path = Path(output_dir) / new_name

                        # Ensure uniqueness
                        count = 1
                        while new_path.exists():
                            new_path = Path(output_dir) / f"{date_name}_{count}{output_path.suffix}"
                            count += 1

                        os.rename(output_path, new_path)
                        merged_files.append(str(new_path))
                        logging.info(f"Merged image: {new_path}")

                        # Remove originals if present in output dir and temp dir
                        try:
                            orig_in_out = Path(output_dir) / Path(main_file).name
                            if orig_in_out.exists() and orig_in_out != new_path:
                                os.remove(orig_in_out)
                                logging.info(f"Removed original main file from output dir: {orig_in_out}")
                        except Exception as rm_err:
                            logging.debug(f"Could not remove original main in output dir: {rm_err}")

                        try:
                            if main_path.exists():
                                main_path.unlink()
                            if overlay_path.exists():
                                overlay_path.unlink()
                        except Exception:
                            pass

                    except Exception as rename_err:
                        logging.warning(f"Merged but could not rename image {base}: {rename_err}")
                        merged_files.append(str(output_path))
                else:
                    logging.warning(f"Failed to merge image {base}: {result}")

        return merged_files

    except Exception as e:
        logging.error(f"Error processing ZIP overlays: {e}", exc_info=True)
        return []
    finally:
        # Clean up temp directory
        if temp_dir and temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
            except Exception as cleanup_error:
                logging.debug(f"Could not clean up temp directory: {cleanup_error}")


def download_media(url, output_path, max_retries=3, progress_callback=None, date_obj=None):
    """Download media file from URL with retry mechanism and optional progress callback.

    Args:
        url: URL to download from
        output_path: Path to save the downloaded file
        max_retries: Number of download attempts
        progress_callback: Optional callback function for progress updates
        date_obj: Optional datetime object from memories_history.json for accurate filenames

    Returns (True, None) on success, (False, None) on failure, or (True, [merged_files]) if ZIP overlay was processed.
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            # Exponential backoff for retries
            if attempt > 0:
                wait_time = 2 ** attempt
                msg = f"Retry attempt {attempt + 1}/{max_retries} after {wait_time}s wait..."
                logging.info(msg)
                if progress_callback:
                    progress_callback(msg)
                time.sleep(wait_time)
            else:
                if progress_callback:
                    progress_callback(f"Attempting download (1/{max_retries})")

            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()

            iterator = response.iter_content(chunk_size=8192)
            try:
                first_chunk = next(iterator)
            except StopIteration:
                last_error = Exception("No content in response")
                if progress_callback:
                    progress_callback("No content returned by server")
                continue

            magic = first_chunk[:32]

            # Detect HTML error pages
            is_html = (magic[:5].lower() == b'<!doc' or
                       magic[:5].lower() == b'<html' or
                       b'<html' in magic.lower() or
                       b'<!doctype' in magic.lower())
            if is_html:
                last_error = Exception("HTML page instead of media file")
                if progress_callback:
                    progress_callback("Downloaded content is HTML (likely an error page), will retry if possible")
                continue

            # If ZIP, write directly to .zip target to avoid rename races
            is_valid_zip = magic[:4] == b'PK\x03\x04'
            if is_valid_zip:
                zip_path = str(output_path) + ".zip"
                write_path = zip_path
            else:
                write_path = output_path

            # Write the first chunk and remaining content
            try:
                with open(write_path, 'wb') as fd:
                    fd.write(first_chunk)
                    for chunk in iterator:
                        if chunk:
                            fd.write(chunk)
            except Exception as write_err:
                last_error = write_err
                logging.warning(f"Failed writing downloaded file to {write_path}: {write_err}")
                try:
                    if os.path.exists(write_path):
                        os.remove(write_path)
                except Exception:
                    pass
                continue

            # If we downloaded a ZIP, try to process it
            if is_valid_zip:
                try:
                    if progress_callback:
                        progress_callback("Downloaded ZIP archive, processing...")
                    merged = process_zip_overlay(write_path, str(Path(output_path).parent), date_obj)
                    if merged:
                        try:
                            os.remove(write_path)
                        except Exception:
                            pass
                        logging.info(f"Created merged images: {merged}")
                        return (True, merged)
                    # Fallback: extract first media file from ZIP into output_path
                    if extract_media_from_zip(write_path, output_path):
                        try:
                            os.remove(write_path)
                        except Exception:
                            pass
                        # Validate the extracted file below using output_path
                        final_path = output_path
                    else:
                        logging.warning(f"Could not extract media from ZIP: {write_path}")
                        final_path = write_path
                except Exception as zip_err:
                    logging.warning(f"Error handling ZIP file: {zip_err}")
                    final_path = write_path
            else:
                final_path = write_path

            # Final validations on the file we will use
            if not os.path.exists(final_path):
                last_error = Exception(f"Downloaded file missing: {final_path}")
                logging.warning(str(last_error))
                if progress_callback:
                    progress_callback(str(last_error))
                continue

            file_size = os.path.getsize(final_path)
            if file_size < 100:
                logging.warning(f"Downloaded file too small ({file_size} bytes), attempt {attempt + 1}/{max_retries}")
                try:
                    os.remove(final_path)
                except Exception:
                    pass
                last_error = Exception("File too small")
                if progress_callback:
                    progress_callback(f"Downloaded file too small ({file_size} bytes), will retry if possible")
                continue

            # Success
            msg = f"Successfully downloaded file ({file_size} bytes)"
            logging.info(msg)
            if progress_callback:
                progress_callback(msg)
            return (True, None)

        except requests.exceptions.RequestException as req_err:
            last_error = req_err
            logging.warning(f"Download attempt {attempt + 1}/{max_retries} failed: {req_err}")
            if progress_callback:
                progress_callback(f"Download attempt {attempt + 1}/{max_retries} failed: {req_err}")
            # Clean up possible partial files
            try:
                if os.path.exists(output_path):
                    os.remove(output_path)
            except Exception:
                pass
            continue
        except Exception as err:
            last_error = err
            logging.error(f"Unexpected error during download attempt {attempt + 1}/{max_retries}: {err}", exc_info=True)
            if progress_callback:
                progress_callback(f"Unexpected error during download attempt {attempt + 1}/{max_retries}: {err}")
            try:
                if os.path.exists(output_path):
                    os.remove(output_path)
            except Exception:
                pass
            continue

    # Exhausted retries
    logging.error(f"Download failed after {max_retries} attempts. Last error: {last_error}")
    if progress_callback:
        progress_callback(f"Download failed after {max_retries} attempts. Last error: {last_error}")
    return (False, None)


def validate_downloaded_file(file_path):
    """Validate the downloaded file to ensure it is complete and not corrupted."""
    try:
        logging.info(f"Validating downloaded file: {file_path}")

        # Check if file exists
        if not os.path.exists(file_path):
            logging.error(f"File does not exist: {file_path}")
            return False

        # Check file size
        file_size = os.path.getsize(file_path)
        if file_size < 100:  # Arbitrary minimum size for a valid file
            logging.error(f"File is too small to be valid: {file_size} bytes")
            return False

        # Read the first few bytes to check for valid magic numbers
        with open(file_path, 'rb') as f:
            magic = f.read(32)

        # Check for valid image formats
        is_valid_jpg = magic[:2] == b'\xff\xd8' or magic[:3] == b'\xff\xd8\xff'
        is_valid_png = magic[:8] == b'\x89PNG\r\n\x1a\n'

        # Check for valid video formats (MP4, MOV, M4V)
        is_valid_mp4 = (
            len(magic) >= 12 and 
            (magic[4:8] == b'ftyp' or  # Standard MP4
             magic[4:8] == b'mdat' or  # Media data
             magic[4:8] == b'moov' or  # Movie atom
             magic[4:8] == b'wide')    # Wide atom
        )
        
        # Check for ZIP file (some Snapchat exports use ZIP)
        is_valid_zip = magic[:4] == b'PK\x03\x04'

        # If the file doesn't match expected formats, it might be corrupted
        if not (is_valid_jpg or is_valid_png or is_valid_mp4 or is_valid_zip):
            magic_hex = magic[:8].hex()
            logging.error(f"File format is not recognized or is corrupted (magic: {magic_hex}).")
            return False

        logging.info("File validation successful.")
        return True

    except Exception as e:
        logging.error(f"Error during file validation: {e}", exc_info=True)
        return False

def get_file_extension(media_type):
    """Determine file extension based on media type."""
    if media_type == "Image":
        return ".jpg"
    elif media_type == "Video":
        return ".mp4"
    else:
        return ".bin"

# ==================== GUI Application ====================

# --- Wrappers to refactored modules (override long original implementations) ---
def extract_media_from_zip(zip_path, output_path):
    return zip_utils.extract_media_from_zip(zip_path, output_path)


def process_zip_overlay(zip_path, output_dir, date_obj=None):
    return zip_utils.process_zip_overlay(zip_path, output_dir, date_obj)


def merge_images(main_img_path, overlay_img_path, output_path):
    return zip_utils.merge_images(main_img_path, overlay_img_path, output_path)


def merge_video_overlay(main_video_path, overlay_image_path, output_path):
    return zip_utils.merge_video_overlay(main_video_path, overlay_image_path, output_path)


def download_media(url, output_path, max_retries=3, progress_callback=None, date_obj=None):
    return downloader.download_media(url, output_path, max_retries, progress_callback, date_obj)


def validate_downloaded_file(file_path):
    return snap_utils.validate_downloaded_file(file_path)


def get_file_extension(media_type):
    return snap_utils.get_file_extension(media_type)


class ScrollableFrame(ttk.Frame):
    """A scrollable frame that allows vertical scrolling of its content."""
    def __init__(self, container, *args, **kwargs):
        super().__init__(container)
        # Canvas for scrolling
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.v_scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.v_scrollbar.set)

        # Pack canvas and scrollbar
        self.canvas.pack(side="left", fill="both", expand=True)
        self.v_scrollbar.pack(side="right", fill="y")

        # Inner frame where widgets should be placed
        self.frame = ttk.Frame(self.canvas, *args, **kwargs)
        self._window = self.canvas.create_window((0, 0), window=self.frame, anchor="nw")

        # Update scrollregion when inner frame changes size
        self.frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        # Make inner window width match canvas width
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width))

        # Mouse wheel support (Windows / macOS typical behavior)
        def _on_mousewheel(event):
            try:
                delta = int(-1 * (event.delta / 120))
            except Exception:
                delta = 0
            if delta:
                self.canvas.yview_scroll(delta, "units")

        # Bind mousewheel to the canvas
        self.canvas.bind_all("<MouseWheel>", _on_mousewheel)

class SnapchatDownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Snapchat Memories Downloader")
        self.root.geometry("700x700")
        self.root.resizable(True, True)
        self.root.minsize(700, 600)
        
        # Variables
        self.json_path = tk.StringVar()
        self.output_path = tk.StringVar(value="downloads")
        # Conversion is automatic when tools are available; no checkbox in UI
        self.max_retries = tk.IntVar(value=3)  # Number of download attempts (initial + retries)
        default_threads = 3
        self.max_threads = min(8, max(1, (os.cpu_count() or 4)))
        self.is_downloading = False
        self.stop_download = False
        
        # Configure style
        self.setup_styles()
        
        # Build UI
        self.create_widgets()
        
        # Center window
        self.center_window()
    
    def setup_styles(self):
        """Configure ttk styles for a modern look."""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Colors
        bg_color = "#f5f6fa"
        primary_color = "#3742fa"
        secondary_color = "#5f27cd"
        success_color = "#00d2d3"
        text_color = "#2f3542"
        
        # Configure root background
        self.root.configure(bg=bg_color)
        
        # Frame style
        style.configure("Card.TFrame", background="white", relief="flat")
        style.configure("Main.TFrame", background=bg_color)
        
        # Label styles
        style.configure("Title.TLabel", background="white", foreground=text_color, 
                       font=("Segoe UI", 18, "bold"))
        style.configure("Subtitle.TLabel", background="white", foreground="#747d8c", 
                       font=("Segoe UI", 10))
        style.configure("Header.TLabel", background="white", foreground=text_color, 
                       font=("Segoe UI", 11, "bold"))
        style.configure("Info.TLabel", background="white", foreground="#747d8c", 
                       font=("Segoe UI", 9))
        style.configure("Status.TLabel", background="white", foreground=text_color, 
                       font=("Segoe UI", 9))
        
        # Button styles
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), 
                       padding=10, relief="flat")
        style.map("Primary.TButton",
                 foreground=[("active", "white"), ("!active", "white"), ("disabled", "#a4b0be")],
                 background=[("active", secondary_color), ("!active", primary_color), ("disabled", "#dfe4ea")])
        
        style.configure("Secondary.TButton", font=("Segoe UI", 9), 
                       padding=8, relief="flat")
        
        style.configure("Stop.TButton", font=("Segoe UI", 9, "bold"), 
                       padding=8, relief="flat")
        style.map("Stop.TButton",
                 foreground=[("active", "white"), ("!active", "white"), ("disabled", "#a4b0be")],
                 background=[("active", "#c23616"), ("!active", "#e84118"), ("disabled", "#dfe4ea")])
        
        # Progressbar style
        style.configure("Custom.Horizontal.TProgressbar", 
                       troughcolor=bg_color, 
                       background=success_color, 
                       thickness=20)
    
    def center_window(self):
        """Center the window on the screen."""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def create_widgets(self):
        """Create and layout all widgets."""
        # Main container (scrollable)
        scroll_container = ScrollableFrame(self.root, style="Main.TFrame", padding=20)
        scroll_container.pack(fill=tk.BOTH, expand=True)
        main_frame = scroll_container.frame
        
        # Header card
        header_card = ttk.Frame(main_frame, style="Card.TFrame", padding=20)
        header_card.pack(fill=tk.X, pady=(0, 20))
        
        title_label = ttk.Label(header_card, text="Snapchat Memories Downloader", 
                               style="Title.TLabel")
        title_label.pack(anchor=tk.W)
        
        subtitle_label = ttk.Label(header_card, 
                                   text="Download your Snapchat memories with metadata preservation", 
                                   style="Subtitle.TLabel")
        subtitle_label.pack(anchor=tk.W, pady=(5, 0))
        
        # Input card
        input_card = ttk.Frame(main_frame, style="Card.TFrame", padding=20)
        input_card.pack(fill=tk.X, pady=(0, 20))
        
        # JSON file selection
        json_label = ttk.Label(input_card, text="JSON File", style="Header.TLabel")
        json_label.pack(anchor=tk.W, pady=(0, 8))
        
        json_frame = ttk.Frame(input_card, style="Card.TFrame")
        json_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.json_entry = ttk.Entry(json_frame, textvariable=self.json_path, 
                                    font=("Segoe UI", 9), width=50)
        self.json_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        json_btn = ttk.Button(json_frame, text="Browse...", 
                             command=self.browse_json, style="Secondary.TButton")
        json_btn.pack(side=tk.LEFT)
        
        json_info = ttk.Label(input_card, 
                             text="Select your memories_history.json file from Snapchat export", 
                             style="Info.TLabel")
        json_info.pack(anchor=tk.W, pady=(0, 15))
        
        # Output directory selection
        output_label = ttk.Label(input_card, text="Output Directory", style="Header.TLabel")
        output_label.pack(anchor=tk.W, pady=(0, 8))
        
        output_frame = ttk.Frame(input_card, style="Card.TFrame")
        output_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_path, 
                                      font=("Segoe UI", 9), width=50)
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        output_btn = ttk.Button(output_frame, text="Browse...", 
                               command=self.browse_output, style="Secondary.TButton")
        output_btn.pack(side=tk.LEFT)
        
        output_info = ttk.Label(input_card, 
                               text="Choose where to save your downloaded memories", 
                               style="Info.TLabel")
        output_info.pack(anchor=tk.W, pady=(0, 15))
        
        # Conversion tools status (ffmpeg / VLC) with install links if missing
        tools_frame = ttk.Frame(input_card, style="Card.TFrame")
        tools_frame.pack(fill=tk.X, pady=(0, 20))

        tools_header = ttk.Label(tools_frame, text="Conversion Tools", style="Header.TLabel")
        tools_header.pack(anchor=tk.W)

        # ffmpeg status
        ffmpeg_installed = check_ffmpeg()
        ffmpeg_text = "✓ ffmpeg installed" if ffmpeg_installed else "⚠ ffmpeg not found — click to download"
        ffmpeg_label = ttk.Label(tools_frame, text=ffmpeg_text, style="Info.TLabel", cursor=("hand2" if not ffmpeg_installed else "arrow"))
        ffmpeg_label.pack(anchor=tk.W, padx=(6,0))
        if not ffmpeg_installed:
            ffmpeg_label.bind("<Button-1>", lambda e: webbrowser.open("https://ffmpeg.org/download.html"))

        # VLC status
        vlc_path = find_vlc_executable()
        vlc_installed = bool(vlc_path or HAS_VLC)
        if vlc_installed and vlc_path:
            vlc_text = f"✓ VLC installed ({vlc_path})"
        elif HAS_VLC:
            vlc_text = "✓ VLC Python bindings available"
        else:
            vlc_text = "⚠ VLC not found — click to download"
        vlc_label = ttk.Label(tools_frame, text=vlc_text, style="Info.TLabel", cursor=("hand2" if not vlc_installed else "arrow"))
        vlc_label.pack(anchor=tk.W, padx=(6,0))
        if not vlc_installed:
            vlc_label.bind("<Button-1>", lambda e: webbrowser.open("https://www.videolan.org/vlc/"))

        info_label = ttk.Label(
            tools_frame,
            text=("Videos will be converted to H.264 automatically when tools are available. "
                  "ffmpeg/VLC are also used to merge Snapchat captions back onto photos or videos; "
                  "click the links to download."),
            style="Info.TLabel",
            wraplength=520,
            justify=tk.LEFT
        )
        info_label.pack(anchor=tk.W, pady=(6, 0))
        # Update wraplength dynamically so the text wraps with the frame width
        tools_frame.bind("<Configure>", lambda e: info_label.config(wraplength=max(e.width - 12, 200)))

        # Small action buttons to open the download pages for ffmpeg and VLC
        download_buttons_frame = ttk.Frame(tools_frame, style="Card.TFrame")
        download_buttons_frame.pack(anchor=tk.W, pady=(8, 0))

        ffmpeg_btn_text = "Open ffmpeg" if ffmpeg_installed else "Download ffmpeg"
        ffmpeg_btn = ttk.Button(download_buttons_frame, text=ffmpeg_btn_text, style="Secondary.TButton", width=18,
                                command=lambda: webbrowser.open("https://ffmpeg.org/download.html"))
        ffmpeg_btn.pack(side=tk.LEFT, padx=(6, 8))

        vlc_btn_text = "Open VLC" if vlc_installed else "Download VLC"
        vlc_btn = ttk.Button(download_buttons_frame, text=vlc_btn_text, style="Secondary.TButton", width=18,
                             command=lambda: webbrowser.open("https://www.videolan.org/vlc/"))
        vlc_btn.pack(side=tk.LEFT)
        
        # Download retries option
        retries_frame = ttk.Frame(input_card, style="Card.TFrame")
        retries_frame.pack(fill=tk.X, pady=(8, 12))
        
        retries_label = ttk.Label(retries_frame, text="Download Retries:", style="Header.TLabel")
        retries_label.pack(side=tk.LEFT)
        
        # Use a Spinbox for retry count
        retries_spin = tk.Spinbox(retries_frame, from_=1, to=10, width=5, textvariable=self.max_retries)
        retries_spin.pack(side=tk.LEFT, padx=(8, 0))
        
        retries_info = ttk.Label(input_card,
                                 text="Number of download attempts (initial try + retries)",
                                 style="Info.TLabel")
        retries_info.pack(anchor=tk.W, pady=(6, 10))

        # Download threads option
        threads_frame = ttk.Frame(input_card, style="Card.TFrame")
        threads_frame.pack(fill=tk.X, pady=(0, 12))

        threads_label = ttk.Label(threads_frame, text="Download Threads:", style="Header.TLabel")
        threads_label.pack(side=tk.LEFT)

        threads_spin = tk.Spinbox(threads_frame, from_=1, to=16, width=5, textvariable=self.max_threads)
        threads_spin.pack(side=tk.LEFT, padx=(8, 0))

        threads_info = ttk.Label(input_card,
                                 text="Number of concurrent downloads (higher uses more bandwidth/CPU)",
                                 style="Info.TLabel")
        threads_info.pack(anchor=tk.W, pady=(6, 10))

        # Check available conversion tools and display status
        # conversion_status = self.get_conversion_status()
        # conversion_info = ttk.Label(input_card,
        #                            text=conversion_status,
        #                            style="Info.TLabel")
        # conversion_info.pack(anchor=tk.W, pady=(0, 20))
        
        # Buttons
        button_frame = ttk.Frame(input_card, style="Card.TFrame")
        button_frame.pack(fill=tk.X)
        
        self.download_btn = ttk.Button(button_frame, text="Start Download", 
                                      command=self.start_download, 
                                      style="Primary.TButton")
        self.download_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_btn = ttk.Button(button_frame, text="⏹ Stop", 
                                   command=self.stop_download_func, 
                                   style="Stop.TButton", state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT)
        
        # Progress card
        self.progress_card = ttk.Frame(main_frame, style="Card.TFrame", padding=20)
        self.progress_card.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        progress_label = ttk.Label(self.progress_card, text="Download Progress", 
                                   style="Header.TLabel")
        progress_label.pack(anchor=tk.W, pady=(0, 15))
        
        # Progress bar
        self.progress_bar = ttk.Progressbar(self.progress_card, 
                                           style="Custom.Horizontal.TProgressbar",
                                           mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 10))
        
        # Status label
        self.status_label = ttk.Label(self.progress_card, 
                                     text="Ready to download", 
                                     style="Status.TLabel")
        self.status_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Log area
        log_frame = ttk.Frame(self.progress_card, style="Card.TFrame")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Allow the log area to resize with the window by not forcing a fixed height
        self.log_text = tk.Text(log_frame, wrap=tk.WORD,
                       font=("Consolas", 9), bg="#f8f9fa",
                       fg="#2f3542", relief=tk.FLAT,
                       yscrollcommand=scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)
    
    def browse_json(self):
        """Open file dialog to select JSON file."""
        filename = filedialog.askopenfilename(
            title="Select Snapchat Memories JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filename:
            self.json_path.set(filename)
    
    def browse_output(self):
        """Open dialog to select output directory."""
        directory = filedialog.askdirectory(title="Select Output Directory")
        if directory:
            self.output_path.set(directory)
    
    def get_conversion_status(self):
        """Check what conversion tools are available and return status message."""
        tools = []
        
        if HAS_PYAV:
            tools.append("PyAV")
        
        vlc_exe = find_vlc_executable()
        if vlc_exe or HAS_VLC:
            tools.append("VLC")
        
        if not tools:
            return ("⚠ No conversion tools found. Videos will be downloaded in original format.\n"
                    "Install PyAV (pip install av) or VLC (https://www.videolan.org/) for H.264 conversion.")
        
        tools_str = " & ".join(tools)
        return f"✓ Conversion available via {tools_str}. Videos will be converted to H.264 for Windows compatibility."
    
    def log(self, message):
        """Add message to log area."""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def update_progress(self, current, total):
        """Update progress bar."""
        progress = (current / total) * 100
        self.progress_bar['value'] = progress
        self.status_label.config(text=f"⬇ Downloading {current} of {total}...", foreground="#00d2d3")
        self.root.update_idletasks()
    
    def start_download(self):
        """Start the download process."""
        if self.is_downloading:
            return
        
        json_file = self.json_path.get()
        output_dir = self.output_path.get()
        
        if not json_file:
            messagebox.showerror("Error", "Please select a JSON file")
            return
        
        if not os.path.exists(json_file):
            messagebox.showerror("Error", f"JSON file not found: {json_file}")
            return
        
        if not output_dir:
            messagebox.showerror("Error", "Please select an output directory")
            return
        
        # Clear log
        self.log_text.delete(1.0, tk.END)
        
        # Update UI state with visual feedback
        self.is_downloading = True
        self.stop_download = False
        self.download_btn.config(state=tk.DISABLED, text="⏳ Downloading...")
        self.stop_btn.config(state=tk.NORMAL)
        self.progress_bar['value'] = 0
        self.status_label.config(text="🔄 Starting download...", foreground="#00d2d3")
        
        # Start download in separate thread
        thread = threading.Thread(target=self.download_thread, 
                                 args=(json_file, output_dir))
        thread.daemon = True
        thread.start()
    
    def stop_download_func(self):
        """Stop the download process."""
        self.stop_download = True
        self.stop_btn.config(state=tk.DISABLED, text="⏹ Stopping...")
        self.status_label.config(text="⚠ Stopping download...", foreground="#f39c12")
        self.log("⚠ Stopping download...")

    def process_media_item(self, idx, total, item, output_path, max_retries):
        logs = [f"[{idx}/{total}] Processing..."]

        def log_local(message):
            logs.append(message)

        def progress_callback(message):
            log_local(f"  {message}")

        try:
            # Extract metadata
            date_str = item.get("Date", "")
            media_type = item.get("Media Type", "Unknown")
            location_str = item.get("Location", "")
            download_url = item.get("Media Download Url", "")

            if not download_url:
                log_local("  ⚠ No download URL found, skipping")
                return logs, False, True

            # Parse date and location
            try:
                date_obj = parse_date(date_str)
            except Exception:
                log_local("  ⚠ Invalid date format, skipping")
                return logs, False, True

            latitude, longitude = parse_location(location_str)

            # Log location data for debugging
            if latitude is not None and longitude is not None:
                log_local(f"  📍 Location: {latitude}, {longitude}")
            else:
                log_local("  📍 No location data available")

            # Generate filename
            date_formatted = date_obj.strftime("%Y%m%d_%H%M%S")
            extension = get_file_extension(media_type)
            filename = f"{date_formatted}_{idx}{extension}"
            file_path = output_path / filename

            log_local(f"  File: {filename}")
            log_local(f"  Type: {media_type}")

            # Download file
            download_success, merged_files = download_media(
                download_url,
                str(file_path),
                max_retries=max_retries,
                progress_callback=progress_callback,
                date_obj=date_obj
            )

            if download_success:
                log_local("  ✓ Downloaded")

                # If merged files were created from ZIP overlay, apply metadata to each
                if merged_files:
                    log_local(f"  ℹ Processing {len(merged_files)} merged file(s) from ZIP overlay")
                    for merged_file in merged_files:
                        merged_path = Path(merged_file)
                        log_local(f"  📄 {merged_path.name}")

                        # Determine if it's a video or image
                        ext = merged_path.suffix.lower()
                        is_video = ext in ['.mp4', '.mov', '.m4v', '.avi', '.mkv']

                        if is_video:
                            # Ensure portrait orientation for merged video
                            try:
                                rot_ok, rot_msg = enforce_portrait_video(str(merged_path))
                                if rot_ok:
                                    log_local("    ✓ Ensured portrait orientation")
                                else:
                                    log_local(f"    ⚠ Could not enforce portrait orientation: {rot_msg}")
                            except Exception as e:
                                log_local(f"    ⚠ Error enforcing portrait orientation: {e}")

                            # Set video metadata - try ffmpeg first for better compatibility, then mutagen
                            metadata_set = False

                            # Try ffmpeg first (sets standard creation_time metadata)
                            try:
                                if set_video_metadata_ffmpeg(str(merged_path), date_obj, latitude, longitude):
                                    log_local("    ✓ Set video metadata (ffmpeg)")
                                    metadata_set = True
                            except Exception as ffmpeg_error:
                                log_local(f"    ℹ ffmpeg metadata setting failed, trying mutagen: {ffmpeg_error}")

                            # Fall back to mutagen if ffmpeg didn't work
                            if not metadata_set and HAS_MUTAGEN:
                                try:
                                    if set_video_metadata(str(merged_path), date_obj, latitude, longitude):
                                        log_local("    ✓ Set video metadata (mutagen)")
                                        metadata_set = True
                                except Exception as metadata_error:
                                    log_local(f"    ⚠ Metadata error: {metadata_error}")

                            if not metadata_set:
                                log_local("    ℹ Video metadata not set (install ffmpeg or mutagen)")

                            set_file_timestamps(str(merged_path), date_obj)
                            log_local("    ✓ Set file timestamps")
                        else:
                            # Set image metadata
                            if HAS_PIEXIF and ext in ['.jpg', '.jpeg']:
                                try:
                                    set_image_exif_metadata(str(merged_path), date_obj, latitude, longitude)
                                    log_local("    ✓ Set EXIF metadata")
                                except Exception as exif_error:
                                    log_local(f"    ⚠ EXIF metadata error: {exif_error}")
                            set_file_timestamps(str(merged_path), date_obj)
                            log_local("    ✓ Set file timestamps")

                    return logs, True, False

                # Set metadata
                if media_type == "Image" and extension.lower() in ['.jpg', '.jpeg']:
                    if HAS_PIEXIF:
                        try:
                            set_image_exif_metadata(str(file_path), date_obj, latitude, longitude)
                            log_local("  ✓ Set EXIF metadata")
                        except Exception as exif_error:
                            log_local(f"  ⚠ EXIF metadata error: {exif_error}")
                    # Always set file timestamps for images
                    set_file_timestamps(str(file_path), date_obj)
                elif media_type == "Video":
                    # Convert all videos to H.264 by default
                    log_local("  🔄 Converting to H.264...")

                    # Check if any conversion tool is available
                    if not HAS_PYAV and not find_vlc_executable() and not HAS_VLC:
                        log_local("  ⚠ No conversion tools available - keeping original format")
                        log_local("  ℹ Install PyAV (pip install av) or VLC for automatic H.264 conversion")
                        # Still count as success - video was downloaded
                    else:
                        # Pass the custom failed_dir path
                        failed_conversions_dir = str(output_path / "failed_conversions")
                        try:
                            success, result = convert_hevc_to_h264(
                                str(file_path),
                                failed_dir_path=failed_conversions_dir
                            )
                            if success:
                                log_local("  ✓ Converted to H.264")
                                # Replace original with converted file
                                try:
                                    os.remove(str(file_path))
                                    os.rename(result, str(file_path))
                                    # CRITICAL: Set timestamps AFTER file replacement
                                    set_file_timestamps(str(file_path), date_obj)
                                    log_local("  ✓ Set file timestamps")
                                except Exception as rename_error:
                                    log_local(f"  ⚠ Could not replace original: {rename_error}")
                                    # If replacement failed but conversion succeeded, still set timestamps on original
                                    set_file_timestamps(str(file_path), date_obj)
                            else:
                                log_local(f"  ⚠ Conversion failed: {result}")
                                # Don't count as error - file is still downloaded in original format
                                # Set timestamps on original file
                                set_file_timestamps(str(file_path), date_obj)
                        except Exception as conversion_error:
                            log_local(f"  ⚠ Conversion error: {conversion_error}")
                            # Ensure timestamps are set even if conversion crashes
                            set_file_timestamps(str(file_path), date_obj)

                    # Try to set video metadata - use ffmpeg first for better compatibility, then mutagen
                    metadata_set = False

                    # Try ffmpeg first (sets standard creation_time metadata)
                    try:
                        if set_video_metadata_ffmpeg(str(file_path), date_obj, latitude, longitude):
                            log_local("  ✓ Set video metadata (ffmpeg)")
                            metadata_set = True
                    except Exception as ffmpeg_error:
                        logging.debug(f"ffmpeg metadata setting failed: {ffmpeg_error}")

                    # Fall back to mutagen if ffmpeg didn't work
                    if not metadata_set and HAS_MUTAGEN:
                        try:
                            if set_video_metadata(str(file_path), date_obj, latitude, longitude):
                                log_local("  ✓ Set video metadata (mutagen)")
                                metadata_set = True
                        except Exception as metadata_error:
                            log_local(f"  ⚠ Metadata error: {metadata_error}")

                    if not metadata_set:
                        log_local("  ℹ Video downloaded (install ffmpeg or mutagen for embedded metadata)")

                # ALWAYS set file timestamps as final step for any media type
                # This ensures the creation/modification date is correct even if other metadata fails
                # Ensure portrait orientation for videos before finalizing timestamps/metadata
                try:
                    if media_type == "Video":
                        try:
                            rot_ok, rot_msg = enforce_portrait_video(str(file_path))
                            if rot_ok:
                                log_local("  ✓ Ensured portrait orientation")
                            else:
                                log_local(f"  ⚠ Could not enforce portrait orientation: {rot_msg}")
                        except Exception as e:
                            log_local(f"  ⚠ Error enforcing portrait orientation: {e}")
                except Exception:
                    pass

                try:
                    set_file_timestamps(str(file_path), date_obj)
                    log_local("  ✓ File date set correctly")
                except Exception as timestamp_error:
                    log_local(f"  ⚠ Failed to set file timestamps: {timestamp_error}")

                # Validate the downloaded file
                try:
                    if not validate_downloaded_file(str(file_path)):
                        log_local("  ⚠ Downloaded file is corrupted or incomplete")
                        return logs, False, True
                except Exception as validation_error:
                    log_local(f"  ⚠ Validation error: {validation_error}")

                return logs, True, False

            log_local("  ✗ Download failed")
            return logs, False, True

        except Exception as item_error:
            log_local(f"  ✗ Error processing item: {item_error}")
            logging.error(f"Error processing item {idx}: {item_error}", exc_info=True)
            return logs, False, True

    def download_thread(self, json_file, output_dir):
        """Download process running in separate thread."""
        try:
            # Create output directory
            output_path = Path(output_dir)
            output_path.mkdir(exist_ok=True)
            
            # Load JSON
            self.log(f"Loading JSON from: {json_file}")
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Get media items
            media_items = data.get("Saved Media", [])
            total = len(media_items)
            self.log(f"Found {total} media items to download\n")
            
            if total == 0:
                self.log("⚠ No media items found in JSON file")
                self.download_complete()
                return
            
            # Process each item
            success_count = 0
            error_count = 0

            max_retries = self.max_retries.get()
            max_workers = max(1, min(self.max_threads.get(), total))
            self.log(f"Using {max_workers} download thread(s)\n")

            items_iter = iter(enumerate(media_items, 1))
            futures = {}
            completed_count = 0
            stop_logged = False

            def submit_next():
                try:
                    idx, item = next(items_iter)
                except StopIteration:
                    return False

                future = executor.submit(
                    self.process_media_item,
                    idx,
                    total,
                    item,
                    output_path,
                    max_retries
                )
                futures[future] = idx
                return True

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                while len(futures) < max_workers and submit_next():
                    pass

                while futures:
                    done, _ = wait(futures, return_when=FIRST_COMPLETED)
                    for future in done:
                        idx = futures.pop(future)
                        completed_count += 1

                        try:
                            logs, success, error = future.result()
                        except Exception as item_error:
                            logs = [
                                f"[{idx}/{total}] Processing...",
                                f"  ✗ Error processing item: {item_error}"
                            ]
                            logging.error(f"Error processing item {idx}: {item_error}", exc_info=True)
                            success = False
                            error = True

                        for line in logs:
                            self.log(line)

                        if success:
                            success_count += 1
                        if error:
                            error_count += 1

                        self.update_progress(completed_count, total)
                        self.log("")  # Empty line

                        if self.stop_download and not stop_logged:
                            self.log("\n⚠ Download stopped by user")
                            stop_logged = True

                    if self.stop_download:
                        continue

                    while len(futures) < max_workers and submit_next():
                        pass
            
            # Final summary
            self.log("=" * 50)
            self.log(f"Download Complete!")
            self.log(f"Success: {success_count}")
            self.log(f"Failed: {error_count}")
            self.log(f"Total: {total}")
            self.log(f"Output: {output_dir}")
            self.log("=" * 50)
            
            if not self.stop_download:
                messagebox.showinfo("Complete", 
                                   f"Downloaded {success_count} of {total} files\n"
                                   f"Output: {output_dir}")
            
        except Exception as e:
            self.log(f"\n✗ Error: {str(e)}")
            messagebox.showerror("Error", f"An error occurred:\n{str(e)}")
        
        finally:
            self.download_complete()
    
    def download_complete(self):
        """Reset UI after download completes."""
        self.is_downloading = False
        self.download_btn.config(state=tk.NORMAL, text="Start Download")
        self.stop_btn.config(state=tk.DISABLED, text="⏹ Stop")
        if self.stop_download:
            self.status_label.config(text="⚠ Download stopped", foreground="#f39c12")
        else:
            self.status_label.config(text="✅ Download complete", foreground="#27ae60")

# ==================== Main ====================

def main():
    """Main function to run the GUI."""
    root = tk.Tk()
    app = SnapchatDownloaderGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()