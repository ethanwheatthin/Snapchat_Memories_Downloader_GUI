import logging
import os
import shutil
import subprocess
import time
import sys
from pathlib import Path
from datetime import datetime

# Windows-specific subprocess flag to prevent command windows from popping up
CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0

# Optional libs
HAS_MUTAGEN = False
try:
    from mutagen.mp4 import MP4
    HAS_MUTAGEN = True
except Exception:
    HAS_MUTAGEN = False

HAS_PYAV = False
try:
    import av
    HAS_PYAV = True
except Exception:
    HAS_PYAV = False

HAS_VLC = False
try:
    import vlc
    HAS_VLC = True
except Exception:
    HAS_VLC = False

# PIL for frame rotation during video conversion
HAS_PIL = False
try:
    from PIL import Image as PILImage
    HAS_PIL = True
except Exception:
    HAS_PIL = False


def sanitize_path(path):
    """Sanitize file path by stripping trailing invalid characters and normalizing.
    
    Fixes issues where paths may have trailing braces, spaces, or other invalid chars.
    
    Args:
        path: Input path (str or Path)
        
    Returns:
        Path object with sanitized absolute path
    """
    if path is None:
        return None
    
    path_str = str(path).strip()
    # Strip common trailing invalid characters
    path_str = path_str.rstrip('{}\t ')
    
    # Convert to Path and resolve to absolute
    return Path(path_str).resolve()


def _get_video_rotation(file_path):
    """Detect rotation metadata from a video file.
    
    Snapchat videos are often stored in landscape resolution with a rotation
    metadata tag that tells players to display them in portrait. When re-encoding,
    this rotation must be applied to the frames to preserve correct orientation.
    
    Returns:
        int: Rotation in degrees (0, 90, 180, 270). 0 means no rotation needed.
    """
    rotation = 0
    
    # Try ffprobe first (most reliable)
    if check_ffmpeg():
        try:
            import json as _json
            cmd = [
                'ffprobe', '-v', 'error', '-select_streams', 'v:0',
                '-show_entries', 'stream_tags=rotate:stream_side_data_list',
                '-of', 'json', str(file_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, creationflags=CREATE_NO_WINDOW)
            if result.returncode == 0 and result.stdout.strip():
                data = _json.loads(result.stdout)
                streams = data.get('streams', [])
                if streams:
                    tags = streams[0].get('tags', {})
                    if 'rotate' in tags:
                        rotation = int(tags['rotate'])
                    # Also check side_data_list for display matrix rotation
                    side_data = streams[0].get('side_data_list', [])
                    for sd in side_data:
                        if sd.get('side_data_type') == 'Display Matrix' and 'rotation' in sd:
                            rotation = int(float(sd['rotation']))
        except Exception as e:
            logging.debug(f"Could not detect rotation via ffprobe: {e}")
    
    # Try PyAV metadata fallback
    if rotation == 0 and HAS_PYAV:
        try:
            container = av.open(str(file_path))
            vstream = container.streams.video[0]
            # Check stream metadata for rotate tag
            if hasattr(vstream, 'metadata') and vstream.metadata:
                rotate_val = vstream.metadata.get('rotate', '0')
                rotation = int(rotate_val)
            container.close()
        except Exception as e:
            logging.debug(f"Could not detect rotation via PyAV: {e}")
    
    # Normalize to 0-359 range, handle negative values
    rotation = rotation % 360
    if rotation < 0:
        rotation += 360
    
    logging.debug(f"Detected rotation for {file_path}: {rotation}°")
    return rotation


def check_ffmpeg():
    import shutil
    return shutil.which('ffmpeg') is not None


def check_vlc():
    return HAS_VLC


def find_vlc_executable():
    vlc_paths = [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    ]
    vlc_in_path = shutil.which('vlc')
    if vlc_in_path:
        return vlc_in_path
    for p in vlc_paths:
        if os.path.exists(p):
            return p
    return None


def validate_video_file(file_path, min_duration=0.1, min_size=1000):
    """Validate video file using ffprobe or fallback to size check.
    
    Args:
        file_path: Path to video file
        min_duration: Minimum duration in seconds (default 0.1)
        min_size: Minimum file size in bytes (default 1000)
        
    Returns:
        Tuple of (is_valid: bool, info: dict)
        info contains: duration, has_video, has_audio, codec, error
    """
    file_path = sanitize_path(file_path)
    info = {
        'duration': None,
        'has_video': False,
        'has_audio': False,
        'codec': None,
        'error': None
    }
    
    # Basic checks
    if not file_path.exists():
        info['error'] = 'File does not exist'
        return False, info
    
    file_size = file_path.stat().st_size
    if file_size < min_size:
        info['error'] = f'File too small: {file_size} bytes'
        return False, info
    
    # Try ffprobe validation if available
    if check_ffmpeg():
        try:
            # Get format info (duration)
            cmd_format = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(file_path)
            ]
            result = subprocess.run(cmd_format, capture_output=True, text=True, timeout=10, creationflags=CREATE_NO_WINDOW)
            if result.returncode == 0 and result.stdout.strip():
                try:
                    info['duration'] = float(result.stdout.strip())
                except ValueError:
                    pass
            
            # Get stream info
            cmd_streams = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'stream=codec_type,codec_name',
                '-of', 'json',
                str(file_path)
            ]
            result = subprocess.run(cmd_streams, capture_output=True, text=True, timeout=10, creationflags=CREATE_NO_WINDOW)
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                for stream in data.get('streams', []):
                    codec_type = stream.get('codec_type')
                    if codec_type == 'video':
                        info['has_video'] = True
                        info['codec'] = stream.get('codec_name')
                    elif codec_type == 'audio':
                        info['has_audio'] = True
            
            # Validation logic
            if not info['has_video']:
                info['error'] = 'No video stream found'
                return False, info
            
            if info['duration'] is not None and info['duration'] < min_duration:
                info['error'] = f"Duration too short: {info['duration']}s"
                return False, info
            
            logging.debug(f"Video validation passed: {file_path} - duration={info['duration']}s, codec={info['codec']}")
            return True, info
            
        except subprocess.TimeoutExpired:
            logging.warning(f"ffprobe validation timed out for {file_path}")
        except Exception as e:
            logging.debug(f"ffprobe validation error: {e}")
    
    # Fallback: if ffprobe not available or failed, just check size
    logging.debug(f"Video validation (size-only): {file_path} - {file_size} bytes")
    return True, info


def convert_with_vlc(input_path, output_path=None):
    """Convert video using VLC (Python bindings or subprocess).
    
    Returns:
        Tuple of (success: bool, result: Path or error_message: str)
    """
    input_path = sanitize_path(input_path)
    
    if output_path is None:
        base = input_path.stem
        ext = input_path.suffix
        output_path = input_path.parent / f"{base}_converted{ext}"
    else:
        output_path = sanitize_path(output_path)

    if HAS_VLC:
        try:
            return convert_with_vlc_python(input_path, output_path)
        except Exception as e:
            logging.warning(f"python-vlc failed: {e}. Trying subprocess method...")

    return convert_with_vlc_subprocess(input_path, output_path)


def convert_with_vlc_python(input_path, output_path):
    """Convert video using VLC Python bindings.
    
    Returns:
        Tuple of (success: bool, result: Path or error_message: str)
    """
    input_path = sanitize_path(input_path)
    output_path = sanitize_path(output_path)
    
    try:
        logging.info(f"Converting with VLC (Python bindings): {input_path}")
        instance = vlc.Instance('--no-xlib')
        player = instance.media_player_new()
        media = instance.media_new(str(input_path))

        # Use forward slashes for VLC compatibility
        output_str = str(output_path).replace('\\', '/')
        transcode_options = (
            f"#transcode{{"
            f"vcodec=h264,venc=x264{{preset=medium,profile=main}},acodec=mp3,ab=192,channels=2,samplerate=44100}}:"
            f"standard{{access=file,mux=mp4,dst={output_str}}}"
        )
        media.add_option(f":sout={transcode_options}")
        media.add_option(":sout-keep")
        player.set_media(media)
        player.play()

        timeout = 300
        start_time = time.time()
        while time.time() - start_time < timeout:
            state = player.get_state()
            if state == vlc.State.Ended:
                break
            elif state == vlc.State.Error:
                player.stop()
                return False, "VLC conversion error"
            time.sleep(0.5)
        else:
            player.stop()
            if output_path.exists():
                output_path.unlink()
            return False, "VLC conversion timed out"

        player.stop()
        player.release()
        media.release()

        if output_path.exists() and output_path.stat().st_size > 1000:
            logging.info(f"VLC Python conversion successful: {output_path}")
            return True, output_path
        else:
            if output_path.exists():
                output_path.unlink()
            return False, "VLC conversion failed"

    except Exception as e:
        logging.error(f"VLC Python conversion error: {e}", exc_info=True)
        if output_path.exists():
            try:
                output_path.unlink()
            except Exception:
                pass
        raise


def convert_with_vlc_subprocess(input_path, output_path):
    """Convert video using VLC subprocess with proper path sanitization.
    
    Returns:
        Tuple of (success: bool, result: Path or error_message: str)
    """
    vlc_path = find_vlc_executable()
    if not vlc_path:
        logging.error("VLC executable not found on system")
        return False, "VLC not installed"
    
    # Sanitize paths to prevent trailing brace issues
    input_path = sanitize_path(input_path)
    output_path = sanitize_path(output_path)
    
    # CRITICAL: Use quotes around path in --sout to prevent issues with special chars
    # Also escape the braces in the transcode options properly
    output_str = str(output_path).replace('\\', '/')  # VLC prefers forward slashes
    
    cmd = [
        vlc_path, "-I", "dummy", "--no-repeat", "--no-loop",
        str(input_path),
        "--sout",
        (f"#transcode{{vcodec=h264,venc=x264{{preset=medium,profile=main}},acodec=mp3,ab=192,channels=2,samplerate=44100}}:"
         f"standard{{access=file,mux=mp4,dst={output_str}}}"),
        "vlc://quit"
    ]

    logging.debug(f"VLC command: {' '.join(cmd)}")
    logging.info(f"Converting with VLC subprocess: {input_path} -> {output_path}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, creationflags=CREATE_NO_WINDOW)
        
        # Log stderr for debugging
        if result.stderr:
            logging.debug(f"VLC stderr: {result.stderr[:500]}")
        
        if output_path.exists() and output_path.stat().st_size > 1000:
            logging.info(f"VLC subprocess conversion successful: {output_path}")
            return True, output_path
        else:
            if output_path.exists():
                output_path.unlink()
            logging.error(f"VLC subprocess conversion failed - output not created or too small")
            return False, "VLC subprocess conversion failed"
    except subprocess.TimeoutExpired:
        logging.error("VLC subprocess conversion timed out")
        if output_path.exists():
            try:
                output_path.unlink()
            except Exception:
                pass
        return False, "VLC subprocess timeout"
    except Exception as e:
        logging.error(f"VLC subprocess conversion error: {e}", exc_info=True)
        if output_path.exists():
            try:
                output_path.unlink()
            except Exception:
                pass
        return False, str(e)


def set_video_metadata(file_path, date_obj, latitude, longitude, timezone_offset=None):
    """Set video metadata using mutagen (MP4).
    
    Args:
        file_path: Path to the MP4 video file
        date_obj: datetime object with timezone info (local time)
        latitude: GPS latitude (or None)
        longitude: GPS longitude (or None)
        timezone_offset: Timezone offset string like '-05:00'
    """
    if not HAS_MUTAGEN:
        logging.debug("Skipping video metadata: mutagen not available")
        return False

    backup_path = f"{file_path}.backup"
    try:
        # Quick sanity check: file must exist and be reasonably sized
        if not os.path.exists(file_path):
            logging.error("Video file does not exist: %s", file_path)
            return False

        shutil.copy2(file_path, backup_path)
        try:
            video = MP4(file_path)
            # Format with timezone offset for better app compatibility
            if timezone_offset:
                creation_time = date_obj.strftime("%Y-%m-%dT%H:%M:%S") + timezone_offset
            else:
                creation_time = date_obj.strftime("%Y-%m-%dT%H:%M:%SZ")
            video["\xa9day"] = creation_time
            try:
                video["\xa9ART"] = date_obj.strftime("%Y")
            except Exception:
                pass

            # CRITICAL for iCloud/Apple Photos: Set Apple-specific creation date
            # iCloud reads 'com.apple.quicktime.creationdate' for the "date taken"
            # Without this, iCloud may show videos with wrong dates (e.g., 01/08/1970)
            try:
                from mutagen.mp4 import MP4FreeForm, AtomDataType
                video["----:com.apple.quicktime:creationdate"] = [
                    MP4FreeForm(creation_time.encode('utf-8'), dataformat=AtomDataType.UTF8)
                ]
                logging.debug(f"Set Apple QuickTime creationdate: {creation_time}")
            except (ImportError, AttributeError):
                # Fallback for older mutagen versions
                video["----:com.apple.quicktime:creationdate"] = [creation_time.encode('utf-8')]
                logging.debug(f"Set Apple QuickTime creationdate (fallback): {creation_time}")

            # Add GPS metadata if available
            if latitude is not None and longitude is not None:
                location_str = f"{latitude:+.6f}{longitude:+.6f}/"
                try:
                    from mutagen.mp4 import MP4FreeForm, AtomDataType
                    video["----:com.apple.quicktime:location-ISO6709"] = [
                        MP4FreeForm(location_str.encode('utf-8'), dataformat=AtomDataType.UTF8)
                    ]
                    video["----:com.apple.quicktime:latitude"] = [
                        MP4FreeForm(str(latitude).encode('utf-8'), dataformat=AtomDataType.UTF8)
                    ]
                    video["----:com.apple.quicktime:longitude"] = [
                        MP4FreeForm(str(longitude).encode('utf-8'), dataformat=AtomDataType.UTF8)
                    ]
                except (ImportError, AttributeError):
                    video["----:com.apple.quicktime:location-ISO6709"] = [location_str.encode('utf-8')]
                    video["----:com.apple.quicktime:latitude"] = [str(latitude).encode('utf-8')]
                    video["----:com.apple.quicktime:longitude"] = [str(longitude).encode('utf-8')]
                logging.info(f"Setting GPS metadata via mutagen: lat={latitude}, lon={longitude} for {file_path}")
            else:
                logging.info(f"No GPS data available for video (mutagen): {file_path}")

            # write tags
            video.save()

            # verify by attempting to load the saved file with mutagen
            try:
                _ = MP4(file_path)
            except Exception as e:
                logging.error("Mutagen failed to re-open saved file, restoring backup: %s", e)
                shutil.copy2(backup_path, file_path)
                os.remove(backup_path)
                return False

            os.remove(backup_path)
            logging.info("Successfully set video metadata using mutagen: %s", file_path)
            return True
        except Exception as e:
            logging.exception("Error writing mutagen metadata, restoring backup if any: %s", file_path)
            if os.path.exists(backup_path):
                try:
                    shutil.copy2(backup_path, file_path)
                    os.remove(backup_path)
                except Exception:
                    pass
            return False

    except Exception:
        logging.exception("Unexpected error in set_video_metadata for %s", file_path)
        if os.path.exists(backup_path):
            try:
                os.remove(backup_path)
            except Exception:
                pass
        return False


def set_video_metadata_ffmpeg(file_path, date_obj, latitude, longitude, timezone_offset=None):
    """Set video metadata using ffmpeg.
    
    Args:
        file_path: Path to the video file
        date_obj: datetime object with timezone info (local time)
        latitude: GPS latitude (or None)
        longitude: GPS longitude (or None)
        timezone_offset: Timezone offset string like '-05:00'
    """
    if not check_ffmpeg():
        logging.debug("ffmpeg not available for metadata writing")
        return False

    temp_output = None
    try:
        temp_output = f"{file_path}.temp.mp4"
        # Format with timezone offset
        if timezone_offset:
            creation_time_str = date_obj.strftime("%Y-%m-%dT%H:%M:%S") + timezone_offset
        else:
            creation_time_str = date_obj.strftime("%Y-%m-%dT%H:%M:%S")
        
        # Also create a UTC version for the moov header (QuickTime standard)
        # iCloud reads creation_time from moov.mvhd which expects UTC
        utc_creation_str = date_obj.strftime("%Y-%m-%dT%H:%M:%S")
        if timezone_offset:
            utc_creation_str = creation_time_str  # ffmpeg handles TZ conversion internally
        else:
            utc_creation_str = creation_time_str + "Z"
        
        cmd = [
            'ffmpeg', '-y', '-i', str(file_path), '-c', 'copy',
            '-metadata', f'creation_time={utc_creation_str}',
            '-metadata', f'date={creation_time_str}',
            # Apple-specific metadata for iCloud/Apple Photos compatibility
            # This is the primary tag iCloud uses for "date taken" on videos
            '-metadata', f'com.apple.quicktime.creationdate={creation_time_str}',
            '-movflags', '+use_metadata_tags',
        ]
        
        # Add location metadata if available
        if latitude is not None and longitude is not None:
            location_iso = f'{latitude:+.6f}{longitude:+.6f}/'
            cmd.extend([
                '-metadata', f'location={location_iso}',
                '-metadata', f'location-eng={latitude}, {longitude}',
                '-metadata', f'com.apple.quicktime.location.ISO6709={location_iso}',
                '-metadata', f'com.apple.quicktime.GPS.latitude={latitude}',
                '-metadata', f'com.apple.quicktime.GPS.longitude={longitude}'
            ])
            logging.info(f"Adding GPS metadata to video: lat={latitude}, lon={longitude}")
        else:
            logging.info(f"No GPS data available for video: {file_path}")
        
        cmd.append(str(temp_output))

        logging.debug(f"Setting video metadata with ffmpeg: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=CREATE_NO_WINDOW)

        if result.returncode == 0 and os.path.exists(temp_output):
            try:
                os.remove(file_path)
                os.rename(temp_output, file_path)
                logging.info(f"Successfully set video metadata using ffmpeg: {file_path}")
                return True
            except Exception as e:
                logging.error(f"Failed to replace file after metadata update: {e}")
                if os.path.exists(temp_output):
                    os.remove(temp_output)
                return False
        else:
            if os.path.exists(temp_output):
                os.remove(temp_output)
            return False
    except subprocess.TimeoutExpired:
        if temp_output and os.path.exists(temp_output):
            try:
                os.remove(temp_output)
            except Exception:
                pass
        return False
    except Exception:
        if temp_output and os.path.exists(temp_output):
            try:
                os.remove(temp_output)
            except Exception:
                pass
        return False


def enforce_portrait_video(file_path, timeout=300):
    # This function intentionally mirrors the main implementation so GUI code can call it unchanged
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
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10, creationflags=CREATE_NO_WINDOW)
            import json
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
                proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=timeout, creationflags=CREATE_NO_WINDOW)
                if proc.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
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


def convert_hevc_to_h264(input_path, output_path=None, max_attempts=3, failed_dir_path="downloads/failed_conversions"):
    """Convert video to H.264 using atomic temp file approach with validation.
    
    Returns:
        Tuple of (success: bool, result: Path or error_message: str)
    """
    input_path = sanitize_path(input_path)
    
    if not HAS_PYAV:
        logging.warning("PyAV not installed. Attempting VLC fallback...")
        return convert_with_vlc(input_path, output_path)

    # Use temp file in same directory for atomic replace
    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}_converted{input_path.suffix}"
    else:
        output_path = sanitize_path(output_path)
    
    # Always write to .temp file first
    temp_output = output_path.parent / f"{output_path.stem}.temp{output_path.suffix}"
    
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        input_container = None
        output_container = None
        conversion_id = f"{input_path.stem}_{int(time.time())}_{attempt}"
        
        try:
            logging.info(f"[{conversion_id}] Attempt {attempt}: Opening input video: {input_path}")
            input_container = av.open(str(input_path))
            input_video_stream = input_container.streams.video[0]

            # Detect rotation metadata BEFORE opening output container
            rotation = _get_video_rotation(input_path)
            needs_rotation = rotation in (90, 180, 270) and HAS_PIL
            if rotation in (90, 180, 270) and not HAS_PIL:
                logging.warning(f"[{conversion_id}] Video has {rotation}° rotation but PIL not available - orientation may be incorrect")
            if needs_rotation:
                logging.info(f"[{conversion_id}] Video has {rotation}° rotation metadata - will apply during conversion")

            logging.info(f"[{conversion_id}] Creating temp output: {temp_output}")
            output_container = av.open(str(temp_output), 'w')

            output_video_stream = output_container.add_stream('h264', rate=input_video_stream.average_rate)
            # Swap width/height for 90° or 270° rotation so portrait videos stay portrait
            if rotation in (90, 270):
                output_video_stream.width = input_video_stream.height
                output_video_stream.height = input_video_stream.width
                logging.info(f"[{conversion_id}] Swapping dimensions: {input_video_stream.width}x{input_video_stream.height} -> {input_video_stream.height}x{input_video_stream.width}")
            else:
                output_video_stream.width = input_video_stream.width
                output_video_stream.height = input_video_stream.height
            output_video_stream.pix_fmt = 'yuv420p'
            output_video_stream.bit_rate = input_video_stream.bit_rate or 2000000

            audio_stream = None
            output_audio_stream = None
            if input_container.streams.audio:
                audio_stream = input_container.streams.audio[0]
                output_audio_stream = output_container.add_stream('aac', rate=audio_stream.rate)
                if hasattr(audio_stream, 'layout') and audio_stream.layout:
                    output_audio_stream.layout = audio_stream.layout

            logging.info(f"[{conversion_id}] Processing frames...")
            for packet in input_container.demux():
                if packet.stream.type == 'video':
                    for frame in packet.decode():
                        if needs_rotation:
                            # Apply rotation via PIL to preserve correct orientation
                            # PIL's rotate() is counterclockwise, so we negate for clockwise
                            try:
                                img = frame.to_image()
                                if rotation == 90:
                                    # 90° CW = transpose ROTATE_270 in PIL
                                    try:
                                        img = img.transpose(PILImage.Transpose.ROTATE_270)
                                    except AttributeError:
                                        img = img.rotate(-90, expand=True)
                                elif rotation == 270:
                                    # 270° CW = transpose ROTATE_90 in PIL
                                    try:
                                        img = img.transpose(PILImage.Transpose.ROTATE_90)
                                    except AttributeError:
                                        img = img.rotate(-270, expand=True)
                                elif rotation == 180:
                                    try:
                                        img = img.transpose(PILImage.Transpose.ROTATE_180)
                                    except AttributeError:
                                        img = img.rotate(180, expand=True)
                                rotated_frame = av.VideoFrame.from_image(img)
                                rotated_frame.pts = frame.pts
                                rotated_frame.time_base = frame.time_base
                                for out_packet in output_video_stream.encode(rotated_frame):
                                    output_container.mux(out_packet)
                            except Exception as rot_err:
                                logging.warning(f"[{conversion_id}] Frame rotation failed, using original: {rot_err}")
                                for out_packet in output_video_stream.encode(frame):
                                    output_container.mux(out_packet)
                        else:
                            for out_packet in output_video_stream.encode(frame):
                                output_container.mux(out_packet)
                elif packet.stream.type == 'audio' and output_audio_stream:
                    for frame in packet.decode():
                        for out_packet in output_audio_stream.encode(frame):
                            output_container.mux(out_packet)

            logging.info(f"[{conversion_id}] Flushing streams...")
            for packet in output_video_stream.encode():
                output_container.mux(packet)
            if output_audio_stream:
                for packet in output_audio_stream.encode():
                    output_container.mux(packet)

            logging.info(f"[{conversion_id}] Closing containers...")
            if input_container:
                input_container.close()
                input_container = None
            if output_container:
                output_container.close()
                output_container = None

            # CRITICAL: Validate the temp file before replacing original
            logging.info(f"[{conversion_id}] Validating converted file...")
            is_valid, validation_info = validate_video_file(temp_output)
            
            if not is_valid:
                logging.warning(f"[{conversion_id}] Validation failed: {validation_info.get('error')}")
                if temp_output.exists():
                    temp_output.unlink()
                continue  # Retry
            
            # Validation passed - atomically replace
            logging.info(f"[{conversion_id}] Validation passed, performing atomic replace...")
            try:
                # Use os.replace for atomic operation (Windows: overwrites if exists)
                os.replace(str(temp_output), str(output_path))
                logging.info(f"[{conversion_id}] Conversion successful: {output_path}")
                return True, output_path
            except Exception as replace_error:
                logging.error(f"[{conversion_id}] Failed to replace file: {replace_error}")
                if temp_output.exists():
                    temp_output.unlink()
                return False, f"Failed to replace file: {replace_error}"

        except Exception as e:
            logging.error(f"[{conversion_id}] Error during conversion: {e}", exc_info=True)
            try:
                if input_container:
                    input_container.close()
            except Exception:
                pass
            try:
                if output_container:
                    output_container.close()
            except Exception:
                pass
            
            if temp_output.exists():
                try:
                    temp_output.unlink()
                    logging.info(f"[{conversion_id}] Removed invalid temp file")
                except Exception as cleanup_error:
                    logging.error(f"[{conversion_id}] Failed to remove temp file: {cleanup_error}")
            
            time.sleep(0.5)

    # All PyAV attempts exhausted - try VLC fallback
    logging.info(f"All PyAV attempts failed for {input_path}. Trying VLC fallback...")
    time.sleep(1)
    
    # VLC fallback also uses temp file
    vlc_temp = output_path.parent / f"{output_path.stem}.vlc_temp{output_path.suffix}"
    vlc_success, vlc_result = convert_with_vlc(input_path, vlc_temp)
    
    if vlc_success:
        # Validate VLC output
        is_valid, validation_info = validate_video_file(vlc_temp)
        if is_valid:
            try:
                os.replace(str(vlc_temp), str(output_path))
                logging.info(f"VLC fallback conversion successful: {output_path}")
                return True, output_path
            except Exception as e:
                logging.error(f"Failed to replace after VLC conversion: {e}")
                if vlc_temp.exists():
                    vlc_temp.unlink()
        else:
            logging.warning(f"VLC conversion validation failed: {validation_info.get('error')}")
            if vlc_temp.exists():
                vlc_temp.unlink()

    # Complete failure - move to failed_conversions with logs
    failed_dir = Path(failed_dir_path)
    failed_dir.mkdir(parents=True, exist_ok=True)
    failed_path = failed_dir / input_path.name

    error_log_path = failed_dir / f"{input_path.stem}_error_{int(time.time())}.log"
    try:
        with open(error_log_path, 'w', encoding='utf-8') as f:
            f.write(f"Failed conversion: {input_path}\\n")
            f.write(f"PyAV: Failed after {max_attempts} attempts\\n")
            f.write(f"VLC: {vlc_result if not vlc_success else 'Failed validation'}\\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\\n")
            if isinstance(vlc_result, str):
                f.write(f"\\nVLC Error Details:\\n{vlc_result}\\n")
        logging.info(f"Saved error log: {error_log_path}")
    except Exception as log_error:
        logging.error(f"Failed to save error log: {log_error}")

    try:
        if not failed_path.exists():
            shutil.copy2(input_path, failed_path)
            logging.info(f"Copied failed file to: {failed_path}")
    except Exception as copy_error:
        logging.error(f"Failed to copy {input_path} to {failed_path}: {copy_error}")

    logging.error(f"All conversion attempts failed for {input_path}")
    return False, f"Failed after {max_attempts} PyAV attempts and VLC fallback"