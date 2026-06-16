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
