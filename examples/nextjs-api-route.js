/**
 * Next.js API Route - YouTube Transcript Proxy
 * 
 * Place this file at: pages/api/transcript.js  (Pages Router)
 * OR:                app/api/transcript/route.js (App Router - see below)
 * 
 * This proxies requests to your deployed Python service,
 * so your frontend calls your own domain (no CORS issues).
 */

// ===== Pages Router version (pages/api/transcript.js) =====
export default async function handler(req, res) {
  // Set CORS for frontend use
  res.setHeader('Access-Control-Allow-Origin', '*');
  
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { video_id, lang = 'hi', mode = 'transcript' } = req.query;

  if (!video_id) {
    return res.status(400).json({ error: 'video_id is required' });
  }

  // Your deployed Python service URL
  const PYTHON_API = process.env.TRANSCRIPT_API_URL || 'https://your-app.onrender.com';

  try {
    const endpoint = mode === 'notes' ? '/api/notes' 
                   : mode === 'quiz' ? '/api/quiz' 
                   : '/api/transcript';
    
    const response = await fetch(
      `${PYTHON_API}${endpoint}?video_id=${encodeURIComponent(video_id)}&lang=${lang}`,
      { timeout: 30000 }
    );
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      return res.status(response.status).json(error);
    }

    const data = await response.json();
    return res.status(200).json(data);
  } catch (error) {
    console.error('Transcript proxy error:', error);
    return res.status(502).json({ error: 'Failed to fetch transcript' });
  }
}


// ===== App Router version (app/api/transcript/route.js) =====
/*
export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const video_id = searchParams.get('video_id');
  const lang = searchParams.get('lang') || 'hi';
  const mode = searchParams.get('mode') || 'transcript';

  if (!video_id) {
    return Response.json({ error: 'video_id is required' }, { status: 400 });
  }

  const PYTHON_API = process.env.TRANSCRIPT_API_URL || 'https://your-app.onrender.com';

  try {
    const endpoint = mode === 'notes' ? '/api/notes' 
                   : mode === 'quiz' ? '/api/quiz' 
                   : '/api/transcript';
    
    const response = await fetch(
      `${PYTHON_API}${endpoint}?video_id=${encodeURIComponent(video_id)}&lang=${lang}`,
      { signal: AbortSignal.timeout(30000) }
    );

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      return Response.json(error, { status: response.status });
    }

    const data = await response.json();
    return Response.json(data);
  } catch (error) {
    console.error('Transcript proxy error:', error);
    return Response.json({ error: 'Failed to fetch transcript' }, { status: 502 });
  }
}
*/
