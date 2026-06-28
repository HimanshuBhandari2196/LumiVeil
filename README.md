# LumiVeil — Lift the Veil on Fake Content

LumiVeil is an open source Chrome extension that automatically detects fake news, AI-generated images, deepfakes, and misinformation in real time as you browse.

🌐 **Website:** [himanshubhandari2196.github.io/LumiVeil](https://himanshubhandari2196.github.io/LumiVeil)

---

## Features

- Auto-detects suspicious content on every page you visit
- Warning banner slides in automatically for low-trust content
- Full analysis report with trust score out of 100
- Checks 100+ trusted news sources across India, USA, UK, Europe, and more
- Detects sensationalism, clickbait, and manipulation patterns
- Image analysis — AI generation + deepfake detection via Sightengine + EXIF metadata
- Freemium model — 30 analyses/day free, Pro and Max plans available
- Light and dark mode in the full report sidebar
- Secure — rate limited, API key authenticated, JWT-based user auth

---

## Plans

| | Free | Pro | Max |
|---|---|---|---|
| Daily analyses | 30 | 300 | Unlimited |
| Wait on exhaustion | 5 hours | None | None |
| Image & deepfake analysis | ❌ | ✅ | ✅ |
| Analysis history | ❌ | Last 50 | Full |
| API access | ❌ | ❌ | ✅ |
| Price | $0 | $6/mo or $59/yr | $12/mo or $100/yr |

---

## How It Works

1. Install the extension in Chrome
2. Create a free account at [himanshubhandari2196.github.io/LumiVeil](https://himanshubhandari2196.github.io/LumiVeil) or continue as guest
3. Start the Python backend locally
4. Browse normally — LumiVeil runs silently in the background
5. Get instant warnings when suspicious content is detected
6. Click "View Full Report" for a detailed breakdown

---

## Tech Stack

- **Chrome Extension** — HTML, CSS, JavaScript (Manifest V3)
- **Backend** — Python, Flask
- **Database** — SQLite (via Python built-in `sqlite3`)
- **Auth** — JWT tokens (custom implementation, no external library)
- **Image Analysis** — Sightengine API (AI generation + deepfake detection)
- **Metadata** — PIL / Pillow (EXIF analysis)
- **NLP** — Custom sensationalism and pattern detection engine

---

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/HimanshuBhandari2196/LumiVeil.git
cd LumiVeil
```

### 2. Install Python dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 3. Set up environment variables
```bash
cp .env.example .env
```

Then open `.env` and fill in:

```
LUMIVEIL_API_KEY=any-secret-string-you-choose
JWT_SECRET=any-long-random-string
IMAGE_ANALYSIS_PROVIDER=sightengine
SIGHTENGINE_API_USER=your-api-user-from-dashboard.sightengine.com
SIGHTENGINE_API_SECRET=your-api-secret-from-dashboard.sightengine.com
```

The `.env` file is git-ignored and will never be committed.

### 4. Start the backend
```bash
python app.py
```

The backend runs at `http://localhost:5000`. The SQLite database (`lumiveil.db`) is created automatically on first run.

### 5. Load the extension in Chrome
- Go to `chrome://extensions`
- Enable Developer Mode (top right toggle)
- Click **Load Unpacked**
- Select the `extension` folder

### 6. Sign in or continue as guest
- Click the LumiVeil icon in Chrome
- Create a free account on the website and paste your token, or click "Continue as guest"

---

## API Endpoints

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/health` | None | Health check |
| POST | `/api/v1/auth/signup` | X-API-Key | Create account |
| POST | `/api/v1/auth/login` | X-API-Key | Login |
| GET | `/api/v1/user/status` | Bearer token | Usage + tier info |
| POST | `/api/v1/analyze` | X-API-Key + Bearer | Analyze content |

---

## Project Structure

```
LumiVeil/
├── index.html              # Landing page (GitHub Pages)
├── extension/
│   ├── manifest.json
│   ├── popup.html/css/js   # Extension popup
│   ├── sidebar.html/css/js # Full report page
│   ├── content.js          # Auto-detection on every page
│   └── background.js       # Service worker
└── backend/
    ├── app.py              # Flask app + all routes
    ├── database.py         # SQLite layer (users, usage, payments)
    ├── auth.py             # Password hashing + JWT
    ├── requirements.txt
    ├── .env.example
    └── .gitignore
```

---

## Known Limitations

- Image analysis only works on direct image URLs ending in `.jpg`, `.png`, `.gif`, `.webp`, `.bmp`
- Video deepfake detection is not yet implemented — actively being researched
- The backend must be running locally — cloud deployment coming in a future update
- `LUMIVEIL_API_KEY` is hardcoded in the extension JS files (unavoidable for client-side code — it is an internal token, not a third-party credential)

---

## Contributing

Pull requests are welcome. If you want to help with video deepfake detection research or cloud deployment, open an issue or reach out directly.

📧 [Himanshubhandari224@gmail.com](mailto:Himanshubhandari224@gmail.com)
🐙 [github.com/HimanshuBhandari2196](https://github.com/HimanshuBhandari2196)

---

## License

MIT License — free to use and modify.

---

*Built by Himanshu Bhandari — BTech CS Student passionate about AI, Robotics, and fighting misinformation.*
