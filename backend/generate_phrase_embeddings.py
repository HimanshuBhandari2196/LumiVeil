"""
LumiVeil — Generate Phrase Embeddings
========================================
Run this ONCE (and again any time you edit sensational_phrases.py) to
pre-compute an embedding vector for every phrase in the list. Saves the
result to phrase_embeddings.json, which semantic_match.py loads at
runtime — so the live backend never has to re-embed the phrase list on
every request, only your actual analyzed text.

Usage:
    cd backend
    python generate_phrase_embeddings.py

Requires GEMINI_API_KEY to be set — either in your environment, or in a
.env file in this folder (loaded automatically via python-dotenv, same
as app.py does).

After it finishes, commit the new phrase_embeddings.json to git — it's
small (a few hundred KB) and needs to ship with the backend so Railway
has it too.
"""

import os
import sys
import time
import json
from dotenv import load_dotenv

load_dotenv()

from sensational_phrases import SENSATIONAL_PHRASES
from semantic_match import get_embeddings_batch, GEMINI_API_KEY, _PHRASE_EMBEDDINGS_PATH

# Google's batch embedding endpoint accepts a limited number of requests
# per call — chunk the phrase list to stay well under that ceiling.
CHUNK_SIZE  = 50
MAX_RETRIES = 4
RETRY_WAIT_SECONDS = 20   # free-tier rate limits are usually per-minute


def embed_chunk_with_retry(chunk, chunk_label):
    """Try a chunk, and if it fails (often a rate limit on the free tier),
    wait and retry a few times before giving up."""
    for attempt in range(1, MAX_RETRIES + 1):
        vectors = get_embeddings_batch(chunk, task_type='SEMANTIC_SIMILARITY', verbose=True)
        if vectors:
            return vectors
        if attempt < MAX_RETRIES:
            print(f'  {chunk_label} failed (attempt {attempt}/{MAX_RETRIES}) — '
                  f'waiting {RETRY_WAIT_SECONDS}s before retrying (likely a rate limit)...')
            time.sleep(RETRY_WAIT_SECONDS)
    return None


def main():
    if not GEMINI_API_KEY:
        print('ERROR: GEMINI_API_KEY is not set. Add it to backend/.env and try again.')
        sys.exit(1)

    print(f'Embedding {len(SENSATIONAL_PHRASES)} phrases using task_type=SEMANTIC_SIMILARITY...')

    all_results = []
    for i in range(0, len(SENSATIONAL_PHRASES), CHUNK_SIZE):
        chunk = SENSATIONAL_PHRASES[i:i + CHUNK_SIZE]
        chunk_label = f'chunk {i // CHUNK_SIZE + 1} (phrases {i + 1}-{i + len(chunk)})'
        print(f'  {chunk_label}')
        vectors = embed_chunk_with_retry(chunk, chunk_label)
        if not vectors:
            print(f'ERROR: embedding request failed for {chunk_label} after {MAX_RETRIES} attempts.')
            print('If this keeps happening, wait a minute or two and just re-run the script —')
            print('it will pick up from a fresh run (it does not resume partway through).')
            sys.exit(1)
        for phrase, vector in zip(chunk, vectors):
            all_results.append({'phrase': phrase, 'embedding': vector})

    with open(_PHRASE_EMBEDDINGS_PATH, 'w') as f:
        json.dump(all_results, f)

    print(f'Done — wrote {len(all_results)} phrase embeddings to {_PHRASE_EMBEDDINGS_PATH}')
    print('Next: commit phrase_embeddings.json to git and push, so Railway has it too.')


if __name__ == '__main__':
    main()
