// LumiVeil Background Service Worker

const BACKEND_URL  = 'https://lumiveil-api-production-8706.up.railway.app/api/v1/analyze';
const LUMIVEIL_KEY = 'lumiveil-secret-2026';

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
        body:    JSON.stringify({ input: request.input, locale: request.locale || '' })
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
