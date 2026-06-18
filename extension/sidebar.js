// ---- THEME TOGGLE ----
const themeToggle = document.getElementById('themeToggle');
const toggleText = document.getElementById('toggleText');
const toggleIcon = document.querySelector('.toggle-icon');

const savedTheme = localStorage.getItem('lumiveil-theme') || 'light';
if (savedTheme === 'dark') {
  document.documentElement.setAttribute('data-theme', 'dark');
  toggleText.textContent = 'Light mode';
  toggleIcon.textContent = '☀️';
}

themeToggle.addEventListener('click', function() {
  const current = document.documentElement.getAttribute('data-theme');
  if (current === 'dark') {
    document.documentElement.removeAttribute('data-theme');
    toggleText.textContent = 'Dark mode';
    toggleIcon.textContent = '🌙';
    localStorage.setItem('lumiveil-theme', 'light');
  } else {
    document.documentElement.setAttribute('data-theme', 'dark');
    toggleText.textContent = 'Light mode';
    toggleIcon.textContent = '☀️';
    localStorage.setItem('lumiveil-theme', 'dark');
  }
});

// ---- MAIN ----
document.addEventListener('DOMContentLoaded', function () {

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

    if (score >= 70) {
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
      const flagCount = result.checks.filter(c => c.includes('X')).length;
      checksPreviewText.textContent = result.checks.length + ' checks — ' + flagCount + ' red flags';
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
        li.textContent = source;
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

    fetch('http://localhost:5000/analyze', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': 'lumiveil-secret-2026'
      },
      body: JSON.stringify({ input: input.trim() })
    })
    .then(response => response.json())
    .then(data => {
      chrome.storage.local.set({ lastResult: data });
      searchBtn.disabled = false;
      searchBtn.textContent = 'Analyze';
      displayResults(data);
    })
    .catch(error => {
      loadingState.classList.remove('visible');
      searchBtn.disabled = false;
      searchBtn.textContent = 'Analyze';
      emptyState.style.display = 'block';
      emptyState.querySelector('h2').textContent = 'Could not connect to backend';
      emptyState.querySelector('p').textContent = 'Make sure the LumiVeil backend is running.';
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