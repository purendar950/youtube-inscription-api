# YouTube Transcript Service

Fetch YouTube transcripts in **Hindi** & **English**, generate **study notes** & **MCQ quizzes**.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/purendar950/youtube-inscription-api)

## Quick Start

```bash
# 1. Install
pip install --upgrade pip
pip install -r requirements.txt

# 2. Start server
python run.py

# 3. Open browser
# http://localhost:8000/docs
```

## API

```
GET  /api/transcript?video_id=VIDEO_ID&lang=hi   → Transcript
GET  /api/notes?video_id=VIDEO_ID&lang=hi        → Study notes
GET  /api/quiz?video_id=VIDEO_ID&lang=en&num_questions=5  → Quiz
```

## Deploy (free)

[**Click here to deploy to Render**](https://render.com/deploy?repo=https://github.com/purendar950/youtube-inscription-api)

Or manually:
1. Push this repo to GitHub
2. Go to [dashboard.render.com](https://dashboard.render.com) → **New +** → **Blueprint**
3. Connect your GitHub repo
4. Render will auto-detect `render.yaml` and deploy 🚀

The free tier spins down after 15 min of inactivity and wakes up on the next request.
