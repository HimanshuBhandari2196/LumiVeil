document.addEventListener('DOMContentLoaded', function () {

  const analyzeBtn = document.getElementById('analyzeBtn');
  const fullReportBtn = document.getElementById('fullReportBtn');
  const userInput = document.getElementById('userInput');
  const resultText = document.getElementById('resultText');

  analyzeBtn.addEventListener('click', function () {

    const input = userInput.value.trim();

    if (input === '') {
      resultText.textContent = 'Please enter a URL, link or claim to analyze.';
      resultText.style.color = '#f59e0b';
      return;
    }

    resultText.textContent = 'Analyzing... please wait.';
    resultText.style.color = '#a78bfa';
    analyzeBtn.disabled = true;
    analyzeBtn.textContent = 'Analyzing...';

    fetch('http://localhost:5000/analyze', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': 'lumiveil-secret-2026'
      },
      body: JSON.stringify({ input: input })
    })

    .then(response => {
      if (response.status === 429) {
        resultText.textContent = 'Too many requests - please wait a minute before trying again.';
        resultText.style.color = '#f59e0b';
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = 'Analyze';
        return null;
      }

      if (response.status === 401) {
        resultText.textContent = 'Unauthorized - Invalid API key.';
        resultText.style.color = '#ef4444';
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = 'Analyze';
        return null;
      }

      if (response.status === 400) {
        resultText.textContent = 'Invalid input - please check what you entered.';
        resultText.style.color = '#f59e0b';
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = 'Analyze';
        return null;
      }

      return response.json();
    })

    .then(data => {
      if (!data) return;

      resultText.textContent = data.summary;
      resultText.style.color = '#ffffff';

      chrome.storage.local.set({ lastResult: data });

      analyzeBtn.disabled = false;
      analyzeBtn.textContent = 'Analyze';
    })

    .catch(error => {
      resultText.textContent = 'Could not connect to LumiVeil backend. Make sure it is running.';
      resultText.style.color = '#ef4444';
      analyzeBtn.disabled = false;
      analyzeBtn.textContent = 'Analyze';
    });

  });

  fullReportBtn.addEventListener('click', function () {
    chrome.tabs.create({ url: chrome.runtime.getURL('sidebar.html') });
  });

});

chrome.runtime.onMessage.addListener(function (request) {
  if (request.action === 'openReport') {
    chrome.tabs.create({ url: chrome.runtime.getURL('sidebar.html') });
  }
});