# LumiVeil — Lift the Veil on Fake Content

LumiVeil is an open source Chrome extension that automatically detects fake news, AI-generated images, deepfakes, and misinformation in real time as you browse.

🌐 **Website:** [himanshubhandari2196.github.io/LumiVeil](https://himanshubhandari2196.github.io/LumiVeil)
🔌 **Live API:** [lumiveil-api-production-8706.up.railway.app](https://lumiveil-api-production-8706.up.railway.app)

---

## Features

- Auto-detects suspicious content on every page you visit
- Warning banner slides in automatically for low-trust content
- Full analysis report with trust score out of 100
- Checks 150+ trusted news sources across India, USA, UK, Europe, MEA, Asia, and sports
- Detects sensationalism and clickbait — both exact keyword matches and reworded/paraphrased language via a semantic (embeddings-based) fallback check
- Fact-checking pipeline — checks Google's Fact Check database first; if nothing exists, asks Gemini (with live search grounding) to find multiple independent sources, cross-reference them, and trace toward a primary source (an official statement, document, or direct quote) rather than trusting a single source's framing
- Four honest verdicts — Real, Fake, Mixed (genuine contradictory evidence), and Unverified (nothing findable either way — LumiVeil only checks what's actually out there, so "we don't know" is a real, distinct answer rather than a forced guess)
- Tone/style is treated as a weak, secondary signal — a confident fact-check verdict can't be overridden by dramatic writing, and dramatic writing only matters when fact-checking is genuinely inconclusive
- Image analysis — AI generation + deepfake detection via Sightengine + EXIF metadata
- Skips auto-analysis on non-news platforms (search engines, streaming, AI chat tools, etc.) — checked against a maintained list plus a general "does this page look like an article" structural heuristic for anything not on it
- One-tap sign-in — no copy-pasting tokens between the website and the extension
- Freemium model — 30 analyses/day free (including guest mode), Pro and Max plans available
- Account features — email verification, forgot/reset password, delete account
- Light and dark mode in the full report sidebar
- Secure — rate limited, API key authenticated, JWT-based user auth, hashed passwords

---

## Plans

| | Guest | Free | Pro | Max |
|---|---|---|---|---|
| Daily analyses | 30 | 30 | 300 | Unlimited |
| Wait on exhaustion | — | 5 hours | None | None |
| Account required | ❌ | ✅ | ✅ | ✅ |
| Image & deepfake analysis | ❌ | ❌ | ✅ | ✅ |
| Analysis history | ❌ | ❌ | Last 50 | Full |
| API access | ❌ | ❌ | ❌ | ✅ |
| Price | Free | $0 | $6/mo or $59/yr | $12/mo or $100/yr |

Guest mode needs no account — usage is tracked by device/network instead of a login, capped at the same daily limit as the Free tier.

---

## How It Works

1. Install the extension in Chrome (see [Installation](#installation) below)
2. Click the LumiVeil icon → sign in (opens the website, one tap, no copy-pasting) or continue as guest
3. Browse normally — LumiVeil runs silently in the background using the hosted backend, nothing to run yourself
4. Get instant warnings when suspicious content is detected
5. Click "View Full Report" for a detailed breakdown

---

## Tech Stack

- **Chrome Extension** — HTML, CSS, JavaScript (Manifest V3)
- **Backend** — Python, Flask, gunicorn — hosted on [Railway](https://railway.app)
- **Database** — PostgreSQL (Railway) — chosen over SQLite because Railway's filesystem is wiped on every redeploy
- **Auth** — Custom JWT (1-hour access token + 60-day refresh token), Google-style one-tap sign-in via `postMessage`
- **Image Analysis** — Sightengine API (AI generation + deepfake detection)
- **Metadata** — PIL / Pillow (EXIF analysis)
- **Fact-checking** — Google Fact Check API first; Gemini 2.5 Flash (Google Search grounding) as a fallback, prompted to cross-reference multiple independent sources and trace toward a primary source rather than return a single opaque verdict
- **Semantic matching** — Gemini embeddings, used as a fallback when exact keyword matching finds nothing, to catch reworded/paraphrased sensational language
- **Email** — Resend (transactional email for verification + password reset)
- **Landing page** — static HTML on GitHub Pages

---

## Installation (using the extension)

You don't need to run anything locally to use LumiVeil — the extension talks to the already-hosted backend.

### 1. Clone the repository
```bash
git clone https://github.com/HimanshuBhandari2196/LumiVeil.git
cd LumiVeil
```

### 2. Load the extension in Chrome
- Go to `chrome://extensions`
- Enable **Developer Mode** (top-right toggle)
- Click **Load Unpacked**
- Select the `extension` folder (not the repo root, not `backend`)

### 3. Sign in or continue as guest
- Click the LumiVeil icon in Chrome
- Click **Sign in** — this opens the website in a new tab; sign in or create a free account there and you're connected automatically, no tokens to copy
- Or click **Continue as guest** to try it with no account (30 analyses/day, same as Free tier)

---

## Running the backend locally (for contributors)

Only needed if you're developing the backend itself.

### 1. Install Python dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Set up environment variables
```bash
cp .env.example .env
```

Then open `.env` and fill in:

```
LUMIVEIL_API_KEY=any-secret-string-you-choose
JWT_SECRET=any-long-random-string
DATABASE_URL=postgresql://user:pass@host:5432/dbname
IMAGE_ANALYSIS_PROVIDER=sightengine
SIGHTENGINE_API_USER=your-api-user-from-dashboard.sightengine.com
SIGHTENGINE_API_SECRET=your-api-secret-from-dashboard.sightengine.com
GEMINI_API_KEY=your-gemini-api-key
GOOGLE_FACTCHECK_KEY=your-google-factcheck-api-key
RESEND_API_KEY=your-resend-api-key
```

You'll need a Postgres database — the easiest way is spinning one up on Railway and copying its connection string into `DATABASE_URL`. The `.env` file is git-ignored and will never be committed.

### 3. Start the backend
```bash
python app.py
```

Tables are created automatically on first run (`init_db()` runs on startup — safe to call every time).

### 4. Point the extension at your local backend
In `extension/background.js`, temporarily change `BACKEND_URL` to `http://localhost:5000/api/v1/analyze`, then reload the extension in `chrome://extensions`.

### 5. (Optional) Enable semantic paraphrase detection
The paraphrase-matching fallback needs pre-computed phrase embeddings, which aren't committed for every environment change — if `backend/phrase_embeddings.json` is missing or stale:
```bash
python generate_phrase_embeddings.py
```
This is safe to skip — without it, sensational-language detection just falls back to exact keyword matching only, no errors or broken behavior.

---

## API Endpoints

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/health` | None | Health check |
| POST | `/api/v1/auth/signup` | X-API-Key | Create account |
| POST | `/api/v1/auth/login` | X-API-Key | Login |
| POST | `/api/v1/auth/refresh` | X-API-Key | Exchange refresh token for a new access token |
| POST | `/api/v1/auth/logout` | X-API-Key | Revoke refresh token |
| POST | `/api/v1/auth/forgot-password` | X-API-Key | Send password reset email |
| POST | `/api/v1/auth/reset-password` | X-API-Key | Consume reset token, set new password |
| GET | `/api/v1/auth/verify-email` | None (token in query) | Verify email address |
| POST | `/api/v1/auth/resend-verification` | X-API-Key + Bearer | Resend verification email |
| POST | `/api/v1/auth/delete-account` | X-API-Key + Bearer | Permanently delete account and all data |
| GET | `/api/v1/user/status` | X-API-Key + Bearer | Usage + tier info |
| POST | `/api/v1/analyze` | X-API-Key (+ Bearer optional) | Analyze a URL, image, or text claim — Bearer identifies the user's tier; omitted = guest, tracked by IP |

---

## Project Structure

```
LumiVeil/
├── index.html               # Landing page + sign-in modal (GitHub Pages)
├── privacy.html              # Privacy Policy page
├── terms.html                 # Terms of Service page
├── railway.toml               # Railway config (repo root)
├── extension/
│   ├── manifest.json
│   ├── popup.html/css/js      # Extension popup — welcome/waiting/main screens
│   ├── sidebar.html/css/js    # Full report page
│   ├── content.js             # Auto-detection on every page + login bridge
│   └── background.js          # Service worker — API calls, token storage
└── backend/
    ├── app.py                       # Flask app + all routes
    ├── database.py                  # PostgreSQL layer (users, usage, guest_usage, payments, tokens)
    ├── auth.py                      # Password hashing + JWT issuing/refresh
    ├── email_service.py             # Resend integration (verification + reset emails)
    ├── sensational_phrases.py       # Curated phrase list for exact-match sensationalism detection
    ├── semantic_match.py            # Embeddings-based paraphrase detection (fallback layer)
    ├── generate_phrase_embeddings.py # One-time setup script — run after editing sensational_phrases.py
    ├── debug_semantic_match.py      # Prints real similarity scores for calibrating the matching threshold
    ├── phrase_embeddings.json       # Generated by generate_phrase_embeddings.py — commit after regenerating
    ├── requirements.txt
    ├── railway.toml
    └── .env.example
```

---

## Known Limitations

- Image analysis only works on direct image URLs ending in `.jpg`, `.png`, `.gif`, `.webp`, `.bmp`
- Video deepfake detection is not yet implemented — actively being researched (structural prompt-template fingerprinting + provenance signals, rather than pixel-level detection)
- Sensational-language detection (both keyword and semantic matching) is English-only — manipulative language in other languages won't be caught by this layer, though fact-checking itself isn't language-limited
- Guest usage tracking is IP-based, so it isn't watertight against VPNs or shared/rotating IPs — good enough for the intended "try before you sign up" use case, not meant to be bulletproof
- The non-news-platform skip list can't be exhaustive — new sites we haven't added yet fall back to a structural "does this look like an article" heuristic, which is a reasonable backstop but not foolproof
- `LUMIVEIL_API_KEY` is baked into the shipped extension JS (unavoidable for client-side code — it's an internal token identifying "this is the real extension," not a third-party credential)
- Payments (Stripe/Razorpay) are not yet wired up — Pro/Max tiers exist in the data model but can't be purchased yet

---

## Contributing

Pull requests are welcome. If you want to help with video deepfake detection research or the payment integration, open an issue or reach out directly.

📧 [Himanshubhandari224@gmail.com](mailto:Himanshubhandari224@gmail.com)
🐙 [github.com/HimanshuBhandari2196](https://github.com/HimanshuBhandari2196)

---

## License

MIT License — free to use and modify.

---

*Built by Himanshu Bhandari — BTech CS Student passionate about AI, Robotics, and fighting misinformation.*
