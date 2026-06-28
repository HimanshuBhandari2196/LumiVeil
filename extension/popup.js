const API_BASE     = 'https://lumiveil-api-production-8706.up.railway.app';
const LUMIVEIL_KEY = 'lumiveil-secret-2026';
const WEBSITE_URL  = 'https://himanshuBhandari2196.github.io/LumiVeil';

// ============================================================
// SCREEN MANAGEMENT
// ============================================================

function showScreen(name) {
  document.getElementById('welcomeScreen').style.display = name === 'welcome' ? 'block' : 'none';
  document.getElementById('mainScreen').style.display    = name === 'main'    ? 'block' : 'none';
}

// ============================================================
// SESSION STORAGE
// ============================================================

function saveSession(token, user) {
  chrome.storage.local.set({ lv_token: token, lv_user: user });
}

function clearSession() {
  chrome.storage.local.remove(['lv_token', 'lv_user', 'lastResult']);
}

function getSession(cb) {
  chrome.storage.local.get(['lv_token', 'lv_user'], cb);
}

// ============================================================
// USAGE BAR
// ============================================================

function updateUsageBar(used, limit) {
  if (limit >= 999999) {
    document.getElementById('usageWrap').style.display = 'none';
    return;
  }
  const pct   = Math.min((used / limit) * 100, 100);
  const fill  = document.getElementById('usageBarFill');
  const label = document.getElementById('usageLabel');

  fill.style.width = pct + '%';
  fill.className   = 'usage-bar-fill';
  if (pct >= 90)      fill.classList.add('danger');
  else if (pct >= 70) fill.classList.add('warn');

  label.textContent = `${used} / ${limit} analyses today  (${Math.max(0, limit - used)} remaining)`;
}

function fetchAndUpdateUsage(token) {
  fetch(`${API_BASE}/api/v1/user/status`, {
    headers: {
      'Authorization': `Bearer ${token}`,
      'X-API-Key': LUMIVEIL_KEY
    }
  })
  .then(r => r.json())
  .then(data => {
    if (data.usage) {
      updateUsageBar(data.usage.today, data.usage.limit);
    }
    if (data.user) {
      const badge = document.getElementById('tierBadge');
      badge.textContent = data.user.tier;
      badge.className   = 'tier-badge ' + data.user.tier;
    }
  })
  .catch(() => {});
}

// ============================================================
// MAIN
// ============================================================

document.addEventListener('DOMContentLoaded', function () {

  // Check for existing session on open
  getSession(function (data) {
    if (data.lv_token && data.lv_user) {
      // Logged in user
      showScreen('main');
      const badge = document.getElementById('tierBadge');
      badge.textContent = data.lv_user.tier || 'free';
      badge.className   = 'tier-badge ' + (data.lv_user.tier || 'free');
      fetchAndUpdateUsage(data.lv_token);
    } else if (data.lv_user && data.lv_user.guest) {
      // Guest
      showScreen('main');
      const badge = document.getElementById('tierBadge');
      badge.textContent = 'guest';
      badge.className   = 'tier-badge guest';
      document.getElementById('usageWrap').style.display = 'none';
    } else {
      showScreen('welcome');
    }
  });

  // ── Create account → open website in new tab ──
  document.getElementById('createAccountBtn').addEventListener('click', function () {
    chrome.tabs.create({ url: WEBSITE_URL + '#pricing' });
  });

  // ── Token paste → validate with backend ──
  document.getElementById('tokenSubmitBtn').addEventListener('click', function () {
    const token = document.getElementById('tokenInput').value.trim();
    const errorEl = document.getElementById('tokenError');
    errorEl.style.display = 'none';

    if (!token) {
      errorEl.textContent = 'Please paste your token first.';
      errorEl.style.display = 'block';
      return;
    }

    const btn = this;
    btn.textContent = 'Checking…';
    btn.disabled    = true;

    // Validate token by hitting /user/status
    fetch(`${API_BASE}/api/v1/user/status`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'X-API-Key': LUMIVEIL_KEY
      }
    })
    .then(r => r.json().then(d => ({ status: r.status, data: d })))
    .then(({ status, data }) => {
      btn.textContent = 'Connect';
      btn.disabled    = false;

      if (status === 200 && data.user) {
        saveSession(token, data.user);
        showScreen('main');
        const badge = document.getElementById('tierBadge');
        badge.textContent = data.user.tier;
        badge.className   = 'tier-badge ' + data.user.tier;
        if (data.usage) {
          updateUsageBar(data.usage.today, data.usage.limit);
        }
      } else {
        errorEl.textContent = 'Invalid token. Copy it from your profile page on the LumiVeil website.';
        errorEl.style.display = 'block';
      }
    })
    .catch(() => {
      btn.textContent = 'Connect';
      btn.disabled    = false;
      errorEl.textContent = 'Could not connect to backend. Make sure Flask is running.';
      errorEl.style.display = 'block';
    });
  });

  // Allow pressing Enter in the token field
  document.getElementById('tokenInput').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') document.getElementById('tokenSubmitBtn').click();
  });

  // ── Guest mode ──
  document.getElementById('guestBtn').addEventListener('click', function () {
    clearSession();
    chrome.storage.local.set({ lv_user: { guest: true } });
    showScreen('main');
    document.getElementById('tierBadge').textContent = 'guest';
    document.getElementById('tierBadge').className   = 'tier-badge guest';
    document.getElementById('usageWrap').style.display = 'none';
  });

  // ── Sign out ──
  document.getElementById('signOutBtn').addEventListener('click', function () {
    clearSession();
    document.getElementById('tokenInput').value = '';
    document.getElementById('resultText').textContent = 'Results will appear here…';
    showScreen('welcome');
  });

  // ── Analyze ──
  document.getElementById('analyzeBtn').addEventListener('click', function () {
    const input      = document.getElementById('userInput').value.trim();
    const resultText = document.getElementById('resultText');
    const analyzeBtn = this;

    if (!input) {
      resultText.textContent = 'Please enter a URL or claim first.';
      resultText.style.color = '#F59E0B';
      return;
    }

    resultText.textContent = 'Analyzing…';
    resultText.style.color = '#9490A8';
    analyzeBtn.disabled    = true;
    analyzeBtn.textContent = 'Analyzing…';

    getSession(function (sessionData) {
      const headers = {
        'Content-Type': 'application/json',
        'X-API-Key':    LUMIVEIL_KEY
      };
      if (sessionData.lv_token) {
        headers['Authorization'] = `Bearer ${sessionData.lv_token}`;
      }

      fetch(`${API_BASE}/api/v1/analyze`, {
        method:  'POST',
        headers: headers,
        body:    JSON.stringify({ input })
      })
      .then(r => r.json().then(d => ({ status: r.status, data: d })))
      .then(({ status, data }) => {
        analyzeBtn.disabled  = false;
        analyzeBtn.textContent = 'Analyze';

        if (status === 429) {
          resultText.textContent = data.reason || 'Daily limit reached. Upgrade to Pro for more.';
          resultText.style.color = '#F59E0B';
          return;
        }
        if (status === 403) {
          resultText.textContent = 'Image analysis is a Pro feature. Upgrade at lumiveil.com';
          resultText.style.color = '#F59E0B';
          return;
        }
        if (status !== 200) {
          resultText.textContent = data.error || 'Something went wrong.';
          resultText.style.color = '#EF4444';
          return;
        }

        resultText.textContent = data.summary;
        resultText.style.color = '#FFFFFF';
        chrome.storage.local.set({ lastResult: data });

        // Update usage bar
        if (sessionData.lv_token && data.remaining_today !== undefined) {
          const limits = { free: 30, pro: 300, max: 999999 };
          const limit  = limits[data.tier] || 30;
          updateUsageBar(limit - data.remaining_today, limit);
        }
      })
      .catch(() => {
        analyzeBtn.disabled    = false;
        analyzeBtn.textContent = 'Analyze';
        resultText.textContent = 'Could not connect to LumiVeil backend. Make sure Flask is running.';
        resultText.style.color = '#EF4444';
      });
    });
  });

  // Enter key in textarea
  document.getElementById('userInput').addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      document.getElementById('analyzeBtn').click();
    }
  });

  // Full report button
  document.getElementById('fullReportBtn').addEventListener('click', function () {
    chrome.tabs.create({ url: chrome.runtime.getURL('sidebar.html') });
  });

});

// Listen for openReport from content.js
chrome.runtime.onMessage.addListener(function (request) {
  if (request.action === 'openReport') {
    chrome.tabs.create({ url: chrome.runtime.getURL('sidebar.html') });
  }
});
