// LumiVeil Background Service Worker

const BACKEND_URL  = 'https://lumiveil-api-production-8706.up.railway.app/api/v1/analyze';
const LUMIVEIL_KEY = 'lumiveil-secret-2026';

// ============================================================
// EXTERNAL MESSAGE LISTENER
// Receives login tokens directly from the LumiVeil website
// after the user signs in — no copy-paste required.
// The website calls chrome.runtime.sendMessage(EXTENSION_ID, ...)
// which routes here via the externally_connectable manifest entry.
// ============================================================
chrome.runtime.onMessageExternal.addListener(function (request, sender, sendResponse) {
  if (request.action === 'lumiveil_login') {
    // Validate the message came from our website
    const allowedOrigins = [
      'https://himanshubhandari2196.github.io',
      'http://localhost:5000',
      'http://127.0.0.1:5000'
    ];
    if (!allowedOrigins.some(o => sender.origin && sender.origin.startsWith(o))) {
      sendResponse({ success: false, error: 'Unauthorized origin' });
      return true;
    }

    const { token, refresh_token, user } = request;
    if (!token || !user) {
      sendResponse({ success: false, error: 'Missing token or user' });
      return true;
    }

    // Store both tokens and user info — popup will read these on next open
    const data = { lv_token: token, lv_user: user };
    if (refresh_token) data.lv_refresh_token = refresh_token;

    chrome.storage.local.set(data, function () {
      sendResponse({ success: true });
    });
    return true; // Keep channel open for async response
  }
});

// ============================================================
// INTERNAL MESSAGE LISTENER
// Handles messages from content.js and popup.js
// ============================================================
chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {

  // Store login tokens relayed from the website via content.js
  if (request.action === 'store_login') {
    const { token, refresh_token, user } = request;
    if (!token || !user) { sendResponse({ success: false }); return true; }
    const data = { lv_token: token, lv_user: user };
    if (refresh_token) data.lv_refresh_token = refresh_token;
    chrome.storage.local.set(data, function () {
      sendResponse({ success: true });
    });
    return true;
  }

  // Content script asking background to analyze the current page
  if (request.action === 'analyze') {
    // Get stored token to send with request if available
    chrome.storage.local.get(['lv_token'], function (session) {
      const headers = {
        'Content-Type': 'application/json',
        'X-API-Key':    LUMIVEIL_KEY
      };
      if (session.lv_token) {
        headers['Authorization'] = `Bearer ${session.lv_token}`;
      }

      fetch(BACKEND_URL, {
        method:  'POST',
        headers: headers,
        body:    JSON.stringify({ input: request.input })
      })
      .then(response => response.json())
      .then(data => {
        chrome.storage.local.set({ lastResult: data });
        sendResponse({ success: true, data: data });
      })
      .catch(() => {
        sendResponse({ success: false });
      });
    });
    return true; // Keep channel open for async response
  }

  // Open full report sidebar
  if (request.action === 'openReport') {
    chrome.tabs.create({
      url: chrome.runtime.getURL('sidebar.html')
    });
  }

  return true;
});
