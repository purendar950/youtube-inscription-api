# YouTube Transcript Service

Fetch YouTube transcripts in **Hindi** & **English**, generate **study notes** & **MCQ quizzes**.

## Quick Start

```bash
# 1. Install
pip install --upgrade pip
pip install fastapi uvicorn yt-dlp httpx

# 2. Start server
python server.py

# 3. Open browser
# http://localhost:8000/docs
```

## API

```
GET  /api/transcript?video_id=VIDEO_ID&lang=hi   → Transcript
GET  /api/notes?video_id=VIDEO_ID&lang=hi        → Study notes
GET  /api/quiz?video_id=VIDEO_ID&lang=en&num_questions=5  → Quiz
```

## If pydantic-core fails to install

```bash
pip install --upgrade pip wheel setuptools
pip install fastapi uvicorn yt-dlp httpx --only-binary :all:
```

## Deploy (free)

See `deploy/render.yaml` for 1-click deploy to Render.
