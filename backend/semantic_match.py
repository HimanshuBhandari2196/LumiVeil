"""
LumiVeil — Semantic Phrase Matching
====================================
Catches sensational language that's been reworded to dodge the exact-match
phrase list in sensational_phrases.py — e.g. "you will not believe this" vs
the listed "you wont believe". Uses Google's embedding model to compare
meaning rather than exact wording.

This is a FALLBACK layer only. app.py's check_sensationalism() calls
find_semantic_matches() only when the free, instant exact-match pass finds
nothing — so the added latency/cost of an embedding API call is only paid
on content that's already made it past the cheap check.

Setup (one-time, or whenever sensational_phrases.py changes):
    python generate_phrase_embeddings.py
This creates phrase_embeddings.json, which this file loads at import time.
If that file is missing, semantic matching is silently skipped — the
exact-match layer keeps working on its own either way.
"""

import os
import re
import json
import math
import requests as http_requests

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
EMBED_MODEL    = 'gemini-embedding-001'
EMBED_ENDPOINT = f'https://generativelanguage.googleapis.com/v1beta/models/{EMBED_MODEL}:batchEmbedContents'

SIMILARITY_THRESHOLD = 0.90   # conservative stopgap floor — see MIN_MARGIN below
MIN_MARGIN            = 0.08  # top match must clearly stand out from the sentence's
                               # average similarity across ALL phrases, not just clear
                               # an absolute number. Needed because this embedding
                               # model appears to score a high baseline similarity
                               # between almost any two pieces of text — a flat
                               # threshold alone let it match unrelated sentences
                               # (e.g. a sentence about a stadium location matching
                               # "new world order") purely because everything scored
                               # uniformly high, not because anything was distinctive.
MAX_SENTENCES         = 20    # cap per request, bounds latency + cost
MIN_SENTENCE_LENGTH    = 15   # skip trivially short fragments

_PHRASE_EMBEDDINGS_PATH = os.path.join(os.path.dirname(__file__), 'phrase_embeddings.json')
_phrase_embeddings_cache = None  # loaded lazily, once, on first use


def _load_phrase_embeddings():
    global _phrase_embeddings_cache
    if _phrase_embeddings_cache is not None:
        return _phrase_embeddings_cache

    if not os.path.exists(_PHRASE_EMBEDDINGS_PATH):
        _phrase_embeddings_cache = []
        return _phrase_embeddings_cache

    with open(_PHRASE_EMBEDDINGS_PATH, 'r') as f:
        _phrase_embeddings_cache = json.load(f)  # list of {"phrase": str, "embedding": [float, ...]}
    return _phrase_embeddings_cache


def _cosine_similarity(a, b):
    dot     = sum(x * y for x, y in zip(a, b))
    norm_a  = math.sqrt(sum(x * x for x in a))
    norm_b  = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _split_sentences(text):
    parts = re.split(r'[.!?\n]+', text)
    parts = [p.strip() for p in parts if len(p.strip()) >= MIN_SENTENCE_LENGTH]
    return parts[:MAX_SENTENCES]


def get_embeddings_batch(texts, task_type='SEMANTIC_SIMILARITY', verbose=False):
    """
    Embed a list of strings in a single API call.
    Returns a list of vectors (same order as input), or None on failure.

    verbose=True prints the actual HTTP status/response on failure —
    used by generate_phrase_embeddings.py so setup errors are visible.
    The live app calls this with verbose=False (the default), and it
    always just returns None on any failure — no retries, no exceptions
    raised — so a slow/failed embeddings call degrades a single request
    instantly rather than making someone's page analysis hang.
    """
    if not GEMINI_API_KEY or not texts:
        if verbose:
            print('  (skipped: GEMINI_API_KEY not set, or empty text list)')
        return None

    try:
        resp = http_requests.post(
            EMBED_ENDPOINT,
            headers={
                'x-goog-api-key': GEMINI_API_KEY,
                'Content-Type':   'application/json'
            },
            json={
                'requests': [
                    {
                        'model':    f'models/{EMBED_MODEL}',
                        'content':  {'parts': [{'text': t}]},
                        'taskType': task_type,
                    }
                    for t in texts
                ]
            },
            timeout=15
        )
        if resp.status_code != 200:
            if verbose:
                print(f'  HTTP {resp.status_code}: {resp.text[:300]}')
            return None
        data = resp.json()
        return [e['values'] for e in data.get('embeddings', [])]
    except Exception as e:
        if verbose:
            print(f'  Exception: {e}')
        return None


def find_semantic_matches(text, threshold=SIMILARITY_THRESHOLD, min_margin=MIN_MARGIN):
    """
    Compare each sentence in `text` against the pre-computed phrase
    embeddings. A sentence only counts as a match if its best-matching
    phrase BOTH clears the absolute threshold AND stands out clearly from
    that sentence's average similarity across the whole phrase list (see
    MIN_MARGIN above for why the margin check matters). Returns a list of
    (sentence, matched_phrase, similarity). Returns [] if embeddings
    aren't available (no API key, no phrase_embeddings.json, or a request
    failure) — callers should treat that the same as "no matches found".
    """
    phrase_embeddings = _load_phrase_embeddings()
    if not phrase_embeddings:
        return []

    sentences = _split_sentences(text)
    if not sentences:
        return []

    sentence_vectors = get_embeddings_batch(sentences)
    if not sentence_vectors:
        return []

    matches = []
    for sentence, vector in zip(sentences, sentence_vectors):
        similarities = [_cosine_similarity(vector, entry['embedding']) for entry in phrase_embeddings]
        best_idx        = max(range(len(similarities)), key=lambda i: similarities[i])
        best_similarity = similarities[best_idx]
        best_phrase     = phrase_embeddings[best_idx]['phrase']
        mean_similarity = sum(similarities) / len(similarities)
        margin          = best_similarity - mean_similarity

        if best_similarity >= threshold and margin >= min_margin:
            matches.append((sentence, best_phrase, best_similarity))

    return matches
