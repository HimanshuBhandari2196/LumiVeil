"""
LumiVeil — Debug Semantic Matching
====================================
Prints the ACTUAL similarity numbers the embedding model produces, for a
mix of genuinely sensational sentences and genuinely normal/factual ones.
Run this after any threshold/margin change to see real evidence instead
of guessing whether it's well-calibrated.

Usage:
    cd backend
    python debug_semantic_match.py
"""

from dotenv import load_dotenv
load_dotenv()

from semantic_match import get_embeddings_batch, _load_phrase_embeddings, _cosine_similarity

# A mix of sentences that SHOULD match (genuinely sensational, reworded to
# dodge the exact-match list) and sentences that should NOT match (normal,
# factual — including a few pulled from the real Al Jazeera false-positive
# case) so we can see both sides side by side.
TEST_SENTENCES = {
    'SHOULD match (sensational/paraphrased)': [
        "This is an absolutely unbelievable turn of events that nobody expected at all",
        "You need to see this before it gets taken down",
        "Doctors are hiding this simple trick from everyone",
    ],
    'should NOT match (normal factual content)': [
        "Messi had waited until the age of 39 to get the chance to play against England",
        "The 2026 final will take place at New York New Jersey Stadium in New Jersey",
        "Argentina's players were clearly fired up, partly by a determination to hold onto their title",
        "His career appeared to be complete when he dragged Argentina to glory in 2022",
        "That translated into a niggly contest, pockmarked by fouls in the first half",
    ],
}


def main():
    phrase_embeddings = _load_phrase_embeddings()
    if not phrase_embeddings:
        print("ERROR: phrase_embeddings.json not found. Run generate_phrase_embeddings.py first.")
        return

    for category, sentences in TEST_SENTENCES.items():
        print(f'\n=== {category} ===')
        vectors = get_embeddings_batch(sentences, verbose=True)
        if not vectors:
            print('Could not get embeddings — check GEMINI_API_KEY in .env')
            return

        for sentence, vector in zip(sentences, vectors):
            similarities = [_cosine_similarity(vector, e['embedding']) for e in phrase_embeddings]
            best_idx  = max(range(len(similarities)), key=lambda i: similarities[i])
            best_sim  = similarities[best_idx]
            best_phrase = phrase_embeddings[best_idx]['phrase']
            mean_sim  = sum(similarities) / len(similarities)
            margin    = best_sim - mean_sim

            print(f'  "{sentence[:60]}..."')
            print(f'    best match: "{best_phrase}"  similarity={best_sim:.3f}  '
                  f'mean={mean_sim:.3f}  margin={margin:.3f}')


if __name__ == '__main__':
    main()
