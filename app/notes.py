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
