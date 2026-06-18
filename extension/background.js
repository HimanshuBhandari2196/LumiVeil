// LumiVeil Background Service Worker

const BACKEND_URL = 'http://127.0.0.1:5000/analyze';

// Listen for messages from content scripts
chrome.runtime.onMessage.addListener(function(request, sender, sendResponse) {
  
  // Content script asking background to analyze
  if (request.action === 'analyze') {
   fetch(BACKEND_URL, {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'X-API-Key': 'lumiveil-secret-2026'
      },
      body: JSON.stringify({ input: request.input })
    })
    .then(response => response.json())
    .then(data => {
      chrome.storage.local.set({ lastResult: data });
      sendResponse({ success: true, data: data });
    })
    .catch(error => {
      sendResponse({ success: false });
    });
    return true; // Keep channel open
  }

  // Open full report
  if (request.action === 'openReport') {
    chrome.tabs.create({ 
      url: chrome.runtime.getURL('sidebar.html') 
    });
  }

  return true;
});