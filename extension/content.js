// LumiVeil - Content Script
// Runs automatically on every webpage

// ---- SETTINGS ----
const BACKEND_URL = 'http://localhost:5000/analyze';
const SCORE_THRESHOLD = 40; // Below this score = show warning
const ANALYSIS_DELAY = 2000; // Wait 2 seconds before analyzing

// ---- INJECT OUR WARNING BANNER STYLES ----
function injectStyles() {
  const style = document.createElement('style');
  style.id = 'lumiveil-styles';
  style.textContent = `
    #lumiveil-banner {
      position: fixed;
      top: -100px;
      left: 0;
      right: 0;
      z-index: 999999;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 20px;
      background: #1a0a0a;
      border-bottom: 2px solid #ef4444;
      font-family: 'Segoe UI', sans-serif;
      font-size: 14px;
      color: #ffffff;
      transition: top 0.4s ease;
      box-shadow: 0 4px 20px rgba(239, 68, 68, 0.3);
    }

    #lumiveil-banner.show {
      top: 0;
    }

    #lumiveil-banner.warning {
      background: #1a1200;
      border-bottom: 2px solid #f59e0b;
      box-shadow: 0 4px 20px rgba(245, 158, 11, 0.3);
    }

    #lumiveil-banner-left {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    #lumiveil-banner-icon {
      font-size: 18px;
    }

    #lumiveil-banner-text {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    #lumiveil-banner-title {
      font-weight: 600;
      font-size: 14px;
      color: #ef4444;
    }

    #lumiveil-banner.warning #lumiveil-banner-title {
      color: #f59e0b;
    }

    #lumiveil-banner-subtitle {
      font-size: 12px;
      color: #888888;
    }

    #lumiveil-banner-right {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    #lumiveil-view-report {
      background: #ef4444;
      color: #ffffff;
      border: none;
      border-radius: 6px;
      padding: 6px 14px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.2s;
    }

    #lumiveil-banner.warning #lumiveil-view-report {
      background: #f59e0b;
    }

    #lumiveil-view-report:hover {
      opacity: 0.85;
    }

    #lumiveil-dismiss {
      background: transparent;
      color: #888888;
      border: 1px solid #333333;
      border-radius: 6px;
      padding: 6px 14px;
      font-size: 12px;
      cursor: pointer;
      transition: all 0.2s;
    }

    #lumiveil-dismiss:hover {
      color: #ffffff;
      border-color: #666666;
    }

    #lumiveil-logo {
      font-size: 12px;
      color: #a78bfa;
      font-weight: 600;
      margin-right: 8px;
    }
  `;
  document.head.appendChild(style);
}

// ---- CREATE WARNING BANNER ----
function createBanner(result) {
  // Remove existing banner if any
  const existing = document.getElementById('lumiveil-banner');
  if (existing) existing.remove();

  const banner = document.createElement('div');
  banner.id = 'lumiveil-banner';

  // Add warning class for mixed content
  if (result.verdict === 'mixed') {
    banner.classList.add('warning');
  }

  banner.innerHTML = `
    <div id="lumiveil-banner-left">
      <span id="lumiveil-banner-icon">${result.verdict === 'fake' ? '❌' : '⚠️'}</span>
      <div id="lumiveil-banner-text">
        <span id="lumiveil-banner-title">
          ${result.verdict === 'fake' ? 'LumiVeil Warning — This page may contain fake content' : 'LumiVeil Caution — This page has mixed signals'}
        </span>
        <span id="lumiveil-banner-subtitle">
          Trust Score: ${result.trust_score}/100 · ${result.checks ? result.checks.length : 0} red flags detected
        </span>
      </div>
    </div>
    <div id="lumiveil-banner-right">
      <span id="lumiveil-logo">👁 LumiVeil</span>
      <button id="lumiveil-view-report">View Full Report</button>
      <button id="lumiveil-dismiss">Dismiss</button>
    </div>
  `;

  document.body.appendChild(banner);

  // Slide in after a tiny delay
  setTimeout(() => banner.classList.add('show'), 100);

  // View full report button
  document.getElementById('lumiveil-view-report').addEventListener('click', function () {
    chrome.runtime.sendMessage({ action: 'openReport' });
  });

  // Dismiss button
  document.getElementById('lumiveil-dismiss').addEventListener('click', function () {
    banner.classList.remove('show');
    setTimeout(() => banner.remove(), 400);
  });
}

// ---- ANALYZE THE CURRENT PAGE ----
function analyzePage() {
  // Don't analyze chrome:// pages or extension pages
  const url = window.location.href;
  if (url.startsWith('chrome://') ||
      url.startsWith('chrome-extension://') ||
      url.startsWith('about:')) {
    return;
  }

  // Get page text
  const pageText = document.body.innerText.slice(0, 3000);
  const inputToAnalyze = url + ' ' + pageText;

  console.log('LumiVeil: Analyzing page...');

  // Send to background script which will call backend
  chrome.runtime.sendMessage({
    action: 'analyze',
    input: inputToAnalyze
  }, function(response) {
    if (response && response.success) {
      console.log('LumiVeil: Analysis complete, score:', response.data.trust_score);
      if (response.data.trust_score < SCORE_THRESHOLD) {
        createBanner(response.data);
      }
    } else {
      console.log('LumiVeil: Analysis failed');
    }
  });
}

// ---- LISTEN FOR MESSAGES FROM POPUP ----
chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
  if (request.action === 'getPageContent') {
    sendResponse({
      title: document.title,
      url: window.location.href,
      text: document.body.innerText.slice(0, 3000),
      images: Array.from(document.querySelectorAll('img'))
        .map(img => img.src)
        .filter(src => src && src.startsWith('http'))
        .slice(0, 5)
    });
  }
  return true;
});

// ---- START ----
injectStyles();

// Listen for analyze trigger from background
chrome.runtime.onMessage.addListener(function(request) {
  if (request.action === 'analyzePage') {
    setTimeout(analyzePage, ANALYSIS_DELAY);
  }
});

// Also run on initial page load
setTimeout(analyzePage, ANALYSIS_DELAY);