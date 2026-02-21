import logging
import shutil
import os
from pathlib import Path
import zipfile
import tempfile
import re
import sys
import subprocess
from datetime import datetime

# Windows-specific subprocess flag to prevent command windows from popping up
CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0

# Pillow detection
HAS_PIL = False
try:
    from PIL import Image as PILImage
    HAS_PIL = True
except Exception:
    HAS_PIL = False


def extract_media_from_zip(zip_path, output_path):
    temp_dir = None
    try:
        logging.info(f"Extracting media from ZIP: {zip_path}")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            media_extensions = ('.jpg', '.jpeg', '.png', '.mp4', '.mov', '.m4v', '.heic')
            media_files = [f for f in file_list if f.lower().endswith(media_extensions)]
            if not media_files:
                logging.warning(f"No media files found in ZIP archive")
                return False
            media_file = media_files[0]
            logging.info(f"Extracting: {media_file}")
            temp_dir = Path(output_path).parent / "temp_extract"
            temp_dir.mkdir(exist_ok=True)
            extracted_path = zip_ref.extract(media_file, temp_dir)
            shutil.move(extracted_path, output_path)
            logging.info(f"Successfully extracted media to: {output_path}")
            return True
    except zipfile.BadZipFile as e:
        logging.warning(f"Invalid ZIP file: {zip_path} - {e}")
        return False
    except Exception as e:
        logging.warning(f"Error extracting ZIP: {e}")
        return False
    finally:
        if temp_dir and temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
            except Exception as cleanup_error:
                logging.debug(f"Could not clean up temp directory: {cleanup_error}")


def merge_images(main_img_path, overlay_img_path, output_path):
    if not HAS_PIL:
        logging.error("Pillow is not installed; cannot merge images")
        return False, "Pillow not installed"

    try:
        main = PILImage.open(main_img_path).convert('RGBA')
        overlay = PILImage.open(overlay_img_path).convert('RGBA')

        if overlay.size != main.size:
            overlay = overlay.resize(main.size, PILImage.LANCZOS)

        merged = PILImage.alpha_composite(main, overlay)
        ext = Path(output_path).suffix.lower()
        if ext in ['.jpg', '.jpeg']:
            bg = PILImage.new('RGB', merged.size, (255, 255, 255))
            bg.paste(merged, mask=merged.split()[3])
            bg.save(output_path, quality=95)
        else:
            merged.save(output_path)

        return True, output_path
    except Exception as e:
        logging.error(f"Error merging images: {e}", exc_info=True)
        return False, str(e)


def merge_video_overlay(main_video_path, overlay_image_path, output_path):
    """Overlay an image (caption) on top of a video using ffmpeg.
    
    CRITICAL FIX: Uses loop filter to repeat the overlay image for the entire video duration.
    Without this, ffmpeg takes the duration of the shortest input (1 second for a static image),
    resulting in a 1-second output video.
    
    Returns (True, output_path) on success or (False, error_message).
    """
    normalized_overlay = None
    try:
        import shutil
        import subprocess
        if shutil.which('ffmpeg') is None:
            logging.warning("ffmpeg not found; cannot merge video overlay")
            return False, "ffmpeg not found"

        # Normalize overlay image to proper PNG format using Pillow
        # This handles WebP, JPEG, and other formats that may have wrong extensions
        # or cause issues with ffmpeg's -loop flag
        if HAS_PIL:
            try:
                logging.debug(f"Normalizing overlay image format: {overlay_image_path}")
                img = PILImage.open(overlay_image_path)
                # Create a temporary PNG file in the same directory
                temp_dir = Path(overlay_image_path).parent
                normalized_overlay = temp_dir / f"{Path(overlay_image_path).stem}_normalized.png"
                img.save(normalized_overlay, format='PNG')
                logging.debug(f"Normalized overlay saved to: {normalized_overlay}")
                # Use the normalized image for ffmpeg
                overlay_to_use = str(normalized_overlay)
            except Exception as normalize_error:
                logging.warning(f"Could not normalize overlay image, using original: {normalize_error}")
                overlay_to_use = str(overlay_image_path)
        else:
            logging.debug("Pillow not available, using original overlay image")
            overlay_to_use = str(overlay_image_path)

        # First, get the duration of the main video to know how long to loop the overlay
        try:
            probe_cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(main_video_path)
            ]
            probe_result = subprocess.run(
                probe_cmd, capture_output=True, text=True, 
                timeout=10, creationflags=CREATE_NO_WINDOW
            )
            video_duration = float(probe_result.stdout.strip())
            logging.info(f"Main video duration: {video_duration} seconds")
        except Exception as probe_error:
            logging.warning(f"Could not determine video duration, using default loop: {probe_error}")
            video_duration = None

        # Build ffmpeg command with proper overlay scaling
        # ffmpeg auto-rotates videos based on metadata by default (-autorotate is on),
        # so the video frames entering the filter graph are already in correct orientation.
        # We only need to scale the overlay image to match the (auto-rotated) video dimensions,
        # then overlay it on top.
        # Using -loop 1 on the image input to loop it, and shortest=1 to end with video.
        cmd = [
            'ffmpeg', '-y',
            '-loop', '1',  # Loop the image input indefinitely
            '-i', overlay_to_use,  # Use normalized overlay
            '-i', str(main_video_path),
            '-filter_complex', 
            '[0:v][1:v]scale2ref[overlay_scaled][video];[video][overlay_scaled]overlay=0:0:shortest=1[outv]',
            '-map', '[outv]',
            '-map', '1:a?',  # Copy audio from main video if it exists
            '-c:a', 'copy',
            '-c:v', 'libx264', '-crf', '18', '-preset', 'veryfast',
            str(output_path)
        ]

        logging.info(f"Running ffmpeg to merge video overlay: {' '.join(cmd)}")
        logging.info(f"Input video: {main_video_path}")
        logging.info(f"Overlay image: {overlay_image_path} (normalized: {overlay_to_use})")
        logging.info(f"Output path: {output_path}")
        
        # Run ffmpeg with Popen to capture real-time progress
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=CREATE_NO_WINDOW
        )
        
        # Read stderr for progress (ffmpeg writes progress to stderr)
        stderr_output = []
        try:
            while True:
                line = proc.stderr.readline()
                if not line and proc.poll() is not None:
                    break
                if line:
                    stderr_output.append(line)
                    # Log progress lines (they contain 'time=' or 'frame=')
                    if 'time=' in line or 'frame=' in line:
                        logging.debug(f"ffmpeg progress: {line.strip()}")
        except Exception as read_error:
            logging.warning(f"Error reading ffmpeg output: {read_error}")
        
        # Wait for completion with timeout
        try:
            proc.wait(timeout=300)
        except subprocess.TimeoutExpired:
            proc.kill()
            logging.error("ffmpeg overlay merge timed out after 300 seconds")
            return False, "ffmpeg timeout"
        
        stderr_text = ''.join(stderr_output)
        proc.returncode = proc.poll()
        stderr_text = ''.join(stderr_output)
        proc.returncode = proc.poll()
        
        if proc.returncode != 0:
            logging.error(f"ffmpeg overlay merge failed with return code {proc.returncode}")
            logging.error(f"ffmpeg stderr: {stderr_text}")
            return False, stderr_text

        # Verify output exists and has reasonable size
        if os.path.exists(output_path):
            output_size = os.path.getsize(output_path)
            logging.info(f"Merged video created: {output_path} ({output_size} bytes)")
            
            if output_size > 1000:
                # Additional verification: check duration of output video
                try:
                    verify_cmd = [
                        'ffprobe', '-v', 'error',
                        '-show_entries', 'format=duration',
                        '-of', 'default=noprint_wrappers=1:nokey=1',
                        str(output_path)
                    ]
                    verify_result = subprocess.run(
                        verify_cmd, capture_output=True, text=True,
                        timeout=10, creationflags=CREATE_NO_WINDOW
                    )
                    output_duration = float(verify_result.stdout.strip())
                    logging.info(f"Output video duration: {output_duration} seconds")
                    
                    if video_duration and output_duration < (video_duration * 0.9):
                        logging.warning(
                            f"Output duration ({output_duration}s) is significantly shorter "
                            f"than input ({video_duration}s) - possible merge issue"
                        )
                except Exception as verify_error:
                    logging.debug(f"Could not verify output duration: {verify_error}")
                
                return True, str(output_path)
            else:
                logging.error(f"Output file too small: {output_size} bytes")
                return False, f"ffmpeg produced file that is too small ({output_size} bytes)"
        else:
            logging.error("ffmpeg did not produce output file")
            return False, "ffmpeg did not produce output file"
            
    except subprocess.TimeoutExpired:
        logging.error("ffmpeg overlay merge timed out after 300 seconds")
        return False, "ffmpeg timeout"
    except Exception as e:
        logging.error(f"Error merging video overlay: {e}", exc_info=True)
        return False, str(e)
    finally:
        # Clean up normalized overlay file if it was created
        if normalized_overlay and os.path.exists(normalized_overlay):
            try:
                os.remove(normalized_overlay)
                logging.debug(f"Cleaned up normalized overlay: {normalized_overlay}")
            except Exception as cleanup_error:
                logging.debug(f"Could not remove normalized overlay: {cleanup_error}")


def process_zip_overlay(zip_path, output_dir, date_obj=None):
    """Process ZIP files containing main and overlay media pairs.
    
    Snapchat exports videos with caption overlays as ZIP files containing:
    - A '-main' file (the original video/image)
    - An '-overlay' file (the caption/sticker overlay)
    
    This function merges these pairs into a single output file.
    
    Args:
        zip_path: Path to the ZIP file
        output_dir: Directory to save merged outputs
        date_obj: Optional datetime object for file naming and metadata
        
    Returns:
        List of merged file paths
    """
    merged_files = []
    temp_dir = None
    try:
        logging.info(f"Processing ZIP for overlays: {zip_path}")
        logging.info(f"Output directory: {output_dir}")
        temp_dir = Path(tempfile.mkdtemp(prefix="zip_extract_"))
        logging.info(f"Temporary extraction directory: {temp_dir}")

        with zipfile.ZipFile(zip_path, 'r') as z:
            namelist = [n for n in z.namelist() if not n.endswith('/')]
            logging.info(f"ZIP contains {len(namelist)} files: {namelist}")
            z.extractall(temp_dir)

            pattern_main = re.compile(r'(?P<base>.+)-main(?P<ext>\.[^.]+)$', re.IGNORECASE)
            pattern_overlay = re.compile(r'(?P<base>.+)-overlay(?P<ext>\.[^.]+)$', re.IGNORECASE)

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

        for base, files in pairs.items():
            main_file = files.get('main')
            overlay_file = files.get('overlay')
            if not main_file or not overlay_file:
                logging.warning(f"Incomplete pair for base '{base}': main={main_file}, overlay={overlay_file}")
                continue

            main_path = temp_dir / main_file
            overlay_path = temp_dir / overlay_file
            ext = Path(main_file).suffix.lower()
            is_video = ext in ['.mp4', '.mov', '.m4v', '.avi', '.mkv']
            output_name = Path(main_file).name.replace('-main', '-merged')
            output_path = Path(output_dir) / output_name

            logging.info(f"Processing pair '{base}': main={main_file}, overlay={overlay_file}")
            logging.info(f"Media type: {'video' if is_video else 'image'}")
            logging.info(f"Output will be: {output_path}")

            if is_video:
                logging.info(f"Starting video overlay merge for: {base}")
                success, result = merge_video_overlay(str(main_path), str(overlay_path), str(output_path))
                if success:
                    logging.info(f"Video overlay merge successful for: {base}")
                    try:
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

                        count = 1
                        while new_path.exists():
                            new_path = Path(output_dir) / f"{date_name}_{count}{output_path.suffix}"
                            count += 1

                        os.rename(output_path, new_path)
                        merged_files.append(str(new_path))

                        try:
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
                success, result = merge_images(str(main_path), str(overlay_path), str(output_path))
                if success:
                    try:
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

                        count = 1
                        while new_path.exists():
                            new_path = Path(output_dir) / f"{date_name}_{count}{output_path.suffix}"
                            count += 1

                        os.rename(output_path, new_path)
                        merged_files.append(str(new_path))

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
        if temp_dir and temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
            except Exception as cleanup_error:
                logging.debug(f"Could not clean up temp directory: {cleanup_error}")