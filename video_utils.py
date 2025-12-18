import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

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


def convert_with_vlc(input_path, output_path=None):
    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_converted{ext}"

    if HAS_VLC:
        try:
            return convert_with_vlc_python(input_path, output_path)
        except Exception as e:
            logging.warning(f"python-vlc failed: {e}. Trying subprocess method...")

    return convert_with_vlc_subprocess(input_path, output_path)


def convert_with_vlc_python(input_path, output_path):
    try:
        logging.info(f"Converting with VLC (Python bindings): {input_path}")
        instance = vlc.Instance('--no-xlib')
        player = instance.media_player_new()
        media = instance.media_new(input_path)

        transcode_options = (
            f"#transcode{{"
            f"vcodec=h264,venc=x264{{preset=medium,profile=main}},acodec=mp3,ab=192,channels=2,samplerate=44100}}:"
            f"standard{{access=file,mux=mp4,dst={output_path}}}"
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
            if os.path.exists(output_path):
                os.remove(output_path)
            return False, "VLC conversion timed out"

        player.stop()
        player.release()
        media.release()

        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return True, output_path
        else:
            if os.path.exists(output_path):
                os.remove(output_path)
            return False, "VLC conversion failed"

    except Exception as e:
        logging.error(f"VLC Python conversion error: {e}", exc_info=True)
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass
        raise


def convert_with_vlc_subprocess(input_path, output_path):
    vlc_path = find_vlc_executable()
    if not vlc_path:
        logging.error("VLC executable not found on system")
        return False, "VLC not installed"

    cmd = [
        vlc_path, "-I", "dummy", "--no-repeat", "--no-loop",
        input_path,
        "--sout",
        (f"#transcode{{vcodec=h264,venc=x264{{preset=medium,profile=main}},acodec=mp3,ab=192,channels=2,samplerate=44100}}:"
         f"standard{{access=file,mux=mp4,dst={output_path}}}"),
        "vlc://quit"
    ]

    logging.debug(f"VLC command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
        return True, output_path
    else:
        if os.path.exists(output_path):
            os.remove(output_path)
        return False, "VLC subprocess conversion failed"


def set_video_metadata(file_path, date_obj, latitude, longitude):
    if not HAS_MUTAGEN:
        return False

    backup_path = f"{file_path}.backup"
    try:
        with open(file_path, 'rb') as f:
            header = f.read(12)
            if len(header) < 8 or header[4:8] not in [b'ftyp', b'mdat', b'moov']:
                return False

        shutil.copy2(file_path, backup_path)
        try:
            video = MP4(file_path)
            creation_time = date_obj.strftime("%Y-%m-%dT%H:%M:%SZ")
            video["\xa9day"] = creation_time
            try:
                video["\xa9ART"] = date_obj.strftime("%Y")
            except Exception:
                pass

            if latitude is not None and longitude is not None:
                location_str = f"{latitude:+.6f}{longitude:+.6f}/"
                video["----:com.apple.quicktime:location-ISO6709"] = location_str.encode('utf-8')
                video["----:com.apple.quicktime:latitude"] = str(latitude).encode('utf-8')
                video["----:com.apple.quicktime:longitude"] = str(longitude).encode('utf-8')

            video.save()

            with open(file_path, 'rb') as f:
                verify_header = f.read(12)
                if len(verify_header) < 8 or verify_header[4:8] not in [b'ftyp', b'mdat', b'moov']:
                    shutil.copy2(backup_path, file_path)
                    os.remove(backup_path)
                    return False

            os.remove(backup_path)
            return True
        except Exception:
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, file_path)
                os.remove(backup_path)
            return False

    except Exception:
        if os.path.exists(backup_path):
            os.remove(backup_path)
        return False


def set_video_metadata_ffmpeg(file_path, date_obj, latitude, longitude):
    if not check_ffmpeg():
        return False

    temp_output = None
    try:
        temp_output = f"{file_path}.temp.mp4"
        creation_time_str = date_obj.strftime("%Y-%m-%dT%H:%M:%S")
        cmd = ['ffmpeg', '-y', '-i', str(file_path), '-c', 'copy', '-metadata', f'creation_time={creation_time_str}', '-metadata', f'date={creation_time_str}']
        if latitude is not None and longitude is not None:
            cmd.extend(['-metadata', f'location={latitude:+.6f}{longitude:+.6f}/', '-metadata', f'location-eng={latitude}, {longitude}'])
        cmd.append(str(temp_output))

        logging.debug(f"Setting video metadata with ffmpeg: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

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
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
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
                proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=timeout)
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
    if not HAS_PYAV:
        logging.warning("PyAV not installed. Attempting VLC fallback...")
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

            logging.info(f"Attempt {attempt}: Creating output container: {output_path}")
            output_container = av.open(output_path, 'w')

            output_video_stream = output_container.add_stream('h264', rate=input_video_stream.average_rate)
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
            time.sleep(0.5)
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                    logging.info(f"Attempt {attempt}: Removed partial output: {output_path}")
                except Exception as cleanup_error:
                    logging.error(f"Attempt {attempt}: Failed to remove partial output {output_path}: {cleanup_error}", exc_info=True)

        logging.warning(f"Attempt {attempt} failed. Retrying...")

    logging.info("All PyAV attempts failed. Trying VLC fallback...")
    time.sleep(1)
    vlc_success, vlc_result = convert_with_vlc(input_path, output_path)
    if vlc_success:
        logging.info(f"VLC fallback conversion successful: {vlc_result}")
        return True, vlc_result

    # Move to failed_conversions
    failed_dir = Path(failed_dir_path)
    failed_dir.mkdir(parents=True, exist_ok=True)
    failed_path = failed_dir / Path(input_path).name

    error_log_path = failed_dir / f"{Path(input_path).stem}_error.txt"
    try:
        with open(error_log_path, 'w') as f:
            f.write(f"Failed conversion: {input_path}\n")
            f.write(f"PyAV result: Failed after {max_attempts} attempts\n")
            f.write(f"VLC result: {vlc_result}\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
    except Exception as log_error:
        logging.error(f"Failed to save error log: {log_error}")

    try:
        shutil.copy2(input_path, failed_path)
        try:
            os.remove(input_path)
        except Exception:
            pass
    except Exception as copy_error:
        logging.error(f"Failed to copy {input_path} to {failed_path}: {copy_error}", exc_info=True)

    logging.error(f"All conversion attempts failed for {input_path}")
    return False, f"Failed after {max_attempts} PyAV attempts and VLC fallback"