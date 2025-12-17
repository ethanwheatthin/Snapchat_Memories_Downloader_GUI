import json
import os
import requests
from datetime import datetime
from pathlib import Path
import platform
import subprocess
import shutil
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import logging
import zipfile
import tempfile
import re

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

def parse_date(date_str):
    """Parse date string from JSON format to datetime object."""
    return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S UTC")

def parse_location(location_str):
    """Parse location string to get latitude and longitude."""
    if not location_str or location_str == "N/A":
        return None, None
    
    try:
        coords = location_str.split(": ")[1]
        lat, lon = coords.split(", ")
        return float(lat), float(lon)
    except:
        return None, None

def decimal_to_dms(decimal):
    """Convert decimal degrees to degrees, minutes, seconds format for EXIF."""
    is_positive = decimal >= 0
    decimal = abs(decimal)
    
    degrees = int(decimal)
    minutes = int((decimal - degrees) * 60)
    seconds = ((decimal - degrees) * 60 - minutes) * 60
    
    return ((degrees, 1), (minutes, 1), (int(seconds * 100), 100))

def set_image_exif_metadata(file_path, date_obj, latitude, longitude):
    """Set EXIF metadata for image files."""
    if not HAS_PIEXIF:
        return
    
    try:
        try:
            img = Image.open(file_path)
            img_format = img.format
            img.close()
        except Exception:
            return
        
        if img_format not in ['JPEG', 'JPG']:
            return
        
        try:
            exif_dict = piexif.load(file_path)
        except:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
        
        date_str = date_obj.strftime("%Y:%m:%d %H:%M:%S").encode('ascii')
        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = date_str
        exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = date_str
        exif_dict["0th"][piexif.ImageIFD.DateTime] = date_str
        
        if latitude is not None and longitude is not None:
            lat_dms = decimal_to_dms(latitude)
            lon_dms = decimal_to_dms(longitude)
            
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = lat_dms
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = b"N" if latitude >= 0 else b"S"
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = lon_dms
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = b"E" if longitude >= 0 else b"W"
        
        exif_bytes = piexif.dump(exif_dict)
        img = Image.open(file_path)
        img.save(file_path, "JPEG", exif=exif_bytes, quality=95)
        img.close()
        
    except Exception:
        pass

def check_ffmpeg():
    """Check if ffmpeg is available on the system."""
    return shutil.which('ffmpeg') is not None

def check_vlc():
    """Check if VLC Python bindings are available."""
    return HAS_VLC

def find_vlc_executable():
    """Find VLC executable on the system."""
    # Common VLC installation paths on Windows
    vlc_paths = [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    ]
    
    # Check if VLC is in PATH
    vlc_in_path = shutil.which('vlc')
    if vlc_in_path:
        return vlc_in_path
    
    # Check common installation paths
    for path in vlc_paths:
        if os.path.exists(path):
            return path
    
    return None

def convert_with_vlc(input_path, output_path=None):
    """Convert video using VLC - tries Python bindings first, then subprocess."""
    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_converted{ext}"
    
    # Try Python VLC bindings first if available
    if HAS_VLC:
        try:
            return convert_with_vlc_python(input_path, output_path)
        except Exception as e:
            logging.warning(f"python-vlc failed: {e}. Trying subprocess method...")
    
    # Fall back to subprocess method
    return convert_with_vlc_subprocess(input_path, output_path)

def convert_with_vlc_python(input_path, output_path):
    """Convert video using VLC Python bindings."""
    try:
        logging.info(f"Converting with VLC (Python bindings): {input_path}")
        
        # Create VLC instance
        instance = vlc.Instance('--no-xlib')
        
        # Create media player
        player = instance.media_player_new()
        media = instance.media_new(input_path)
        
        # Set up transcoding options matching VLC GUI: Video - H.264 + MP3 (MP4)
        transcode_options = (
            f"#transcode{{"
            f"vcodec=h264,"
            f"vb=2000,"  # Video bitrate in kb/s
            f"venc=x264{{"
                f"preset=medium,"
                f"profile=main"
            f"}},"
            f"acodec=mp3,"
            f"ab=192,"  # Audio bitrate in kb/s
            f"channels=2,"
            f"samplerate=44100"
            f"}}:"
            f"standard{{"
                f"access=file,"
                f"mux=mp4,"
                f"dst={output_path}"
            f"}}"
        )
        
        # Add sout option to media
        media.add_option(f":sout={transcode_options}")
        media.add_option(":sout-keep")
        
        player.set_media(media)
        
        # Start playback (which triggers conversion)
        player.play()
        
        # Wait for conversion to complete
        import time
        timeout = 300  # 5 minutes
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            state = player.get_state()
            
            # Check if finished or error
            if state == vlc.State.Ended:
                logging.info("VLC conversion completed")
                break
            elif state == vlc.State.Error:
                logging.error("VLC conversion encountered an error")
                player.stop()
                return False, "VLC conversion error"
            elif state == vlc.State.Stopped:
                # Check if output file exists and has content
                if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                    logging.info("VLC conversion stopped - checking output")
                    break
                else:
                    logging.error("VLC conversion stopped prematurely")
                    return False, "VLC conversion stopped"
            
            time.sleep(0.5)
        else:
            # Timeout reached
            logging.error("VLC conversion timed out")
            player.stop()
            if os.path.exists(output_path):
                os.remove(output_path)
            return False, "VLC conversion timed out"
        
        # Stop player and release resources
        player.stop()
        player.release()
        media.release()
        
        # Verify output file
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            logging.info(f"VLC conversion successful: {output_path}")
            return True, output_path
        else:
            logging.error("VLC conversion failed - output file not created or too small")
            if os.path.exists(output_path):
                os.remove(output_path)
            return False, "VLC conversion failed"
            
    except Exception as e:
        logging.error(f"VLC Python conversion error: {e}", exc_info=True)
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass
        raise

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
        return False, "VLC conversion timed out"
    except Exception as e:
        logging.error(f"VLC subprocess conversion error: {e}", exc_info=True)
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass
        return False, str(e)

def set_video_metadata(file_path, date_obj, latitude, longitude):
    """Set metadata for video files using mutagen (no ffmpeg required).
    
    Sets standard QuickTime metadata tags that are recognized by galleries and video players:
    - Creation date (©day tag and file timestamps)
    - Location data (when available)
    """
    if not HAS_MUTAGEN:
        return False
    
    # Create backup before attempting to modify
    backup_path = f"{file_path}.backup"
    
    try:
        # Validate it's a proper MP4 file first
        with open(file_path, 'rb') as f:
            header = f.read(12)
            # Check for valid MP4/MOV signatures (ftyp box)
            if len(header) < 8 or header[4:8] not in [b'ftyp', b'mdat', b'moov']:
                return False
        
        # Create backup
        shutil.copy2(file_path, backup_path)
        
        try:
            video = MP4(file_path)
            
            # Set creation date using multiple standard tags for better compatibility
            # ISO 8601 format for ©day tag
            creation_time = date_obj.strftime("%Y-%m-%dT%H:%M:%SZ")
            video["\xa9day"] = creation_time  # Standard QuickTime date tag
            
            # Some players also recognize these tags
            # Add creation date in various formats for maximum compatibility
            try:
                # Store as year for sorting/grouping
                video["\xa9ART"] = date_obj.strftime("%Y")  # Year as artist field (some apps use this)
            except Exception:
                pass
            
            # Add location if available (using custom tags)
            if latitude is not None and longitude is not None:
                # Store as ISO 6709 format string
                location_str = f"{latitude:+.6f}{longitude:+.6f}/"
                video["----:com.apple.quicktime:location-ISO6709"] = location_str.encode('utf-8')
                
                # Also store individual coordinates
                video["----:com.apple.quicktime:latitude"] = str(latitude).encode('utf-8')
                video["----:com.apple.quicktime:longitude"] = str(longitude).encode('utf-8')
            
            video.save()
            
            # Verify the file is still valid after save
            with open(file_path, 'rb') as f:
                verify_header = f.read(12)
                if len(verify_header) < 8 or verify_header[4:8] not in [b'ftyp', b'mdat', b'moov']:
                    # Restore from backup if corrupted
                    shutil.copy2(backup_path, file_path)
                    os.remove(backup_path)
                    return False
            
            # Success - remove backup
            os.remove(backup_path)
            return True
            
        except Exception as e:
            # Restore from backup on any error
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, file_path)
                os.remove(backup_path)
            return False
        
    except Exception:
        # Clean up backup if it exists
        if os.path.exists(backup_path):
            os.remove(backup_path)
        return False

def set_video_metadata_ffmpeg(file_path, date_obj, latitude, longitude):
    """Set video metadata using ffmpeg if available.
    
    This method sets standard metadata tags that are widely recognized by gallery apps:
    - creation_time: Standard MP4 creation time metadata
    - location: GPS coordinates if available (ISO 6709 format)
    
    Returns True if ffmpeg is available and metadata was set, False otherwise.
    """
    if not check_ffmpeg():
        return False
    
    temp_output = None
    try:
        # Create a temporary output file
        temp_output = f"{file_path}.temp.mp4"
        
        # Format creation time in ISO 8601 format as required by ffmpeg
        creation_time_str = date_obj.strftime("%Y-%m-%dT%H:%M:%S")
        
        # Build ffmpeg command to copy video/audio streams and add metadata
        cmd = [
            'ffmpeg', '-y',
            '-i', str(file_path),
            '-c', 'copy',  # Copy streams without re-encoding
            '-metadata', f'creation_time={creation_time_str}',
            '-metadata', f'date={creation_time_str}',
        ]
        
        # Add location metadata if available (ISO 6709 format: ±DD.DDDD±DDD.DDDD/)
        if latitude is not None and longitude is not None:
            cmd.extend([
                '-metadata', f'location={latitude:+.6f}{longitude:+.6f}/',
                '-metadata', f'location-eng={latitude}, {longitude}',
            ])
        
        cmd.append(str(temp_output))
        
        logging.debug(f"Setting video metadata with ffmpeg: {' '.join(cmd)}")
        
        # Run ffmpeg
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0 and os.path.exists(temp_output):
            # Replace original file with the one that has metadata
            try:
                os.remove(file_path)
                os.rename(temp_output, file_path)
                logging.info(f"Successfully set video metadata using ffmpeg: {file_path}")
                return True
            except Exception as e:
                logging.error(f"Failed to replace file after metadata update: {e}")
                # Clean up temp file
                if os.path.exists(temp_output):
                    os.remove(temp_output)
                return False
        else:
            logging.warning(f"ffmpeg metadata setting failed: {result.stderr}")
            # Clean up temp file if it exists
            if os.path.exists(temp_output):
                os.remove(temp_output)
            return False
            
    except subprocess.TimeoutExpired:
        logging.error("ffmpeg metadata setting timed out")
        if temp_output and os.path.exists(temp_output):
            try:
                os.remove(temp_output)
            except:
                pass
        return False
    except Exception as e:
        logging.error(f"Error setting video metadata with ffmpeg: {e}", exc_info=True)
        if temp_output and os.path.exists(temp_output):
            try:
                os.remove(temp_output)
            except:
                pass
        return False

def set_file_timestamps(file_path, date_obj):
    """Set file modification and access times."""
    timestamp = date_obj.timestamp()
    
    try:
        os.utime(file_path, (timestamp, timestamp))
    except Exception:
        pass


def enforce_portrait_video(file_path, timeout=300):
    """Ensure the video is portrait (height >= width).

    Attempts to physically rotate the video when necessary using ffmpeg (preferred)
    or PyAV as a fallback. Returns (True, path) on success or (False, message) on failure.
    """
    try:
        if not os.path.exists(file_path):
            return False, "File not found"

        # Try ffprobe/ffmpeg first
        if check_ffmpeg():
            try:
                cmd = [
                    'ffprobe', '-v', 'error', '-select_streams', 'v:0',
                    '-show_entries', 'stream=width,height:stream_tags=rotate',
                    '-of', 'json', file_path
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                info = json.loads(res.stdout) if res.stdout else {}
                streams = info.get('streams', [])
                if streams:
                    s = streams[0]
                    width = int(s.get('width', 0))
                    height = int(s.get('height', 0))
                    tags = s.get('tags') or {}
                    rotate_tag = tags.get('rotate') if tags else None

                    need_rotate = False
                    vf = None

                    if rotate_tag is not None:
                        try:
                            r = int(rotate_tag) % 360
                            if r == 90:
                                need_rotate = True
                                vf = 'transpose=1'
                            elif r == 270:
                                need_rotate = True
                                vf = 'transpose=2'
                            elif r == 180:
                                need_rotate = True
                                vf = 'transpose=1,transpose=1'
                        except Exception:
                            pass
                    else:
                        # No rotate tag - check frame dimensions
                        if width > height:
                            need_rotate = True
                            vf = 'transpose=1'

                    if not need_rotate:
                        return True, "Already portrait"

                    out_path = f"{file_path}.rotated{Path(file_path).suffix}"
                    ffmpeg_cmd = [
                        'ffmpeg', '-y', '-i', file_path,
                        '-vf', vf,
                        '-c:v', 'libx264', '-crf', '18', '-preset', 'veryfast',
                        '-c:a', 'copy', out_path
                    ]
                    proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=timeout)
                    if proc.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                        # Replace original with rotated
                        try:
                            backup = f"{file_path}.backup"
                            shutil.move(file_path, backup)
                            shutil.move(out_path, file_path)
                            try:
                                os.remove(backup)
                            except Exception:
                                pass
                            return True, file_path
                        except Exception as e:
                            # Try to restore
                            try:
                                if os.path.exists(backup) and not os.path.exists(file_path):
                                    shutil.move(backup, file_path)
                            except Exception:
                                pass
                            if os.path.exists(out_path):
                                os.remove(out_path)
                            return False, f"Failed to replace original: {e}"
                    else:
                        if os.path.exists(out_path):
                            try:
                                os.remove(out_path)
                            except Exception:
                                pass
                        return False, f"ffmpeg failed: {proc.stderr}"
            except Exception as e:
                logging.debug(f"ffmpeg portrait enforcement error: {e}", exc_info=True)

        # Fallback to PyAV if available
        if HAS_PYAV:
            try:
                input_container = av.open(file_path)
                vstream = input_container.streams.video[0]
                width = vstream.width
                height = vstream.height
                need_rotate = width > height
                if not need_rotate:
                    input_container.close()
                    return True, "Already portrait"

                out_path = f"{file_path}.rotated{Path(file_path).suffix}"
                output_container = av.open(out_path, 'w')
                output_vs = output_container.add_stream('h264', rate=vstream.average_rate)
                output_vs.width = height
                output_vs.height = width
                output_vs.pix_fmt = 'yuv420p'

                output_audio = None
                if input_container.streams.audio:
                    audio_stream = input_container.streams.audio[0]
                    output_audio = output_container.add_stream('aac', rate=audio_stream.rate)
                    if hasattr(audio_stream, 'layout') and audio_stream.layout:
                        output_audio.layout = audio_stream.layout

                for packet in input_container.demux():
                    if packet.stream.type == 'video':
                        for frame in packet.decode():
                            img = frame.to_image().rotate(90, expand=True)
                            new_frame = av.VideoFrame.from_image(img)
                            for out_packet in output_vs.encode(new_frame):
                                output_container.mux(out_packet)
                    elif packet.stream.type == 'audio' and output_audio:
                        for frame in packet.decode():
                            for out_packet in output_audio.encode(frame):
                                output_container.mux(out_packet)

                for pkt in output_vs.encode():
                    output_container.mux(pkt)
                if output_audio:
                    for pkt in output_audio.encode():
                        output_container.mux(pkt)

                input_container.close()
                output_container.close()

                if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                    try:
                        backup = f"{file_path}.backup"
                        shutil.move(file_path, backup)
                        shutil.move(out_path, file_path)
                        try:
                            os.remove(backup)
                        except Exception:
                            pass
                        return True, file_path
                    except Exception as e:
                        return False, f"Failed to replace original after PyAV rotate: {e}"
            except Exception as e:
                logging.debug(f"PyAV portrait enforcement error: {e}", exc_info=True)

        return False, "No available method to rotate video or rotation not needed"
    except Exception as e:
        logging.error(f"Error in enforce_portrait_video: {e}", exc_info=True)
        return False, str(e)

def convert_hevc_to_h264(input_path, output_path=None, max_attempts=3, failed_dir_path="downloads/failed_conversions"):
    """Convert any video to H.264 for better compatibility using PyAV, with VLC fallback."""
    if not HAS_PYAV:
        logging.warning("PyAV not installed. Attempting VLC fallback...")
        # Try VLC as fallback
        return convert_with_vlc(input_path, output_path)

    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_temp{ext}"

    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        input_container = None
        output_container = None
        try:
            logging.info(f"Attempt {attempt}: Opening input video: {input_path}")
            input_container = av.open(input_path)
            input_video_stream = input_container.streams.video[0]

            # Always convert to H.264 regardless of the input codec
            logging.info(f"Attempt {attempt}: Creating output container: {output_path}")
            output_container = av.open(output_path, 'w')

            # Add video stream with H.264 codec
            output_video_stream = output_container.add_stream('h264', rate=input_video_stream.average_rate)
            output_video_stream.width = input_video_stream.width
            output_video_stream.height = input_video_stream.height
            output_video_stream.pix_fmt = 'yuv420p'
            output_video_stream.bit_rate = input_video_stream.bit_rate or 2000000

            # Copy audio stream if exists
            audio_stream = None
            output_audio_stream = None
            if input_container.streams.audio:
                audio_stream = input_container.streams.audio[0]
                output_audio_stream = output_container.add_stream('aac', rate=audio_stream.rate)
                if hasattr(audio_stream, 'layout') and audio_stream.layout:
                    output_audio_stream.layout = audio_stream.layout

            logging.info(f"Attempt {attempt}: Processing frames...")
            for packet in input_container.demux():
                if packet.stream.type == 'video':
                    for frame in packet.decode():
                        for out_packet in output_video_stream.encode(frame):
                            output_container.mux(out_packet)
                elif packet.stream.type == 'audio' and output_audio_stream:
                    for frame in packet.decode():
                        for out_packet in output_audio_stream.encode(frame):
                            output_container.mux(out_packet)

            logging.info(f"Attempt {attempt}: Flushing streams...")
            for packet in output_video_stream.encode():
                output_container.mux(packet)
            if output_audio_stream:
                for packet in output_audio_stream.encode():
                    output_container.mux(packet)

            logging.info(f"Attempt {attempt}: Closing containers...")
            # Explicitly close containers before file operations
            if input_container:
                input_container.close()
                input_container = None
            if output_container:
                output_container.close()
                output_container = None

            logging.info(f"Conversion to H.264 successful on attempt {attempt}: {output_path}")
            return True, output_path

        except Exception as e:
            logging.error(f"Attempt {attempt}: Error during conversion: {e}", exc_info=True)
            # Ensure containers are closed
            try:
                if input_container:
                    input_container.close()
            except:
                pass
            try:
                if output_container:
                    output_container.close()
            except:
                pass
            
            # Small delay to ensure file handles are released
            import time
            time.sleep(0.5)
            
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                    logging.info(f"Attempt {attempt}: Removed partial output: {output_path}")
                except Exception as cleanup_error:
                    logging.error(f"Attempt {attempt}: Failed to remove partial output {output_path}: {cleanup_error}", exc_info=True)

        logging.warning(f"Attempt {attempt} failed. Retrying...")

    # PyAV failed all attempts, try VLC as fallback
    logging.info("All PyAV attempts failed. Trying VLC fallback...")
    
    # Add delay to ensure file handles are released
    import time
    time.sleep(1)
    
    vlc_success, vlc_result = convert_with_vlc(input_path, output_path)
    
    if vlc_success:
        logging.info(f"VLC fallback conversion successful: {vlc_result}")
        return True, vlc_result
    
    # Both PyAV and VLC failed - move to failed_conversions folder
    logging.error("Both PyAV and VLC conversion methods failed")
    
    # Ensure delay before file operations
    time.sleep(1)
    
    failed_dir = Path(failed_dir_path)
    failed_dir.mkdir(parents=True, exist_ok=True)
    failed_path = failed_dir / Path(input_path).name
    
    # Save error log with the failed file
    error_log_path = failed_dir / f"{Path(input_path).stem}_error.txt"
    try:
        with open(error_log_path, 'w') as f:
            f.write(f"Failed conversion: {input_path}\n")
            f.write(f"PyAV result: Failed after {max_attempts} attempts\n")
            f.write(f"VLC result: {vlc_result}\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        logging.info(f"Error log saved: {error_log_path}")
    except Exception as log_error:
        logging.error(f"Failed to save error log: {log_error}")
    
    try:
        # Use copy instead of move to avoid file locking issues
        shutil.copy2(input_path, failed_path)
        logging.info(f"Copied failed conversion to: {failed_path}")
        
        # Try to remove original, but don't fail if we can't
        try:
            os.remove(input_path)
            logging.info(f"Removed original file: {input_path}")
        except Exception as remove_error:
            logging.warning(f"Could not remove original {input_path}: {remove_error}")
            
    except Exception as copy_error:
        logging.error(f"Failed to copy {input_path} to {failed_path}: {copy_error}", exc_info=True)

    logging.error(f"All conversion attempts failed for {input_path}")
    return False, f"Failed after {max_attempts} PyAV attempts and VLC fallback"

def extract_media_from_zip(zip_path, output_path):
    """Extract media file from ZIP archive."""
    temp_dir = None
    try:
        logging.info(f"Extracting media from ZIP: {zip_path}")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Get list of files in the ZIP
            file_list = zip_ref.namelist()
            
            # Filter for media files (images and videos)
            media_extensions = ('.jpg', '.jpeg', '.png', '.mp4', '.mov', '.m4v', '.heic')
            media_files = [f for f in file_list if f.lower().endswith(media_extensions)]
            
            if not media_files:
                logging.warning(f"No media files found in ZIP archive")
                return False
            
            # Extract the first media file found
            media_file = media_files[0]
            logging.info(f"Extracting: {media_file}")
            
            # Extract to temporary location
            temp_dir = Path(output_path).parent / "temp_extract"
            temp_dir.mkdir(exist_ok=True)
            
            extracted_path = zip_ref.extract(media_file, temp_dir)
            
            # Move extracted file to desired output path
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
        # Always clean up temp directory if it exists
        if temp_dir and temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
            except Exception as cleanup_error:
                logging.debug(f"Could not clean up temp directory: {cleanup_error}")

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
        self.convert_hevc = tk.BooleanVar(value=True)
        self.max_retries = tk.IntVar(value=3)  # Number of download attempts (initial + retries)
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
        
        # Conversion option
        conversion_frame = ttk.Frame(input_card, style="Card.TFrame")
        conversion_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.convert_checkbox = ttk.Checkbutton(
            conversion_frame, 
            text="Convert videos to H.264 for better compatibility",
            variable=self.convert_hevc,
            style="Info.TLabel"
        )
        self.convert_checkbox.pack(anchor=tk.W)
        
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

        # Check available conversion tools and display status
        conversion_status = self.get_conversion_status()
        conversion_info = ttk.Label(input_card,
                                   text=conversion_status,
                                   style="Info.TLabel")
        conversion_info.pack(anchor=tk.W, pady=(0, 20))
        
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
            
            for idx, item in enumerate(media_items, 1):
                if self.stop_download:
                    self.log("\n⚠ Download stopped by user")
                    break
                
                try:
                    self.update_progress(idx, total)
                    self.log(f"[{idx}/{total}] Processing...")
                    
                    # Extract metadata
                    date_str = item.get("Date", "")
                    media_type = item.get("Media Type", "Unknown")
                    location_str = item.get("Location", "")
                    download_url = item.get("Media Download Url", "")
                    
                    if not download_url:
                        self.log("  ⚠ No download URL found, skipping\n")
                        error_count += 1
                        continue
                    
                    # Parse date and location
                    try:
                        date_obj = parse_date(date_str)
                    except:
                        self.log("  ⚠ Invalid date format, skipping\n")
                        error_count += 1
                        continue
                        
                    latitude, longitude = parse_location(location_str)
                    
                    # Generate filename
                    date_formatted = date_obj.strftime("%Y%m%d_%H%M%S")
                    extension = get_file_extension(media_type)
                    filename = f"{date_formatted}_{idx}{extension}"
                    file_path = output_path / filename
                    
                    self.log(f"  File: {filename}")
                    self.log(f"  Type: {media_type}")
                    
                    # Download file
                    download_success, merged_files = download_media(download_url, str(file_path), max_retries=self.max_retries.get(), progress_callback=self.log, date_obj=date_obj)
                    if download_success:
                        self.log("  ✓ Downloaded")
                        
                        # If merged files were created from ZIP overlay, apply metadata to each
                        if merged_files:
                            self.log(f"  ℹ Processing {len(merged_files)} merged file(s) from ZIP overlay")
                            for merged_file in merged_files:
                                merged_path = Path(merged_file)
                                self.log(f"  📄 {merged_path.name}")
                                
                                # Determine if it's a video or image
                                ext = merged_path.suffix.lower()
                                is_video = ext in ['.mp4', '.mov', '.m4v', '.avi', '.mkv']
                                
                                if is_video:
                                    # Ensure portrait orientation for merged video
                                    try:
                                        rot_ok, rot_msg = enforce_portrait_video(str(merged_path))
                                        if rot_ok:
                                            self.log("    ✓ Ensured portrait orientation")
                                        else:
                                            self.log(f"    ⚠ Could not enforce portrait orientation: {rot_msg}")
                                    except Exception as e:
                                        self.log(f"    ⚠ Error enforcing portrait orientation: {e}")

                                    # Set video metadata - try ffmpeg first for better compatibility, then mutagen
                                    metadata_set = False
                                    
                                    # Try ffmpeg first (sets standard creation_time metadata)
                                    try:
                                        if set_video_metadata_ffmpeg(str(merged_path), date_obj, latitude, longitude):
                                            self.log("    ✓ Set video metadata (ffmpeg)")
                                            metadata_set = True
                                    except Exception as ffmpeg_error:
                                        self.log(f"    ℹ ffmpeg metadata setting failed, trying mutagen: {ffmpeg_error}")
                                    
                                    # Fall back to mutagen if ffmpeg didn't work
                                    if not metadata_set and HAS_MUTAGEN:
                                        try:
                                            if set_video_metadata(str(merged_path), date_obj, latitude, longitude):
                                                self.log("    ✓ Set video metadata (mutagen)")
                                                metadata_set = True
                                        except Exception as metadata_error:
                                            self.log(f"    ⚠ Metadata error: {metadata_error}")
                                    
                                    if not metadata_set:
                                        self.log("    ℹ Video metadata not set (install ffmpeg or mutagen)")
                                    
                                    set_file_timestamps(str(merged_path), date_obj)
                                    self.log("    ✓ Set file timestamps")
                                else:
                                    # Set image metadata
                                    if HAS_PIEXIF and ext in ['.jpg', '.jpeg']:
                                        try:
                                            set_image_exif_metadata(str(merged_path), date_obj, latitude, longitude)
                                            self.log("    ✓ Set EXIF metadata")
                                        except Exception as exif_error:
                                            self.log(f"    ⚠ EXIF metadata error: {exif_error}")
                                    set_file_timestamps(str(merged_path), date_obj)
                                    self.log("    ✓ Set file timestamps")
                            
                            success_count += 1
                            continue
                        
                        # Set metadata
                        if media_type == "Image" and extension.lower() in ['.jpg', '.jpeg']:
                            if HAS_PIEXIF:
                                try:
                                    set_image_exif_metadata(str(file_path), date_obj, latitude, longitude)
                                    self.log("  ✓ Set EXIF metadata")
                                except Exception as exif_error:
                                    self.log(f"  ⚠ EXIF metadata error: {exif_error}")
                            # Always set file timestamps for images
                            set_file_timestamps(str(file_path), date_obj)
                        elif media_type == "Video":
                            # Convert all videos to H.264 by default
                            self.log("  🔄 Converting to H.264...")
                            
                            # Check if any conversion tool is available
                            if not HAS_PYAV and not find_vlc_executable() and not HAS_VLC:
                                self.log("  ⚠ No conversion tools available - keeping original format")
                                self.log("  ℹ Install PyAV (pip install av) or VLC for automatic H.264 conversion")
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
                                        self.log(f"  ✓ Converted to H.264")
                                        # Replace original with converted file
                                        try:
                                            os.remove(str(file_path))
                                            os.rename(result, str(file_path))
                                            # CRITICAL: Set timestamps AFTER file replacement
                                            set_file_timestamps(str(file_path), date_obj)
                                            self.log("  ✓ Set file timestamps")
                                        except Exception as rename_error:
                                            self.log(f"  ⚠ Could not replace original: {rename_error}")
                                            # If replacement failed but conversion succeeded, still set timestamps on original
                                            set_file_timestamps(str(file_path), date_obj)
                                    else:
                                        self.log(f"  ⚠ Conversion failed: {result}")
                                        # Don't count as error - file is still downloaded in original format
                                        # Set timestamps on original file
                                        set_file_timestamps(str(file_path), date_obj)
                                except Exception as conversion_error:
                                    self.log(f"  ⚠ Conversion error: {conversion_error}")
                                    # Ensure timestamps are set even if conversion crashes
                                    set_file_timestamps(str(file_path), date_obj)
                            
                            # Try to set video metadata - use ffmpeg first for better compatibility, then mutagen
                            metadata_set = False
                            
                            # Try ffmpeg first (sets standard creation_time metadata)
                            try:
                                if set_video_metadata_ffmpeg(str(file_path), date_obj, latitude, longitude):
                                    self.log("  ✓ Set video metadata (ffmpeg)")
                                    metadata_set = True
                            except Exception as ffmpeg_error:
                                logging.debug(f"ffmpeg metadata setting failed: {ffmpeg_error}")
                            
                            # Fall back to mutagen if ffmpeg didn't work
                            if not metadata_set and HAS_MUTAGEN:
                                try:
                                    if set_video_metadata(str(file_path), date_obj, latitude, longitude):
                                        self.log("  ✓ Set video metadata (mutagen)")
                                        metadata_set = True
                                except Exception as metadata_error:
                                    self.log(f"  ⚠ Metadata error: {metadata_error}")
                            
                            if not metadata_set:
                                self.log("  ℹ Video downloaded (install ffmpeg or mutagen for embedded metadata)")
                        
                        # ALWAYS set file timestamps as final step for any media type
                        # This ensures the creation/modification date is correct even if other metadata fails
                        # Ensure portrait orientation for videos before finalizing timestamps/metadata
                        try:
                            if media_type == "Video":
                                try:
                                    rot_ok, rot_msg = enforce_portrait_video(str(file_path))
                                    if rot_ok:
                                        self.log("  ✓ Ensured portrait orientation")
                                    else:
                                        self.log(f"  ⚠ Could not enforce portrait orientation: {rot_msg}")
                                except Exception as e:
                                    self.log(f"  ⚠ Error enforcing portrait orientation: {e}")
                        except Exception:
                            pass

                        try:
                            set_file_timestamps(str(file_path), date_obj)
                            self.log("  ✓ File date set correctly")
                        except Exception as timestamp_error:
                            self.log(f"  ⚠ Failed to set file timestamps: {timestamp_error}")
                        
                        # Validate the downloaded file
                        try:
                            if not validate_downloaded_file(str(file_path)):
                                self.log("  ⚠ Downloaded file is corrupted or incomplete")
                                error_count += 1
                                continue
                        except Exception as validation_error:
                            self.log(f"  ⚠ Validation error: {validation_error}")
                        
                        success_count += 1
                    else:
                        self.log("  ✗ Download failed")
                        error_count += 1
                
                except Exception as item_error:
                    # Catch any error during processing of this item to prevent crash
                    self.log(f"  ✗ Error processing item: {item_error}")
                    logging.error(f"Error processing item {idx}: {item_error}", exc_info=True)
                    error_count += 1
                
                self.log("")  # Empty line
            
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
