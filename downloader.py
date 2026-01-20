import logging
import os
import time
import requests
from pathlib import Path
import zip_utils
import snap_utils
from pathlib import Path
import tempfile
import threading

# Thread-local storage for unique temporary file suffixes
_thread_local = threading.local()

def _get_thread_id():
    """Get a unique identifier for the current thread."""
    if not hasattr(_thread_local, 'thread_id'):
        _thread_local.thread_id = threading.get_ident()
    return _thread_local.thread_id



def download_media(url, output_path, max_retries=3, progress_callback=None, date_obj=None):
    last_error = None
    
    # Create thread-safe temporary file path
    output_path = Path(output_path)
    thread_id = _get_thread_id()
    timestamp = int(time.time() * 1000)  # milliseconds for uniqueness
    temp_suffix = f".tmp_{thread_id}_{timestamp}"

    for attempt in range(max_retries):
        try:
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

            # Log the URL and output path for debugging duplicate file issues
            logging.info(f"Downloading from: {url}")
            logging.info(f"Saving to: {output_path}")
            
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

            is_html = (magic[:5].lower() == b'<!doc' or
                       magic[:5].lower() == b'<html' or
                       b'<html' in magic.lower() or
                       b'<!doctype' in magic.lower())
            if is_html:
                last_error = Exception("HTML page instead of media file")
                if progress_callback:
                    progress_callback("Downloaded content is HTML (likely an error page), will retry if possible")
                continue

            is_valid_zip = magic[:4] == b'PK\x03\x04'
            if is_valid_zip:
                # Use thread-safe temp path for ZIP
                zip_path = str(output_path) + temp_suffix + ".zip"
                write_path = zip_path
            else:
                # Use thread-safe temp path for regular files
                write_path = str(output_path) + temp_suffix

            try:
                with open(write_path, 'wb') as fd:
                    fd.write(first_chunk)
                    bytes_written = len(first_chunk)
                    for chunk in iterator:
                        if chunk:
                            fd.write(chunk)
                            bytes_written += len(chunk)
                logging.info(f"Wrote {bytes_written} bytes to {write_path}")
            except Exception as write_err:
                last_error = write_err
                logging.warning(f"Failed writing downloaded file to {write_path}: {write_err}")
                try:
                    if os.path.exists(write_path):
                        os.remove(write_path)
                except Exception:
                    pass
                continue

            if is_valid_zip:
                try:
                    if progress_callback:
                        progress_callback("Downloaded ZIP archive, processing...")
                    merged = zip_utils.process_zip_overlay(write_path, str(Path(output_path).parent), date_obj)
                    if merged:
                        try:
                            os.remove(write_path)
                        except Exception:
                            pass
                        logging.info(f"Created merged images: {merged}")
                        return (True, merged)

                    if zip_utils.extract_media_from_zip(write_path, str(output_path)):
                        try:
                            os.remove(write_path)
                        except Exception:
                            pass
                        # File was extracted directly to output_path
                        final_path = str(output_path)
                    else:
                        logging.warning(f"Could not extract media from ZIP: {write_path}")
                        # Keep the ZIP with temp suffix
                        final_path = write_path
                except Exception as zip_err:
                    logging.warning(f"Error handling ZIP file: {zip_err}")
                    final_path = write_path
            else:
                # Regular file - atomically rename from temp to final
                try:
                    logging.info(f"Atomically moving {write_path} to {output_path}")
                    os.replace(write_path, str(output_path))
                    final_path = str(output_path)
                    logging.info(f"Successfully moved to final path: {final_path}")
                except Exception as rename_err:
                    logging.error(f"Failed to rename temp file to final path: {rename_err}")
                    last_error = rename_err
                    try:
                        if os.path.exists(write_path):
                            os.remove(write_path)
                    except Exception:
                        pass
                    continue

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
            # Clean up any temp files
            try:
                for pattern in [str(output_path) + temp_suffix, str(output_path) + temp_suffix + ".zip"]:
                    if os.path.exists(pattern):
                        os.remove(pattern)
            except Exception:
                pass
            continue
        except Exception as err:
            last_error = err
            logging.error(f"Unexpected error during download attempt {attempt + 1}/{max_retries}: {err}", exc_info=True)
            if progress_callback:
                progress_callback(f"Unexpected error during download attempt {attempt + 1}/{max_retries}: {err}")
            # Clean up any temp files
            try:
                for pattern in [str(output_path) + temp_suffix, str(output_path) + temp_suffix + ".zip"]:
                    if os.path.exists(pattern):
                        os.remove(pattern)
            except Exception:
                pass
            continue

    logging.error(f"Download failed after {max_retries} attempts. Last error: {last_error}")
    if progress_callback:
        progress_callback(f"Download failed after {max_retries} attempts. Last error: {last_error}")
    return (False, None)
