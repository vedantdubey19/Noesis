const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const syncBtn = document.getElementById("syncBtn");
const searchBtn = document.getElementById("searchBtn");
const saveBtn = document.getElementById("saveBtn");
const apiUrlInput = document.getElementById("apiUrl");
const apiTokenInput = document.getElementById("apiToken");
const searchInput = document.getElementById("searchInput");

const DEFAULT_API_URL = "http://localhost:8000/api/context";

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0];
}

async function extractContext(tabId) {
  return chrome.tabs.sendMessage(tabId, { type: "EXTRACT_CONTEXT" });
}

function buildSearchUrl(apiUrl) {
  try {
    const parsed = new URL(apiUrl);
    parsed.pathname = "/api/search";
    return parsed.toString();
  } catch (_err) {
    return "http://localhost:8000/api/search";
  }
}

function renderCards(results) {
  resultsEl.innerHTML = "";
  if (!results || results.length === 0) {
    resultsEl.innerHTML = "<div class='snippet'>No relevant context found for this page</div>";
    return;
  }
  for (const item of results) {
    const sourceClass = item.source === "notion" ? "badge-notion" : "badge-gmail";
    const score = Math.round((item.score || 0) * 100);
    const strong = (item.score || 0) > 0.85 ? "<span class='strong'>strong match</span>" : "";
    const snippet = (item.text || "").slice(0, 200);
    const title = item.doc_title || "Untitled";
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="card-title">${title}</div>
      <div>
        <span class="badge ${sourceClass}">${item.source || "unknown"}</span>
        <span class="score">${score}%</span>
        ${strong}
      </div>
      <div class="snippet">${snippet}</div>
    `;
    resultsEl.appendChild(card);
  }
}

async function loadSettings() {
  const data = await chrome.storage.local.get(["apiUrl", "apiToken"]);
  apiUrlInput.value = data.apiUrl || DEFAULT_API_URL;
  apiTokenInput.value = data.apiToken || "";
}

saveBtn.addEventListener("click", async () => {
  await chrome.storage.local.set({
    apiUrl: apiUrlInput.value.trim(),
    apiToken: apiTokenInput.value.trim()
  });
  statusEl.textContent = "Settings saved";
});

syncBtn.addEventListener("click", async () => {
  statusEl.textContent = "Collecting page context...";
  try {
    const apiUrl = apiUrlInput.value.trim() || DEFAULT_API_URL;
    const apiToken = apiTokenInput.value.trim();
    if (!apiToken) {
      throw new Error("Set API token first");
    }

    const tab = await getActiveTab();
    const context = await extractContext(tab.id);

    statusEl.textContent = "Sending to backend...";
    const response = await fetch(apiUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiToken}`
      },
      body: JSON.stringify(context)
    });

    if (!response.ok) {
      throw new Error(`Request failed (${response.status})`);
    }
    const data = await response.json();
    statusEl.textContent = `Data synced for ${data.url}`;
    renderCards(data.context_cards || []);
  } catch (error) {
    statusEl.textContent = `Sync failed: ${error.message}`;
  }
});

searchBtn.addEventListener("click", async () => {
  statusEl.textContent = "Searching...";
  try {
    const apiUrl = apiUrlInput.value.trim() || DEFAULT_API_URL;
    const apiToken = apiTokenInput.value.trim();
    const query = searchInput.value.trim();
    if (!apiToken) {
      throw new Error("Set API token first");
    }
    if (!query) {
      throw new Error("Enter a search query");
    }

    const response = await fetch(buildSearchUrl(apiUrl), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiToken}`
      },
      body: JSON.stringify({ query, limit: 5 })
    });
    if (!response.ok) {
      throw new Error(`Search failed (${response.status})`);
    }
    const data = await response.json();
    renderCards(data);
    statusEl.textContent = `Found ${data.length} results`;
  } catch (error) {
    statusEl.textContent = `Search failed: ${error.message}`;
  }
});

loadSettings();
