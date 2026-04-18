const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const syncBtn = document.getElementById("syncBtn");
const searchBtn = document.getElementById("searchBtn");
const saveBtn = document.getElementById("saveBtn");
const apiUrlInput = document.getElementById("apiUrl");
const apiTokenInput = document.getElementById("apiToken");
const searchInput = document.getElementById("searchInput");

const DEFAULT_API_URL = "http://localhost:8000/api/context";

const ACTIVITY_STYLES = {
  decision: { bg: "#FAEEDA", color: "#633806", label: "Decision" },
  question: { bg: "#EEEDFE", color: "#3C3489", label: "Question" },
  task: { bg: "#E1F5EE", color: "#085041", label: "Task" },
  reference: { bg: "#F3F4F6", color: "#374151", label: "Reference" },
  reflection: { bg: "#FCE7F3", color: "#831843", label: "Reflection" }
};

const CARD_TYPE_LABELS = {
  past_decision: "Past decision",
  related_note: "Related note",
  open_question: "Open question",
  person_context: "Person context"
};

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

function showPipelineSkeleton() {
  resultsEl.innerHTML = `
    <div class="pipeline-meta skeleton-line"></div>
    <div class="card skeleton-card"><div class="skeleton-line short"></div><div class="skeleton-line"></div></div>
    <div class="card skeleton-card"><div class="skeleton-line short"></div><div class="skeleton-line"></div></div>
  `;
}

function activityBadge(activityType) {
  if (!activityType) return "";
  const key = String(activityType).toLowerCase();
  const st = ACTIVITY_STYLES[key] || ACTIVITY_STYLES.reference;
  return `<span class="activity-badge" style="background:${st.bg};color:${st.color}">${st.label}</span>`;
}

function formatFooter(latencyMs, cached) {
  const sec = typeof latencyMs === "number" ? (latencyMs / 1000).toFixed(1) : "—";
  const source = cached ? "from cache" : "live";
  return `Noesis · ${sec}s · ${source}`;
}

function renderPipelineResult(data) {
  resultsEl.innerHTML = "";
  const meta = document.createElement("div");
  meta.className = "pipeline-meta";

  const topic = data.topic ? `<span class="topic-pill">${escapeHtml(data.topic)}</span>` : "";
  meta.innerHTML = `${activityBadge(data.activity_type)} ${topic}`;

  const summary = (data.summary || "").trim();
  if (summary) {
    const sub = document.createElement("div");
    sub.className = "summary-sub";
    sub.textContent = summary;
    meta.appendChild(sub);
  }

  resultsEl.appendChild(meta);

  const cards = data.context_cards || [];
  if (cards.length === 0) {
    const empty = document.createElement("div");
    empty.className = "snippet muted";
    empty.textContent = summary || "No relevant context found for this page.";
    resultsEl.appendChild(empty);
  } else {
    for (const item of cards) {
      const sourceClass = item.source === "notion" ? "badge-notion" : "badge-gmail";
      const score = Math.round((item.relevance_score ?? item.score ?? 0) * 100);
      const cardType = item.card_type || "related_note";
      const typeLabel = CARD_TYPE_LABELS[cardType] || cardType;
      const title = item.doc_title || "Untitled";
      const snippet = (item.text || "").slice(0, 220);
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `
        <div class="card-type-label">${escapeHtml(typeLabel)}</div>
        <div class="card-title">${escapeHtml(title)}</div>
        <div>
          <span class="badge ${sourceClass}">${item.source || "unknown"}</span>
          <span class="score">${score}%</span>
        </div>
        <div class="snippet">${escapeHtml(snippet)}</div>
      `;
      resultsEl.appendChild(card);
    }
  }

  if (data.suggested_action) {
    const cta = document.createElement("div");
    cta.className = "suggested-action";
    cta.textContent = data.suggested_action;
    resultsEl.appendChild(cta);
  }

  const foot = document.createElement("div");
  foot.className = "popup-footer";
  foot.textContent = formatFooter(data.latency_ms, data.cached);
  resultsEl.appendChild(foot);
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function renderSearchCards(results) {
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
  showPipelineSkeleton();
  try {
    const apiUrl = apiUrlInput.value.trim() || DEFAULT_API_URL;
    const apiToken = apiTokenInput.value.trim();
    if (!apiToken) {
      throw new Error("Set API token first");
    }

    const tab = await getActiveTab();
    const context = await extractContext(tab.id);

    statusEl.textContent = "Running pipeline...";
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
    statusEl.textContent = "Ready";
    renderPipelineResult(data);
  } catch (error) {
    statusEl.textContent = `Sync failed: ${error.message}`;
    resultsEl.innerHTML = "";
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
    renderSearchCards(data);
    statusEl.textContent = `Found ${data.length} results`;
  } catch (error) {
    statusEl.textContent = `Search failed: ${error.message}`;
  }
});

loadSettings();
