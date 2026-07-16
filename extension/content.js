// LumiVeil — Content Script
// Runs automatically on every webpage

const BACKEND_URL    = 'https://lumiveil-api-production-8706.up.railway.app/api/v1/analyze';
const SCORE_THRESHOLD = 40;
const ANALYSIS_DELAY  = 2000;

// Platforms that were never news/article content to begin with — search
// engines, streaming/OTT, e-commerce, productivity tools. Auto-analysis
// skips these entirely rather than scoring them as if they were
// (possibly fake) news, which produced confusing false positives like
// flagging a Google search results page or a Hotstar show listing.
// Add more here as they come up — this list can't be exhaustive, but it
// covers the common cases people actually browse day to day.
const NON_NEWS_DOMAINS = [
  // Search engines
  'google.com', 'bing.com', 'duckduckgo.com', 'search.yahoo.com', 'yandex.com',
  // Streaming / OTT
  'netflix.com', 'hotstar.com', 'primevideo.com', 'disneyplus.com', 'hulu.com',
  'jiocinema.com', 'sonyliv.com', 'zee5.com', 'spotify.com', 'youtube.com',
  // E-commerce
  'amazon.com', 'amazon.in', 'flipkart.com', 'ebay.com', 'etsy.com',
  // Productivity / webmail / cloud tools
  'mail.google.com', 'docs.google.com', 'drive.google.com', 'calendar.google.com',
  'outlook.com', 'notion.so', 'slack.com', 'zoom.us',
  // AI chat interfaces — conversational replies aren't news claims either
  'chatgpt.com', 'chat.openai.com', 'claude.ai', 'gemini.google.com',
  'perplexity.ai', 'copilot.microsoft.com', 'poe.com', 'grok.com',
];

// ============================================================
// WEBSITE → EXTENSION LOGIN BRIDGE
// When the user signs in on the LumiVeil website, the page
// fires a postMessage with the tokens. This content script
// listens for it and relays it to background.js, which stores
// the tokens so the popup can detect the login automatically.
// ============================================================
window.addEventListener('message', function (event) {
  if (event.source !== window) return;
  if (!event.data || event.data.type !== 'LUMIVEIL_LOGIN') return;

  const { token, refresh_token, user } = event.data;
  if (!token || !user) return;

  chrome.runtime.sendMessage({
    action:        'store_login',
    token:         token,
    refresh_token: refresh_token,
    user:          user
  }, function (response) {
    if (response && response.success) {
      // Tell the page the extension received the tokens
      window.postMessage({ type: 'LUMIVEIL_LOGIN_ACK' }, '*');
    }
  });
});

// ============================================================
// INJECT BANNER STYLES
// ============================================================
function injectStyles() {
  if (document.getElementById('lumiveil-styles')) return;
  const style = document.createElement('style');
  style.id = 'lumiveil-styles';
  style.textContent = `
    /* ---- BANNER ---- */
    #lumiveil-banner {
      position: fixed;
      top: -90px;
      left: 0; right: 0;
      z-index: 2147483647;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 12px 20px;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      font-size: 13px;
      color: #fff;
      transition: top 0.4s cubic-bezier(0.16, 1, 0.3, 1);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
    }

    /* Fake verdict — red */
    #lumiveil-banner.lv-fake {
      background: rgba(18, 8, 8, 0.92);
      border-bottom: 1px solid rgba(239,68,68,0.5);
      box-shadow: 0 4px 24px rgba(239,68,68,0.15), 0 1px 0 rgba(239,68,68,0.3) inset;
    }

    /* Mixed verdict — amber */
    #lumiveil-banner.lv-mixed {
      background: rgba(18, 14, 6, 0.92);
      border-bottom: 1px solid rgba(245,158,11,0.5);
      box-shadow: 0 4px 24px rgba(245,158,11,0.12), 0 1px 0 rgba(245,158,11,0.25) inset;
    }

    #lumiveil-banner.lv-show { top: 0; }

    /* ---- LEFT: logo + text ---- */
    #lv-left {
      display: flex; align-items: center; gap: 12px; flex: 1; min-width: 0;
    }

    #lv-logo-mark {
      display: flex; align-items: center; gap: 6px;
      flex-shrink: 0;
      font-size: 12px; font-weight: 700; letter-spacing: 0.04em;
      color: #7C6FF7;
      opacity: 0.9;
    }

    #lv-logo-mark svg { flex-shrink: 0; }

    #lv-divider {
      width: 1px; height: 28px;
      background: rgba(255,255,255,0.1);
      flex-shrink: 0;
    }

    #lv-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }

    #lv-title {
      font-size: 13px; font-weight: 600; line-height: 1.3;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .lv-fake  #lv-title { color: #FCA5A5; }
    .lv-mixed #lv-title { color: #FCD34D; }

    #lv-subtitle {
      font-size: 11px; color: rgba(255,255,255,0.45); line-height: 1.3;
    }

    /* ---- RIGHT: score pill + buttons ---- */
    #lv-right {
      display: flex; align-items: center; gap: 8px; flex-shrink: 0;
    }

    #lv-score {
      font-size: 11px; font-weight: 700;
      padding: 3px 10px; border-radius: 100px;
      letter-spacing: 0.04em;
    }
    .lv-fake  #lv-score { background: rgba(239,68,68,0.15); color: #EF4444; border: 1px solid rgba(239,68,68,0.3); }
    .lv-mixed #lv-score { background: rgba(245,158,11,0.15); color: #F59E0B; border: 1px solid rgba(245,158,11,0.3); }

    #lv-report-btn {
      display: flex; align-items: center; gap: 5px;
      padding: 6px 14px; border-radius: 8px; border: none;
      font-size: 12px; font-weight: 600; cursor: pointer;
      font-family: inherit; transition: opacity 0.2s, transform 0.15s;
      color: #fff;
    }
    .lv-fake  #lv-report-btn { background: #EF4444; }
    .lv-mixed #lv-report-btn { background: #F59E0B; color: #0C0C10; }
    #lv-report-btn:hover { opacity: 0.88; transform: translateY(-1px); }

    #lv-dismiss-btn {
      background: transparent;
      color: rgba(255,255,255,0.4);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 8px; padding: 6px 12px;
      font-size: 12px; font-family: inherit;
      cursor: pointer; transition: all 0.2s; flex-shrink: 0;
    }
    #lv-dismiss-btn:hover { color: #fff; border-color: rgba(255,255,255,0.3); }
  `;
  document.head.appendChild(style);
}

// ============================================================
// CREATE BANNER
// ============================================================
function createBanner(result) {
  const existing = document.getElementById('lumiveil-banner');
  if (existing) existing.remove();

  const isFake  = result.verdict === 'fake';
  const isMixed = result.verdict === 'mixed';
  const score   = result.trust_score;
  // Match the definition used in sidebar.js's full report — ❌ (hard flag),
  // ⚠️ (warning, e.g. AI-image/deepfake detection, paraphrased sensational
  // language), and 🚩 (AI fact-check's own red_flags) all count;
  // ✅/ℹ️/🔍/💭 are neutral/positive.
  const flags = result.checks ? result.checks.filter(c => c.includes('❌') || c.includes('⚠️') || c.includes('🚩')).length : 0;

  const title    = isFake
    ? 'This page may contain fake or misleading content'
    : 'This page has mixed credibility signals';

  const subtitle = `Trust score ${score}/100 · ${flags} red flag${flags !== 1 ? 's' : ''} detected`;

  const banner = document.createElement('div');
  banner.id = 'lumiveil-banner';
  banner.classList.add(isFake ? 'lv-fake' : 'lv-mixed');

  banner.innerHTML = `
    <div id="lv-left">
      <div id="lv-logo-mark">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <ellipse cx="12" cy="12" rx="10" ry="6"/>
          <circle cx="12" cy="12" r="2.5" fill="currentColor" stroke="none"/>
        </svg>
        LumiVeil
      </div>
      <div id="lv-divider"></div>
      <div id="lv-text">
        <span id="lv-title">${title}</span>
        <span id="lv-subtitle">${subtitle}</span>
      </div>
    </div>
    <div id="lv-right">
      <span id="lv-score">${score}/100</span>
      <button id="lv-report-btn">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
          <circle cx="12" cy="12" r="3"/>
        </svg>
        View full report
      </button>
      <button id="lv-dismiss-btn">Dismiss</button>
    </div>
  `;

  document.body.appendChild(banner);
  setTimeout(() => banner.classList.add('lv-show'), 80);

  document.getElementById('lv-report-btn').addEventListener('click', function () {
    chrome.runtime.sendMessage({ action: 'openReport' });
  });

  document.getElementById('lv-dismiss-btn').addEventListener('click', function () {
    banner.classList.remove('lv-show');
    setTimeout(() => banner.remove(), 420);
  });
}

// ============================================================
// ANALYZE THE CURRENT PAGE
// ============================================================
function analyzePage() {
  const url = window.location.href;
  if (url.startsWith('chrome://') ||
      url.startsWith('chrome-extension://') ||
      url.startsWith('about:') ||
      url.startsWith('moz-extension://')) return;

  const hostname = window.location.hostname.replace(/^www\./, '');
  if (NON_NEWS_DOMAINS.some(d => hostname === d || hostname.endsWith('.' + d))) {
    console.log('LumiVeil: Skipping non-news platform:', hostname);
    return;
  }

  // Backstop for sites NOT on the list above (which can never be
  // exhaustive — e.g. new AI chat tools, dashboards, web apps we haven't
  // thought to add yet). A real news article almost always has either a
  // semantic <article> tag, an og:type=article meta tag, or several
  // substantial <p> paragraphs. Chat UIs, dashboards, and similar app
  // interfaces typically have none of these, so treat their absence as a
  // signal this probably isn't an article worth auto-analyzing.
  // Social media platforms are exempt from this check — short posts are
  // expected there, and the backend has dedicated logic (is_social) built
  // specifically to fact-check them despite not looking like articles.
  const socialDomains = ['twitter.com', 'x.com', 'facebook.com', 'instagram.com',
                        'reddit.com', 'tiktok.com', 'linkedin.com', 'telegram.org'];
  const isSocialPlatform = socialDomains.some(d => hostname === d || hostname.endsWith('.' + d));

  if (!isSocialPlatform) {
    const hasArticleTag = !!document.querySelector('article');
    const ogType = document.querySelector('meta[property="og:type"]');
    const isArticleMeta = ogType && ogType.content === 'article';
    const substantialParagraphs = Array.from(document.querySelectorAll('p'))
      .filter(p => p.innerText && p.innerText.trim().length > 40).length;

    if (!hasArticleTag && !isArticleMeta && substantialParagraphs < 3) {
      console.log('LumiVeil: Skipping — page does not look like an article:', hostname);
      return;
    }
  }

  const pageText = document.body ? document.body.innerText.slice(0, 3000) : '';

  console.log('LumiVeil: Analyzing page...');

  chrome.runtime.sendMessage({
    action: 'analyze',
    input:  url,       // clean URL — used for domain/pattern checks
    text:   pageText,  // actual page content — used for sensationalism checks
    locale: navigator.language || ''
  }, function (response) {
    if (response && response.success) {
      console.log('LumiVeil: Score:', response.data.trust_score);
      if (response.data.trust_score < SCORE_THRESHOLD) {
        createBanner(response.data);
      }
    } else {
      console.log('LumiVeil: Analysis failed');
    }
  });
}

// ============================================================
// LISTEN FOR MESSAGES
// ============================================================
chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
  if (request.action === 'getPageContent') {
    sendResponse({
      title:  document.title,
      url:    window.location.href,
      text:   document.body ? document.body.innerText.slice(0, 3000) : '',
      images: Array.from(document.querySelectorAll('img'))
        .map(img => img.src)
        .filter(src => src && src.startsWith('http'))
        .slice(0, 5)
    });
  }
  if (request.action === 'analyzePage') {
    setTimeout(analyzePage, ANALYSIS_DELAY);
  }
  return true;
});

// ============================================================
// START
// ============================================================
injectStyles();
setTimeout(analyzePage, ANALYSIS_DELAY);
