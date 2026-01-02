import logging
import os
from pathlib import Path

# piexif/Pillow imports handled lazily, but log failures so we know why HAS_PIEXIF is False
HAS_PIEXIF = False
_PIEXIF_IMPORT_ERROR = None
try:
    from PIL import Image
    import piexif
    HAS_PIEXIF = True
except Exception as e:
    HAS_PIEXIF = False
    _PIEXIF_IMPORT_ERROR = e
    logging.debug("piexif/Pillow import failed: %s", e, exc_info=True)


def decimal_to_dms(decimal):
    """Local helper used by EXIF writer (keeps same format)."""
    decimal = float(decimal)
    decimal = abs(decimal)
    degrees = int(decimal)
    minutes = int((decimal - degrees) * 60)
    seconds = ((decimal - degrees) * 60 - minutes) * 60
    return ((degrees, 1), (minutes, 1), (int(seconds * 100), 100))


def set_image_exif_metadata(file_path, date_obj, latitude, longitude, timezone_offset=None):
    """Set EXIF metadata for JPEG image files using piexif (if available).
    
    Args:
        file_path: Path to the JPEG file
        date_obj: datetime object with timezone info (local time)
        latitude: GPS latitude (or None)
        longitude: GPS longitude (or None)
        timezone_offset: Timezone offset string like '-05:00' (EXIF 2.31 standard)
    """
    if not HAS_PIEXIF:
        logging.debug("Skipping EXIF metadata: piexif/Pillow not available: %s", _PIEXIF_IMPORT_ERROR)
        return False

    file_path = str(file_path)
    try:
        img = Image.open(file_path)
        img_format = img.format
        img.close()
    except Exception as e:
        logging.exception("Failed to open image for EXIF write: %s", file_path)
        return False

    if img_format not in ['JPEG', 'JPG']:
        logging.debug("Image is not JPEG, skipping EXIF write: %s (%s)", file_path, img_format)
        return False

    try:
        try:
            exif_dict = piexif.load(file_path)
        except Exception:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

        date_str = date_obj.strftime("%Y:%m:%d %H:%M:%S").encode('ascii')
        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = date_str
        exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = date_str
        exif_dict["0th"][piexif.ImageIFD.DateTime] = date_str
        
        # Add timezone offset tags (EXIF 2.31 standard)
        if timezone_offset:
            offset_bytes = timezone_offset.encode('ascii')
            try:
                exif_dict["Exif"][piexif.ExifIFD.OffsetTimeOriginal] = offset_bytes
                exif_dict["Exif"][piexif.ExifIFD.OffsetTimeDigitized] = offset_bytes
                # Note: OffsetTime is only valid in Exif IFD, not ImageIFD, so we skip 0th dictionary
                logging.debug("Added timezone offset to EXIF: %s", timezone_offset)
            except Exception as e:
                logging.debug("Could not add timezone offset tags to EXIF: %s", e)

        if latitude is not None and longitude is not None:
            lat_dms = decimal_to_dms(latitude)
            lon_dms = decimal_to_dms(longitude)

            exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = lat_dms
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = b"N" if latitude >= 0 else b"S"
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = lon_dms
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = b"E" if longitude >= 0 else b"W"

        exif_bytes = piexif.dump(exif_dict)

        # Use a temporary file + atomic replace to avoid problems with in-place saves on shared filesystems
        src_path = Path(file_path)
        temp_path = src_path.with_suffix(src_path.suffix + ".exif.tmp")

        try:
            img = Image.open(file_path)
            img.save(str(temp_path), "JPEG", exif=exif_bytes, quality=95)
            img.close()
            # atomic replace (works across OS where os.replace is supported)
            os.replace(str(temp_path), file_path)
            logging.info("Wrote EXIF metadata to %s", file_path)
            return True
        except Exception:
            # cleanup temp file if something went wrong
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            logging.exception("Failed to save EXIF metadata to temporary file for %s", file_path)
            return False

    except Exception:
        logging.exception("Failed to set EXIF metadata for %s", file_path)
        return False
