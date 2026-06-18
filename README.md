# LumiVeil — Lift the Veil on Fake Content

LumiVeil is an open source Chrome Extension that automatically detects fake news, AI generated images, deepfakes, and misinformation as you browse the internet.

## Features

- Auto detects suspicious content on every page you visit
- Warning banner appears automatically for fake or misleading content
- Full analysis report with trust score out of 100
- Checks 100+ trusted news sources globally
- Detects sensational language and clickbait patterns
- Image analysis using Hive AI + metadata detection
- Light and dark mode
- Secure — rate limited, API key authenticated

## How It Works

1. Install the extension in Chrome
2. Start the Python backend
3. Browse normally — LumiVeil runs in the background
4. Get instant warnings when suspicious content is detected
5. Click View Full Report for detailed analysis

## Tech Stack

- Chrome Extension — HTML, CSS, JavaScript
- Backend — Python, Flask
- AI Detection — Hive Moderation API
- Image Analysis — PIL, EXIF metadata
- NLP — Custom sensationalism detection

## Installation

### 1. Clone the repository
```
git clone https://github.com/YOUR_USERNAME/LumiVeil.git
```

### 2. Install Python dependencies
```
cd LumiVeil/backend
pip install -r requirements.txt
```

### 3. Set up your environment variables
Copy the example file and fill in your own keys:
```
cp .env.example .env
```
Then open `.env` and add:
- `LUMIVEIL_API_KEY` — any secret string of your choice
- `HIVE_API_KEY` — your Hive Moderation API key from hivemoderation.com

The `.env` file is git-ignored and will never be committed.

### 4. Start the backend
```
python app.py
```

### 5. Load the extension in Chrome
- Go to chrome://extensions
- Enable Developer Mode
- Click Load Unpacked
- Select the extension folder

## Known Issues / Help Needed

- Hive API V3 authentication returns a 403 "Invalid Auth Token" error — looking for contributors who have experience with Hive's API to help debug
- Image detection limited to direct image URLs ending in .jpg .png etc
- Video deepfake detection not yet implemented

## Contributing

Pull requests are welcome! If you can help with any of the known issues above please open an issue or PR.

## License

MIT License — free to use and modify

## Author

Built by Himanshu — BTech CS Student passionate about AI, Robotics, and fighting misinformation
