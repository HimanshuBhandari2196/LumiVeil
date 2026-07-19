// ---- THEME TOGGLE ----
const themeToggle = document.getElementById('themeToggle');
const toggleText = document.getElementById('toggleText');
const toggleIcon = document.querySelector('.toggle-icon');

// Default is now dark — matches new design
const savedTheme = localStorage.getItem('lumiveil-theme') || 'dark';
if (savedTheme === 'light') {
  document.documentElement.setAttribute('data-theme', 'light');
  toggleText.textContent = 'Dark mode';
} else {
  document.documentElement.removeAttribute('data-theme');
  toggleText.textContent = 'Light mode';
}

themeToggle.addEventListener('click', function() {
  const current = document.documentElement.getAttribute('data-theme');
  if (current === 'light') {
    document.documentElement.removeAttribute('data-theme');
    toggleText.textContent = 'Light mode';
    localStorage.setItem('lumiveil-theme', 'dark');
  } else {
    document.documentElement.setAttribute('data-theme', 'light');
    toggleText.textContent = 'Dark mode';
    localStorage.setItem('lumiveil-theme', 'light');
  }
});

// ---- MAIN ----
document.addEventListener('DOMContentLoaded', function () {

  // ---- CONTENT TYPE TOGGLES ----
  document.querySelectorAll('.type-toggle').forEach(function(btn) {
    btn.addEventListener('click', function() {
      document.querySelectorAll('.type-toggle').forEach(function(b) {
        b.classList.remove('is-active');
      });
      this.classList.add('is-active');
      // Update placeholder based on type
      var type = this.dataset.type;
      var placeholders = {
        'url':    'Paste a news URL to verify…',
        'image':  'Paste an image URL to check for AI generation or deepfakes…',
        'social': 'Paste a social media post or claim to verify…'
      };
      document.getElementById('searchInput').placeholder = placeholders[type] || 'Paste a URL, image link, or type a claim…';
    });
  });

  const emptyState = document.getElementById('emptyState');
  const loadingState = document.getElementById('loadingState');
  const resultsSection = document.getElementById('resultsSection');
  const searchInput = document.getElementById('searchInput');
  const searchBtn = document.getElementById('searchBtn');
  const clearBtn = document.getElementById('clearBtn');
  const verdictBanner = document.getElementById('verdictBanner');

  // ---- DISPLAY RESULTS ----
  function displayResults(result) {
    verdictBanner.style.display = 'flex';
    verdictBanner.className = 'verdict-banner';

    const verdictIcon = document.getElementById('verdictIcon');
    const verdictText = document.getElementById('verdictText');

    if (result.verdict === 'fake') {
      verdictBanner.classList.add('verdict-fake');
      verdictIcon.textContent = 'FAKE';
      verdictText.textContent = 'Likely Fake';
    } else if (result.verdict === 'real') {
      verdictBanner.classList.add('verdict-real');
      verdictIcon.textContent = 'REAL';
      verdictText.textContent = 'Likely Real';
    } else if (result.verdict === 'unverified') {
      verdictBanner.classList.add('verdict-unverified');
      verdictIcon.textContent = 'UNVERIFIED';
      verdictText.textContent = 'Not Enough Evidence — Can\'t Confirm Either Way';
    } else {
      verdictBanner.classList.add('verdict-mixed');
      verdictIcon.textContent = 'MIXED';
      verdictText.textContent = 'Mixed — Needs Caution';
    }

    const score = result.trust_score || 0;
    const trustScore = document.getElementById('trustScore');
    const trustBarFill = document.getElementById('trustBarFill');
    const trustLabel = document.getElementById('trustLabel');
    const trustPreviewText = document.getElementById('trustPreviewText');
    const trustDot = document.getElementById('trustDot');
    const checksPreviewText = document.getElementById('checksPreviewText');

    trustScore.innerHTML = score + ' <span>/ 100</span>';
    trustBarFill.style.width = score + '%';
    trustBarFill.className = 'trust-bar-fill';

    if (result.verdict === 'unverified') {
      // A neutral score here doesn't mean "somewhat credible" — it means
      // there was nothing to check it against. Say that plainly instead
      // of reusing the "mixed credibility" label the number would imply.
      trustBarFill.classList.add('trust-medium');
      trustLabel.textContent = 'Not enough evidence to verify';
      trustLabel.style.color = '#9490A8';
      trustPreviewText.textContent = 'Not enough evidence available';
      trustDot.style.background = '#9490A8';
    } else if (score >= 70) {
      trustBarFill.classList.add('trust-high');
      trustLabel.textContent = 'High credibility';
      trustLabel.style.color = '#22c55e';
      trustPreviewText.textContent = score + '/100 — High credibility';
      trustDot.style.background = '#22c55e';
    } else if (score >= 40) {
      trustBarFill.classList.add('trust-medium');
      trustLabel.textContent = 'Mixed credibility';
      trustLabel.style.color = '#f59e0b';
      trustPreviewText.textContent = score + '/100 — Mixed credibility';
      trustDot.style.background = '#f59e0b';
    } else {
      trustBarFill.classList.add('trust-low');
      trustLabel.textContent = 'Low credibility';
      trustLabel.style.color = '#ef4444';
      trustPreviewText.textContent = score + '/100 — Low credibility';
      trustDot.style.background = '#ef4444';
    }

    document.getElementById('summaryText').textContent = result.summary || 'No summary available.';

    const checksList = document.getElementById('checksList');
    checksList.innerHTML = '';
    if (result.checks && result.checks.length > 0) {
      // Backend prefixes real concerns with ❌ (hard flag), ⚠️ (warning),
      // or 🚩 (AI fact-check's own red_flags list) — ✅/ℹ️/🔍/💭 etc. are
      // neutral/positive status lines, not red flags.
      const flagCount = result.checks.filter(c => c.includes('❌') || c.includes('⚠️') || c.includes('🚩')).length;
      checksPreviewText.textContent = result.checks.length + ' checks — ' + flagCount + (flagCount === 1 ? ' red flag' : ' red flags');
      result.checks.forEach(function (check) {
        const li = document.createElement('li');
        li.textContent = check;
        checksList.appendChild(li);
      });
    } else {
      checksList.innerHTML = '<li>No checks available.</li>';
    }

    document.getElementById('realText').textContent = result.real_info || 'No verified information available.';

    const sourcesList = document.getElementById('sourcesList');
    sourcesList.innerHTML = '';
    if (result.sources && result.sources.length > 0) {
      result.sources.forEach(function (source) {
        const li = document.createElement('li');
        // Real fact-check results are full URLs; the generic fallback list
        // is bare domain names (e.g. "reuters.com") — link both correctly.
        const isUrl = /^https?:\/\//i.test(source);
        const href  = isUrl ? source : `https://${source}`;
        const a = document.createElement('a');
        a.href = href;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        a.textContent = source;
        li.appendChild(a);
        sourcesList.appendChild(li);
      });
    } else {
      sourcesList.innerHTML = '<li>No sources checked.</li>';
    }

    resultsSection.classList.add('visible');
    emptyState.style.display = 'none';
    loadingState.classList.remove('visible');
  }

  // ---- SEARCH FUNCTION ----
  function performSearch(input) {
    if (!input || input.trim() === '') return;

    emptyState.style.display = 'none';
    resultsSection.classList.remove('visible');
    verdictBanner.style.display = 'none';
    loadingState.classList.add('visible');
    searchBtn.disabled = true;
    searchBtn.textContent = 'Analyzing...';

    // Pull token from storage so usage is tracked for logged-in users
    chrome.storage.local.get(['lv_token'], function (sessionData) {
      const headers = {
        'Content-Type': 'application/json',
        'X-API-Key': 'lumiveil-secret-2026'
      };
      if (sessionData.lv_token) {
        headers['Authorization'] = 'Bearer ' + sessionData.lv_token;
      }

      fetch('https://lumiveil-api-production-8706.up.railway.app/api/v1/analyze', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ input: input.trim(), locale: navigator.language || '' })
      })
      .then(function(response) {
        return response.json().then(function(d) { return { status: response.status, data: d }; });
      })
      .then(function({ status, data }) {
        searchBtn.disabled = false;
        searchBtn.textContent = 'Analyze';

        if (status === 429) {
          loadingState.classList.remove('visible');
          emptyState.style.display = 'block';
          emptyState.querySelector('h2').textContent = 'Daily limit reached';
          emptyState.querySelector('p').textContent = data.reason || 'Upgrade to Pro for more analyses.';
          return;
        }
        if (status === 403) {
          loadingState.classList.remove('visible');
          emptyState.style.display = 'block';
          emptyState.querySelector('h2').textContent = 'Pro feature';
          emptyState.querySelector('p').textContent = data.reason || 'Image analysis requires a Pro plan.';
          return;
        }

        chrome.storage.local.set({ lastResult: data });
        displayResults(data);
      })
      .catch(function() {
        loadingState.classList.remove('visible');
        searchBtn.disabled = false;
        searchBtn.textContent = 'Analyze';
        emptyState.style.display = 'block';
        emptyState.querySelector('h2').textContent = 'Could not connect to backend';
        emptyState.querySelector('p').textContent = 'Make sure the LumiVeil backend is running.';
      });
    });
  }

  // ---- SEARCH BUTTON ----
  searchBtn.addEventListener('click', function () {
    performSearch(searchInput.value);
  });

  // ---- ENTER KEY ----
  searchInput.addEventListener('keypress', function (e) {
    if (e.key === 'Enter') {
      performSearch(searchInput.value);
    }
  });

  // ---- CLEAR BUTTON ----
  clearBtn.addEventListener('click', function () {
    searchInput.value = '';
    chrome.storage.local.remove('lastResult');
    resultsSection.classList.remove('visible');
    verdictBanner.style.display = 'none';
    loadingState.classList.remove('visible');
    emptyState.style.display = 'block';
    emptyState.querySelector('h2').textContent = 'Lift the veil on fake content';
    emptyState.querySelector('p').textContent = 'Paste a URL, image link, or type a claim above to start analyzing';
  });

  // ---- LOAD EXISTING RESULT FROM POPUP ----
  chrome.storage.local.get('lastResult', function (data) {
    if (data.lastResult) {
      displayResults(data.lastResult);
    }
  });

});