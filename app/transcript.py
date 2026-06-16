"""
YouTube Transcript Fetcher
Supports Hindi, English, and auto-detect language transcripts.
Uses yt-dlp for robust subtitle extraction with multiple fallback strategies.
"""

import re
import json
import os
import tempfile
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


# ─── Video ID Extraction ───────────────────────────────────────────────────────

def extract_video_id(url_or_id: str) -> Optional[str]:
    """Extract YouTube video ID from URL or return the ID if already clean."""
    if re.match(r'^[A-Za-z0-9_-]{11}$', url_or_id):
        return url_or_id
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})',
        r'youtube\.com/watch\?.*[&?]v=([A-Za-z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    return None


# ─── Language mapping ──────────────────────────────────────────────────────────

LANG_MAP = {
    "hi": "hi", "en": "en", "en-US": "en", "en-GB": "en",
    "english": "en", "hindi": "hi",
}

# yt-dlp uses language codes like "hi", "en", etc.
# For auto-generated subtitles, the format is "a.en", "a.hi" etc.


# ─── Strategy 1: yt-dlp (most reliable) ───────────────────────────────────────

def _fetch_with_ytdlp(video_id: str, lang: str) -> Optional[dict]:
    """
    Fetch transcript using yt-dlp.
    Downloads subtitle files and parses them.
    """
    try:
        import yt_dlp
    except ImportError:
        logger.warning("yt-dlp not installed")
        return None

    url = f"https://www.youtube.com/watch?v={video_id}"
    tmpdir = tempfile.mkdtemp(prefix="ytsub_")

    # Try exact language first, then auto-generated
    lang_codes = [lang]
    if lang == "hi":
        lang_codes = ["hi", "hi-en"]  # Hindi, or Hindi from English
    elif lang == "en":
        lang_codes = ["en", "en-orig"]

    for attempt in range(2):  # Try manual then auto subs
        for lc in lang_codes:
            try:
                ydl_opts = {
                    "writesubtitles": attempt == 0,
                    "writeautomaticsub": attempt == 1,
                    "subtitleslangs": [lc],
                    "skip_download": True,
                    "subtitlesformat": "vtt",
                    "outtmpl": os.path.join(tmpdir, "%(id)s"),
                    "quiet": True,
                    "no_warnings": True,
                    "extract_flat": False,
                    # Avoid 429 errors with delay
                    "throttledratelimit": 100000,
                }
                _add_cookie_opts(ydl_opts)
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])

                # Find the downloaded subtitle file
                for fname in os.listdir(tmpdir):
                    if fname.endswith(".vtt") and video_id in fname:
                        filepath = os.path.join(tmpdir, fname)
                        segments = _parse_vtt(filepath)
                        if segments:
                            full_text = " ".join(s["text"] for s in segments)
                            # Clean up
                            import shutil
                            shutil.rmtree(tmpdir, ignore_errors=True)
                            return {
                                "text": full_text,
                                "segments": segments,
                                "language": lc,
                                "source": f"yt-dlp_{'auto' if attempt == 1 else 'manual'}",
                            }
            except Exception as e:
                logger.debug(f"yt-dlp ({lc}, attempt={attempt}): {e}")
                continue

    # Clean up
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
    return None


def _parse_vtt(vtt_path: str) -> list[dict]:
    """
    Parse a VTT subtitle file into segments.
    Returns list of {text, start, duration}
    """
    segments = []
    with open(vtt_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split into cue blocks
    # VTT format:
    # WEBVTT
    # ...
    # 00:00:01.360 --> 00:00:03.040
    # text line 1
    # text line 2
    #
    # Next cue...

    # Remove header
    content = re.sub(r'^WEBVTT.*?\n\n', '', content, flags=re.DOTALL)

    # Find all cue blocks
    cue_pattern = re.compile(
        r'(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})\s*\n(.+?)(?:\n\n|\Z)',
        re.DOTALL
    )

    for match in cue_pattern.finditer(content):
        start_str = match.group(1)
        end_str = match.group(2)
        text = match.group(3).strip()

        # Skip empty or music-only cues
        if not text or text == "[♪♪♪]" or text == "[Music]":
            continue

        # Remove VTT tags like <c> or </c>
        text = re.sub(r'<[^>]+>', '', text)
        # Replace newlines with spaces
        text = re.sub(r'\s*\n\s*', ' ', text)
        text = text.strip()

        if not text:
            continue

        start_sec = _vtt_time_to_seconds(start_str)
        end_sec = _vtt_time_to_seconds(end_str)
        duration = end_sec - start_sec

        segments.append({
            "text": text,
            "start": start_sec,
            "duration": max(duration, 0.5),
        })

    return segments


def _vtt_time_to_seconds(tstr: str) -> float:
    """Convert VTT timestamp (HH:MM:SS.mmm) to seconds."""
    parts = tstr.split(":")
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = "0", parts[0], parts[1]
    else:
        return 0.0
    return int(h) * 3600 + int(m) * 60 + float(s)


# ─── Strategy 2: YouTube page scrape (no external deps) ───────────────────────

def _fetch_from_youtube_page(video_id: str, lang: str) -> Optional[dict]:
    """
    Fallback: Extract caption info directly from YouTube watch page
    and fetch the caption XML/JSON.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        resp = httpx.get(
            f"https://www.youtube.com/watch?v={video_id}",
            headers=headers,
            timeout=15,
        )
        if resp.status_code != 200:
            return None

        html = resp.text

        # Find initial player response
        match = re.search(r'ytInitialPlayerResponse\s*=\s*({.*?});', html)
        if not match:
            return None

        player_data = json.loads(match.group(1))
        caption_tracks = (
            player_data.get("captions", {})
            .get("playerCaptionsTracklistRenderer", {})
            .get("captionTracks", [])
        )

        if not caption_tracks:
            return None

        # Find matching track
        selected = None
        for track in caption_tracks:
            lc = track.get("languageCode", "")
            if lc == lang:
                selected = track
                break

        # Fallback to first available
        if not selected:
            selected = caption_tracks[0]

        base_url = selected.get("baseUrl", "")
        if not base_url:
            return None

        # Try different formats
        for fmt in ["json3", "srv3", "srv2", "srv1"]:
            try:
                sub_resp = httpx.get(
                    f"{base_url}&fmt={fmt}",
                    headers=headers,
                    timeout=15,
                )
                if sub_resp.status_code == 200 and len(sub_resp.content) > 10:
                    content_type = sub_resp.headers.get("content-type", "")
                    if "json" in content_type or fmt == "json3":
                        data = sub_resp.json()
                        events = data.get("events", [])
                        segments = []
                        for event in events:
                            segs = event.get("segs", [])
                            if not segs:
                                continue
                            text = " ".join(
                                s.get("utf8", "") for s in segs
                            ).strip()
                            if text:
                                segments.append({
                                    "text": text,
                                    "start": float(event.get("tStartMs", 0)) / 1000,
                                    "duration": float(event.get("dDurationMs", 0)) / 1000,
                                })
                        if segments:
                            full_text = " ".join(s["text"] for s in segments)
                            return {
                                "text": full_text,
                                "segments": segments,
                                "language": selected.get("languageCode", lang),
                                "source": "youtube_page",
                            }
            except Exception:
                continue

    except Exception as e:
        logger.debug(f"YouTube page scrape failed: {e}")

    return None


# ─── Main public API ───────────────────────────────────────────────────────────

def get_available_languages(video_id: str) -> list[dict]:
    """List all available transcript languages for a video."""
    try:
        import yt_dlp
        url = f"https://www.youtube.com/watch?v={video_id}"
        ydl_opts = {"quiet": True, "no_warnings": True}
        _add_cookie_opts(ydl_opts)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            subs = info.get("subtitles", {})
            auto_subs = info.get("automatic_captions", {})

        languages = []
        for lang_code, formats in subs.items():
            languages.append({
                "language": lang_code,
                "language_code": lang_code,
                "is_generated": False,
                "is_translatable": True,
            })
        for lang_code in auto_subs:
            if lang_code not in [l["language_code"] for l in languages]:
                languages.append({
                    "language": lang_code,
                    "language_code": lang_code,
                    "is_generated": True,
                    "is_translatable": True,
                })

        return languages
    except Exception as e:
        logger.debug(f"Failed to list languages: {e}")
        return []


def fetch_transcript(
    video_id: str,
    lang: str = "hi",
    fallback_langs: Optional[list[str]] = None,
) -> dict:
    """
    Fetch transcript for a YouTube video using multiple strategies.

    Args:
        video_id: YouTube video ID (11 chars)
        lang: Primary language code ('hi' for Hindi, 'en' for English)
        fallback_langs: Fallback language codes

    Returns:
        dict with keys: text, segments, language, source, available_languages
    """
    if fallback_langs is None:
        fallback_langs = ["en", "hi"]

    result = {
        "text": "",
        "segments": [],
        "language": None,
        "source": None,
        "available_languages": [],
    }

    # Normalize language
    normalized_lang = LANG_MAP.get(lang.lower(), lang)
    search_langs = [normalized_lang]
    for fb in fallback_langs:
        fb_norm = LANG_MAP.get(fb.lower(), fb)
        if fb_norm not in search_langs:
            search_langs.append(fb_norm)

    strategies = [
        ("yt-dlp", _fetch_with_ytdlp),
        ("YouTube Page", _fetch_from_youtube_page),
    ]

    for strategy_name, strategy_fn in strategies:
        for sl in search_langs:
            try:
                logger.info(f"Trying {strategy_name} with lang={sl}")
                data = strategy_fn(video_id, sl)
                if data and data.get("segments"):
                    result.update(data)
                    logger.info(f"✓ Success: {strategy_name} ({sl})")

                    # Get available languages (best-effort)
                    try:
                        result["available_languages"] = get_available_languages(video_id)
                    except Exception:
                        pass

                    return result
            except Exception as e:
                logger.debug(f"{strategy_name}({sl}) error: {e}")
                continue

    result["error"] = "No transcript available for this video."
    return result


def fetch_transcript_for_notes(video_id: str, lang: str = "hi") -> dict:
    """
    Fetch transcript and format it nicely for note-making.
    Groups segments into logical paragraphs (~30s intervals).
    """
    result = fetch_transcript(video_id, lang)

    if "error" in result:
        return result

    segments = result["segments"]
    paragraphs = []
    current_para = []
    current_start = 0
    para_duration = 0

    for seg in segments:
        if para_duration >= 30 and current_para:
            paragraphs.append({
                "start_time": _seconds_to_timestamp(current_start),
                "text": " ".join(current_para),
                "segments": len(current_para),
            })
            current_para = []
            current_start = seg["start"]
            para_duration = 0
        current_para.append(seg["text"])
        para_duration += seg["duration"]

    if current_para:
        paragraphs.append({
            "start_time": _seconds_to_timestamp(current_start),
            "text": " ".join(current_para),
            "segments": len(current_para),
        })

    result["paragraphs"] = paragraphs
    return result


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _seconds_to_timestamp(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"


# ─── Cookie Helpers ───────────────────────────────────────────────────────────

COOKIE_SOURCES = []

def _init_cookies():
    """Initialize cookies from env vars on first call."""
    if COOKIE_SOURCES:
        return
    # Option 1: YT_COOKIES_FILE env var pointing to a cookies.txt file
    cookie_file = os.environ.get("YT_COOKIES_FILE")
    if cookie_file and os.path.exists(cookie_file):
        COOKIE_SOURCES.append(("cookiefile", cookie_file))
        logger.info(f"Using cookies file: {cookie_file}")
    # Option 2: YT_COOKIES_B64 env var with base64-encoded cookies.txt
    cookie_b64 = os.environ.get("YT_COOKIES_B64")
    if cookie_b64:
        import base64
        try:
            decoded = base64.b64decode(cookie_b64).decode("utf-8")
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
            tmp.write(decoded)
            tmp.close()
            COOKIE_SOURCES.append(("cookiefile", tmp.name))
            logger.info("Using cookies from YT_COOKIES_B64 env var")
        except Exception as e:
            logger.warning(f"Failed to decode YT_COOKIES_B64: {e}")


def _add_cookie_opts(ydl_opts: dict):
    """Add cookie options to yt-dlp opts dict if available."""
    _init_cookies()
    for kind, value in COOKIE_SOURCES:
        ydl_opts[kind] = value
    # Also add a browser-like User-Agent header to reduce bot detection
    ydl_opts.setdefault("http_headers", {})
    ydl_opts["http_headers"].update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
    })
