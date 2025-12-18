import logging

# piexif/Pillow imports handled lazily
HAS_PIEXIF = False
try:
    from PIL import Image
    import piexif
    HAS_PIEXIF = True
except Exception:
    HAS_PIEXIF = False


def decimal_to_dms(decimal):
    """Local helper used by EXIF writer (keeps same format)."""
    decimal = float(decimal)
    decimal = abs(decimal)
    degrees = int(decimal)
    minutes = int((decimal - degrees) * 60)
    seconds = ((decimal - degrees) * 60 - minutes) * 60
    return ((degrees, 1), (minutes, 1), (int(seconds * 100), 100))


def set_image_exif_metadata(file_path, date_obj, latitude, longitude):
    """Set EXIF metadata for JPEG image files using piexif (if available)."""
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
        except Exception:
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
        logging.exception("Failed to set EXIF metadata for %s", file_path)
