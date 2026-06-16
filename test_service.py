#!/usr/bin/env python3
"""
YouTube Transcript Service - Quick Test
Run this on your own machine to verify everything works.
"""

import requests
import sys
import json

BASE = "http://localhost:8000"

def test(name, method="GET", path="/health", params=None, json_data=None, timeout=30):
    url = f"{BASE}{path}"
    try:
        if method == "GET":
            r = requests.get(url, params=params, timeout=timeout)
        else:
            r = requests.post(url, json=json_data, timeout=timeout)
        
        status = "✅" if r.status_code == 200 else "❌"
        print(f"  {status} {method} {path} → {r.status_code}")
        
        if r.status_code == 200:
            return r.json()
        else:
            print(f"      Error: {r.text[:100]}")
            return None
    except requests.exceptions.ConnectionError:
        print(f"  ❌ {method} {path} → CONNECTION REFUSED")
        print(f"      Is the server running on {BASE}?")
        return None

if __name__ == "__main__":
    print("=" * 60)
    print("  YouTube Transcript Service - Live Test")
    print("=" * 60)
    print(f"\n  Testing server at: {BASE}")
    print(f"  Make sure to start the server first:  python run.py\n")
    
    # Test 1: Health
    print("  [1/6] Basic Endpoints")
    data = test("Health", "GET", "/health")
    if data: print(f"         Status: {data.get('status')}")
    
    # Test 2: Root
    data = test("Info", "GET", "/")
    if data: print(f"         Service: {data.get('service')} v{data.get('version')}")
    
    # Test 3: Languages
    print("\n  [2/6] Available Languages")
    data = test("Languages", "GET", "/api/languages", params={"video_id": "jNQXAC9IVRw"})
    if data:
        langs = data.get("available_languages", [])
        print(f"         Found {len(langs)} languages:")
        for l in langs[:3]:
            print(f"           - {l['language_code']} ({l['language']})")
    
    # Test 4: Transcript (English)
    print("\n  [3/6] Transcript (English)")
    data = test("Transcript", "GET", "/api/transcript", params={"video_id": "jNQXAC9IVRw", "lang": "en", "raw": "true"})
    if data:
        text = data.get("text", "")
        print(f"         Source: {data.get('source', '?')}")
        print(f"         Length: {len(text)} chars")
        print(f'         Preview: "{text[:80]}..."')
    
    # Test 5: Notes
    print("\n  [4/6] Study Notes")
    data = test("Notes", "GET", "/api/notes", params={"video_id": "jNQXAC9IVRw", "lang": "en"})
    if data:
        notes = data.get("notes", {})
        stats = notes.get("stats", {})
        print(f"         Words: {stats.get('total_words')}")
        print(f"         Sections: {len(notes.get('timestamped_sections', []))}")
        print(f'         Summary: "{notes.get("summary", "")[:60]}..."')
    
    # Test 6: Quiz
    print("\n  [5/6] Quiz Generation")
    data = test("Quiz", "GET", "/api/quiz", params={"video_id": "jNQXAC9IVRw", "lang": "en", "num_questions": 3})
    if data:
        quiz = data.get("quiz", {})
        print(f"         Questions: {quiz.get('total_questions')}")
        for i, q in enumerate(quiz.get("questions", [])):
            print(f"           Q{i+1}: {q.get('question', '')[:40]}...")
            print(f"                Answer: {q.get('correct_answer')}")
    
    # Test 7: Hindi
    print("\n  [6/6] Hindi Transcript (auto-fallback)")
    data = test("Hindi", "GET", "/api/transcript", params={"video_id": "jNQXAC9IVRw", "lang": "hi", "raw": "true"})
    if data:
        print(f"         Language: {data.get('language')}")
        print(f"         Source: {data.get('source')}")
    
    print(f"\n  {'=' * 56}")
    print(f"  ✅ Done! Open http://localhost:8000/docs in your browser")
    print(f"  {'=' * 56}")
