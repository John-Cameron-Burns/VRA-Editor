"""Reading dimensions/EXIF/IPTC from an image file, and writing IPTC back
into one. Pure functions, no Qt/UI dependency -- vra_editor.ui code calls
these, not the other way around, matching this app's core/ui layering.

Two libraries, for two different jobs:
  - Pillow: pixel dimensions, DPI, and decoding for the preview pane. Used
    for preview specifically because Qt's own bundled TIFF plugin can't
    open JPEG-compressed TIFFs (confirmed against this project's own real
    sample file) -- QPixmap(path) silently fails where Pillow succeeds.
  - pyexiv2 (libexiv2): EXIF GPS/timestamp reading and IPTC reading/
    writing. Pillow's own EXIF support doesn't cover GPS IFD parsing or
    IPTC at all, and unlike lighter pure-Python IPTC writers (iptcinfo3,
    JPEG only), pyexiv2 handles TIFF too.

read_iptc/write_iptc are the two halves of the same round trip: Inject
(see DocumentController.build_iptc_fields/inject_iptc) writes a record's
fields out to a file's IPTC block; read_iptc reads that same block back
(see DocumentController._populate_from_iptc), so a file that already
carries IPTC data -- whether from a previous Inject, or from a
photographer/agency's own tooling -- can seed a record's Title/
Description/People/Rights/Subjects instead of leaving them blank.

write_exif is the other direction for the record's creation date
specifically: Inject also pushes it into the file's own EXIF capture-
date tag, not just IPTC, since plenty of tools (including this app's
own read_image_info) only ever look at EXIF.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image

# pyexiv2 (IPTC read/write) and PySide6 (the preview QImage) are each
# imported lazily, inside only the one or two functions that actually
# need them, rather than up here -- read_image_info (Pillow/EXIF only)
# has to stay importable and callable in an environment with neither
# installed (the web backend's media-sync compare endpoint, which has
# no Qt at all and treats pyexiv2 as optional -- see
# webapp/routes/media_routes.py's own feature-detection).

_GPS_IFD_TAG = 0x8825
_EXIF_IFD_TAG = 0x8769
_DATETIME_ORIGINAL_TAG = 36867  # lives in the Exif sub-IFD, not the main one
_DATETIME_TAG = 306  # lives in the main IFD directly


@dataclass(frozen=True)
class ImageInfo:
    width: int
    height: int
    dpi: Optional[float]  # None if the file doesn't declare one
    gps_lat: Optional[float]  # decimal degrees, None if no GPS EXIF
    gps_lon: Optional[float]
    date: Optional[str]  # ISO "YYYY-MM-DD", None if no capture timestamp
    file_size: int  # bytes, from the filesystem -- not an EXIF/IPTC tag


def _dms_to_decimal(dms, ref: str) -> float:
    """EXIF GPS coordinates are (degrees, minutes, seconds) as IFDRationals;
    ref is 'N'/'S'/'E'/'W' -- south and west are negative."""
    degrees, minutes, seconds = (float(v) for v in dms)
    decimal = degrees + minutes / 60 + seconds / 3600
    return -decimal if ref in ('S', 'W') else decimal


def _read_gps(exif) -> tuple[Optional[float], Optional[float]]:
    gps_ifd = exif.get_ifd(_GPS_IFD_TAG)
    if not gps_ifd:
        return None, None
    lat = gps_ifd.get(2)  # GPSLatitude
    lat_ref = gps_ifd.get(1)  # GPSLatitudeRef
    lon = gps_ifd.get(4)  # GPSLongitude
    lon_ref = gps_ifd.get(3)  # GPSLongitudeRef
    if not (lat and lat_ref and lon and lon_ref):
        return None, None
    return _dms_to_decimal(lat, lat_ref), _dms_to_decimal(lon, lon_ref)


def _read_date(exif) -> Optional[str]:
    exif_ifd = exif.get_ifd(_EXIF_IFD_TAG)
    raw = (exif_ifd.get(_DATETIME_ORIGINAL_TAG) if exif_ifd else None) or exif.get(_DATETIME_TAG)
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%Y:%m:%d %H:%M:%S').date().isoformat()
    except ValueError:
        return None


def read_image_info(path) -> ImageInfo:
    with Image.open(path) as im:
        width, height = im.size
        dpi_info = im.info.get('dpi')
        dpi = float(dpi_info[0]) if dpi_info else None
        exif = im.getexif()
        gps_lat, gps_lon = _read_gps(exif)
        date = _read_date(exif)
    file_size = Path(path).stat().st_size
    return ImageInfo(width=width, height=height, dpi=dpi, gps_lat=gps_lat, gps_lon=gps_lon, date=date,
                      file_size=file_size)


def load_preview_image(path):
    """Decodes via Pillow and hands Qt raw pixel bytes, rather than
    QPixmap(path)/QImage(path) -- Qt's own bundled TIFF plugin can't open
    JPEG-compressed TIFFs, which real archival scans commonly are.
    Returns a QImage -- desktop-only, hence the deferred import (see
    this module's own docstring)."""
    from PySide6.QtGui import QImage
    with Image.open(path) as im:
        rgb = im.convert('RGB')
        data = rgb.tobytes('raw', 'RGB')
        qimage = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888)
        return qimage.copy()  # detach from `data`, which goes out of scope on return


def read_iptc(path) -> dict:
    """The file's existing IPTC fields, in the same {Iptc.Application2.*
    key: value} shape build_iptc_fields/write_iptc use -- scalar fields
    (ObjectName, Caption, ...) come back as str, repeatable ones
    (Byline, Keywords) as list[str]. Empty dict if the file has no IPTC
    block at all. Raises ImportError if pyexiv2 isn't installed -- see
    this module's own docstring on why that import is deferred to here."""
    import pyexiv2
    img = pyexiv2.Image(str(path))
    try:
        return img.read_iptc()
    finally:
        img.close()


def write_iptc(path, iptc_fields: dict) -> None:
    """iptc_fields is {Iptc.Application2.* key: value}, already built by
    the caller (DocumentController, which knows the VRA-to-IPTC field
    mapping) -- this function has no VRA-specific knowledge, just writes
    whatever it's given. Raises ImportError if pyexiv2 isn't installed."""
    import pyexiv2
    img = pyexiv2.Image(str(path))
    try:
        img.modify_iptc(iptc_fields)
    finally:
        img.close()


# VRA date fields are free text and can be far fuzzier than a real
# calendar date ("circa 1990", a bare decade, a range) -- these are the
# only shapes worth trying to write into EXIF, which has no concept of
# "approximately" at all. Tried in order, most specific first.
_VRA_DATE_FORMATS = ('%Y-%m-%d', '%Y-%m', '%Y')


def parse_vra_date(date_str: str) -> Optional[datetime]:
    """A real calendar date from a VRA date field's text, or None if it
    doesn't parse as one of the (limited) shapes EXIF can represent --
    deliberately conservative: writing a wrong date into EXIF is worse
    than writing none at all."""
    date_str = date_str.strip()
    for fmt in _VRA_DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def build_exif_date_field(date_str: str) -> dict:
    """{Exif.Photo.DateTimeOriginal: 'YYYY:MM:DD HH:MM:SS'} if date_str
    parses as a real calendar date (see parse_vra_date), else {} --
    no time-of-day is ever available from a VRA date, so it's always
    written as midnight."""
    parsed = parse_vra_date(date_str)
    if parsed is None:
        return {}
    return {'Exif.Photo.DateTimeOriginal': parsed.strftime('%Y:%m:%d 00:00:00')}


def write_exif(path, exif_fields: dict) -> None:
    """exif_fields is {Exif.* key: value} -- see build_exif_date_field.
    A no-op if exif_fields is empty, so callers don't need to guard
    against an unparseable date themselves. Raises ImportError if
    pyexiv2 isn't installed."""
    if not exif_fields:
        return
    import pyexiv2
    img = pyexiv2.Image(str(path))
    try:
        img.modify_exif(exif_fields)
    finally:
        img.close()
