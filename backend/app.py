from flask import Flask, request, jsonify, abort
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import requests
from bs4 import BeautifulSoup
import re
import secrets
import hashlib
import base64
import io
from PIL import Image
import json
import os
from dotenv import load_dotenv

# ---- LOAD ENVIRONMENT VARIABLES ----
# Reads secrets from a local .env file (never committed to Git)
load_dotenv()

app = Flask(__name__)

# ---- CORS SETUP ----
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "allow_headers": ["Content-Type", "X-API-Key"],
        "methods": ["GET", "POST", "OPTIONS"]
    }
})

# ---- RATE LIMITER SETUP ----
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per day", "30 per minute"],
    storage_uri="memory://",
    strategy="fixed-window"
)

# ---- API KEY ----
# Loaded from environment variables — see .env.example for setup
API_KEY = os.environ.get('LUMIVEIL_API_KEY', 'change-this-in-your-env-file')
API_KEY_HASH = hashlib.sha256(API_KEY.encode()).hexdigest()

# ---- HIVE API KEY ----
HIVE_API_KEY = os.environ.get('HIVE_API_KEY', '')

# ---- SECURITY HELPERS ----

def validate_api_key(request):
    """Check if request has valid API key"""
    key = request.headers.get('X-API-Key')
    if not key:
        return False
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    return secrets.compare_digest(key_hash, API_KEY_HASH)

def validate_input(user_input):
    """Validate and sanitize user input"""
    errors = []

    # Check if empty
    if not user_input or user_input.strip() == '':
        errors.append('Input cannot be empty')
        return False, errors

    # Check length — max 5000 characters
    if len(user_input) > 5000:
        errors.append('Input too long — maximum 5000 characters')
        return False, errors

    # Check for suspicious code injection patterns
    suspicious_patterns = [
        '<script', 'javascript:', 'eval(',
        'exec(', 'import os', 'subprocess',
        '__import__', 'DROP TABLE', 'SELECT *',
        'INSERT INTO', 'DELETE FROM'
    ]

    input_lower = user_input.lower()
    for pattern in suspicious_patterns:
        if pattern.lower() in input_lower:
            errors.append(f'Suspicious content detected in input')
            return False, errors

    return True, []

@app.after_request
def add_security_headers(response):
    """Add security headers to every response"""
    response.headers['Access-Control-Allow-Private-Network'] = 'true'
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

# ---- HELPER FUNCTIONS ----

def fetch_page_text(url):
    """Fetch and extract text from a URL"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        paragraphs = soup.find_all('p')
        text = ' '.join([p.get_text() for p in paragraphs])
        return text[:3000]
    except:
        return None
    

def analyze_image_with_hive(image_url):
    """Send image to Hive API for AI/deepfake detection"""
    try:
        # Download the image first
        # Download the image first — mimic a real browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': image_url,
            'Connection': 'keep-alive'
        }
        image_response = requests.get(image_url, headers=headers, timeout=15)
        if image_response.status_code != 200:
            return None, ['⚠️ Could not download image for analysis']

        # Convert to base64
        image_data = base64.b64encode(image_response.content).decode('utf-8')

        # Send to Hive API
        hive_response = requests.post(
            'https://api.thehive.ai/api/v2/task/sync',
            headers={
                'Authorization': f'Token {HIVE_API_KEY}',
                'Content-Type': 'application/json'
            },
            json={
                'image': image_data
            },
            timeout=30
        )

        if hive_response.status_code != 200:
            return None, ['⚠️ Hive API returned an error']

        data = hive_response.json()
        flags = []
        score_penalty = 0

        # Parse Hive response
        if 'status' in data and len(data['status']) > 0:
            classes = data['status'][0].get('response', {}).get('output', [{}])[0].get('classes', [])

            for cls in classes:
                name = cls.get('class', '')
                score = cls.get('score', 0)

                # AI generated image detection
                if name == 'ai_generated' and score > 0.7:
                    flags.append(f'❌ Image appears to be AI generated (confidence: {int(score*100)}%)')
                    score_penalty += 40

                elif name == 'ai_generated' and score > 0.4:
                    flags.append(f'⚠️ Image may be AI generated (confidence: {int(score*100)}%)')
                    score_penalty += 20

                # Deepfake detection
                if name == 'deepfake' and score > 0.7:
                    flags.append(f'❌ Deepfake detected (confidence: {int(score*100)}%)')
                    score_penalty += 50

                elif name == 'deepfake' and score > 0.4:
                    flags.append(f'⚠️ Possible deepfake detected (confidence: {int(score*100)}%)')
                    score_penalty += 25

        if not flags:
            flags.append('✅ No AI generation or deepfake detected by Hive')

        return score_penalty, flags

    except Exception as e:
        return None, [f'⚠️ Image analysis error: {str(e)}']


def analyze_image_metadata(image_url):
    """Analyze image metadata for suspicious patterns"""
    try:
        # Download image — mimic a real browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': image_url,
            'Connection': 'keep-alive'
        }
        image_response = requests.get(image_url, headers=headers, timeout=15)
        if image_response.status_code != 200:
            return 0, ['⚠️ Could not download image for metadata analysis']

        # Open with Pillow
        img = Image.open(io.BytesIO(image_response.content))
        flags = []
        score_penalty = 0

        # Check for EXIF data
        exif_data = img._getexif() if hasattr(img, '_getexif') else None

        if exif_data is None:
            flags.append('⚠️ No metadata found — image may have been edited or screenshot')
            score_penalty += 10
        else:
            # Check for software tag — indicates editing
            software = exif_data.get(305, '')
            if software:
                suspicious_software = [
                    'photoshop', 'gimp', 'lightroom',
                    'stable diffusion', 'midjourney',
                    'dall-e', 'firefly', 'canva'
                ]
                for sw in suspicious_software:
                    if sw.lower() in software.lower():
                        flags.append(f'❌ Image was edited with: {software}')
                        score_penalty += 20
                        break
                else:
                    flags.append(f'✅ Image software: {software}')

            # Check GPS data — real news photos often have location
            gps_info = exif_data.get(34853, None)
            if gps_info:
                flags.append('✅ GPS metadata present — location data exists')
            else:
                flags.append('⚠️ No GPS data found in image')

            # Check date taken
            date_taken = exif_data.get(36867, None)
            if date_taken:
                flags.append(f'✅ Photo taken: {date_taken}')
            else:
                flags.append('⚠️ No date taken found in metadata')

        # Check image format
        img_format = img.format
        img_mode = img.mode
        flags.append(f'✅ Image format: {img_format}, Mode: {img_mode}')

        return score_penalty, flags

    except Exception as e:
        return 0, [f'⚠️ Metadata analysis error: {str(e)}']

def check_url_credibility(url):
    """Check if the URL is from a known credible source"""


    # ---- GLOBAL SOURCES ---- always checked regardless of location
    global_credible = [
        # International News
        'reuters.com', 'apnews.com', 'bbc.com',
        'theguardian.com', 'aljazeera.com',
        'dw.com', 'france24.com', 'euronews.com',
        # Science and Research
        'nature.com', 'science.org', 'scientificamerican.com',
        'newscientist.com', 'arxiv.org', 'pubmed.ncbi.nlm.nih.gov',
        # International Organizations
        'who.int', 'un.org', 'unesco.org', 'unicef.org',
        'worldbank.org', 'imf.org', 'nato.int',
        # Fact Checking
        'snopes.com', 'factcheck.org', 'politifact.com',
        'fullfact.org', 'boomlive.in', 'altnews.in',
        'thelogicalindian.com', 'vishvasnews.com'
    ]

    # ---- INDIA SOURCES ----
    india_credible = [
        # Major News
        'ndtv.com', 'thehindu.com', 'hindustantimes.com',
        'indianexpress.com', 'timesofindia.com', 'livemint.com',
        'thewire.in', 'scroll.in', 'theprint.in',
        'businessstandard.com', 'economictimes.indiatimes.com',
        # TV Channels
        'aajtak.in', 'abplive.com', 'zeenews.india.com',
        'news18.com', 'republicworld.com', 'wionews.com',
        # Government
        'pib.gov.in', 'india.gov.in', 'mygov.in',
        'isro.gov.in', 'rbi.org.in'
    ]

    # ---- USA SOURCES ----
    usa_credible = [
        # Major News
        'nytimes.com', 'washingtonpost.com', 'wsj.com',
        'usatoday.com', 'newsweek.com', 'time.com',
        'theatlantic.com', 'npr.org', 'pbs.org',
        'abcnews.go.com', 'cbsnews.com', 'nbcnews.com',
        'foxnews.com', 'cnn.com', 'msnbc.com',
        # Government
        'nasa.gov', 'nih.gov', 'cdc.gov', 'fda.gov',
        'whitehouse.gov', 'congress.gov', 'supremecourt.gov'
    ]

    # ---- UK SOURCES ----
    uk_credible = [
        'bbc.co.uk', 'theguardian.com', 'thetimes.co.uk',
        'telegraph.co.uk', 'independent.co.uk', 'mirror.co.uk',
        'dailymail.co.uk', 'sky.com', 'itv.com',
        'gov.uk', 'parliament.uk'
    ]

    # ---- EUROPE SOURCES ----
    europe_credible = [
        'spiegel.de', 'lemonde.fr', 'lefigaro.fr',
        'elpais.com', 'corriere.it', 'nrc.nl',
        'svt.se', 'yle.fi', 'rte.ie',
        'europa.eu', 'ecb.europa.eu'
    ]

    # ---- MIDDLE EAST AND AFRICA SOURCES ----
    mea_credible = [
        'aljazeera.com', 'alarabiya.net', 'thenationalnews.com',
        'timesofisrael.com', 'haaretz.com', 'dailymaverick.co.za',
        'nation.africa', 'theafricareport.com'
    ]

    # ---- ASIA PACIFIC SOURCES ----
    asia_credible = [
        'scmp.com', 'straitstimes.com', 'japantimes.co.jp',
        'koreaherald.com', 'abc.net.au', 'nzherald.co.nz',
        'channelnewsasia.com', 'bangkokpost.com'
    ]

    # ---- SOCIAL MEDIA PLATFORMS ----
    # We don't trust or distrust these — we just note them
    social_media = [
        'twitter.com', 'x.com', 'facebook.com',
        'instagram.com', 'linkedin.com', 'reddit.com',
        'youtube.com', 'tiktok.com', 'telegram.org',
        'whatsapp.com', 'pinterest.com', 'snapchat.com'
    ]

    # ---- KNOWN FAKE NEWS DOMAINS ----
    known_fake = [
        'beforeitsnews.com', 'naturalnews.com', 'infowars.com',
        'worldnewsdailyreport.com', 'empirenews.net',
        'nationalreport.net', 'abcnews.com.co',
        'theonion.com', 'clickhole.com', 'waterfordwhispersnews.com',
        'dailybuzzlive.com', 'huzlers.com', 'thepinacoladepress.com'
    ]

    # ---- SUSPICIOUS URL PATTERNS ----
    suspicious_patterns = [
        'breaking-news', 'viral', 'exclusive-leaked',
        'truth-revealed', 'they-dont-want-you',
        'shocking', 'what-media-wont-tell',
        'banned-video', 'censored', 'deep-state',
        'new-world-order', 'illuminati', 'false-flag',
        'mainstream-media-wont', 'suppressed-news',
        'wake-up-sheeple', 'crisis-actor'
    ]

    # ---- COMBINE ALL CREDIBLE SOURCES ----
    all_credible = (
        global_credible + india_credible + usa_credible +
        uk_credible + europe_credible + mea_credible + asia_credible
    )

    score = 50
    flags = []
    url_lower = url.lower()

    # Check known fake domains first
    for domain in known_fake:
        if domain in url_lower:
            score -= 40
            flags.append(f'❌ Known fake news domain detected: {domain}')
            return max(0, score), flags

    # Check social media
    for platform in social_media:
        if platform in url_lower:
            flags.append(f'⚠️ Content is from social media: {platform} — verify with news sources')
            score -= 5
            break

    # Check credible domains
    matched = False
    for domain in all_credible:
        if domain in url_lower:
            score += 30
            flags.append(f'✅ Source is from trusted domain: {domain}')
            matched = True
            break

    if not matched:
        flags.append('⚠️ Source domain is not in our trusted list')
        score -= 10

    # Check suspicious URL patterns
    for pattern in suspicious_patterns:
        if pattern in url_lower:
            score -= 15
            flags.append(f'❌ Suspicious URL pattern detected: {pattern}')

    return max(0, min(100, score)), flags

def check_sensationalism(text):
    """Check if the text uses sensational language"""
    sensational_words = [
        # Urgency and Fear
        'shocking', 'terrifying', 'horrifying', 'disturbing',
        'alarming', 'devastating', 'catastrophic', 'emergency',
        'crisis', 'panic', 'chaos', 'mayhem', 'disaster',

        # Conspiracy Language
        'they dont want you to know', 'secret revealed',
        'what mainstream media wont tell', 'suppressed',
        'censored', 'banned', 'deep state', 'new world order',
        'illuminati', 'false flag', 'crisis actor', 'wake up',
        'sheeple', 'shadow government', 'they are hiding',
        'cover up', 'coverup', 'truth they hide',

        # Clickbait Language
        'explosive', 'bombshell', 'leaked', 'exclusive',
        'breaking', 'viral', 'exposed', 'miracle',
        'hoax', 'conspiracy', 'you wont believe',
        'mind blowing', 'mind-blowing', 'jaw dropping',
        'jaw-dropping', 'game changer', 'game-changer',
        'this changes everything', 'nothing will be the same',
        'share before deleted', 'share before they delete',
        'watch before removed', 'watch before banned',

        # Medical Misinformation
        'miracle cure', 'doctors dont want you',
        'big pharma hiding', 'natural cure banned',
        'cancer cure suppressed', 'doctors exposed',
        'vaccine kills', 'poison in', 'toxins in',
        'detox miracle', 'cure for everything',
        'big pharma doesnt want', 'medical establishment hiding',

        # Political Manipulation
        'election stolen', 'voter fraud proof',
        'rigged election', 'deep state plot',
        'globalist agenda', 'socialist takeover',
        'communist infiltration', 'radical left',
        'extreme right', 'they are replacing',
        'great replacement', 'population control',

        # Financial Misinformation  
        'get rich quick', 'make money fast',
        'guaranteed returns', 'risk free investment',
        'bitcoin millionaire', 'secret investment',
        'banks dont want you', 'financial secret',
        'retire in 30 days', 'unlimited income',

        # Religious and Cultural Manipulation
        'end times', 'apocalypse now', 'prophecy fulfilled',
        'sign of the end', 'biblical prophecy',
        'god told me', 'divine revelation exclusive',

        # Fake Credibility Signals
        'scientists baffled', 'doctors stunned',
        'experts shocked', 'government admits',
        'finally admitted', 'officially confirmed',
        'leaked documents prove', 'insider reveals',
        'whistleblower exposes', 'anonymous source confirms',

        # Emotional Manipulation
        'will make you cry', 'will restore your faith',
        'will make you sick', 'will make you angry',
        'will shock you', 'prepare to be amazed',
        'you need to see this', 'everyone is talking about',
        'the truth is out', 'finally the truth'
    ]

    score = 0
    flags = []
    text_lower = text.lower()

    for word in sensational_words:
        if word in text_lower:
            score += 1
            flags.append(f'❌ Sensational language detected: "{word}"')

    # Count excessive caps
    caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
    if caps_ratio > 0.3:
        score += 2
        flags.append('❌ Excessive capital letters detected')

    # Count exclamation marks
    exclamations = text.count('!')
    if exclamations > 3:
        score += 1
        flags.append(f'❌ Excessive exclamation marks: {exclamations} found')

    return score, flags

def fact_check_with_google(query):
    """Search Google Fact Check API"""
    try:
        api_url = f'https://factchecktools.googleapis.com/v1alpha1/claims:search?query={query}&key=YOUR_API_KEY'
        response = requests.get(api_url, timeout=10)
        data = response.json()
        if 'claims' in data and len(data['claims']) > 0:
            claim = data['claims'][0]
            return f"Fact check found: {claim.get('text', 'No details')}"
        return None
    except:
        return None

def calculate_final_score(url_score, sensational_count, flags):
    """Calculate the final trust score with weighted factors"""

    score = url_score

    # ---- SENSATIONALISM PENALTY ----
    # More sensational words = exponentially worse
    if sensational_count == 0:
        pass  # No penalty
    elif sensational_count <= 2:
        score -= (sensational_count * 5)  # Mild penalty
    elif sensational_count <= 5:
        score -= (sensational_count * 8)  # Moderate penalty
    else:
        score -= (sensational_count * 12)  # Heavy penalty

    # ---- FLAG BASED PENALTIES ----
    for flag in flags:
        # Known fake domain is an instant heavy penalty
        if 'Known fake news domain' in flag:
            score -= 50

        # Suspicious URL patterns
        if 'Suspicious URL pattern' in flag:
            score -= 10

        # Excessive caps
        if 'Excessive capital letters' in flag:
            score -= 8

        # Excessive exclamation marks
        if 'Excessive exclamation marks' in flag:
            score -= 8

        # Social media source
        if 'social media' in flag:
            score -= 5

    # ---- POSITIVE SIGNALS ----
    for flag in flags:
        # Trusted domain is a strong positive signal
        if 'trusted domain' in flag:
            score += 10

        # Fact checking sites get extra boost
        fact_checkers = [
            'snopes.com', 'factcheck.org', 'politifact.com',
            'boomlive.in', 'altnews.in', 'fullfact.org'
        ]
        for fc in fact_checkers:
            if fc in flag:
                score += 15

        # Government and scientific sources get extra boost
        trusted_extensions = ['.gov', '.edu', '.org']
        for ext in trusted_extensions:
            if ext in flag:
                score += 5

    # ---- KEEP WITHIN 0-100 ----
    score = max(0, min(100, score))
    return score

def get_verdict(score):
    """Get verdict based on score"""
    if score >= 70:
        return 'real'
    elif score >= 40:
        return 'mixed'
    else:
        return 'fake'

# ---- MAIN ROUTE ----

@app.route('/analyze', methods=['POST'])
@limiter.limit("10 per minute")
def analyze():

    # ---- VALIDATE API KEY ----
    if not validate_api_key(request):
        return jsonify({
            'error': 'Unauthorized — Invalid or missing API key'
        }), 401

    # ---- VALIDATE INPUT ----
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    user_input = data.get('input', '')
    is_valid, errors = validate_input(user_input)

    if not is_valid:
        return jsonify({
            'error': 'Invalid input',
            'details': errors
        }), 400

    all_flags = []
    url_score = 50
    image_penalty = 0

    # Check if input is an image URL
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
    is_image = any(user_input.lower().endswith(ext) for ext in image_extensions)

    # Check if input is a URL
    is_url = user_input.startswith('http://') or user_input.startswith('https://')

    if is_image and is_url:
        # ---- IMAGE ANALYSIS ----
        all_flags.append('🔍 Image detected — running AI and metadata analysis...')

        # Hive AI detection
        hive_penalty, hive_flags = analyze_image_with_hive(user_input)
        all_flags.extend(hive_flags)
        if hive_penalty:
            image_penalty += hive_penalty

        # Metadata analysis
        meta_penalty, meta_flags = analyze_image_metadata(user_input)
        all_flags.extend(meta_flags)
        image_penalty += meta_penalty

        # Adjust URL score for images
        url_score = max(0, 70 - image_penalty)
        sensational_count = 0

    elif is_url:
        # ---- URL ANALYSIS ----
        url_score, url_flags = check_url_credibility(user_input)
        all_flags.extend(url_flags)

        # Fetch page content
        page_text = fetch_page_text(user_input)
        if page_text:
            sensational_count, sensational_flags = check_sensationalism(page_text)
            all_flags.extend(sensational_flags)
        else:
            sensational_count = 0
            all_flags.append('⚠️ Could not fetch page content')
    else:
        # ---- TEXT ANALYSIS ----
        sensational_count, sensational_flags = check_sensationalism(user_input)
        all_flags.extend(sensational_flags)

    # Calculate final score
    final_score = calculate_final_score(url_score, sensational_count, all_flags)
    verdict = get_verdict(final_score)

    # Build summary
    if verdict == 'fake':
        summary = f'⚠️ This content shows {len(all_flags)} red flags and scores low on our trust meter. Treat with caution.'
    elif verdict == 'real':
        summary = f'✅ This content appears credible with a trust score of {final_score}/100.'
    else:
        summary = f'⚠️ This content has mixed signals. Verify with trusted sources before sharing.'

    # Build response
    return jsonify({
        'verdict': verdict,
        'trust_score': final_score,
        'summary': summary,
        'checks': all_flags if all_flags else ['✅ No red flags detected'],
        'real_info': 'Always cross-check with Reuters, BBC, AP News, or The Hindu for verified information.',
        'sources': [
            'reuters.com',
            'bbc.com',
            'apnews.com',
            'thehindu.com',
            'ndtv.com'
        ]
    })

# ---- RUN SERVER ----
if __name__ == '__main__':
    app.run(debug=False, port=5000)