"""Utilities for processing Snapchat chat_media exports.

A chat_media folder contains five kinds of files, all prefixed YYYY-MM-DD_:

  _b~<id>.<ext>          standalone chat media (direct sends)
  _media~zip-<uuid>      primary media from a snap exported as a zip bundle
  _overlay~zip-<uuid>    caption/sticker overlay for a same-date media file
  _thumbnail~zip-<uuid>  thumbnail (video first frame WITH overlay burned in)
  _metadata~zip-<uuid>   JSON sidecar (Discover/Cameos publisher info)
  _<md5hash>.<ext>       rare: chat media with a bare hash id

The zip-<uuid> values are unique per file — components of the same snap share
nothing but the date prefix, so overlay→media pairing on dates with several
snaps is resolved by compositing each overlay onto each media's first frame
and comparing against the thumbnails (which have the overlay burned in).

Timestamps come from, in priority order:
  1. json/chat_history.json — "Media IDs" match b~/hash filenames exactly
  2. json/snap_history.json — date + media-type ordinal pairing
  3. the media file's embedded creation_time (videos)
  4. the file's modification time — Snapchat writes the real send time
     into the export zip entries, so extracted files carry it (validated
     against the filename date in case extraction discarded it)
  5. the filename date (midday local time)
"""

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except Exception:
    HAS_PIL = False

VIDEO_EXTS = ('.mp4', '.mov', '.m4v', '.avi', '.mkv', '.webm')
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.heic')

_B_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})_(b~[^.]+)\.(\w+)$')
# id part variants seen in real exports:
#   zip-<UUID>                       (unique per file — no cross-file linkage)
#   Snapchat-<number>.zip.nomedia    (camera-roll re-sends — media & overlay
#                                     SHARE the number, so they pair directly)
#   <empty>
_ZIP_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2})_(media|overlay|thumbnail|metadata)~(.*)\.(\w+)$'
)
_HASH_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})_([0-9a-f]{32})\.(\w+)$')


def _normalize_zip_id(raw_id):
    """Normalize the id segment of a media~/overlay~ filename.

    Returns (media_id, shared) where shared=True means the id is common to
    all components of the same snap (pairable directly).
    """
    if raw_id.startswith('zip-'):
        return raw_id[4:], False
    if raw_id.endswith('.zip.nomedia'):
        return raw_id[:-len('.zip.nomedia')], True
    return raw_id, bool(raw_id)


# ==================== Scanning ====================

def detect_file_type(file_path):
    """Sniff the real media type of a file from its magic bytes.

    Returns an extension string ('.jpg', '.png', '.mp4', '.webp', '.gif')
    or None if the format is unrecognized (e.g. Snapchat's undecryptable
    b~*.unknown blobs).
    """
    try:
        with open(file_path, 'rb') as f:
            magic = f.read(16)
    except Exception:
        return None
    if magic[:3] == b'\xff\xd8\xff':
        return '.jpg'
    if magic[:8] == b'\x89PNG\r\n\x1a\n':
        return '.png'
    if magic[:6] in (b'GIF87a', b'GIF89a'):
        return '.gif'
    if magic[:4] == b'RIFF' and magic[8:12] == b'WEBP':
        return '.webp'
    if len(magic) >= 12 and magic[4:8] in (b'ftyp', b'moov', b'mdat', b'wide'):
        return '.mp4'
    if magic[:1] == b'{':
        return '.json'
    return None


def scan_chat_media(folder):
    """Parse a chat_media folder into typed records.

    Returns a dict:
      'standalone'  — list of records for b~ and hash-named media files
      'zip_by_date' — {date: {'media': [...], 'overlay': [...],
                              'thumbnail': [...], 'metadata': [...]}}
      'unreadable'  — files whose content format could not be identified
      'unrecognized'— filenames that match no known pattern

    Each record is a dict: path, fname, date (YYYY-MM-DD str), kind,
    media_id (b~…/hash or zip uuid, may be ''), ext (real extension after
    magic-byte sniffing for .unknown files), is_video.
    """
    standalone = []
    zip_by_date = {}
    unreadable = []
    unrecognized = []

    for fname in sorted(os.listdir(folder)):
        path = os.path.join(folder, fname)
        if not os.path.isfile(path):
            continue

        m = _B_RE.match(fname)
        if m:
            date_str, media_id, ext = m.group(1), m.group(2), '.' + m.group(3).lower()
            record = {'path': path, 'fname': fname, 'date': date_str,
                      'kind': 'b', 'media_id': media_id, 'ext': ext}
            if ext == '.unknown':
                real = detect_file_type(path)
                if real is None or real == '.json':
                    unreadable.append(record)
                    continue
                record['ext'] = real
            record['is_video'] = record['ext'] in VIDEO_EXTS
            standalone.append(record)
            continue

        m = _ZIP_RE.match(fname)
        if m:
            date_str, kind, ext = m.group(1), m.group(2), '.' + m.group(4).lower()
            media_id, shared = _normalize_zip_id(m.group(3))
            record = {'path': path, 'fname': fname, 'date': date_str,
                      'kind': kind, 'media_id': media_id, 'ext': ext,
                      'shared_id': shared}
            if ext == '.unknown':
                real = detect_file_type(path)
                if real is None:
                    unreadable.append(record)
                    continue
                record['ext'] = real
            record['is_video'] = record['ext'] in VIDEO_EXTS
            zip_by_date.setdefault(date_str, {}).setdefault(kind, []).append(record)
            continue

        m = _HASH_RE.match(fname)
        if m:
            date_str, media_id, ext = m.group(1), m.group(2), '.' + m.group(3).lower()
            record = {'path': path, 'fname': fname, 'date': date_str,
                      'kind': 'hash', 'media_id': media_id, 'ext': ext,
                      'is_video': ext in VIDEO_EXTS}
            standalone.append(record)
            continue

        unrecognized.append(fname)

    return {'standalone': standalone, 'zip_by_date': zip_by_date,
            'unreadable': unreadable, 'unrecognized': unrecognized}


# ==================== Chat / snap history index ====================

def find_export_json_dir(chat_media_dir):
    """Locate the export's json/ folder relative to a chat_media folder."""
    parent = Path(chat_media_dir).parent
    for candidate in (parent / 'json', Path(chat_media_dir) / 'json'):
        if (candidate / 'chat_history.json').exists() or \
           (candidate / 'snap_history.json').exists():
            return str(candidate)
    return None


def build_chat_index(json_dir):
    """Index chat_history.json and snap_history.json for media matching.

    Returns a dict:
      'id_to_msg'     — media id ('b~…' or bare hash) -> message dict
      'msgs_by_date'  — date -> [media message dicts] (all MEDIA messages,
                        used for ordinal pairing of zip bundles)
      'snaps_by_date' — date -> [snap entry dicts] from snap_history
    Message/snap dicts gain '_dt' (aware UTC datetime) and '_ids' (list).
    Returns None if json_dir is None or has no usable files.
    """
    if not json_dir:
        return None

    index = {'id_to_msg': {}, 'msgs_by_date': {}, 'snaps_by_date': {}}
    found_any = False

    chat_path = os.path.join(json_dir, 'chat_history.json')
    if os.path.exists(chat_path):
        try:
            with open(chat_path, encoding='utf-8') as f:
                conversations = json.load(f)
            for conv_key, messages in conversations.items():
                for msg in messages:
                    ids = [i.strip() for i in (msg.get('Media IDs') or '').split('|')
                           if i.strip()]
                    if not ids:
                        continue
                    msg['_ids'] = ids
                    msg['_dt'] = _msg_datetime(msg)
                    msg['_conversation'] = msg.get('Conversation Title') or conv_key
                    for media_id in ids:
                        index['id_to_msg'].setdefault(media_id, msg)
                    if msg['_dt'] is not None:
                        day = msg['_dt'].strftime('%Y-%m-%d')
                        index['msgs_by_date'].setdefault(day, []).append(msg)
            found_any = True
            logging.info("chat_history.json: indexed %d media ids",
                         len(index['id_to_msg']))
        except Exception as e:
            logging.warning("Could not parse chat_history.json: %s", e)

    snap_path = os.path.join(json_dir, 'snap_history.json')
    if os.path.exists(snap_path):
        try:
            with open(snap_path, encoding='utf-8') as f:
                snap_data = json.load(f)
            for sender_key, entries in snap_data.items():
                for entry in entries:
                    entry['_dt'] = _msg_datetime(entry)
                    entry['_conversation'] = entry.get('Conversation Title') or sender_key
                    if entry['_dt'] is not None:
                        day = entry['_dt'].strftime('%Y-%m-%d')
                        index['snaps_by_date'].setdefault(day, []).append(entry)
            found_any = True
            logging.info("snap_history.json: indexed %d snaps",
                         sum(len(v) for v in index['snaps_by_date'].values()))
        except Exception as e:
            logging.warning("Could not parse snap_history.json: %s", e)

    for day in index['msgs_by_date']:
        index['msgs_by_date'][day].sort(key=lambda m: m['_dt'])
    for day in index['snaps_by_date']:
        index['snaps_by_date'][day].sort(key=lambda m: m['_dt'])

    return index if found_any else None


def _msg_datetime(msg):
    """Aware UTC datetime from a chat/snap history entry."""
    micros = msg.get('Created(microseconds)')
    if micros:
        try:
            # Despite the field name, exports have shipped both true
            # microseconds (16 digits) and milliseconds (13 digits) —
            # disambiguate by magnitude.
            value = int(micros)
            if value >= 10**14:
                value /= 1_000_000
            elif value >= 10**11:
                value /= 1000
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except Exception:
            pass
    created = msg.get('Created')
    if created:
        try:
            return datetime.strptime(created, '%Y-%m-%d %H:%M:%S UTC').replace(
                tzinfo=timezone.utc)
        except Exception:
            pass
    return None


# ==================== Matching ====================

def match_standalone(records, index):
    """Attach chat/snap history matches to standalone (b~/hash) records.

    Sets record['match'] to the message dict (or None) and returns
    (matched_count, snap_matched_count). Records that fail the direct id
    lookup are paired against same-date snap_history entries of the same
    media type, in filename order vs. capture-time order — only when the
    counts for that (date, type) agree, so pairings are never guesses
    across mixed sets.
    """
    if index is None:
        for r in records:
            r['match'] = None
        return 0, 0

    matched = 0
    leftovers = {}
    for r in records:
        msg = index['id_to_msg'].get(r['media_id'])
        r['match'] = msg
        if msg is not None:
            matched += 1
        else:
            kind = 'VIDEO' if r['is_video'] else 'IMAGE'
            leftovers.setdefault((r['date'], kind), []).append(r)

    # Snap entries have no media ids: pair by (date, type) ordinal.
    snap_matched = 0
    claimed = set()
    for (day, kind), recs in leftovers.items():
        candidates = [s for s in index['snaps_by_date'].get(day, [])
                      if s.get('Media Type') == kind and id(s) not in claimed]
        if len(candidates) == len(recs):
            for r in recs:
                get_export_mtime(r)
            for r, snap in zip(sorted(recs, key=_capture_sort_key), candidates):
                r['match'] = snap
                claimed.add(id(snap))
                snap_matched += 1

    return matched, snap_matched


def match_zip_groups(zip_by_date, index, claimed_ids=None):
    """Attach history matches to zip-bundle media records.

    Zip bundles are chat/snap media whose ids were replaced by per-file
    uuids, so the only linkage is the date. For each date, the candidate
    pool is: MEDIA messages whose ids have no standalone file, plus snap
    entries. When the pool size equals the media count, pair ordinally —
    media sorted by embedded creation_time (falling back to filename),
    messages by capture time. Sets record['match'] on each media record.
    """
    if index is None:
        for kinds in zip_by_date.values():
            for r in kinds.get('media', []):
                r['match'] = None
        return 0

    claimed_ids = claimed_ids or set()
    matched = 0
    for day, kinds in zip_by_date.items():
        media_records = kinds.get('media', [])
        if not media_records:
            continue

        pool = []
        for msg in index['msgs_by_date'].get(day, []):
            if any(i not in claimed_ids for i in msg['_ids']):
                pool.append(msg)
        pool.extend(index['snaps_by_date'].get(day, []))
        pool.sort(key=lambda m: m['_dt'])

        for r in media_records:
            r['match'] = None
            r['_ctime'] = get_video_creation_time(r['path']) if r['is_video'] else None
            get_export_mtime(r)

        if len(pool) == len(media_records):
            ordered = sorted(media_records, key=_capture_sort_key)
            for r, msg in zip(ordered, pool):
                r['match'] = msg
                matched += 1
        else:
            # Pool disagrees — still try to align each file's known capture
            # time with the closest message (within 10 minutes).
            for r in media_records:
                probe = r['_ctime'] or r['_mtime']
                if probe is None or not pool:
                    continue
                best = min(pool, key=lambda m: abs((m['_dt'] - probe).total_seconds()))
                if abs((best['_dt'] - probe).total_seconds()) <= 600:
                    r['match'] = best
                    matched += 1
    return matched


def _capture_sort_key(record):
    """Sort key ordering records by best-known capture time, then filename."""
    dt = record.get('_ctime') or record.get('_mtime')
    return (dt is None, dt or record['fname'], record['fname'])


def collect_claimed_ids(standalone_records):
    """Media ids that resolved to an actual standalone file."""
    return {r['media_id'] for r in standalone_records if r.get('match') is not None}


# ==================== Timestamp resolution ====================

def get_video_creation_time(file_path):
    """Embedded creation_time of a video as aware UTC datetime, or None."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format_tags=creation_time',
             '-of', 'default=nw=1:nk=1', str(file_path)],
            capture_output=True, text=True, timeout=15,
            creationflags=CREATE_NO_WINDOW,
        )
        raw = result.stdout.strip()
        if not raw:
            return None
        raw = raw.replace('Z', '+00:00')
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # Snapchat sometimes writes epoch/zero dates; ignore anything absurd
        if dt.year < 2005:
            return None
        return dt
    except Exception:
        return None


def get_export_mtime(record):
    """The file's modification time as aware UTC datetime, or None.

    Snapchat writes each file's real send time into the export zip entries,
    which extraction preserves. Trusted only when it lands within two days
    of the filename's date — an extractor that discarded zip times leaves
    mtimes at extraction time, which must not be mistaken for a send time.
    """
    if '_mtime' in record:
        return record['_mtime']
    mtime = None
    try:
        raw = datetime.fromtimestamp(os.path.getmtime(record['path']),
                                     tz=timezone.utc)
        file_date = datetime.strptime(record['date'], '%Y-%m-%d').replace(
            tzinfo=timezone.utc)
        if abs((raw - file_date).total_seconds()) <= 2 * 86400:
            mtime = raw
    except Exception:
        pass
    record['_mtime'] = mtime
    return mtime


def resolve_timestamp(record):
    """Best available capture time (aware UTC) and its source label.

    Priority: matched history entry -> embedded video creation_time ->
    export file mtime -> filename date at 12:00 local time (noon local
    keeps the calendar date right everywhere and reads as a deliberate
    date-only default, unlike noon UTC which showed up as e.g. 6:00 AM
    for US users).
    """
    match = record.get('match')
    if match is not None and match.get('_dt') is not None:
        return match['_dt'], 'chat history'

    if record.get('_ctime'):
        return record['_ctime'], 'embedded creation_time'
    if record.get('is_video'):
        ctime = get_video_creation_time(record['path'])
        if ctime is not None:
            record['_ctime'] = ctime
            return ctime, 'embedded creation_time'

    mtime = get_export_mtime(record)
    if mtime is not None:
        return mtime, 'export file time'

    dt = datetime.strptime(record['date'], '%Y-%m-%d').replace(
        hour=12).astimezone().astimezone(timezone.utc)
    return dt, 'filename date'


# ==================== Overlay pairing ====================

def _extract_first_frame(video_path, out_path):
    try:
        result = subprocess.run(
            ['ffmpeg', '-y', '-v', 'error', '-i', str(video_path),
             '-frames:v', '1', str(out_path)],
            capture_output=True, timeout=30, creationflags=CREATE_NO_WINDOW,
        )
        return result.returncode == 0 and os.path.exists(out_path)
    except Exception:
        return False


_DIFF_SIZE = (90, 160)


def _image_diff(img_a, img_b, size=_DIFF_SIZE):
    """Mean absolute per-channel difference of two PIL images."""
    a = img_a.convert('RGB').resize(size)
    b = img_b.convert('RGB').resize(size)
    pa, pb = a.load(), b.load()
    total = 0
    for x in range(size[0]):
        for y in range(size[1]):
            ca, cb = pa[x, y], pb[x, y]
            total += abs(ca[0] - cb[0]) + abs(ca[1] - cb[1]) + abs(ca[2] - cb[2])
    return total / (size[0] * size[1] * 3)


def _masked_diff(img_a, img_b, mask, size=_DIFF_SIZE):
    """Mean absolute difference restricted to where mask alpha > 128.

    Small captions barely move a full-frame diff, so comparisons are done
    only inside the overlay's own opaque pixels. Returns None when the
    mask has no opaque pixels at comparison size.
    """
    a = img_a.convert('RGB').resize(size)
    b = img_b.convert('RGB').resize(size)
    pa, pb, pm = a.load(), b.load(), mask.load()
    total = 0
    count = 0
    for x in range(size[0]):
        for y in range(size[1]):
            if pm[x, y] > 128:
                ca, cb = pa[x, y], pb[x, y]
                total += abs(ca[0] - cb[0]) + abs(ca[1] - cb[1]) + abs(ca[2] - cb[2])
                count += 1
    if count == 0:
        return None
    return total / (count * 3)


def pair_overlays(kinds, log_fn=None):
    """Decide which overlay belongs to which media file for one date.

    Returns (pairs, unmatched_overlays) where pairs is a list of
    (media_record, overlay_record_or_None) covering every media record,
    and unmatched_overlays lists overlays that could not be attached to
    any media (callers should preserve them rather than drop them).

    Pairing signals, strongest first:
      1. shared filename id (Snapchat-<n>.zip.nomedia camera-roll exports)
      2. thumbnail verification — pre-2018 exports burn the overlay into
         the thumbnail, so compositing the overlay onto each media's first
         frame and diffing inside the overlay's opaque pixels identifies
         the owner with near-zero error
      3. equal-count file-order fallback (logged as unverified — newer
         exports ship plain thumbnails, which cannot confirm ownership)
    """
    log = log_fn or (lambda m: None)
    media = list(kinds.get('media', []))
    overlays = list(kinds.get('overlay', []))
    thumbs = kinds.get('thumbnail', [])

    if not media:
        return [], list(overlays)

    # Signal 1: shared filename id. zip-<uuid> ids are unique per file, so
    # this can never mis-pair those.
    id_pairs = []
    overlay_by_id = {o['media_id']: o for o in overlays
                     if o.get('shared_id') and o['media_id']}
    remaining_media = []
    for m_rec in media:
        ov = overlay_by_id.get(m_rec['media_id']) if m_rec.get('shared_id') else None
        if ov is not None:
            id_pairs.append((m_rec, ov))
            overlays.remove(ov)
        else:
            remaining_media.append(m_rec)
    media = remaining_media

    if not media:
        return id_pairs, list(overlays)
    if not overlays:
        return id_pairs + [(m, None) for m in media], []
    if len(media) == 1:
        # All overlays for the date belong to the only media file; merge the
        # first (multiples on a single media are rare and near-identical).
        return id_pairs + [(media[0], overlays[0])], overlays[1:]

    # Signal 2: thumbnail verification.
    assignments = {}
    used_overlays = set()
    if HAS_PIL and thumbs:
        tmp_dir = tempfile.mkdtemp(prefix='chatmedia_frames_')
        try:
            frames = {}
            for m in media:
                if m['is_video']:
                    frame_path = os.path.join(tmp_dir, m['fname'] + '.png')
                    if _extract_first_frame(m['path'], frame_path):
                        frames[m['fname']] = PILImage.open(frame_path).convert('RGBA')
                else:
                    try:
                        frames[m['fname']] = PILImage.open(m['path']).convert('RGBA')
                    except Exception:
                        pass

            thumb_imgs = []
            for t in thumbs:
                try:
                    thumb_imgs.append(PILImage.open(t['path']))
                except Exception:
                    pass

            for ov in overlays:
                try:
                    ov_img = PILImage.open(ov['path']).convert('RGBA')
                    mask = ov_img.split()[3].resize(_DIFF_SIZE)
                except Exception:
                    continue
                best_media, best_diff = None, None
                for m in media:
                    frame = frames.get(m['fname'])
                    if frame is None:
                        continue
                    merged = PILImage.alpha_composite(frame, ov_img.resize(frame.size))
                    for t_img in thumb_imgs:
                        md = _masked_diff(merged, t_img, mask)
                        if md is None:
                            md = _image_diff(merged, t_img)  # fully transparent overlay
                        pd = _masked_diff(frame, t_img, mask)
                        # The overlay must explain the thumbnail better than
                        # the bare frame does.
                        if pd is not None and md >= pd:
                            continue
                        if best_diff is None or md < best_diff:
                            best_media, best_diff = m, md
                if best_media is not None and best_diff is not None and best_diff < 12 \
                        and best_media['fname'] not in assignments:
                    assignments[best_media['fname']] = ov
                    used_overlays.add(ov['fname'])
                    log(f"    ✓ Overlay matched via thumbnail: {ov['fname'][:40]}… → "
                        f"{best_media['fname'][:40]}…")
        finally:
            try:
                import shutil
                shutil.rmtree(tmp_dir)
            except Exception:
                pass

    # Signal 3: equal-count file-order fallback for whatever is left.
    left_media = [m for m in media if m['fname'] not in assignments]
    left_overlays = [o for o in overlays if o['fname'] not in used_overlays]
    if left_overlays and len(left_media) == len(left_overlays):
        log(f"    ⚠ Pairing {len(left_overlays)} overlay(s) by file order — "
            f"could not verify via thumbnails")
        for m, ov in zip(sorted(left_media, key=lambda r: r['fname']),
                         sorted(left_overlays, key=lambda r: r['fname'])):
            assignments[m['fname']] = ov
            used_overlays.add(ov['fname'])
        left_overlays = []
    elif left_overlays:
        log(f"    ⚠ {len(left_overlays)} overlay(s) could not be paired — "
            f"they will be copied to unmatched_overlays/")

    pairs = id_pairs + [(m, assignments.get(m['fname'])) for m in media]
    return pairs, left_overlays


# ==================== Sidecar metadata ====================

def parse_metadata_sidecar(path):
    """Read a metadata~zip JSON sidecar; returns dict or None."""
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None
