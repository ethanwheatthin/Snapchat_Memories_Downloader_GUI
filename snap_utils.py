import os
import logging
from datetime import datetime, timezone
from pathlib import Path

# Optional timezone support
HAS_TIMEZONE_SUPPORT = False
_TIMEZONE_IMPORT_ERROR = None
try:
    from timezonefinder import TimezoneFinder
    import pytz
    HAS_TIMEZONE_SUPPORT = True
except Exception as e:
    HAS_TIMEZONE_SUPPORT = False
    _TIMEZONE_IMPORT_ERROR = e
    logging.debug("Timezone support libraries not available: %s", e, exc_info=True)


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
    dt_naive = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S UTC")
    # Convert naive datetime to timezone-aware UTC
    # This ensures timestamp() returns correct Unix timestamp regardless of local timezone
    return dt_naive.replace(tzinfo=timezone.utc)


def convert_to_local_timezone(utc_datetime, latitude, longitude, force_system_tz=False):
    """
    Convert UTC datetime to local timezone using GPS coordinates or system timezone.
    
    Args:
        utc_datetime: timezone-aware UTC datetime object
        latitude: GPS latitude coordinate (can be None)
        longitude: GPS longitude coordinate (can be None)
        force_system_tz: If True, use system timezone instead of GPS-based lookup
    
    Returns:
        Tuple of (local_datetime, timezone_name, timezone_offset_str)
        local_datetime: timezone-aware datetime in local timezone
        timezone_name: IANA timezone name (e.g., 'America/New_York')
        timezone_offset_str: offset string like '-05:00' or '-04:00'
    """
    if not HAS_TIMEZONE_SUPPORT:
        logging.debug("Timezone support not available, using UTC: %s", _TIMEZONE_IMPORT_ERROR)
        offset_str = utc_datetime.strftime("%z")
        offset_str = (offset_str[:-2] + ":" + offset_str[-2:]) if len(offset_str) >= 5 else "+00:00"
        return utc_datetime, "UTC", offset_str
    
    # Try GPS-based timezone lookup if coordinates are available
    if not force_system_tz and latitude is not None and longitude is not None:
        try:
            tf = TimezoneFinder()
            tz_name = tf.timezone_at(lat=latitude, lng=longitude)
            if tz_name:
                local_tz = pytz.timezone(tz_name)
                local_dt = utc_datetime.astimezone(local_tz)
                offset_str = local_dt.strftime("%z")
                offset_str = (offset_str[:-2] + ":" + offset_str[-2:]) if len(offset_str) >= 5 else "+00:00"
                logging.debug(
                    "Converted %s UTC to %s (%s) using GPS coordinates (%.4f, %.4f)",
                    utc_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                    tz_name,
                    offset_str,
                    latitude,
                    longitude
                )
                return local_dt, tz_name, offset_str
        except Exception as e:
            logging.warning("GPS timezone lookup failed for (%.4f, %.4f): %s", latitude, longitude, e)
    
    # Fall back to system timezone
    try:
        local_tz = pytz.timezone('UTC')
        try:
            import tzlocal
            local_tz_str = tzlocal.get_localzone_name()
            local_tz = pytz.timezone(local_tz_str)
        except Exception:
            # Fallback: try to detect from system
            pass
        
        local_dt = utc_datetime.astimezone(local_tz)
        offset_str = local_dt.strftime("%z")
        offset_str = (offset_str[:-2] + ":" + offset_str[-2:]) if len(offset_str) >= 5 else "+00:00"
        tz_name = str(local_tz)
        logging.debug(
            "Converted %s UTC to system timezone %s (%s)",
            utc_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            tz_name,
            offset_str
        )
        return local_dt, tz_name, offset_str
    except Exception as e:
        logging.error("Failed to convert to local timezone: %s", e)
        offset_str = "+00:00"
        return utc_datetime, "UTC", offset_str


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
