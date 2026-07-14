"""
LumiVeil — Sensational Phrase List
===================================
The manually-curated list of sensational / misinformation phrases used
for exact-match detection in app.py's check_sensationalism().

Pulled into its own file (instead of living inline in app.py) so it can
also be imported by generate_phrase_embeddings.py, which pre-computes an
embedding for every phrase here. If you add or remove phrases below,
re-run generate_phrase_embeddings.py so phrase_embeddings.json stays in
sync — otherwise the semantic (paraphrase) matching layer will be
comparing against a stale list.
"""

SENSATIONAL_PHRASES = [
    # Urgency & fear
    'shocking', 'terrifying', 'horrifying', 'disturbing', 'alarming',
    'devastating', 'catastrophic', 'emergency', 'crisis', 'panic',
    'chaos', 'mayhem', 'disaster',
    # Conspiracy
    'they dont want you to know', 'secret revealed',
    'what mainstream media wont tell', 'suppressed', 'censored',
    'banned', 'deep state', 'new world order', 'illuminati',
    'false flag', 'crisis actor', 'wake up', 'sheeple',
    'shadow government', 'they are hiding', 'cover up', 'coverup',
    # Clickbait
    'explosive', 'bombshell', 'leaked', 'exclusive', 'breaking',
    'viral', 'exposed', 'miracle', 'hoax', 'conspiracy',
    'you wont believe', 'mind blowing', 'mind-blowing',
    'jaw dropping', 'jaw-dropping', 'game changer', 'game-changer',
    'this changes everything', 'nothing will be the same',
    'share before deleted', 'share before they delete',
    'watch before removed', 'watch before banned',
    # Medical misinformation
    'miracle cure', 'doctors dont want you', 'big pharma hiding',
    'natural cure banned', 'cancer cure suppressed', 'doctors exposed',
    'vaccine kills', 'poison in', 'toxins in', 'detox miracle',
    'cure for everything', 'big pharma doesnt want',
    'medical establishment hiding',
    # Political manipulation
    'election stolen', 'voter fraud proof', 'rigged election',
    'deep state plot', 'globalist agenda', 'socialist takeover',
    'communist infiltration', 'radical left', 'extreme right',
    'they are replacing', 'great replacement', 'population control',
    # Financial misinformation
    'get rich quick', 'make money fast', 'guaranteed returns',
    'risk free investment', 'bitcoin millionaire', 'secret investment',
    'banks dont want you', 'financial secret',
    'retire in 30 days', 'unlimited income',
    # Religious / apocalyptic manipulation
    'end times', 'apocalypse now', 'prophecy fulfilled',
    'sign of the end', 'biblical prophecy',
    'god told me', 'divine revelation exclusive',
    # Fake credibility signals
    'scientists baffled', 'doctors stunned', 'experts shocked',
    'government admits', 'finally admitted', 'officially confirmed',
    'leaked documents prove', 'insider reveals',
    'whistleblower exposes', 'anonymous source confirms',
    # Emotional manipulation
    'will make you cry', 'will restore your faith',
    'will make you sick', 'will make you angry',
    'will shock you', 'prepare to be amazed',
    'you need to see this', 'everyone is talking about',
    'the truth is out', 'finally the truth',
]
