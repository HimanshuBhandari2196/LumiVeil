const API_BASE     = 'https://lumiveil-api-production-8706.up.railway.app';
const LUMIVEIL_KEY = 'lumiveil-secret-2026';
const WEBSITE_URL  = 'https://himanshubhandari2196.github.io/LumiVeil';

// ============================================================
// SCREEN MANAGEMENT
// ============================================================

function showScreen(name) {
  ['welcomeScreen', 'waitingScreen', 'mainScreen'].forEach(function(id) {
    document.getElementById(id).style.display = (id === name + 'Screen') ? 'block' : 'none';
  });
}

// ============================================================
// SESSION STORAGE
// ============================================================

function saveSession(token, user, refreshToken) {
  const data = { lv_token: token, lv_user: user };
  if (refreshToken) data.lv_refresh_token = refreshToken;
  chrome.storage.local.set(data);
}

function clearSession() {
  chrome.storage.local.remove(['lv_token', 'lv_user', 'lv_refresh_token', 'lastResult']);
}

function getSession(cb) {
  chrome.storage.local.get(['lv_token', 'lv_user', 'lv_refresh_token'], cb);
}

// ============================================================
// SILENT TOKEN REFRESH
// ============================================================

function silentRefresh(callback) {
  getSession(function (session) {
    if (!session.lv_refresh_token) { callback(null); return; }
    fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': LUMIVEIL_KEY },
      body:    JSON.stringify({ refresh_token: session.lv_refresh_token })
    })
    .then(r => r.json().then(d => ({ status: r.status, data: d })))
    .then(({ status, data }) => {
      if (status === 200 && data.token) {
        chrome.storage.local.set({ lv_token: data.token });
        callback(data.token);
      } else {
        clearSession();
        callback(null);
      }
    })
    .catch(() => callback(null));
  });
}

function authedFetch(url, options, onResult) {
  fetch(url, options)
    .then(r => r.json().then(d => ({ status: r.status, data: d })))
    .then(({ status, data }) => {
      if (status === 401) {
        silentRefresh(function (newToken) {
          if (!newToken) { onResult({ status: 401, data }); return; }
          const retryOpts = Object.assign({}, options, {
            headers: Object.assign({}, options.headers, { 'Authorization': `Bearer ${newToken}` })
          });
          fetch(url, retryOpts)
            .then(r2 => r2.json().then(d2 => ({ status: r2.status, data: d2 })))
            .then(onResult)
            .catch(() => onResult({ status: 0, data: { error: 'Network error' } }));
        });
      } else {
        onResult({ status, data });
      }
    })
    .catch(() => onResult({ status: 0, data: { error: 'Network error' } }));
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
  authedFetch(`${API_BASE}/api/v1/user/status`, {
    headers: { 'Authorization': `Bearer ${token}`, 'X-API-Key': LUMIVEIL_KEY }
  }, function ({ status, data }) {
    if (status === 401) { clearSession(); showScreen('welcome'); return; }
    if (data.usage) {
      const used  = typeof data.usage.today === 'number' ? data.usage.today : 0;
      const limit = typeof data.usage.limit === 'number' ? data.usage.limit : 30;
      setTimeout(function() { updateUsageBar(used, limit); }, 100);
    }
    if (data.user) {
      const badge = document.getElementById('tierBadge');
      if (badge) { badge.textContent = data.user.tier || 'free'; badge.className = 'tier-badge ' + (data.user.tier || 'free'); }
      chrome.storage.local.set({ lv_user: data.user });
    }
  });
}

// ============================================================
// LISTEN FOR LOGIN MESSAGE FROM WEBSITE
// The website sends tokens here directly after sign-in —
// no copy-paste needed. background.js receives the external
// message and stores it; we poll storage here to detect it.
// ============================================================

let loginPollInterval = null;

function startLoginPoll() {
  // Poll chrome.storage every second to detect when background.js
  // has received and stored the login tokens from the website
  loginPollInterval = setInterval(function() {
    getSession(function(data) {
      if (data.lv_token && data.lv_user) {
        stopLoginPoll();
        showMainScreen(data.lv_token, data.lv_user);
      }
    });
  }, 1000);
}

function stopLoginPoll() {
  if (loginPollInterval) {
    clearInterval(loginPollInterval);
    loginPollInterval = null;
  }
}

function showMainScreen(token, user) {
  showScreen('main');
  const badge = document.getElementById('tierBadge');
  if (badge) {
    badge.textContent = user.tier || 'free';
    badge.className   = 'tier-badge ' + (user.tier || 'free');
  }
  fetchAndUpdateUsage(token);
}

// ============================================================
// MAIN
// ============================================================

document.addEventListener('DOMContentLoaded', function () {

  // Check for existing session on open
  getSession(function (data) {
    if (data.lv_token && data.lv_user && !data.lv_user.guest) {
      showMainScreen(data.lv_token, data.lv_user);
    } else if (data.lv_user && data.lv_user.guest) {
      showScreen('main');
      const badge = document.getElementById('tierBadge');
      if (badge) { badge.textContent = 'guest'; badge.className = 'tier-badge guest'; }
      document.getElementById('usageWrap').style.display = 'none';
    } else {
      showScreen('welcome');
    }
  });

  // ── Sign in button → open website in new tab + show waiting screen ──
  document.getElementById('signInBtn').addEventListener('click', function () {
    chrome.tabs.create({ url: `${WEBSITE_URL}?lumiveil_signin=1` });
    showScreen('waiting');
    startLoginPoll();
  });

  // ── Cancel waiting ──
  document.getElementById('cancelWaitBtn').addEventListener('click', function () {
    stopLoginPoll();
    showScreen('welcome');
  });

  // ── Guest mode ──
  document.getElementById('guestBtn').addEventListener('click', function () {
    clearSession();
    chrome.storage.local.set({ lv_user: { guest: true } });
    showScreen('main');
    const badge = document.getElementById('tierBadge');
    if (badge) { badge.textContent = 'guest'; badge.className = 'tier-badge guest'; }
    document.getElementById('usageWrap').style.display = 'none';
  });

  // ── Sign out ──
  document.getElementById('signOutBtn').addEventListener('click', function () {
    getSession(function (session) {
      if (session.lv_refresh_token) {
        fetch(`${API_BASE}/api/v1/auth/logout`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json', 'X-API-Key': LUMIVEIL_KEY },
          body:    JSON.stringify({ refresh_token: session.lv_refresh_token })
        }).catch(() => {});
      }
      clearSession();
      document.getElementById('resultText').textContent = 'Results will appear here…';
      showScreen('welcome');
    });
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
      const headers = { 'Content-Type': 'application/json', 'X-API-Key': LUMIVEIL_KEY };
      if (sessionData.lv_token) headers['Authorization'] = `Bearer ${sessionData.lv_token}`;

      authedFetch(`${API_BASE}/api/v1/analyze`, {
        method: 'POST', headers, body: JSON.stringify({ input, locale: navigator.language || '' })
      }, function ({ status, data }) {
        analyzeBtn.disabled    = false;
        analyzeBtn.textContent = 'Analyze';

        if (status === 429) { resultText.textContent = data.reason || 'Daily limit reached.'; resultText.style.color = '#F59E0B'; return; }
        if (status === 403) { resultText.textContent = 'Image analysis is a Pro feature.'; resultText.style.color = '#F59E0B'; return; }
        if (status === 401) { resultText.textContent = 'Session expired. Please sign in again.'; resultText.style.color = '#F59E0B'; clearSession(); return; }
        if (status !== 200) { resultText.textContent = data.error || 'Something went wrong.'; resultText.style.color = '#EF4444'; return; }

        resultText.textContent = data.summary;
        resultText.style.color = '#FFFFFF';
        chrome.storage.local.set({ lastResult: data });

        if (sessionData.lv_token && data.remaining_today !== undefined) {
          const limits = { free: 30, pro: 300, max: 999999 };
          const limit  = limits[data.tier] || 30;
          updateUsageBar(limit - data.remaining_today, limit);
        }
      });
    });
  });

  // Enter key in textarea
  document.getElementById('userInput').addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); document.getElementById('analyzeBtn').click(); }
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
