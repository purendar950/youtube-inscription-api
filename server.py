#!/usr/bin/env python3
"""
YouTube Transcript API - Single File Server
For Hindi & English transcripts, notes, and quiz generation.
Start:  python server.py
"""

import re, json, os, tempfile, logging, random
from typing import Optional
from pathlib import Path

import httpx

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────
# transcript.py
# ──────────────────────────────────────
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
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
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


# ──────────────────────────────────────
# notes.py
# ──────────────────────────────────────
"""
Note-Making Engine
Converts YouTube transcripts into structured study notes.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def generate_notes(transcript_data: dict, title: str = "Video Notes") -> dict:
    """
    Generate structured study notes from a YouTube transcript.

    Returns notes with:
    - Summary (first 20% of content condensed)
    - Key points (topic-based extraction)
    - Timestamped sections
    - Vocabulary/glossary (for Hindi-English bilingual content)
    - Full cleaned transcript
    """
    text = transcript_data.get("text", "")
    paragraphs = transcript_data.get("paragraphs", [])
    segments = transcript_data.get("segments", [])
    language = transcript_data.get("language", "unknown")

    if not text:
        return {"error": "No transcript text to generate notes from."}

    # ── Summary (first ~20% + last ~10% for intro+conclusion) ──────────────
    words = text.split()
    summary_words = words[:min(len(words) // 5, 200)] + words[-min(len(words) // 10, 100):]
    summary = " ".join(summary_words)

    # ── Timestamped Sections ────────────────────────────────────────────────
    timestamped_sections = []
    for para in paragraphs[:20]:  # Limit to avoid huge output
        timestamped_sections.append({
            "timestamp": para["start_time"],
            "text": para["text"],
        })

    # ── Key Points (extract sentences with important markers) ──────────────
    sentences = re.split(r'[.!?]+', text)
    importance_markers = [
        "important", "key", "main", "crucial", "essential", "significant",
        "note that", "remember", "always", "never", "must", "should",
        "मुख्य", "महत्वपूर्ण", "जरूरी", "आवश्यक", "ध्यान दें", "याद रखें",
        "सबसे", "प्रमुख", "विशेष",
    ]
    key_points = []
    seen = set()
    for s in sentences:
        s = s.strip()
        if len(s) < 15 or len(s) > 500:
            continue
        s_lower = s.lower()
        for marker in importance_markers:
            if marker in s_lower and s[:100] not in seen:
                key_points.append(s)
                seen.add(s[:100])
                break

    # ── Vocabulary / Glossary (for mixed language content) ────────────────
    # Detect Hindi words (Devanagari script) and pair with context
    hindi_pattern = re.compile(r'[\u0900-\u097F]+')
    vocabulary = []
    for seg in segments[:100]:
        seg_text = seg["text"]
        hindi_words = hindi_pattern.findall(seg_text)
        for hw in hindi_words[:3]:  # Max 3 per segment
            if len(hw) > 2 and hw not in [v["word"] for v in vocabulary]:
                vocabulary.append({
                    "word": hw,
                    "context": seg_text[:120],
                    "timestamp": _sec_to_ts(seg["start"]),
                })

    # ── Stats ──────────────────────────────────────────────────────────────
    hindi_word_count = len(hindi_pattern.findall(text)) if 'hindi_pattern' in dir() else 0
    # Recalculate
    hindi_words_in_text = len(re.findall(r'[\u0900-\u097F]+', text))

    notes = {
        "title": title,
        "language": language,
        "summary": summary[:1000] + ("..." if len(summary) > 1000 else ""),
        "key_points": key_points[:20],  # Top 20
        "timestamped_sections": timestamped_sections,
        "vocabulary": vocabulary[:30],  # Top 30 vocab items
        "stats": {
            "total_words": len(words),
            "total_sentences": len(sentences),
            "hindi_words": hindi_words_in_text,
            "english_words": len(words) - hindi_words_in_text,
            "duration_seconds": transcript_data.get("segments", [{}])[-1].get("start", 0) + 
                                transcript_data.get("segments", [{}])[-1].get("duration", 0) 
                                if transcript_data.get("segments") else 0,
        },
    }

    return notes


def _sec_to_ts(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"


# ──────────────────────────────────────
# quiz.py
# ──────────────────────────────────────
"""
Quiz Generator
Creates MCQ quizzes from YouTube transcript content.
Uses rule-based NLP to extract question-answer pairs from sentences.
"""

import re
import random
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def generate_quiz(
    transcript_data: dict,
    num_questions: int = 10,
    difficulty: str = "medium",
    quiz_title: str = "Video Quiz",
) -> dict:
    """
    Generate multiple-choice quiz questions from transcript content.

    difficulty: 'easy', 'medium', 'hard'
        - easy: simple fill-in-the-blank from first sentences
        - medium: fact-based questions with one correct answer
        - hard: inferential questions requiring deeper understanding
    """
    text = transcript_data.get("text", "")
    segments = transcript_data.get("segments", [])
    language = transcript_data.get("language", "unknown")

    if not text:
        return {"error": "No transcript text to generate quiz from.", "questions": [], "total_questions": 0}

    # Clean text
    text = re.sub(r'\s+', ' ', text).strip()

    # Split into sentences
    sentence_delimiters = r'(?<=[.!?])\s+|(?<=\n)\s*'
    raw_sentences = re.split(sentence_delimiters, text)
    
    # Filter out empty, short, and music-only sentences
    sentences = []
    for s in raw_sentences:
        s = s.strip()
        # Skip music cues
        if s in ("[♪♪♪]", "[Music]", "♪", "[♪]", "♪♪"):
            continue
        # Remove leading/trailing ♪
        s = re.sub(r'^[♪\s]+|[♪\s]+$', '', s).strip()
        if len(s) > 15:
            sentences.append(s)

    if len(sentences) < 3:
        # Not enough sentences, try splitting on other boundaries
        sentences = [s.strip() for s in re.split(r'[,;:]\s*', text) if len(s.strip()) > 20]
        if len(sentences) < 3:
            # Last resort: use segments
            sentences = [s["text"] for s in segments if len(s["text"]) > 20]
            if len(sentences) < 3:
                return {
                    "error": "Not enough content to generate quiz.",
                    "questions": [],
                    "total_questions": 0,
                }

    # Shuffle for variety
    random.shuffle(sentences)

    questions = []
    used_sentences = set()

    for sentence in sentences:
        if len(questions) >= num_questions:
            break

        # Skip very long or very short sentences
        if len(sentence) < 25 or len(sentence) > 400:
            continue

        sent_key = sentence[:50]
        if sent_key in used_sentences:
            continue

        quiz_data = _make_mcq(sentence, difficulty)
        if quiz_data:
            used_sentences.add(sent_key)
            timestamp = _find_timestamp(segments, sentence)
            quiz_data["timestamp"] = timestamp
            questions.append(quiz_data)

    # If not enough questions, try simpler extraction
    if len(questions) < num_questions and len(sentences) > 2:
        for sentence in sentences:
            if len(questions) >= num_questions:
                break
            sent_key = sentence[:50]
            if sent_key in used_sentences or len(sentence) < 15:
                continue
            
            words = sentence.split()
            if len(words) >= 5:
                # Find meaningful words to blank out
                candidates = []
                for i, w in enumerate(words):
                    clean_w = w.strip(".,!?;:'\"()[]{}")
                    if len(clean_w) > 4 and not clean_w.startswith(("the", "a ", "an ", "is ", "are ", "was ")):
                        candidates.append((i, clean_w))
                
                if candidates:
                    idx, answer = random.choice(candidates)
                    answer_clean = answer.strip(".,!?;:")
                    
                    # Generate distractors from other words in the text
                    other_words = [w.strip(".,!?;:\"'") for s in sentences 
                                  for w in s.split() 
                                  if len(w.strip(".,!?;:\"'")) > 3 
                                  and w.strip(".,!?;:\"'") != answer_clean]
                    other_words = list(dict.fromkeys(other_words))  # deduplicate preserving order
                    random.shuffle(other_words)
                    
                    distractors = other_words[:3]
                    if len(distractors) >= 3:
                        options = distractors + [answer_clean]
                        random.shuffle(options)
                        q_text = sentence.replace(answer, "________", 1)
                        used_sentences.add(sent_key)
                        timestamp = _find_timestamp(segments, sentence)
                        questions.append({
                            "question": q_text,
                            "options": options,
                            "correct_answer": answer_clean,
                            "difficulty": "easy",
                            "timestamp": timestamp,
                        })

    return {
        "title": quiz_title,
        "language": language,
        "total_questions": len(questions),
        "difficulty": difficulty,
        "questions": questions[:num_questions],
    }


def _make_mcq(sentence: str, difficulty: str) -> Optional[dict]:
    """
    Try to create a meaningful MCQ from a sentence.
    Returns dict or None if sentence isn't suitable.
    """
    words = sentence.split()
    if len(words) < 6:
        return None

    # Strategy: Find a number, proper noun, or key term to question
    candidates = []

    for i, w in enumerate(words):
        clean_w = w.strip(".,!?;:\"'()[]{}")
        if not clean_w:
            continue

        # Numbers are great for quiz questions
        if re.match(r'^\d+$', clean_w):
            candidates.append((i, clean_w, "number"))

        # Capitalized words (proper nouns, key terms)
        elif clean_w[0].isupper() and len(clean_w) > 2:
            candidates.append((i, clean_w, "proper_noun"))

        # Long words (likely important terms)
        elif len(clean_w) > 6 and not clean_w[0].isupper():
            candidates.append((i, clean_w, "term"))

    if not candidates:
        return None

    # Pick the best candidate
    if difficulty == "easy":
        idx, answer, _ = candidates[0]
    elif difficulty == "hard":
        idx, answer, _ = candidates[-1] if len(candidates) > 1 else candidates[0]
    else:  # medium
        idx, answer, _ = random.choice(candidates[:min(3, len(candidates))])

    answer_clean = answer.strip(".,!?;:")

    # Generate distractors
    all_words = [w.strip(".,!?;:\"'") for w in words if len(w.strip(".,!?;:\"'")) > 2]
    distractors = _generate_distractors(answer_clean, all_words)

    if not distractors or len(distractors) < 3:
        return None

    options = distractors[:3]
    options.append(answer_clean)
    random.shuffle(options)

    question_text = sentence.replace(answer, "________", 1)

    return {
        "question": question_text,
        "options": options,
        "correct_answer": answer_clean,
        "difficulty": difficulty,
    }


def _generate_distractors(answer: str, all_words: list[str]) -> list[str]:
    """Generate plausible wrong answers from available words."""
    similar = [w for w in all_words 
              if abs(len(w) - len(answer)) <= 3 
              and w.lower() != answer.lower()
              and w not in (answer, answer.lower(), answer.upper())]
    
    seen = set()
    unique_similar = []
    for w in similar:
        if w.lower() not in seen:
            seen.add(w.lower())
            unique_similar.append(w)
    
    if len(unique_similar) < 3:
        generics = ["None of the above", "All of the above", "Not specified", 
                    "Cannot be determined", f"{random.randint(1, 100)}"]
        for g in generics:
            if g.lower() != answer.lower() and g not in unique_similar:
                unique_similar.append(g)
            if len(unique_similar) >= 4:
                break

    return unique_similar


def _find_timestamp(segments: list[dict], sentence: str) -> str:
    """Find approximate timestamp for a sentence in the transcript."""
    if not segments:
        return "00:00"
    
    first_words = sentence[:30].lower().strip()
    for seg in segments:
        if first_words[:20] in seg["text"].lower():
            minutes = int(seg["start"] // 60)
            secs = int(seg["start"] % 60)
            return f"{minutes:02d}:{secs:02d}"
    
    return "00:00"


# ──────────────────────────────────────
# main.py (FastAPI app)
# ──────────────────────────────────────

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="YouTube Transcript API",
    description="Fetch transcripts (Hindi/English), generate notes & quizzes",
    version="1.0.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TranscriptRequest(BaseModel):
    url_or_id: str
    lang: str = "hi"
    fallback_langs: list[str] = ["en", "hi"]

class NotesRequest(BaseModel):
    url_or_id: str
    lang: str = "hi"
    title: str = "Video Notes"

class QuizRequest(BaseModel):
    url_or_id: str
    lang: str = "hi"
    num_questions: int = 10
    difficulty: str = "medium"
    quiz_title: str = "Video Quiz"

@app.get("/")
def root():
    return {"service": "YouTube Transcript API", "version": "1.0.0", "docs": "/docs"}

@app.get("/api/languages")
def list_languages(video_id: str = Query(...)):
    vid = extract_video_id(video_id)
    if not vid:
        raise HTTPException(400, "Invalid YouTube video ID or URL.")
    available = get_available_languages(vid)
    if not available:
        raise HTTPException(404, "No transcripts found.")
    return {"video_id": vid, "available_languages": available}

@app.get("/api/transcript")
def get_transcript(video_id: str = Query(...), lang: str = Query("hi"), raw: bool = Query(False)):
    vid = extract_video_id(video_id)
    if not vid:
        raise HTTPException(400, "Invalid YouTube video ID or URL.")
    result = fetch_transcript(vid, lang)
    if "error" in result:
        raise HTTPException(404, result["error"])
    if raw:
        return {"text": result["text"], "language": result["language"], "source": result.get("source")}
    return {"video_id": vid, "language": result["language"], "source": result.get("source"),
            "transcript_length": len(result["text"]), "segment_count": len(result["segments"]),
            "text": result["text"], "segments": result["segments"],
            "available_languages": result.get("available_languages", [])}

@app.get("/api/notes")
def get_notes(video_id: str = Query(...), lang: str = Query("hi"), title: str = Query("Video Notes")):
    vid = extract_video_id(video_id)
    if not vid:
        raise HTTPException(400, "Invalid YouTube video ID or URL.")
    transcript_data = fetch_transcript_for_notes(vid, lang)
    if "error" in transcript_data:
        raise HTTPException(404, transcript_data["error"])
    notes = generate_notes(transcript_data, title)
    return {"video_id": vid, "notes": notes}

@app.get("/api/quiz")
def get_quiz(video_id: str = Query(...), lang: str = Query("hi"),
             num_questions: int = Query(10, ge=3, le=50), difficulty: str = Query("medium"),
             quiz_title: str = Query("Video Quiz")):
    vid = extract_video_id(video_id)
    if not vid:
        raise HTTPException(400, "Invalid YouTube video ID or URL.")
    transcript_data = fetch_transcript(vid, lang)
    if "error" in transcript_data:
        raise HTTPException(404, transcript_data["error"])
    quiz = generate_quiz(transcript_data, num_questions, difficulty, quiz_title)
    return {"video_id": vid, "quiz": quiz}

@app.post("/api/transcript")
def post_transcript(req: TranscriptRequest):
    vid = extract_video_id(req.url_or_id)
    if not vid:
        raise HTTPException(400, "Invalid YouTube video ID or URL.")
    result = fetch_transcript(vid, req.lang, req.fallback_langs)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return {"video_id": vid, **result}

@app.post("/api/notes")
def post_notes(req: NotesRequest):
    vid = extract_video_id(req.url_or_id)
    if not vid:
        raise HTTPException(400, "Invalid YouTube video ID or URL.")
    transcript_data = fetch_transcript_for_notes(vid, req.lang)
    if "error" in transcript_data:
        raise HTTPException(404, transcript_data["error"])
    notes = generate_notes(transcript_data, req.title)
    return {"video_id": vid, "notes": notes}

@app.post("/api/quiz")
def post_quiz(req: QuizRequest):
    vid = extract_video_id(req.url_or_id)
    if not vid:
        raise HTTPException(400, "Invalid YouTube video ID or URL.")
    transcript_data = fetch_transcript(vid, req.lang)
    if "error" in transcript_data:
        raise HTTPException(404, transcript_data["error"])
    quiz = generate_quiz(transcript_data, req.num_questions, req.difficulty, req.quiz_title)
    return {"video_id": vid, "quiz": quiz}

@app.get("/health")
def health():
    return {"status": "ok", "service": "youtube-transcript-api"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("__main__:app", host="0.0.0.0", port=8000, reload=True)
