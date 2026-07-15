"""
LumiVeil — Backend API
======================
Flask backend for fake news, misinformation, and AI-image detection.

Structure
---------
  1. Imports & config
  2. Security helpers     (API key validation, input sanitisation)
  3. Image analysis layer (provider abstraction — swap Sightengine ↔ Hive via .env)
  4. Content analysis     (URL credibility, sensationalism, scoring)
  5. Routes              (/api/v1/analyze, /api/v1/health)
  6. Entry point

Adding a new image-analysis provider
-------------------------------------
  1. Add its credentials to .env + .env.example
  2. Load them in the "Provider credentials" section below
  3. Write  _analyze_with_<name>(image_url) -> (penalty: int|None, flags: list[str])
  4. Add an elif branch inside analyze_image()
  5. Set  IMAGE_ANALYSIS_PROVIDER=<name>  in .env
"""

# ===========================================================================
# 1. IMPORTS & CONFIG
# ===========================================================================

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
import requests as http_requests
from bs4 import BeautifulSoup
import secrets
import hashlib
import io
import re
import json
from PIL import Image
import os
from dotenv import load_dotenv
from database import init_db, get_user_by_email, create_user, check_usage_allowed, increment_usage, TIER_LIMITS, get_usage_today, update_last_login, create_email_verification_token, verify_email_token, create_password_reset_token, verify_password_reset_token, consume_password_reset_token, check_guest_usage_allowed, increment_guest_usage
from auth import hash_password, verify_password, generate_token, get_user_from_token, issue_token_pair, refresh_access_token, revoke_refresh_token_plaintext
from email_service import send_verification_email, send_password_reset_email
from sensational_phrases import SENSATIONAL_PHRASES
from semantic_match import find_semantic_matches

load_dotenv()

app = Flask(__name__)

# Railway (like most PaaS) sits behind a reverse proxy, so request.remote_addr
# would otherwise return the proxy's internal address for every request —
# silently breaking all per-IP rate limiting and guest usage tracking below.
# x_for=1 trusts a single hop of X-Forwarded-For, which matches Railway's setup.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Initialise database on startup
init_db()

# ---- CORS ----
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "allow_headers": ["Content-Type", "X-API-Key", "Authorization", "Accept"],
        "expose_headers": ["Content-Type"],
        "methods": ["GET", "POST", "OPTIONS"],
        "supports_credentials": False
    }
})

# ---- RATE LIMITER ----
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per day", "30 per minute"],
    storage_uri="memory://",
    strategy="fixed-window"
)

# ---- LUMIVEIL INTERNAL API KEY ----
# Used to authenticate requests from the extension to this backend.
# Set LUMIVEIL_API_KEY in .env — see .env.example.
_API_KEY      = os.environ.get('LUMIVEIL_API_KEY', 'change-this-in-your-env-file')
_API_KEY_HASH = hashlib.sha256(_API_KEY.encode()).hexdigest()

# ---- IMAGE ANALYSIS PROVIDER ----
# Change IMAGE_ANALYSIS_PROVIDER in .env to switch providers.
# Supported now: 'sightengine'
# Ready to enable: 'hive'  (uncomment the Hive section below + .env creds)
IMAGE_ANALYSIS_PROVIDER = os.environ.get('IMAGE_ANALYSIS_PROVIDER', 'sightengine')

# Provider credentials
SIGHTENGINE_API_USER   = os.environ.get('SIGHTENGINE_API_USER', '')
SIGHTENGINE_API_SECRET = os.environ.get('SIGHTENGINE_API_SECRET', '')
GEMINI_API_KEY         = os.environ.get('GEMINI_API_KEY', '')
GOOGLE_FACTCHECK_KEY   = os.environ.get('GOOGLE_FACTCHECK_KEY', '')
# HIVE_API_KEY         = os.environ.get('HIVE_API_KEY', '')   # uncomment for Hive


# ===========================================================================
# 2. SECURITY HELPERS
# ===========================================================================

def _validate_api_key(req):
    """Constant-time comparison of the X-API-Key header against the stored hash."""
    key = req.headers.get('X-API-Key', '')
    if not key:
        return False
    return secrets.compare_digest(
        hashlib.sha256(key.encode()).hexdigest(),
        _API_KEY_HASH
    )


def _get_current_user(req):
    """
    Extract and validate the Bearer token from the Authorization header.
    Returns the user dict if valid, or None.
    """
    auth_header = req.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    token = auth_header[7:]
    return get_user_from_token(token)


def _validate_input(user_input):
    """Basic length and injection-pattern checks.
    Returns (is_valid: bool, errors: list[str]).
    """
    if not user_input or not user_input.strip():
        return False, ['Input cannot be empty']

    if len(user_input) > 5000:
        return False, ['Input too long — maximum 5000 characters']

    injection_patterns = [
        '<script', 'javascript:', 'eval(', 'exec(',
        'import os', 'subprocess', '__import__',
        'DROP TABLE', 'SELECT *', 'INSERT INTO', 'DELETE FROM'
    ]
    lower = user_input.lower()
    for pattern in injection_patterns:
        if pattern.lower() in lower:
            return False, ['Suspicious content detected in input']

    return True, []


@app.after_request
def _security_headers(response):
    """Attach security and CORS headers to every response."""
    response.headers['Access-Control-Allow-Origin']      = '*'
    response.headers['Access-Control-Allow-Headers']     = 'Content-Type, X-API-Key, Authorization, Accept'
    response.headers['Access-Control-Allow-Methods']     = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Private-Network'] = 'true'
    response.headers['X-Content-Type-Options']           = 'nosniff'
    response.headers['X-Frame-Options']                  = 'DENY'
    response.headers['X-XSS-Protection']                 = '1; mode=block'
    return response


@app.route('/api/v1/auth/signup', methods=['OPTIONS'])
@app.route('/api/v1/auth/login', methods=['OPTIONS'])
@app.route('/api/v1/auth/refresh', methods=['OPTIONS'])
@app.route('/api/v1/auth/logout', methods=['OPTIONS'])
@app.route('/api/v1/auth/forgot-password', methods=['OPTIONS'])
@app.route('/api/v1/auth/reset-password', methods=['OPTIONS'])
@app.route('/api/v1/auth/resend-verification', methods=['OPTIONS'])
@app.route('/api/v1/auth/delete-account', methods=['OPTIONS'])
@app.route('/api/v1/analyze', methods=['OPTIONS'])
@app.route('/api/v1/user/status', methods=['OPTIONS'])
def handle_options():
    """Explicit preflight handler for all API routes."""
    return '', 200


# ===========================================================================
# 3. IMAGE ANALYSIS — PROVIDER ABSTRACTION
# ===========================================================================
# Every provider function must return:
#   penalty (int | None)  — points deducted from trust score; None = provider error
#   flags   (list[str])   — human-readable results shown in the full report

def _parse_image_scores(ai_score, deepfake_score):
    """
    Shared threshold logic used by every provider.
    Centralised so tuning thresholds here affects all backends at once.
    """
    flags        = []
    penalty      = 0

    # AI-generated image
    if ai_score > 0.7:
        flags.append(f'❌ Image appears to be AI generated (confidence: {int(ai_score * 100)}%)')
        penalty += 40
    elif ai_score > 0.4:
        flags.append(f'⚠️ Image may be AI generated (confidence: {int(ai_score * 100)}%)')
        penalty += 20
    else:
        flags.append(f'✅ Image does not appear to be AI generated (confidence: {int((1 - ai_score) * 100)}%)')

    # Deepfake
    if deepfake_score > 0.7:
        flags.append(f'❌ Deepfake detected (confidence: {int(deepfake_score * 100)}%)')
        penalty += 50
    elif deepfake_score > 0.4:
        flags.append(f'⚠️ Possible deepfake detected (confidence: {int(deepfake_score * 100)}%)')
        penalty += 25
    else:
        flags.append(f'✅ No deepfake detected (confidence: {int((1 - deepfake_score) * 100)}%)')

    return penalty, flags


# ---------------------------------------------------------------------------
# Provider: Sightengine (active default)
# Docs: https://sightengine.com/docs/ai-generated-image-detection
#       https://sightengine.com/docs/deepfake-detection
# ---------------------------------------------------------------------------

def _analyze_with_sightengine(image_url):
    if not SIGHTENGINE_API_USER or not SIGHTENGINE_API_SECRET:
        return None, ['⚠️ Sightengine credentials missing — set SIGHTENGINE_API_USER and SIGHTENGINE_API_SECRET in .env']

    resp = http_requests.get(
        'https://api.sightengine.com/1.0/check.json',
        params={
            'url':        image_url,
            'models':     'genai,deepfake',
            'api_user':   SIGHTENGINE_API_USER,
            'api_secret': SIGHTENGINE_API_SECRET,
        },
        timeout=30
    )

    if resp.status_code != 200:
        return None, [f'⚠️ Sightengine API error: HTTP {resp.status_code}']

    data = resp.json()
    if data.get('status') != 'success':
        return None, ['⚠️ Sightengine returned an unsuccessful response']

    ai_score       = data.get('type', {}).get('ai_generated', 0)
    deepfake_score = data.get('type', {}).get('deepfake', 0)

    return _parse_image_scores(ai_score, deepfake_score)


# ---------------------------------------------------------------------------
# Provider: Hive (ready to enable — uncomment when you have enterprise access)
# Docs: https://docs.thehive.ai/docs/visual-content-moderation
# ---------------------------------------------------------------------------
#
# def _analyze_with_hive(image_url):
#     if not HIVE_API_KEY:
#         return None, ['⚠️ Hive credentials missing — set HIVE_API_KEY in .env']
#
#     resp = http_requests.post(
#         'https://api.thehive.ai/api/v3/chat/completions',
#         headers={
#             'Authorization': f'Bearer {HIVE_API_KEY}',
#             'Content-Type':  'application/json',
#         },
#         json={
#             'model':      'hive/moderation-11b-vision-language-model',
#             'max_tokens': 1000,
#             'messages': [{
#                 'role': 'user',
#                 'content': [
#                     {'type': 'text',      'text': 'Analyze this image for AI generation and deepfakes.'},
#                     {'type': 'image_url', 'image_url': {'url': image_url}},
#                 ]
#             }]
#         },
#         timeout=30
#     )
#
#     if resp.status_code != 200:
#         return None, [f'⚠️ Hive API error: HTTP {resp.status_code}']
#
#     content = resp.json().get('choices', [{}])[0].get('message', {}).get('content', '')
#     # TODO: parse natural-language content string → extract float scores
#     # then: return _parse_image_scores(ai_score, deepfake_score)
#     return None, ['⚠️ Hive response parsing not yet implemented']


# ---------------------------------------------------------------------------
# Public dispatcher — the ONLY function the rest of the app calls
# ---------------------------------------------------------------------------

def analyze_image(image_url):
    """
    Route to the correct provider based on IMAGE_ANALYSIS_PROVIDER in .env.
    Catches all provider-level exceptions so a broken provider never crashes
    the whole /analyze endpoint.
    """
    provider = IMAGE_ANALYSIS_PROVIDER.lower().strip()
    try:
        if provider == 'sightengine':
            return _analyze_with_sightengine(image_url)
        # elif provider == 'hive':
        #     return _analyze_with_hive(image_url)
        else:
            return None, [f'⚠️ Unknown provider "{provider}" — check IMAGE_ANALYSIS_PROVIDER in .env']
    except Exception as exc:
        return None, [f'⚠️ Image analysis error ({provider}): {exc}']


# ---------------------------------------------------------------------------
# EXIF metadata analysis (provider-independent)
# ---------------------------------------------------------------------------

def analyze_image_metadata(image_url):
    """Download image and inspect EXIF metadata for manipulation signals."""
    try:
        headers = {
            'User-Agent':      'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept':          'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer':         image_url,
        }
        img_resp = http_requests.get(image_url, headers=headers, timeout=15)
        if img_resp.status_code != 200:
            return 0, ['⚠️ Could not download image for metadata analysis']

        img     = Image.open(io.BytesIO(img_resp.content))
        flags   = []
        penalty = 0

        exif = img._getexif() if hasattr(img, '_getexif') else None

        if exif is None:
            flags.append('⚠️ No EXIF metadata — image may have been edited or screenshotted')
            penalty += 10
        else:
            software = exif.get(305, '')
            if software:
                suspicious_sw = [
                    'photoshop', 'gimp', 'lightroom',
                    'stable diffusion', 'midjourney', 'dall-e', 'firefly', 'canva'
                ]
                if any(s in software.lower() for s in suspicious_sw):
                    flags.append(f'❌ Image edited with suspicious software: {software}')
                    penalty += 20
                else:
                    flags.append(f'✅ Image software: {software}')

            if exif.get(34853):
                flags.append('✅ GPS metadata present — location data exists')
            else:
                flags.append('⚠️ No GPS data found in image')

            date_taken = exif.get(36867)
            if date_taken:
                flags.append(f'✅ Photo taken: {date_taken}')
            else:
                flags.append('⚠️ No date taken in metadata')

        flags.append(f'✅ Image format: {img.format}, mode: {img.mode}')
        return penalty, flags

    except Exception as exc:
        return 0, [f'⚠️ Metadata analysis error: {exc}']


def check_with_google_factcheck(claim):
    """
    Search Google's Fact Check Tools API for existing fact-checks on a claim.
    Returns (found: bool, results: list[dict]) where each result has:
      { publisher, title, url, rating, claim_reviewed }
    Docs: https://developers.google.com/fact-check/tools/api
    """
    if not GOOGLE_FACTCHECK_KEY:
        return False, []

    try:
        resp = http_requests.get(
            'https://factchecktools.googleapis.com/v1alpha1/claims:search',
            params={
                'query':        claim[:500],
                'key':          GOOGLE_FACTCHECK_KEY,
                'languageCode': 'en',
                'pageSize':     5
            },
            timeout=10
        )
        if resp.status_code != 200:
            return False, []

        data   = resp.json()
        claims = data.get('claims', [])
        if not claims:
            return False, []

        results = []
        for c in claims:
            review = c.get('claimReview', [{}])[0]
            results.append({
                'claim_reviewed': c.get('text', ''),
                'publisher':      review.get('publisher', {}).get('name', 'Unknown'),
                'title':          review.get('title', ''),
                'url':            review.get('url', ''),
                'rating':         review.get('textualRating', 'Unknown')
            })
        return True, results

    except Exception:
        return False, []


def analyze_with_gemini(claim, context=''):
    """
    Use Gemini Flash with Google Search grounding to fact-check a claim.
    Returns (score_adjustment: int, flags: list[str], summary: str, sources: list[str])

    score_adjustment is positive (credible) or negative (questionable).
    Falls back gracefully if API key missing or quota exceeded.
    """
    if not GEMINI_API_KEY:
        return 0, [], '', []

    prompt = f"""You are a fact-checker. Analyze this claim and determine if it is likely true, false, or unverifiable.

CLAIM: {claim}
{f'CONTEXT: {context}' if context else ''}

Respond in this exact JSON format (no markdown, no backticks):
{{
  "verdict": "true" | "false" | "misleading" | "unverifiable",
  "confidence": 0-100,
  "reasoning": "1-2 sentence explanation",
  "red_flags": ["list", "of", "specific", "issues"] or [],
  "sources_to_check": ["suggested", "sources"] or []
}}"""

    GEMINI_MODELS = [
        'gemini-2.5-flash',
        'gemini-2.0-flash',
        'gemini-1.5-flash',
    ]

    try:
        resp = None
        for model in GEMINI_MODELS:
            resp = http_requests.post(
                f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
                headers={
                    'x-goog-api-key': GEMINI_API_KEY,
                    'Content-Type': 'application/json'
                },
                json={
                    'contents': [{'parts': [{'text': prompt}]}],
                    'tools': [{'google_search': {}}],
                    'generationConfig': {
                        'temperature':     0.1,
                        'maxOutputTokens': 500
                    }
                },
                timeout=30
            )
            if resp.status_code == 200:
                break
            elif resp.status_code == 503:
                continue  # Try next model
            else:
                return 0, [f'⚠️ AI fact-check unavailable (status {resp.status_code}): {resp.text[:100]}'], '', []

        if not resp or resp.status_code != 200:
            return 0, ['⚠️ AI fact-check temporarily unavailable — all models overloaded. Try again shortly.'], '', []

        data = resp.json()
        text = ''

        # Gemini with search grounding may return content in different structures
        candidates = data.get('candidates', [])
        if not candidates:
            return 0, ['⚠️ AI fact-check returned no candidates'], '', []

        candidate = candidates[0]
        content   = candidate.get('content', {})
        parts     = content.get('parts', [])

        for part in parts:
            if 'text' in part:
                text += part['text']

        if not text:
            # Try alternate structure
            if 'text' in candidate:
                text = candidate['text']

        if not text:
            return 0, ['ℹ️ AI analysis completed — no text response received'], '', []

        # Clean and parse JSON response
        text = text.strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        text = text.strip()

        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            return 0, ['ℹ️ AI analysis completed but response was unclear'], '', []

        verdict    = result.get('verdict', 'unverifiable')
        confidence = int(result.get('confidence', 50))
        reasoning  = result.get('reasoning', '')
        red_flags  = result.get('red_flags', [])
        sources    = result.get('sources_to_check', [])

        flags = []
        score_adjustment = 0

        if verdict == 'true':
            score_adjustment = max(10, int(confidence * 0.3))
            flags.append(f'✅ AI fact-check: Likely true (confidence: {confidence}%)')
        elif verdict == 'false':
            score_adjustment = -max(20, int(confidence * 0.5))
            flags.append(f'❌ AI fact-check: Likely false (confidence: {confidence}%)')
        elif verdict == 'misleading':
            score_adjustment = -15
            flags.append(f'⚠️ AI fact-check: Misleading or missing context (confidence: {confidence}%)')
        else:
            flags.append(f'ℹ️ AI fact-check: Could not verify this claim (confidence: {confidence}%)')

        if reasoning:
            flags.append(f'💭 {reasoning}')

        for flag in red_flags[:3]:
            flags.append(f'🚩 {flag}')

        if sources:
            flags.append(f'🔍 Suggested sources: {", ".join(sources[:3])}')

        return score_adjustment, flags, reasoning, sources

    except Exception as e:
        return 0, [f'⚠️ AI fact-check error: {str(e)[:80]}'], '', []


# ===========================================================================
# 4. CONTENT ANALYSIS
# ===========================================================================

def fetch_page_text(url):
    """Fetch visible paragraph text from a URL (max 3000 chars)."""
    try:
        resp = http_requests.get(
            url,
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=10
        )
        soup = BeautifulSoup(resp.text, 'html.parser')
        text = ' '.join(p.get_text() for p in soup.find_all('p'))
        return text[:3000]
    except Exception:
        return None


def get_regional_sources(locale):
    """
    Return the primary trusted-source list for a given locale string.
    locale is a BCP-47 tag like 'en-IN', 'en-US', 'de-DE', 'fr-FR' etc.
    Falls back to global sources when no region match is found.
    """
    if not locale:
        return []

    loc = locale.lower().strip()

    # Extract region code (e.g. 'en-IN' → 'in', 'de-DE' → 'de')
    region = loc.split('-')[1] if '-' in loc else loc

    region_map = {
        'in': [  # India
            'ndtv.com', 'thehindu.com', 'hindustantimes.com',
            'indianexpress.com', 'timesofindia.com', 'livemint.com',
            'thewire.in', 'scroll.in', 'theprint.in',
            'businessstandard.com', 'economictimes.indiatimes.com',
            'aajtak.in', 'abplive.com', 'zeenews.india.com',
            'news18.com', 'republicworld.com', 'wionews.com',
            'pib.gov.in', 'india.gov.in', 'mygov.in',
            'isro.gov.in', 'rbi.org.in', 'boomlive.in', 'altnews.in',
        ],
        'us': [  # United States
            'nytimes.com', 'washingtonpost.com', 'wsj.com',
            'usatoday.com', 'newsweek.com', 'time.com',
            'theatlantic.com', 'npr.org', 'pbs.org',
            'abcnews.go.com', 'cbsnews.com', 'nbcnews.com',
            'foxnews.com', 'cnn.com', 'msnbc.com',
            'nasa.gov', 'nih.gov', 'cdc.gov', 'fda.gov',
            'whitehouse.gov', 'congress.gov', 'supremecourt.gov',
            'factcheck.org', 'politifact.com', 'snopes.com',
        ],
        'gb': [  # United Kingdom
            'bbc.co.uk', 'bbc.com', 'thetimes.co.uk', 'telegraph.co.uk',
            'independent.co.uk', 'mirror.co.uk', 'dailymail.co.uk',
            'theguardian.com', 'sky.com', 'itv.com',
            'gov.uk', 'parliament.uk', 'fullfact.org',
        ],
        'au': [  # Australia
            'abc.net.au', 'nzherald.co.nz', 'smh.com.au',
            'theaustralian.com.au', 'theguardian.com/au',
            'sbs.com.au', 'news.com.au',
        ],
        'de': [  # Germany
            'spiegel.de', 'zeit.de', 'sueddeutsche.de',
            'faz.net', 'tagesschau.de', 'dw.com',
            'bundesregierung.de',
        ],
        'fr': [  # France
            'lemonde.fr', 'lefigaro.fr', 'liberation.fr',
            'france24.com', 'rfi.fr', 'bfmtv.com',
            'gouvernement.fr',
        ],
        'jp': [  # Japan
            'japantimes.co.jp', 'nhk.or.jp', 'asahi.com',
            'mainichi.jp', 'yomiuri.co.jp',
        ],
        'kr': [  # South Korea
            'koreaherald.com', 'koreatimes.co.kr',
            'yonhapnewsagency.com',
        ],
        'sg': [  # Singapore
            'straitstimes.com', 'channelnewsasia.com',
            'todayonline.com', 'gov.sg',
        ],
        'za': [  # South Africa
            'dailymaverick.co.za', 'news24.com',
            'timeslive.co.za', 'businesslive.co.za',
        ],
        'ng': [  # Nigeria
            'premiumtimesng.com', 'thecable.ng',
            'punchng.com', 'vanguardngr.com',
        ],
        'pk': [  # Pakistan
            'dawn.com', 'geo.tv', 'thenews.com.pk',
            'arynews.tv',
        ],
        'ca': [  # Canada
            'cbc.ca', 'globeandmail.com', 'nationalpost.com',
            'thestar.com', 'macleans.ca',
        ],
        'ae': [  # UAE / Middle East
            'thenationalnews.com', 'khaleejtimes.com',
            'gulfnews.com', 'alarabiya.net',
        ],
    }

    return region_map.get(region, [])


def check_url_credibility(url, locale=None):
    """
    Score a URL against regional trusted-domain lists, known fake-news
    domains, social media platforms, and suspicious URL patterns.

    locale: BCP-47 string from the user's browser (e.g. 'en-IN', 'en-US').
    When provided, matching a regional source gives a +40 bonus instead of
    the default +30 — making local verification more meaningful.

    Returns (score: int, flags: list[str]).
    """

    # -- Trusted domains by region --
    global_credible = [
        # International wire services & broadcasters
        'reuters.com', 'apnews.com', 'bbc.com', 'bbc.co.uk', 'theguardian.com',
        'aljazeera.com', 'dw.com', 'france24.com', 'euronews.com',
        # Science & academic
        'nature.com', 'science.org', 'scientificamerican.com',
        'newscientist.com', 'arxiv.org', 'pubmed.ncbi.nlm.nih.gov',
        # International organisations
        'who.int', 'un.org', 'unesco.org', 'unicef.org',
        'worldbank.org', 'imf.org', 'nato.int',
        # Fact-checkers
        'snopes.com', 'factcheck.org', 'politifact.com',
        'fullfact.org', 'boomlive.in', 'altnews.in',
        'thelogicalindian.com', 'vishvasnews.com',
        # Major sports news
        'espn.com', 'espn.in', 'espncricinfo.com',
        'skysports.com', 'goal.com', 'bleacherreport.com',
        'theathletic.com', 'sportbible.com', 'marca.com',
        'as.com', 'gazzetta.it', 'lequipe.fr',
        'cricbuzz.com', 'icc-cricket.com', 'fifa.com',
        'uefa.com', 'olympics.com', 'nba.com', 'nfl.com',
        'formula1.com', 'wimbledon.com', 'bcci.tv',
        # Major general & business news
        'economist.com', 'bloomberg.com', 'ft.com',
        'cnbc.com', 'forbes.com', 'businessinsider.com',
        'vox.com', 'foreignpolicy.com', 'foreignaffairs.com',
        # LumiVeil own domains
        'himanshubhandari2196.github.io',
        'github.io', 'github.com',
        'railway.app',
    ]

    india_credible = [
        'ndtv.com', 'thehindu.com', 'hindustantimes.com',
        'indianexpress.com', 'timesofindia.com', 'livemint.com',
        'thewire.in', 'scroll.in', 'theprint.in',
        'businessstandard.com', 'economictimes.indiatimes.com',
        'aajtak.in', 'abplive.com', 'zeenews.india.com',
        'news18.com', 'republicworld.com', 'wionews.com',
        'pib.gov.in', 'india.gov.in', 'mygov.in',
        'isro.gov.in', 'rbi.org.in',
    ]
    usa_credible = [
        'nytimes.com', 'washingtonpost.com', 'wsj.com',
        'usatoday.com', 'newsweek.com', 'time.com',
        'theatlantic.com', 'npr.org', 'pbs.org',
        'abcnews.go.com', 'cbsnews.com', 'nbcnews.com',
        'foxnews.com', 'cnn.com', 'msnbc.com',
        'nasa.gov', 'nih.gov', 'cdc.gov', 'fda.gov',
        'whitehouse.gov', 'congress.gov', 'supremecourt.gov',
    ]
    uk_credible = [
        'bbc.co.uk', 'thetimes.co.uk', 'telegraph.co.uk',
        'independent.co.uk', 'mirror.co.uk', 'dailymail.co.uk',
        'sky.com', 'itv.com', 'gov.uk', 'parliament.uk',
    ]
    europe_credible = [
        'spiegel.de', 'lemonde.fr', 'lefigaro.fr', 'elpais.com',
        'corriere.it', 'nrc.nl', 'svt.se', 'yle.fi', 'rte.ie',
        'europa.eu', 'ecb.europa.eu',
    ]
    mea_credible = [
        'alarabiya.net', 'thenationalnews.com', 'timesofisrael.com',
        'haaretz.com', 'dailymaverick.co.za',
        'nation.africa', 'theafricareport.com',
    ]
    asia_credible = [
        'scmp.com', 'straitstimes.com', 'japantimes.co.jp',
        'koreaherald.com', 'abc.net.au', 'nzherald.co.nz',
        'channelnewsasia.com', 'bangkokpost.com',
    ]

    all_credible = (
        global_credible + india_credible + usa_credible +
        uk_credible + europe_credible + mea_credible + asia_credible
    )

    # Regional sources for this user's locale
    regional_sources = get_regional_sources(locale)

    # -- Social media: neutral note, slight penalty --
    social_media = [
        'twitter.com', 'x.com', 'facebook.com', 'instagram.com',
        'linkedin.com', 'reddit.com', 'youtube.com', 'tiktok.com',
        'telegram.org', 'whatsapp.com', 'pinterest.com', 'snapchat.com',
    ]

    # -- Known fake-news domains --
    known_fake = [
        'beforeitsnews.com', 'naturalnews.com', 'infowars.com',
        'worldnewsdailyreport.com', 'empirenews.net',
        'nationalreport.net', 'abcnews.com.co',
        'theonion.com', 'clickhole.com', 'waterfordwhispersnews.com',
        'dailybuzzlive.com', 'huzlers.com', 'thepinacoladepress.com',
    ]

    # -- Suspicious path/slug patterns --
    suspicious_patterns = [
        'breaking-news', 'viral', 'exclusive-leaked',
        'truth-revealed', 'they-dont-want-you',
        'shocking', 'what-media-wont-tell',
        'banned-video', 'censored', 'deep-state',
        'new-world-order', 'illuminati', 'false-flag',
        'mainstream-media-wont', 'suppressed-news',
        'wake-up-sheeple', 'crisis-actor',
    ]

    score    = 50
    flags    = []
    url_low  = url.lower()

    # Known fake domain — early return
    for domain in known_fake:
        if domain in url_low:
            score -= 40
            flags.append(f'❌ Known fake-news domain: {domain}')
            return max(0, score), flags

    # Social media — early return with honest "unverifiable" verdict
    # Social media content can be real or fake — we can't determine which.
    # Returning a fixed 45 score (mixed) with a clear explanation is more
    # honest than penalising it and potentially calling real content fake.
    for platform in social_media:
        if platform in url_low:
            flags.append(f'⚠️ Content from social media ({platform})')
            flags.append('ℹ️ Social media posts cannot be independently verified by LumiVeil')
            flags.append('💡 Cross-check with the original news source or official account')
            return 45, flags   # Fixed mixed score — honest about limitations

    # Regional source check — higher bonus than generic global match
    matched = False
    if regional_sources:
        for domain in regional_sources:
            if domain in url_low:
                score += 40
                flags.append(f'✅ Trusted regional source: {domain}')
                matched = True
                break

    # Fall back to global trusted list
    if not matched:
        for domain in all_credible:
            if domain in url_low:
                score += 30
                flags.append(f'✅ Trusted domain: {domain}')
                matched = True
                break

    if not matched:
        flags.append('⚠️ Domain not in our trusted list')
        score -= 10

    # Suspicious URL patterns
    for pattern in suspicious_patterns:
        if pattern in url_low:
            score -= 15
            flags.append(f'❌ Suspicious URL pattern: "{pattern}"')

    return max(0, min(100, score)), flags


def check_sensationalism(text):
    """
    Scan text for sensational / misinformation language patterns.
    Returns (count: int, flags: list[str]).

    Two passes:
      1. Exact-match against SENSATIONAL_PHRASES (instant, free, always runs)
      2. If pass 1 finds nothing, a semantic (paraphrase) check via
         embeddings — catches reworded versions of the same phrases.
         Only runs when needed, so most requests never pay the extra
         latency/cost of an embedding API call.
    """
    count    = 0
    flags    = []
    text_low = text.lower()

    for phrase in SENSATIONAL_PHRASES:
        if phrase in text_low:
            count += 1
            flags.append(f'❌ Sensational language: "{phrase}"')

    caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
    if caps_ratio > 0.3:
        count += 2
        flags.append('❌ Excessive capital letters')

    exclamations = text.count('!')
    if exclamations > 3:
        count += 1
        flags.append(f'❌ Excessive exclamation marks ({exclamations} found)')

    # Semantic fallback — only when the exact-match pass found nothing,
    # so the common case (obviously sensational content) never touches it.
    if count == 0 and len(text.strip()) > 40:
        try:
            semantic_matches = find_semantic_matches(text)
            for sentence, phrase, similarity in semantic_matches:
                count += 1
                flags.append(
                    f'⚠️ Sensational language (paraphrased): "{sentence[:80]}" '
                    f'— similar to "{phrase}"'
                )
        except Exception:
            # Embeddings API unavailable/failed — degrade gracefully to
            # exact-match-only results rather than breaking the analysis.
            pass

    return count, flags


def calculate_final_score(url_score, sensational_count, flags):
    """
    Combine URL score, sensationalism penalty, and flag-based bonuses/penalties
    into a final 0-100 trust score.
    """
    score = url_score

    # Sensationalism penalty (exponential)
    if sensational_count <= 2:
        score -= sensational_count * 5
    elif sensational_count <= 5:
        score -= sensational_count * 8
    else:
        score -= sensational_count * 12

    # Flag-based adjustments
    fact_checkers = [
        'snopes.com', 'factcheck.org', 'politifact.com',
        'boomlive.in', 'altnews.in', 'fullfact.org',
    ]
    for flag in flags:
        if 'Known fake-news domain'        in flag: score -= 50
        if 'Suspicious URL pattern'        in flag: score -= 10
        if 'Excessive capital letters'     in flag: score -= 8
        if 'Excessive exclamation marks'   in flag: score -= 8
        if 'social media'                  in flag: score -= 5
        if 'Trusted domain'                in flag: score += 10
        if any(fc in flag for fc in fact_checkers): score += 15
        if any(ext in flag for ext in ['.gov', '.edu', '.org']): score += 5

    return max(0, min(100, score))


def get_verdict(score):
    if score >= 70: return 'real'
    if score >= 40: return 'mixed'
    return 'fake'


# ===========================================================================
# 5. ROUTES
# ===========================================================================

@app.route('/api/v1/health', methods=['GET'])
def health():
    """Simple health-check endpoint — no auth required."""
    return jsonify({
        'status': 'ok',
        'provider': IMAGE_ANALYSIS_PROVIDER,
        'version': '1.0.0'
    })


@app.route('/ping', methods=['GET'])
def ping():
    """Ultra-lightweight keep-alive endpoint for Railway free tier."""
    return 'pong', 200


# ---------------------------------------------------------------------------
# AUTH ROUTES
# ---------------------------------------------------------------------------

@app.route('/api/v1/auth/signup', methods=['POST'])
@limiter.limit("5 per minute")
def signup():
    """
    Register a new user.
    Body: { "email": "...", "password": "..." }
    Returns: { "token": "...", "refresh_token": "...", "user": { id, email, tier } }

    "token" is a short-lived (1hr) access token, sent with every /analyze request.
    "refresh_token" is long-lived (60 days) — store it, and use it to silently
    get a new access token via /api/v1/auth/refresh when the old one expires.
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({'error': 'Request body must be JSON'}), 400

    email    = body.get('email', '').strip().lower()
    password = body.get('password', '')

    # Basic validation
    if not email or not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        return jsonify({'error': 'Valid email required'}), 400
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    user_id = create_user(email, hash_password(password))
    if user_id is None:
        return jsonify({'error': 'An account with this email already exists'}), 409

    # Send verification email (non-blocking — signup succeeds even if email fails)
    try:
        verification_token = create_email_verification_token(user_id)
        send_verification_email(email, verification_token)
    except Exception:
        pass  # Don't block signup if email fails

    tokens = issue_token_pair(user_id, email, 'free')
    return jsonify({
        'token':         tokens['access_token'],
        'refresh_token': tokens['refresh_token'],
        'user':          {'id': user_id, 'email': email, 'tier': 'free', 'email_verified': False}
    }), 201


@app.route('/api/v1/auth/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    """
    Login with email + password.
    Body: { "email": "...", "password": "..." }
    Returns: { "token": "...", "refresh_token": "...", "user": { id, email, tier } }
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({'error': 'Request body must be JSON'}), 400

    email    = body.get('email', '').strip().lower()
    password = body.get('password', '')

    user = get_user_by_email(email)
    if not user or not verify_password(password, user['password_hash']):
        return jsonify({'error': 'Invalid email or password'}), 401

    update_last_login(user['id'])

    tokens = issue_token_pair(user['id'], user['email'], user['tier'])
    return jsonify({
        'token':         tokens['access_token'],
        'refresh_token': tokens['refresh_token'],
        'user':          {'id': user['id'], 'email': user['email'], 'tier': user['tier']}
    })


@app.route('/api/v1/auth/refresh', methods=['POST'])
@limiter.limit("30 per minute")
def refresh():
    """
    Exchange a valid refresh token for a brand new access token.
    Body: { "refresh_token": "..." }
    Returns: { "token": "..." }

    The extension/website calls this automatically and silently whenever an
    access token has expired — the user is never shown a login screen unless
    the refresh token itself has expired (60 days) or been revoked.
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({'error': 'Request body must be JSON'}), 400

    refresh_token = body.get('refresh_token', '')
    if not refresh_token:
        return jsonify({'error': 'refresh_token is required'}), 400

    try:
        new_access_token = refresh_access_token(refresh_token)
        return jsonify({'token': new_access_token})
    except ValueError as e:
        return jsonify({'error': str(e)}), 401


@app.route('/api/v1/auth/verify-email', methods=['GET'])
def verify_email():
    """
    Called when user clicks the verification link in their email.
    Marks the account as verified and redirects to the website.
    """
    token = request.args.get('token', '')
    if not token:
        return '<h2>Invalid verification link.</h2>', 400

    user_id = verify_email_token(token)
    if not user_id:
        return '''
        <html><body style="font-family:sans-serif;text-align:center;padding:60px;background:#0C0C10;color:#fff;">
        <h2 style="color:#EF4444;">❌ Invalid or expired verification link.</h2>
        <p style="color:#9490A8;">This link may have expired (24 hours) or already been used.</p>
        <a href="https://himanshubhandari2196.github.io/LumiVeil" style="color:#7C6FF7;">Return to LumiVeil</a>
        </body></html>
        ''', 400

    return '''
    <html><body style="font-family:sans-serif;text-align:center;padding:60px;background:#0C0C10;color:#fff;">
    <h2 style="color:#22C55E;">✅ Email verified successfully!</h2>
    <p style="color:#9490A8;">Your LumiVeil account is now fully activated.</p>
    <p style="color:#9490A8;">You can close this tab and return to the extension.</p>
    <a href="https://himanshubhandari2196.github.io/LumiVeil" style="color:#7C6FF7;">Return to LumiVeil</a>
    </body></html>
    '''


@app.route('/api/v1/auth/forgot-password', methods=['POST'])
@limiter.limit("5 per minute")
def forgot_password():
    """
    Send a password reset email.
    Body: { "email": "..." }
    Always returns 200 to prevent email enumeration attacks.
    """
    body  = request.get_json(silent=True) or {}
    email = body.get('email', '').strip().lower()

    if email:
        user = get_user_by_email(email)
        if user:
            try:
                token = create_password_reset_token(user['id'])
                send_password_reset_email(email, token)
            except Exception:
                pass

    # Always return success — don't reveal whether email exists
    return jsonify({'message': 'If an account exists with this email, a reset link has been sent.'})


@app.route('/api/v1/auth/reset-password', methods=['POST'])
@limiter.limit("5 per minute")
def reset_password():
    """
    Reset a user's password using a valid reset token.
    Body: { "token": "...", "password": "..." }
    """
    body     = request.get_json(silent=True) or {}
    token    = body.get('token', '')
    password = body.get('password', '')

    if not token or not password:
        return jsonify({'error': 'Token and password are required'}), 400
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    success = consume_password_reset_token(token, hash_password(password))
    if not success:
        return jsonify({'error': 'Invalid or expired reset token'}), 400

    return jsonify({'message': 'Password reset successfully. You can now sign in.'})


@app.route('/api/v1/auth/resend-verification', methods=['POST'])
@limiter.limit("3 per minute")
def resend_verification():
    """
    Resend the verification email for the current user.
    Requires: Authorization: Bearer <token>
    """
    user = _get_current_user(request)
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    if user.get('email_verified'):
        return jsonify({'message': 'Email already verified'}), 200

    try:
        token = create_email_verification_token(user['id'])
        send_verification_email(user['email'], token)
        return jsonify({'message': 'Verification email sent'})
    except Exception as e:
        return jsonify({'error': 'Failed to send email'}), 500


@app.route('/api/v1/auth/logout', methods=['POST'])
def logout():
    """
    Revoke a refresh token so it can never be used again.
    Body: { "refresh_token": "..." }
    """
    body = request.get_json(silent=True) or {}
    refresh_token = body.get('refresh_token', '')
    if refresh_token:
        revoke_refresh_token_plaintext(refresh_token)
    return jsonify({'status': 'signed out'})


@app.route('/api/v1/auth/delete-account', methods=['POST'])
@limiter.limit("3 per minute")
def delete_account():
    """
    Permanently delete the current user's account and all associated data.
    Requires: Authorization: Bearer <token>
    Body: { "password": "..." } — password confirmation required
    """
    user = _get_current_user(request)
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    body     = request.get_json(silent=True) or {}
    password = body.get('password', '')

    if not password:
        return jsonify({'error': 'Password confirmation required'}), 400

    if not verify_password(password, user['password_hash']):
        return jsonify({'error': 'Incorrect password'}), 401

    try:
        from database import get_db
        conn    = get_db()
        cur     = conn.cursor()
        user_id = user['id']

        cur.execute("DELETE FROM refresh_tokens WHERE user_id = %s",      (user_id,))
        cur.execute("DELETE FROM email_verifications WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM password_resets WHERE user_id = %s",     (user_id,))
        cur.execute("DELETE FROM usage WHERE user_id = %s",               (user_id,))
        cur.execute("DELETE FROM payments WHERE user_id = %s",            (user_id,))
        cur.execute("DELETE FROM users WHERE id = %s",                    (user_id,))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({'message': 'Account deleted successfully'})
    except Exception as e:
        return jsonify({'error': f'Failed to delete account: {str(e)[:80]}'}), 500


@app.route('/api/v1/user/status', methods=['GET'])
def user_status():
    """
    Return the current user's tier and today's usage.
    Requires: Authorization: Bearer <token>
    """
    user = _get_current_user(request)
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    count, last_used = get_usage_today(user['id'])
    limits = TIER_LIMITS.get(user['tier'], TIER_LIMITS['free'])

    return jsonify({
        'user': {
            'id':    user['id'],
            'email': user['email'],
            'tier':  user['tier'],
        },
        'usage': {
            'today':     count,
            'limit':     limits['daily_limit'],
            'remaining': max(0, limits['daily_limit'] - count),
            'last_used': last_used,
        },
        'features': {
            'image_analysis': limits['image_analysis'],
            'api_access':     limits['api_access'],
            'history_limit':  limits['history_limit'],
        }
    })


# ---------------------------------------------------------------------------
# MAIN ANALYZE ROUTE
# ---------------------------------------------------------------------------

@app.route('/api/v1/analyze', methods=['POST'])
@limiter.limit("10 per minute")
def analyze():
    """
    Main analysis endpoint.

    Headers:
        X-API-Key:     <LUMIVEIL_API_KEY>          (required — extension auth)
        Authorization: Bearer <jwt>                 (optional — identifies user tier)

    Body: { "input": "<url | image-url | plain text claim>" }

    If no valid JWT is supplied, the request is treated as a guest — tracked
    by hashed IP with the same daily cap as the free tier, image analysis
    still blocked.
    """

    # -- Extension auth --
    if not _validate_api_key(request):
        return jsonify({'error': 'Unauthorized — invalid or missing API key'}), 401

    # -- Identify user (optional) --
    user = _get_current_user(request)
    tier = user['tier'] if user else 'free'

    # -- Usage check --
    guest_ip_hash = None
    if user:
        allowed, reason, remaining = check_usage_allowed(user['id'], tier)
        if not allowed:
            return jsonify({
                'error':     'Usage limit reached',
                'reason':    reason,
                'tier':      tier,
                'upgrade':   'Visit lumiveil.github.io/#pricing to upgrade'
            }), 429
    else:
        # Guest request — no account, so track usage by hashed client IP
        # instead. This is the persistent (DB-backed) cap that replaces the
        # old behaviour where anonymous requests were never tracked at all.
        guest_ip_hash = hashlib.sha256(get_remote_address().encode()).hexdigest()
        allowed, reason, remaining = check_guest_usage_allowed(guest_ip_hash)
        if not allowed:
            return jsonify({
                'error':   'Usage limit reached',
                'reason':  reason,
                'tier':    'guest',
                'upgrade': 'Sign up free at lumiveil.github.io to keep your own tracked limit, or upgrade to Pro.'
            }), 429

    # -- Parse body --
    body = request.get_json(silent=True)
    if not body:
        return jsonify({'error': 'Request body must be JSON'}), 400

    user_input = body.get('input', '')
    locale     = body.get('locale', '')   # BCP-47 locale from browser e.g. 'en-IN'
    valid, errors = _validate_input(user_input)
    if not valid:
        return jsonify({'error': 'Invalid input', 'details': errors}), 400

    # Sanitise locale — only allow safe characters
    import re as _re
    locale = _re.sub(r'[^a-zA-Z\-]', '', locale)[:10] if locale else ''

    # -- Classify input type --
    image_exts = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')
    is_url     = user_input.startswith(('http://', 'https://'))
    is_image   = is_url and user_input.lower().endswith(image_exts)

    all_flags     = []
    url_score     = 50
    image_penalty = 0
    sensational_count = 0
    real_info_parts = []   # actual verified facts found during analysis, if any
    real_sources     = []  # actual source URLs found during analysis, if any

    if is_image:
        # Image analysis — Pro/Max only
        limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
        if not limits['image_analysis']:
            return jsonify({
                'error':   'Image analysis is a Pro feature',
                'reason':  'Upgrade to Pro to analyse images and detect deepfakes.',
                'tier':    tier,
                'upgrade': 'Visit lumiveil.github.io/#pricing to upgrade'
            }), 403

        all_flags.append('🔍 Image detected — running AI and metadata analysis...')

        ai_penalty, ai_flags = analyze_image(user_input)
        all_flags.extend(ai_flags)
        if ai_penalty:
            image_penalty += ai_penalty

        meta_penalty, meta_flags = analyze_image_metadata(user_input)
        all_flags.extend(meta_flags)
        image_penalty += meta_penalty

        url_score = max(0, 70 - image_penalty)

    elif is_url:
        url_score, url_flags = check_url_credibility(user_input, locale=locale)
        all_flags.extend(url_flags)

        page_text = fetch_page_text(user_input)
        if page_text:
            sensational_count, sens_flags = check_sensationalism(page_text)
            all_flags.extend(sens_flags)

            # For social media URLs, also run Gemini fact-check on the page text
            social_domains = ['twitter.com', 'x.com', 'facebook.com', 'instagram.com',
                            'reddit.com', 'tiktok.com', 'linkedin.com', 'telegram.org']
            is_social = any(d in user_input.lower() for d in social_domains)
            if is_social and page_text:
                all_flags.append('🔍 Running AI fact-check on social media content...')
                # Google Fact Check first
                found, fc_results = check_with_google_factcheck(page_text[:300])
                if found:
                    for r in fc_results[:2]:
                        rating = r.get('rating', 'Unknown')
                        publisher = r.get('publisher', 'Unknown')
                        title = r.get('title', '')
                        url_field = r.get('url', '')
                        all_flags.append(f'📋 Fact-checked by {publisher}: "{rating}"')
                        real_info_parts.append(
                            f'{publisher} rated this "{rating}"' + (f' — {title}' if title else '')
                        )
                        if url_field:
                            real_sources.append(url_field)
                        if any(w in rating.lower() for w in ['false', 'fake', 'incorrect', 'misleading']):
                            url_score -= 25
                        elif any(w in rating.lower() for w in ['true', 'correct', 'accurate']):
                            url_score += 15
                else:
                    # Fall back to Gemini
                    score_adj, gemini_flags, gemini_reasoning, gemini_sources = analyze_with_gemini(page_text[:500])
                    url_score = max(0, min(100, url_score + score_adj))
                    all_flags.extend(gemini_flags)
                    if gemini_reasoning:
                        real_info_parts.append(gemini_reasoning)
                    real_sources.extend(gemini_sources)
        else:
            all_flags.append('⚠️ Could not fetch page content for text analysis')

    else:
        # Plain text or social media post pasted directly
        sensational_count, sens_flags = check_sensationalism(user_input)
        all_flags.extend(sens_flags)

        # Run Google Fact Check first
        all_flags.append('🔍 Searching fact-checker database...')
        found, fc_results = check_with_google_factcheck(user_input)

        if found:
            all_flags.append(f'📋 Found {len(fc_results)} existing fact-check(s):')
            for r in fc_results[:3]:
                rating    = r.get('rating', 'Unknown')
                publisher = r.get('publisher', 'Unknown')
                title     = r.get('title', '')
                url_field = r.get('url', '')
                all_flags.append(f'  • {publisher}: "{rating}"')
                if title:
                    all_flags.append(f'    "{title[:80]}"')
                real_info_parts.append(
                    f'{publisher} rated this "{rating}"' + (f' — {title}' if title else '')
                )
                if url_field:
                    real_sources.append(url_field)
                # Adjust score based on rating
                rating_low = rating.lower()
                if any(w in rating_low for w in ['false', 'fake', 'incorrect', 'misleading', 'pants on fire']):
                    url_score -= 30
                elif any(w in rating_low for w in ['true', 'correct', 'accurate', 'verified']):
                    url_score += 20
                elif any(w in rating_low for w in ['mixed', 'partly', 'partially', 'missing context']):
                    url_score -= 10
        else:
            all_flags.append('ℹ️ No existing fact-checks found — running AI analysis...')
            # Run Gemini with Google Search grounding
            score_adj, gemini_flags, gemini_reasoning, gemini_sources = analyze_with_gemini(user_input)
            url_score = max(0, min(100, 50 + score_adj))
            all_flags.extend(gemini_flags)
            if gemini_reasoning:
                real_info_parts.append(gemini_reasoning)
            real_sources.extend(gemini_sources)

    # -- Score + verdict --
    final_score = calculate_final_score(url_score, sensational_count, all_flags)
    verdict     = get_verdict(final_score)

    if verdict == 'fake':
        summary = f'⚠️ This content shows {len(all_flags)} red flags and scores low on our trust meter. Treat with caution.'
    elif verdict == 'real':
        summary = f'✅ This content appears credible with a trust score of {final_score}/100.'
    else:
        summary = '⚠️ This content has mixed signals. Verify with trusted sources before sharing.'

    # -- Track usage (logged-in users get a DB row; guests get an IP-hash row) --
    if user:
        increment_usage(user['id'])
        remaining_after = max(0, TIER_LIMITS[tier]['daily_limit'] - (get_usage_today(user['id'])[0]))
    elif guest_ip_hash:
        increment_guest_usage(guest_ip_hash)
        remaining_after = max(0, remaining - 1)
    else:
        remaining_after = None

    # -- "What is real" — built from actual findings above. Falls back to
    # a generic pointer only when no fact-check data was found at all,
    # instead of always showing the same message regardless of results. --
    if real_info_parts:
        real_info = ' | '.join(real_info_parts[:3])
    else:
        real_info = ('No existing fact-checks found for this claim. Always cross-check with '
                     'Reuters, BBC, AP News, or The Hindu for verified information.')

    if real_sources:
        seen = set()
        sources = []
        for s in real_sources:
            if s not in seen:
                seen.add(s)
                sources.append(s)
        sources = sources[:5]
    else:
        sources = ['reuters.com', 'bbc.com', 'apnews.com', 'thehindu.com', 'ndtv.com']

    response = {
        'verdict':     verdict,
        'trust_score': final_score,
        'summary':     summary,
        'checks':      all_flags or ['✅ No red flags detected'],
        'real_info':   real_info,
        'sources':     sources,
        'tier':        tier,
    }
    if remaining_after is not None:
        response['remaining_today'] = remaining_after

    return jsonify(response)


# Backward-compatibility alias
@app.route('/analyze', methods=['POST'])
@limiter.limit("10 per minute")
def analyze_legacy():
    return analyze()


# ===========================================================================
# 6. ENTRY POINT
# ===========================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
