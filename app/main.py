"""
YouTube Transcript API - The Pundits Official
FastAPI service for transcript fetching, note-making, and quiz generation.
Supports Hindi and English.

Deploy anywhere: Render, Railway, Fly.io, PythonAnywhere
"""

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .transcript import (
    extract_video_id,
    fetch_transcript,
    fetch_transcript_for_notes,
    get_available_languages,
)
from .notes import generate_notes
from .quiz import generate_quiz

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="YouTube Transcript API",
    description="Fetch YouTube transcripts (Hindi/English), generate notes & quizzes. Built for The Pundits Official.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow all origins for integration with any frontend (Next.js, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request/Response Models ──────────────────────────────────────────────────

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


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "service": "YouTube Transcript API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "GET /api/languages?video_id=XXX": "List available transcript languages",
            "GET /api/transcript?video_id=XXX&lang=hi": "Fetch transcript",
            "GET /api/notes?video_id=XXX&lang=hi": "Generate study notes",
            "GET /api/quiz?video_id=XXX&lang=hi&num_questions=10": "Generate quiz",
            "POST /api/transcript": "Fetch transcript (POST)",
            "POST /api/notes": "Generate notes (POST)",
            "POST /api/quiz": "Generate quiz (POST)",
        },
    }


@app.get("/api/languages")
def list_languages(video_id: str = Query(..., description="YouTube video ID or URL")):
    """List all available transcript languages for a video."""
    vid = extract_video_id(video_id)
    if not vid:
        raise HTTPException(400, "Invalid YouTube video ID or URL.")
    available = get_available_languages(vid)
    if not available:
        raise HTTPException(404, "No transcripts found for this video.")
    return {"video_id": vid, "available_languages": available}


@app.get("/api/transcript")
def get_transcript(
    video_id: str = Query(..., description="YouTube video ID or URL"),
    lang: str = Query("hi", description="Language code (hi, en, etc.)"),
    raw: bool = Query(False, description="Return text + language only"),
):
    """Fetch YouTube transcript in specified language."""
    vid = extract_video_id(video_id)
    if not vid:
        raise HTTPException(400, "Invalid YouTube video ID or URL.")

    result = fetch_transcript(vid, lang)

    if "error" in result:
        raise HTTPException(404, result["error"])

    if raw:
        return {
            "text": result["text"],
            "language": result["language"],
            "source": result.get("source"),
        }

    return {
        "video_id": vid,
        "language": result["language"],
        "source": result.get("source"),
        "transcript_length": len(result["text"]),
        "segment_count": len(result["segments"]),
        "text": result["text"],
        "segments": result["segments"],
        "available_languages": result.get("available_languages", []),
    }


@app.get("/api/notes")
def get_notes(
    video_id: str = Query(..., description="YouTube video ID or URL"),
    lang: str = Query("hi", description="Language code"),
    title: str = Query("Video Notes", description="Title for the notes"),
):
    """Generate structured study notes from a YouTube video transcript."""
    vid = extract_video_id(video_id)
    if not vid:
        raise HTTPException(400, "Invalid YouTube video ID or URL.")

    transcript_data = fetch_transcript_for_notes(vid, lang)

    if "error" in transcript_data:
        raise HTTPException(404, transcript_data["error"])

    notes = generate_notes(transcript_data, title)
    return {"video_id": vid, "notes": notes}


@app.get("/api/quiz")
def get_quiz(
    video_id: str = Query(..., description="YouTube video ID or URL"),
    lang: str = Query("hi", description="Language code"),
    num_questions: int = Query(10, ge=3, le=50, description="Number of questions"),
    difficulty: str = Query("medium", regex="^(easy|medium|hard)$"),
    quiz_title: str = Query("Video Quiz"),
):
    """Generate MCQ quiz from a YouTube video transcript."""
    vid = extract_video_id(video_id)
    if not vid:
        raise HTTPException(400, "Invalid YouTube video ID or URL.")

    transcript_data = fetch_transcript(vid, lang)

    if "error" in transcript_data:
        raise HTTPException(404, transcript_data["error"])

    quiz = generate_quiz(transcript_data, num_questions, difficulty, quiz_title)
    return {"video_id": vid, "quiz": quiz}


# ─── POST variants (for larger payloads / future auth) ────────────────────────

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


# ─── Health Check ─────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "youtube-transcript-api"}


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
