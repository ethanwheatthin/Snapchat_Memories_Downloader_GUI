import os
import logging
from datetime import datetime, timezone
from pathlib import Path


def parse_date(date_str):
    """Parse date string from JSON format to timezone-aware datetime object.
    
    CRITICAL FIX: Creates timezone-aware UTC datetime to prevent timezone offset bugs.
    Previously created naive datetime which Python interpreted as local time when
    calling timestamp(), causing 1-hour offset in DST-observing timezones.
    
    Args:
        date_str: Date string in format "YYYY-MM-DD HH:MM:SS UTC"
        
    Returns:
        datetime: Timezone-aware datetime object in UTC
    """
    # Parse the date string (ignoring the literal 'UTC' suffix)
    naive_dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S UTC")
    
    # Convert to timezone-aware UTC datetime
    # This ensures timestamp() returns correct Unix timestamp regardless of local timezone
    aware_dt = naive_dt.replace(tzinfo=timezone.utc)
    
    logging.debug(f"Parsed date: {date_str} -> {aware_dt} (UTC timestamp: {aware_dt.timestamp()})")
    return aware_dt


def parse_location(location_str):
    """Parse location string to get latitude and longitude."""
    if not location_str or location_str == "N/A":
        return None, None

    try:
        coords = location_str.split(": ")[1]
        lat, lon = coords.split(", ")
        return float(lat), float(lon)
    except Exception:
        return None, None


def decimal_to_dms(decimal):
    """Convert decimal degrees to degrees, minutes, seconds format for EXIF."""
    decimal = float(decimal)
    decimal = abs(decimal)

    degrees = int(decimal)
    minutes = int((decimal - degrees) * 60)
    seconds = ((decimal - degrees) * 60 - minutes) * 60

    return ((degrees, 1), (minutes, 1), (int(seconds * 100), 100))


def set_file_timestamps(file_path, date_obj):
    """Set file modification and access times."""
    timestamp = date_obj.timestamp()
    try:
        os.utime(file_path, (timestamp, timestamp))
    except Exception:
        logging.debug("Failed to set timestamps for %s", file_path)


def get_file_extension(media_type):
    """Determine file extension based on media type."""
    if media_type == "Image":
        return ".jpg"
    elif media_type == "Video":
        return ".mp4"
    else:
        return ".bin"


def validate_downloaded_file(file_path):
    """Validate the downloaded file to ensure it is complete and not corrupted."""
    try:
        logging.info(f"Validating downloaded file: {file_path}")

        if not os.path.exists(file_path):
            logging.error(f"File does not exist: {file_path}")
            return False

        file_size = os.path.getsize(file_path)
        if file_size < 100:
            logging.error(f"File is too small to be valid: {file_size} bytes")
            return False

        with open(file_path, 'rb') as f:
            magic = f.read(32)

        is_valid_jpg = magic[:2] == b'\xff\xd8' or magic[:3] == b'\xff\xd8\xff'
        is_valid_png = magic[:8] == b'\x89PNG\r\n\x1a\n'

        is_valid_mp4 = (
            len(magic) >= 12 and 
            (magic[4:8] == b'ftyp' or
             magic[4:8] == b'mdat' or
             magic[4:8] == b'moov' or
             magic[4:8] == b'wide')
        )

        is_valid_zip = magic[:4] == b'PK\x03\x04'

        if not (is_valid_jpg or is_valid_png or is_valid_mp4 or is_valid_zip):
            magic_hex = magic[:8].hex()
            logging.error(f"File format is not recognized or is corrupted (magic: {magic_hex}).")
            return False

        logging.info("File validation successful.")
        return True

    except Exception as e:
        logging.error(f"Error during file validation: {e}", exc_info=True)
        return False
