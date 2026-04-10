let currentWindow = "1h";
let selectedTicker = null;
let detailChart = null;
let refreshTimer = null;

const CUSTOM_STORAGE_KEY = "sc_custom_tickers";

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".tab").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentWindow = btn.dataset.window;
      loadTickers();
    });
  });

  document.getElementById("scan-btn").addEventListener("click", triggerScan);

  // Custom watchlist panel — opened from the pane's Edit button
  document.getElementById("custom-watchlist-btn").addEventListener("click", openCustomPanel);
  document.getElementById("custom-close").addEventListener("click", closeCustomPanel);
  document.getElementById("custom-overlay").addEventListener("click", closeCustomPanel);
  initCustomSearch();
  syncCustomFromStorage();   // push stored tickers to server on load

  loadStatus();
  loadWatchlist();
  loadTickers();
  scheduleRefresh();
});

function scheduleRefresh() {
  clearInterval(refreshTimer);
  refreshTimer = setInterval(() => {
    loadStatus();
    loadTickers();
    if (selectedTicker) loadDetail(selectedTicker);
  }, 60_000);
}

// ── API helpers ───────────────────────────────────────────────────────────────
async function apiFetch(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// ── Status bar ────────────────────────────────────────────────────────────────
async function loadStatus() {
  try {
    const data = await apiFetch("/api/scan/status");
    document.getElementById("kpi-tickers").textContent = data.total_tickers_tracked ?? "—";
    document.getElementById("kpi-posts").textContent =
      (data.total_posts_in_db ?? 0).toLocaleString();

    const scan = data.last_scan;
    if (scan?.finished_at) {
      const diff = Math.round((Date.now() - new Date(scan.finished_at + "Z")) / 60_000);
      document.getElementById("last-scan").textContent =
        diff <= 1 ? "Last scan: just now" : `Last scan: ${diff}m ago`;
    } else {
      document.getElementById("last-scan").textContent = "No scans yet";
    }
  } catch {
    document.getElementById("last-scan").textContent = "Status unavailable";
  }
}

// ── Watchlist strip ───────────────────────────────────────────────────────────
async function loadWatchlist() {
  try {
    const data = await apiFetch("/api/watchlist");
    const container = document.getElementById("watchlist-chips");

    container.innerHTML = data.tickers.map(({ rank, ticker, change_pct, price_source }) => {
      const hasPct = change_pct !== null && change_pct !== undefined;
      const sign = hasPct && change_pct >= 0 ? "+" : "";
      const pctClass = !hasPct ? "" : change_pct >= 0 ? "wl-up" : "wl-down";
      const pctLabel = hasPct
        ? `<span class="wl-pct ${pctClass}">${sign}${change_pct}%</span>`
        : "";
      const srcBadge = price_source === "premarket"
        ? `<span class="wl-src-badge">PM</span>`
        : "";
      return `
        <span class="wl-chip" data-ticker="${ticker}">
          <span class="wl-rank">#${rank}</span>${ticker}${pctLabel}${srcBadge}
        </span>`;
    }).join("");

    container.querySelectorAll(".wl-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        window.open(`https://finance.yahoo.com/quote/${chip.dataset.ticker}`, "_blank", "noopener");
      });
    });

    if (data.last_refreshed) {
      const diff = Math.round((Date.now() - new Date(data.last_refreshed + "Z")) / 60_000);
      document.getElementById("watchlist-refreshed").textContent =
        `Updated ${diff <= 1 ? "just now" : diff + "m ago"}`;
    }
  } catch {
    document.getElementById("watchlist-chips").innerHTML =
      `<span class="watchlist-loading">Watchlist unavailable</span>`;
  }
}

// ── Ticker table ──────────────────────────────────────────────────────────────
async function loadTickers() {
  try {
    const tickers = await apiFetch(`/api/tickers?window=${currentWindow}&limit=25`);
    renderTable(tickers);

    const bullish = tickers.filter(t => t.sentiment_score > 0.1)
      .sort((a, b) => b.sentiment_score - a.sentiment_score);
    const bearish = tickers.filter(t => t.sentiment_score < -0.1)
      .sort((a, b) => a.sentiment_score - b.sentiment_score);
    document.getElementById("kpi-bullish").textContent = bullish[0]?.ticker ?? "—";
    document.getElementById("kpi-bearish").textContent = bearish[0]?.ticker ?? "—";
  } catch (err) {
    document.getElementById("ticker-tbody").innerHTML =
      `<tr><td colspan="7" class="loading">Error loading data: ${err.message}</td></tr>`;
  }
}

function renderTable(tickers) {
  const tbody = document.getElementById("ticker-tbody");
  if (!tickers.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="loading">No data for this window — trigger a scan first.</td></tr>`;
    return;
  }

  tbody.innerHTML = tickers.map((t, i) => {
    const scoreClass = t.sentiment_score > 0.1 ? "score-bullish"
                     : t.sentiment_score < -0.1 ? "score-bearish"
                     : "score-neutral";
    const scoreLabel = t.sentiment_score > 0.1 ? `+${(t.sentiment_score * 100).toFixed(0)}`
                     : (t.sentiment_score * 100).toFixed(0);
    const isSelected = t.ticker === selectedTicker ? "selected" : "";
    return `
      <tr class="${isSelected}" data-ticker="${t.ticker}">
        <td class="rank">${i + 1}</td>
        <td><span class="ticker-symbol">${t.ticker}</span></td>
        <td class="mention-count">${t.mention_count}</td>
        <td class="bullish-pct">${t.bullish_pct}%</td>
        <td class="bearish-pct">${t.bearish_pct}%</td>
        <td>
          <div class="sentiment-bar-wrap">
            <div class="bar-bullish" style="width:${t.bullish_pct}%"></div>
            <div class="bar-bearish" style="width:${t.bearish_pct}%"></div>
          </div>
        </td>
        <td><span class="score-badge ${scoreClass}">${scoreLabel}</span></td>
      </tr>`;
  }).join("");

  tbody.querySelectorAll("tr[data-ticker]").forEach(row => {
    row.addEventListener("click", () => {
      selectedTicker = row.dataset.ticker;
      tbody.querySelectorAll("tr").forEach(r => r.classList.remove("selected"));
      row.classList.add("selected");
      loadDetail(selectedTicker);
    });
  });
}

// ── Detail panel ──────────────────────────────────────────────────────────────
async function loadDetail(ticker) {
  try {
    const data = await apiFetch(`/api/tickers/${ticker}?limit=20`);
    renderDetail(data);
  } catch (err) {
    console.error("Detail load failed:", err);
  }
}

function renderDetail(data) {
  document.querySelector(".detail-placeholder").style.display = "none";
  const content = document.querySelector(".detail-content");
  content.style.display = "block";

  document.getElementById("detail-ticker").textContent = `$${data.ticker}`;

  // Donut chart
  const s = data.summary;
  const ctx = document.getElementById("detail-chart").getContext("2d");
  if (detailChart) detailChart.destroy();
  detailChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["Bullish", "Bearish", "Neutral"],
      datasets: [{
        data: [s.bullish_count || 0, s.bearish_count || 0, s.neutral_count || 0],
        backgroundColor: ["#22c55e", "#ef4444", "#374151"],
        borderWidth: 0,
      }],
    },
    options: {
      cutout: "65%",
      plugins: {
        legend: {
          position: "right",
          labels: { color: "#6b6e82", font: { size: 11 }, padding: 8, boxWidth: 10 },
        },
      },
    },
  });

  // Posts list
  const list = document.getElementById("detail-posts");
  if (!data.posts.length) {
    list.innerHTML = `<li style="color:var(--muted);font-size:13px">No posts found.</li>`;
  } else {
    list.innerHTML = data.posts.map(p => {
      const ts = p.published_at || p.created_at;
      const timeLabel = ts ? fmtDatetime(ts) : "";
      return `
      <li class="post-item">
        <div class="post-meta">
          <span class="post-source">${p.source}</span>
          <span class="post-sentiment sent-${p.sentiment}">${p.sentiment}</span>
          <span class="post-confidence">${Math.round(p.confidence * 100)}% conf.</span>
          ${timeLabel ? `<span class="post-time">${timeLabel}</span>` : ""}
        </div>
        <div class="post-text">${escHtml(p.text)}</div>
        ${p.reason ? `<div class="post-reason">${escHtml(p.reason)}</div>` : ""}
        ${p.url ? `<a class="post-link" href="${p.url}" target="_blank" rel="noopener">View post ↗</a>` : ""}
      </li>`;
    }).join("");
  }

  // Lazy-load strategy card
  loadStrategy(data.ticker);
}

// ── Strategy card ─────────────────────────────────────────────────────────────
async function loadStrategy(ticker) {
  const card = document.getElementById("strategy-card");
  const loading = document.getElementById("strategy-loading");
  const body = document.getElementById("strategy-body");

  card.style.display = "block";
  loading.style.display = "block";
  loading.textContent = "Analyzing…";
  body.style.display = "none";

  try {
    const s = await apiFetch(`/api/tickers/${ticker}/strategy`);
    document.getElementById("strategy-action").textContent = s.action;
    document.getElementById("strategy-action").className =
      `strategy-action action-${(s.action || "wait").toLowerCase()}`;
    document.getElementById("strategy-rationale").textContent = s.rationale || "";
    document.getElementById("strategy-entry").textContent = s.entry_signal || "—";
    document.getElementById("strategy-exit").textContent = s.exit_signal || "—";
    document.getElementById("strategy-risk").textContent = s.risk_level || "—";
    loading.style.display = "none";
    body.style.display = "block";
  } catch {
    loading.textContent = "Strategy unavailable";
  }
}

// ── Custom watchlist panel ────────────────────────────────────────────────────
function openCustomPanel() {
  document.getElementById("custom-panel").classList.add("open");
  document.getElementById("custom-overlay").classList.add("open");
  renderCustomList();
}

function closeCustomPanel() {
  document.getElementById("custom-panel").classList.remove("open");
  document.getElementById("custom-overlay").classList.remove("open");
  document.getElementById("custom-search").value = "";
  document.getElementById("custom-search-results").innerHTML = "";
}

function getStoredCustom() {
  try { return JSON.parse(localStorage.getItem(CUSTOM_STORAGE_KEY) || "[]"); }
  catch { return []; }
}

function saveStoredCustom(tickers) {
  localStorage.setItem(CUSTOM_STORAGE_KEY, JSON.stringify(tickers));
}

async function syncCustomToApi(tickers) {
  try {
    await apiFetch("/api/watchlist/custom", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tickers }),
    });
  } catch (err) {
    console.warn("Failed to sync custom watchlist:", err);
  }
}

async function syncCustomFromStorage() {
  const stored = getStoredCustom();
  if (stored.length) await syncCustomToApi(stored);
  renderCustomList();
  renderCustomPane();
}

function renderCustomList() {
  const tickers = getStoredCustom();
  const list = document.getElementById("custom-list");
  const countEl = document.getElementById("custom-count");
  countEl.textContent = tickers.length;

  if (!tickers.length) {
    list.innerHTML = `<li class="custom-empty">No tickers added yet.</li>`;
    return;
  }

  list.innerHTML = tickers.map(t => `
    <li class="custom-item">
      <span class="custom-item-ticker">${t}</span>
      <button class="custom-remove-btn" data-ticker="${t}">✕</button>
    </li>`).join("");

  list.querySelectorAll(".custom-remove-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const t = btn.dataset.ticker;
      const updated = getStoredCustom().filter(x => x !== t);
      saveStoredCustom(updated);
      await syncCustomToApi(updated);
      renderCustomList();
      renderCustomPane();
    });
  });
}

function addCustomTicker(ticker) {
  ticker = ticker.toUpperCase().trim();
  if (!ticker) return;
  const current = getStoredCustom();
  if (current.includes(ticker)) return;
  if (current.length >= 10) {
    alert("Custom watchlist is capped at 10 tickers.");
    return;
  }
  const updated = [...current, ticker];
  saveStoredCustom(updated);
  syncCustomToApi(updated);
  renderCustomList();
  renderCustomPane();
}

// ── Custom watchlist pane (inline, below the volatile stocks pane) ─────────────
async function renderCustomPane() {
  const tickers = getStoredCustom();
  const container = document.getElementById("custom-pane-chips");

  if (!tickers.length) {
    container.innerHTML = `<span class="watchlist-loading">No tickers added — click Edit to add some.</span>`;
    document.getElementById("custom-pane-refreshed").textContent = "";
    return;
  }

  container.innerHTML = `<span class="watchlist-loading">Fetching prices…</span>`;

  let priceMap = {};
  try {
    priceMap = await apiFetch("/api/prices/custom");
  } catch { /* prices unavailable — chips show without % */ }

  container.innerHTML = tickers.map((ticker, i) => {
    const p = priceMap[ticker];
    const hasPct = p && p.change_pct !== null && p.change_pct !== undefined;
    const sign = hasPct && p.change_pct >= 0 ? "+" : "";
    const pctClass = !hasPct ? "" : p.change_pct >= 0 ? "wl-up" : "wl-down";
    const pctLabel = hasPct
      ? `<span class="wl-pct ${pctClass}">${sign}${p.change_pct}%</span>`
      : "";
    const srcBadge = p?.source === "premarket"
      ? `<span class="wl-src-badge">PM</span>`
      : "";
    return `
      <span class="wl-chip" data-ticker="${ticker}">
        <span class="wl-rank">#${i + 1}</span>${ticker}${pctLabel}${srcBadge}
      </span>`;
  }).join("");

  const now = new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  document.getElementById("custom-pane-refreshed").textContent = `Updated ${now}`;

  container.querySelectorAll(".wl-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      window.open(`https://finance.yahoo.com/quote/${chip.dataset.ticker}`, "_blank", "noopener");
    });
  });
}

let _searchDebounce = null;

function initCustomSearch() {
  const input = document.getElementById("custom-search");
  const results = document.getElementById("custom-search-results");

  input.addEventListener("input", () => {
    clearTimeout(_searchDebounce);
    const q = input.value.trim();
    if (q.length < 1) { results.innerHTML = ""; return; }
    _searchDebounce = setTimeout(async () => {
      try {
        const data = await apiFetch(`/api/search/tickers?q=${encodeURIComponent(q)}`);
        const stored = getStoredCustom();
        results.innerHTML = data.results.map(t => {
          const added = stored.includes(t);
          return `<li class="custom-result-item ${added ? "already-added" : ""}" data-ticker="${t}">
            ${t}${added ? ' <span class="custom-added-tag">added</span>' : ""}
          </li>`;
        }).join("");
        results.querySelectorAll(".custom-result-item:not(.already-added)").forEach(li => {
          li.addEventListener("click", () => {
            addCustomTicker(li.dataset.ticker);
            input.value = "";
            results.innerHTML = "";
          });
        });
      } catch { results.innerHTML = ""; }
    }, 250);
  });

  // Close dropdown when clicking outside
  document.addEventListener("click", (e) => {
    if (!input.contains(e.target) && !results.contains(e.target)) {
      results.innerHTML = "";
    }
  });
}

// ── Manual scan ───────────────────────────────────────────────────────────────
async function triggerScan() {
  const btn = document.getElementById("scan-btn");
  btn.disabled = true;
  btn.textContent = "Scanning…";
  try {
    await fetch("/api/scan/trigger", { method: "POST" });
    document.getElementById("last-scan").textContent = "Scan running…";
    let polls = 0;
    const poll = setInterval(async () => {
      polls++;
      await loadStatus();
      loadTickers();
      if (polls >= 30) {
        clearInterval(poll);
        btn.disabled = false;
        btn.textContent = "Scan Now";
      }
    }, 5_000);
  } catch {
    btn.disabled = false;
    btn.textContent = "Scan Now";
  }
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function escHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function fmtDatetime(iso) {
  try {
    const d = new Date(iso.includes("Z") || iso.includes("+") ? iso : iso + "Z");
    return d.toLocaleString(undefined, {
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return ""; }
}
