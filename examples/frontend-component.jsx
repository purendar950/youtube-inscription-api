/**
 * YouTube Transcript -> Notes & Quiz
 * React component for use in Next.js project
 * 
 * Integrates with your backend API.
 */

import { useState } from 'react';

// Change this to your deployed API URL
const API_BASE = process.env.NEXT_PUBLIC_TRANSCRIPT_API || 'http://localhost:8000';

export default function YouTubeTranscriptTool() {
  const [url, setUrl] = useState('');
  const [lang, setLang] = useState('hi');
  const [mode, setMode] = useState('transcript'); // transcript | notes | quiz
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  function extractVideoId(input) {
    const match = input.match(
      /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([A-Za-z0-9_-]{11})/
    );
    return match ? match[1] : input;
  }

  async function fetchTranscript() {
    if (!url.trim()) return;
    setLoading(true);
    setError('');
    setData(null);

    const videoId = extractVideoId(url);

    try {
      const endpoint = mode === 'notes' ? '/api/notes' 
                     : mode === 'quiz' ? '/api/quiz' 
                     : '/api/transcript';

      const res = await fetch(
        `${API_BASE}${endpoint}?video_id=${videoId}&lang=${lang}${mode === 'quiz' ? '&num_questions=10' : ''}`
      );

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || err.error || 'Failed to fetch');
      }

      const result = await res.json();
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: 20 }}>
      <h2>📺 YouTube Transcript Tool</h2>
      <p style={{ color: '#666' }}>
        Fetch transcripts in Hindi/English, generate notes & quizzes
      </p>

      {/* Input */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <input
          type="text"
          value={url}
          onChange={e => setUrl(e.target.value)}
          placeholder="YouTube URL or Video ID"
          style={{ flex: 1, padding: 8, borderRadius: 4, border: '1px solid #ccc' }}
        />
        <select
          value={lang}
          onChange={e => setLang(e.target.value)}
          style={{ padding: 8, borderRadius: 4, border: '1px solid #ccc' }}
        >
          <option value="hi">🇮🇳 Hindi</option>
          <option value="en">🇬🇧 English</option>
        </select>
      </div>

      {/* Mode Tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        {['transcript', 'notes', 'quiz'].map(m => (
          <button
            key={m}
            onClick={() => setMode(m)}
            style={{
              padding: '6px 16px',
              borderRadius: 4,
              border: '1px solid #0070f3',
              background: mode === m ? '#0070f3' : 'white',
              color: mode === m ? 'white' : '#0070f3',
              cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {m === 'transcript' ? '📝 Transcript' : m === 'notes' ? '📚 Notes' : '🧠 Quiz'}
          </button>
        ))}
      </div>

      <button
        onClick={fetchTranscript}
        disabled={loading}
        style={{
          padding: '8px 24px',
          background: '#0070f3',
          color: 'white',
          border: 'none',
          borderRadius: 4,
          cursor: loading ? 'not-allowed' : 'pointer',
          opacity: loading ? 0.7 : 1,
        }}
      >
        {loading ? 'Fetching...' : 'Fetch'}
      </button>

      {error && (
        <div style={{ marginTop: 16, padding: 12, background: '#fff0f0', borderRadius: 4, color: '#d00' }}>
          ❌ {error}
        </div>
      )}

      {/* Results */}
      {data && (
        <div style={{ marginTop: 16 }}>
          {mode === 'transcript' && <TranscriptView data={data} />}
          {mode === 'notes' && <NotesView data={data} />}
          {mode === 'quiz' && <QuizView data={data} />}
        </div>
      )}
    </div>
  );
}

/* ─── Transcript View ─────────────────────────────────────────── */
function TranscriptView({ data }) {
  return (
    <div style={{ background: '#f9f9f9', padding: 16, borderRadius: 8 }}>
      <h4>📝 Transcript ({data.language})</h4>
      <p style={{ color: '#888', fontSize: 14 }}>
        {data.segment_count || data.transcript_length} chars
      </p>
      <div style={{ maxHeight: 400, overflowY: 'auto', whiteSpace: 'pre-wrap', 
                    background: 'white', padding: 12, borderRadius: 4, fontSize: 14 }}>
        {data.text}
      </div>
      {data.available_languages?.length > 0 && (
        <p style={{ fontSize: 12, color: '#888', marginTop: 8 }}>
          Available languages: {data.available_languages.map(l => l.language).join(', ')}
        </p>
      )}
    </div>
  );
}

/* ─── Notes View ──────────────────────────────────────────────── */
function NotesView({ data }) {
  const notes = data.notes;
  if (!notes) return null;

  return (
    <div style={{ background: '#f0f7ff', padding: 16, borderRadius: 8 }}>
      <h4>📚 {notes.title}</h4>

      {notes.stats && (
        <div style={{ display: 'flex', gap: 12, fontSize: 13, color: '#666', marginBottom: 12 }}>
          <span>📊 {notes.stats.total_words} words</span>
          <span>🇮🇳 {notes.stats.hindi_words} Hindi</span>
          <span>🇬🇧 {notes.stats.english_words} English</span>
        </div>
      )}

      {/* Summary */}
      <div style={{ marginBottom: 16 }}>
        <h5 style={{ marginBottom: 4 }}>Summary</h5>
        <p style={{ background: 'white', padding: 12, borderRadius: 4, fontSize: 14, lineHeight: 1.6 }}>
          {notes.summary}
        </p>
      </div>

      {/* Key Points */}
      {notes.key_points?.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <h5 style={{ marginBottom: 4 }}>Key Points</h5>
          <ul style={{ background: 'white', padding: '12px 24px', borderRadius: 4, fontSize: 14, lineHeight: 1.8 }}>
            {notes.key_points.map((kp, i) => <li key={i}>{kp}</li>)}
          </ul>
        </div>
      )}

      {/* Timestamped Sections */}
      {notes.timestamped_sections?.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <h5 style={{ marginBottom: 4 }}>Timestamped Sections</h5>
          {notes.timestamped_sections.map((sec, i) => (
            <div key={i} style={{ background: 'white', padding: '8px 12px', marginBottom: 4, borderRadius: 4, fontSize: 13 }}>
              <span style={{ color: '#0070f3', fontWeight: 600 }}>⏱ {sec.timestamp}</span>
              <p style={{ margin: '4px 0 0' }}>{sec.text.slice(0, 200)}...</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Quiz View ───────────────────────────────────────────────── */
function QuizView({ data }) {
  const quiz = data.quiz;
  const [answers, setAnswers] = useState({});

  if (!quiz) return null;

  function handleAnswer(qIdx, option) {
    setAnswers(prev => ({ ...prev, [qIdx]: option }));
  }

  return (
    <div style={{ background: '#fefcf0', padding: 16, borderRadius: 8 }}>
      <h4>🧠 {quiz.title} ({quiz.total_questions} questions)</h4>
      <p style={{ color: '#888', fontSize: 13, marginBottom: 12 }}>
        Difficulty: {quiz.difficulty} | Language: {quiz.language}
      </p>

      {quiz.questions?.map((q, idx) => (
        <div key={idx} style={{
          background: 'white', padding: 12, marginBottom: 12,
          borderRadius: 8, border: '1px solid #eee',
        }}>
          <p style={{ fontWeight: 500, marginBottom: 8 }}>
            {idx + 1}. {q.question}
            {q.timestamp && <span style={{ color: '#888', fontSize: 12, marginLeft: 8 }}>⏱ {q.timestamp}</span>}
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {q.options.map((opt, oi) => {
              const isSelected = answers[idx] === opt;
              const isCorrect = opt === q.correct_answer;
              const showResult = answers[idx] !== undefined;
              const bgColor = showResult
                ? isCorrect ? '#d4edda' : isSelected ? '#f8d7da' : 'white'
                : isSelected ? '#e3f2fd' : 'white';

              return (
                <button
                  key={oi}
                  onClick={() => handleAnswer(idx, opt)}
                  style={{
                    padding: '6px 14px',
                    border: `1px solid ${showResult && isCorrect ? '#28a745' : '#ccc'}`,
                    borderRadius: 4,
                    background: bgColor,
                    cursor: 'pointer',
                    fontSize: 13,
                  }}
                >
                  {opt}
                  {showResult && isCorrect && ' ✓'}
                </button>
              );
            })}
          </div>
          {answers[idx] && answers[idx] !== q.correct_answer && (
            <p style={{ color: '#d00', fontSize: 12, marginTop: 4 }}>
              Correct answer: <strong>{q.correct_answer}</strong>
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
