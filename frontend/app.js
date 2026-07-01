// frontend/app.js
const API_BASE = "";

const qInput = document.getElementById("q");
const searchBtn = document.getElementById("searchBtn");
const resultsDiv = document.getElementById("results");
const suggestionsDiv = document.getElementById("suggestions");

let debounceTimer = null;

qInput.addEventListener("input", (e) => {
  const v = e.target.value.trim();
  if (debounceTimer) clearTimeout(debounceTimer);
  if (!v) {
    suggestionsDiv.textContent = "";
    return;
  }
  debounceTimer = setTimeout(() => {
    fetchSuggestions(v);
  }, 200);
});

searchBtn.addEventListener("click", () => {
  const q = qInput.value.trim();
  if (q) doSearch(q);
});

qInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const q = qInput.value.trim();
    if (q) doSearch(q);
  }
});

async function fetchSuggestions(q) {
  // Lightweight suggestion: call /search with small limit and show titles
  try {
    const res = await fetch(`/search?q=${encodeURIComponent(q)}&limit=5`);
    if (!res.ok) {
      suggestionsDiv.textContent = "No suggestions";
      return;
    }
    const data = await res.json();
    const hits = data.hits || data.hits || [];
    suggestionsDiv.innerHTML = hits.map(h => `<div>${escapeHtml(h.title || h.url)}</div>`).join("");
  } catch (e) {
    suggestionsDiv.textContent = "Suggestions unavailable";
  }
}

async function doSearch(q) {
  resultsDiv.innerHTML = "<p>Searching…</p>";
  try {
    const res = await fetch(`/search?q=${encodeURIComponent(q)}&limit=20`);
    if (!res.ok) {
      resultsDiv.innerHTML = `<p>Error: ${res.statusText}</p>`;
      return;
    }
    const data = await res.json();
    const hits = data.hits || [];
    if (!hits.length) {
      resultsDiv.innerHTML = "<p>No results</p>";
      return;
    }
    resultsDiv.innerHTML = hits.map(renderHit).join("");
  } catch (e) {
    resultsDiv.innerHTML = `<p>Search failed: ${e.message}</p>`;
  }
}

function renderHit(h) {
  const title = escapeHtml(h.title || h.url);
  const url = escapeHtml(h.url);
  const snippet = escapeHtml((h.content || "").slice(0, 400));
  return `<div class="result"><h3><a href="${url}" target="_blank" rel="noopener">${title}</a></h3><p>${snippet}</p><small>${url}</small></div>`;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (m) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}
