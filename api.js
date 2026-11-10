/**
 * api.js - Client-Side Data Fetcher and DOM Manipulator
 * Communicates with FastAPI backend (/auth, /api/leagues, /api/history, /api/import/sleeper)
 * Normalizes and renders historical matchups, franchise standings, and player statistics.
 */

// Global State
const appState = {
  currentSuperLeagueId: null,
  currentGroupBy: "matchup", // "matchup" | "franchise" | "players"
  leagues: [],
  historicalData: [],
  filterYear: "",
  filterWeek: "",
  filterFranchise: "",
  searchQuery: "",
};

// DOM Elements
const superLeagueSelect = document.getElementById("super-league-select");
const filterYearSelect = document.getElementById("filter-year");
const filterWeekSelect = document.getElementById("filter-week");
const filterWeekWrap = document.getElementById("filter-week-wrap");
const filterFranchiseSelect = document.getElementById("filter-franchise");
const filterSearchInput = document.getElementById("filter-search-input");

const btnGroupMatchup = document.getElementById("btn-group-matchup");
const btnGroupFranchise = document.getElementById("btn-group-franchise");
const btnGroupPlayers = document.getElementById("btn-group-players");

const historyTable = document.getElementById("history-table");
const historyTableHeaders = document.getElementById("history-table-headers");
const historyTableBody = document.getElementById("history-table-body");
const historyRecordCount = document.getElementById("history-record-count");

const btnRefreshData = document.getElementById("btn-refresh-data");
const btnTriggerTick = document.getElementById("btn-trigger-tick");

const espnForm = document.getElementById("espn-import-form");
const sleeperForm = document.getElementById("sleeper-import-form");
const importNotification = document.getElementById("import-notification");


// ==========================================
// Initialization & Event Listeners
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
  initEventListeners();
  populateWeeksDropdown();
  loadLeagues();
});

function initEventListeners() {
  // SuperLeague selector change
  superLeagueSelect.addEventListener("change", (e) => {
    appState.currentSuperLeagueId = e.target.value ? parseInt(e.target.value) : null;
    updateFiltersForCurrentLeague();
    fetchHistoryData();
  });

  // Group By Button Clicks
  btnGroupMatchup.addEventListener("click", () => switchGroupBy("matchup"));
  btnGroupFranchise.addEventListener("click", () => switchGroupBy("franchise"));
  btnGroupPlayers.addEventListener("click", () => switchGroupBy("players"));

  // Filters change
  filterYearSelect.addEventListener("change", (e) => {
    appState.filterYear = e.target.value;
    fetchHistoryData();
  });

  filterWeekSelect.addEventListener("change", (e) => {
    appState.filterWeek = e.target.value;
    fetchHistoryData();
  });

  filterFranchiseSelect.addEventListener("change", (e) => {
    appState.filterFranchise = e.target.value;
    fetchHistoryData();
  });

  filterSearchInput.addEventListener("input", (e) => {
    appState.searchQuery = e.target.value.toLowerCase().trim();
    renderCurrentData();
  });

  btnRefreshData.addEventListener("click", () => {
    loadLeagues();
  });

  btnTriggerTick.addEventListener("click", async () => {
    try {
      btnTriggerTick.disabled = true;
      btnTriggerTick.innerHTML = "Sending...";
      await fetch("/api/live/trigger-demo-tick", { method: "POST" });
    } catch (err) {
      console.error("Error triggering tick:", err);
    } finally {
      setTimeout(() => {
        btnTriggerTick.disabled = false;
        btnTriggerTick.innerHTML = `<span class="btn-icon">⚡</span> Push Live Update`;
      }, 500);
    }
  });

  // ESPN Ingestion Form Submit
  espnForm.addEventListener("submit", handleESPNSubmit);

  // Sleeper Ingestion Form Submit
  sleeperForm.addEventListener("submit", handleSleeperSubmit);
}


// ==========================================
// API Fetching Functions
// ==========================================

/**
 * Fetches all SuperLeagues and populates dropdowns.
 */
async function loadLeagues() {
  try {
    const res = await fetch("/api/leagues");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    appState.leagues = data;

    superLeagueSelect.innerHTML = "";
    if (data.length === 0) {
      superLeagueSelect.innerHTML = `<option value="">No Leagues Found</option>`;
      return;
    }

    data.forEach((league, index) => {
      const opt = document.createElement("option");
      opt.value = league.id;
      opt.textContent = `${league.name} (${league.sport}) - ${league.franchises_count} Franchises`;
      superLeagueSelect.appendChild(opt);
    });

    if (!appState.currentSuperLeagueId || !data.some(l => l.id === appState.currentSuperLeagueId)) {
      appState.currentSuperLeagueId = data[0].id;
    }
    superLeagueSelect.value = appState.currentSuperLeagueId;

    updateFiltersForCurrentLeague();
    await fetchHistoryData();
  } catch (err) {
    console.error("Failed to load leagues:", err);
    historyTableBody.innerHTML = `<tr><td colspan="8" class="text-center py-4" style="color: #f87171">Failed to connect to backend: ${err.message}</td></tr>`;
  }
}

/**
 * Updates Year and Franchise dropdown options based on selected SuperLeague.
 */
function updateFiltersForCurrentLeague() {
  const current = appState.leagues.find(l => l.id === appState.currentSuperLeagueId);
  if (!current) return;

  // Years from platform leagues
  const years = new Set();
  (current.platform_leagues || []).forEach(pl => years.add(pl.year));
  const sortedYears = Array.from(years).sort((a, b) => b - a);

  filterYearSelect.innerHTML = `<option value="">All Seasons</option>`;
  sortedYears.forEach(yr => {
    const opt = document.createElement("option");
    opt.value = yr;
    opt.textContent = `${yr} Season`;
    filterYearSelect.appendChild(opt);
  });

  // Franchises
  filterFranchiseSelect.innerHTML = `<option value="">All Franchises</option>`;
  (current.franchises || []).forEach(f => {
    const opt = document.createElement("option");
    opt.value = f.id;
    opt.textContent = `${f.name} (${f.owner_name || 'Owner'})`;
    filterFranchiseSelect.appendChild(opt);
  });
}

function populateWeeksDropdown() {
  filterWeekSelect.innerHTML = `<option value="">All Weeks</option>`;
  for (let w = 1; w <= 18; w++) {
    const opt = document.createElement("option");
    opt.value = w;
    opt.textContent = `Week ${w}`;
    filterWeekSelect.appendChild(opt);
  }
}

/**
 * Switches the active group-by tab and refetches data.
 */
function switchGroupBy(newGroupBy) {
  appState.currentGroupBy = newGroupBy;

  [btnGroupMatchup, btnGroupFranchise, btnGroupPlayers].forEach(btn => btn.classList.remove("active"));
  if (newGroupBy === "matchup") btnGroupMatchup.classList.add("active");
  if (newGroupBy === "franchise") btnGroupFranchise.classList.add("active");
  if (newGroupBy === "players") btnGroupPlayers.classList.add("active");

  // Week filter is only meaningful for Matchup and Player stats
  filterWeekWrap.style.display = (newGroupBy === "franchise") ? "none" : "flex";

  fetchHistoryData();
}

/**
 * Fetches historical data from /api/history based on current state.
 */
async function fetchHistoryData() {
  if (!appState.currentSuperLeagueId) return;

  historyTableBody.innerHTML = `<tr><td colspan="8" class="text-center py-4">Querying unified records...</td></tr>`;

  const params = new URLSearchParams({
    super_league_id: appState.currentSuperLeagueId,
    group_by: appState.currentGroupBy,
  });

  if (appState.filterYear) params.append("year", appState.filterYear);
  if (appState.filterWeek && appState.currentGroupBy !== "franchise") params.append("week", appState.filterWeek);
  if (appState.filterFranchise) params.append("franchise_id", appState.filterFranchise);

  try {
    const res = await fetch(`/api/history?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const result = await res.json();
    appState.historicalData = result.data || [];
    renderCurrentData();
  } catch (err) {
    console.error("Failed to fetch history:", err);
    historyTableBody.innerHTML = `<tr><td colspan="8" class="text-center py-4" style="color: #f87171">Error fetching data: ${err.message}</td></tr>`;
  }
}


// ==========================================
// DOM Rendering Functions
// ==========================================

function renderCurrentData() {
  if (appState.currentGroupBy === "matchup") {
    renderMatchupsTable();
  } else if (appState.currentGroupBy === "franchise") {
    renderFranchiseTable();
  } else if (appState.currentGroupBy === "players") {
    renderPlayersTable();
  }
}

/**
 * Renders Matchups view: constructs <tr> and <td> in memory,
 * applying .win-highlight and .loss-highlight dynamically.
 */
function renderMatchupsTable() {
  historyTableHeaders.innerHTML = `
    <tr>
      <th>Season</th>
      <th>Week</th>
      <th>Platform</th>
      <th>Team A</th>
      <th>Score A</th>
      <th>Score B</th>
      <th>Team B</th>
      <th>Winner</th>
    </tr>
  `;

  let items = appState.historicalData;
  if (appState.searchQuery) {
    items = items.filter(m =>
      (m.team_a_name && m.team_a_name.toLowerCase().includes(appState.searchQuery)) ||
      (m.team_b_name && m.team_b_name.toLowerCase().includes(appState.searchQuery)) ||
      (m.team_a_owner && m.team_a_owner.toLowerCase().includes(appState.searchQuery)) ||
      (m.team_b_owner && m.team_b_owner.toLowerCase().includes(appState.searchQuery))
    );
  }

  historyRecordCount.textContent = `${items.length} matchup(s) displayed`;
  historyTableBody.innerHTML = "";

  if (items.length === 0) {
    historyTableBody.innerHTML = `<tr><td colspan="8" class="text-center py-4">No matching matchups found.</td></tr>`;
    return;
  }

  const fragment = document.createDocumentFragment();

  items.forEach(m => {
    const tr = document.createElement("tr");

    const aWon = m.team_a_score > m.team_b_score;
    const bWon = m.team_b_score > m.team_a_score;
    const isTie = m.team_a_score === m.team_b_score && m.team_b_id !== null;

    // Cells
    const tdYear = document.createElement("td");
    tdYear.textContent = m.year;

    const tdWeek = document.createElement("td");
    tdWeek.textContent = `Week ${m.week}${m.is_playoffs ? ' (Playoffs)' : ''}`;

    const tdPlatform = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `badge-tag ${m.platform === 'ESPN' ? 'badge-espn' : 'badge-sleeper'}`;
    badge.textContent = m.platform;
    tdPlatform.appendChild(badge);

    const tdTeamA = document.createElement("td");
    tdTeamA.innerHTML = `<strong>${escapeHtml(m.team_a_name)}</strong> <small style="color:var(--text-muted)">(${escapeHtml(m.team_a_owner || '')})</small>`;

    const tdScoreA = document.createElement("td");
    tdScoreA.textContent = m.team_a_score.toFixed(2);
    tdScoreA.className = aWon ? "win-highlight" : (bWon ? "loss-highlight" : (isTie ? "tie-highlight" : ""));

    const tdScoreB = document.createElement("td");
    tdScoreB.textContent = m.team_b_id ? m.team_b_score.toFixed(2) : "-";
    tdScoreB.className = bWon ? "win-highlight" : (aWon && m.team_b_id ? "loss-highlight" : (isTie ? "tie-highlight" : ""));

    const tdTeamB = document.createElement("td");
    tdTeamB.innerHTML = m.team_b_id
      ? `<strong>${escapeHtml(m.team_b_name)}</strong> <small style="color:var(--text-muted)">(${escapeHtml(m.team_b_owner || '')})</small>`
      : `<span style="color:var(--text-muted)">BYE WEEK</span>`;

    const tdOutcome = document.createElement("td");
    if (aWon) {
      tdOutcome.innerHTML = `<span class="badge-tag badge-win">🏆 ${escapeHtml(m.team_a_name)}</span>`;
    } else if (bWon) {
      tdOutcome.innerHTML = `<span class="badge-tag badge-win">🏆 ${escapeHtml(m.team_b_name)}</span>`;
    } else if (isTie) {
      tdOutcome.innerHTML = `<span class="badge-tag">🤝 Tie</span>`;
    } else {
      tdOutcome.innerHTML = `<span class="badge-tag">Bye</span>`;
    }

    tr.appendChild(tdYear);
    tr.appendChild(tdWeek);
    tr.appendChild(tdPlatform);
    tr.appendChild(tdTeamA);
    tr.appendChild(tdScoreA);
    tr.appendChild(tdScoreB);
    tr.appendChild(tdTeamB);
    tr.appendChild(tdOutcome);

    fragment.appendChild(tr);
  });

  historyTableBody.appendChild(fragment);
}

/**
 * Renders Standings/Franchise view: all-time records across all merged seasons.
 */
function renderFranchiseTable() {
  historyTableHeaders.innerHTML = `
    <tr>
      <th>Rank</th>
      <th>Franchise</th>
      <th>Owner</th>
      <th>Record (W-L-T)</th>
      <th>Win Pct</th>
      <th>Points For</th>
      <th>Points Against</th>
      <th>PPG</th>
    </tr>
  `;

  let items = appState.historicalData;
  if (appState.searchQuery) {
    items = items.filter(f =>
      (f.name && f.name.toLowerCase().includes(appState.searchQuery)) ||
      (f.owner_name && f.owner_name.toLowerCase().includes(appState.searchQuery))
    );
  }

  historyRecordCount.textContent = `${items.length} franchise(s) displayed`;
  historyTableBody.innerHTML = "";

  if (items.length === 0) {
    historyTableBody.innerHTML = `<tr><td colspan="8" class="text-center py-4">No franchise records found.</td></tr>`;
    return;
  }

  const fragment = document.createDocumentFragment();

  items.forEach((f, idx) => {
    const tr = document.createElement("tr");

    const isWinningRecord = f.win_pct >= 0.5;
    const isLosingRecord = f.win_pct < 0.5 && f.games_played > 0;

    const tdRank = document.createElement("td");
    tdRank.innerHTML = `<strong>#${idx + 1}</strong>`;

    const tdName = document.createElement("td");
    tdName.innerHTML = `<strong>${escapeHtml(f.name)}</strong>`;

    const tdOwner = document.createElement("td");
    tdOwner.textContent = f.owner_name || "-";

    const tdRecord = document.createElement("td");
    tdRecord.textContent = `${f.wins}-${f.losses}-${f.ties}`;
    tdRecord.className = isWinningRecord ? "win-highlight" : (isLosingRecord ? "loss-highlight" : "");

    const tdWinPct = document.createElement("td");
    tdWinPct.textContent = (f.win_pct * 100).toFixed(1) + "%";

    const tdPF = document.createElement("td");
    tdPF.textContent = f.points_for.toFixed(2);

    const tdPA = document.createElement("td");
    tdPA.textContent = f.points_against.toFixed(2);

    const tdPPG = document.createElement("td");
    tdPPG.textContent = f.ppg.toFixed(2);

    tr.appendChild(tdRank);
    tr.appendChild(tdName);
    tr.appendChild(tdOwner);
    tr.appendChild(tdRecord);
    tr.appendChild(tdWinPct);
    tr.appendChild(tdPF);
    tr.appendChild(tdPA);
    tr.appendChild(tdPPG);

    fragment.appendChild(tr);
  });

  historyTableBody.appendChild(fragment);
}

/**
 * Renders Top Player Stats view.
 */
function renderPlayersTable() {
  historyTableHeaders.innerHTML = `
    <tr>
      <th>Rank</th>
      <th>Player Name</th>
      <th>Position</th>
      <th>Appearances</th>
      <th>Total Points</th>
      <th>Avg PPG</th>
      <th>Max Score</th>
    </tr>
  `;

  let items = appState.historicalData;
  if (appState.searchQuery) {
    items = items.filter(p =>
      (p.player_name && p.player_name.toLowerCase().includes(appState.searchQuery)) ||
      (p.position && p.position.toLowerCase().includes(appState.searchQuery))
    );
  }

  historyRecordCount.textContent = `${items.length} player(s) displayed`;
  historyTableBody.innerHTML = "";

  if (items.length === 0) {
    historyTableBody.innerHTML = `<tr><td colspan="7" class="text-center py-4">No player statistics found.</td></tr>`;
    return;
  }

  const fragment = document.createDocumentFragment();

  items.forEach((p, idx) => {
    const tr = document.createElement("tr");

    const tdRank = document.createElement("td");
    tdRank.innerHTML = `<strong>#${idx + 1}</strong>`;

    const tdName = document.createElement("td");
    tdName.innerHTML = `<strong>${escapeHtml(p.player_name)}</strong>`;

    const tdPos = document.createElement("td");
    tdPos.innerHTML = `<span class="badge-tag">${escapeHtml(p.position)}</span>`;

    const tdApp = document.createElement("td");
    tdApp.textContent = p.appearances;

    const tdTotal = document.createElement("td");
    tdTotal.textContent = p.total_points.toFixed(2);
    tdTotal.className = "win-highlight";

    const tdAvg = document.createElement("td");
    tdAvg.textContent = p.avg_points.toFixed(2);

    const tdMax = document.createElement("td");
    tdMax.textContent = p.max_points.toFixed(2);

    tr.appendChild(tdRank);
    tr.appendChild(tdName);
    tr.appendChild(tdPos);
    tr.appendChild(tdApp);
    tr.appendChild(tdTotal);
    tr.appendChild(tdAvg);
    tr.appendChild(tdMax);

    fragment.appendChild(tr);
  });

  historyTableBody.appendChild(fragment);
}


// ==========================================
// Ingestion Forms Handlers (ESPN & Sleeper)
// ==========================================

async function handleESPNSubmit(e) {
  e.preventDefault();
  const btn = document.getElementById("btn-submit-espn");
  const origText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = "Authenticating & Ingesting...";
  showNotification("Connecting to ESPN Fantasy v3 API...", "info");

  const payload = {
    league_id: document.getElementById("espn-league-id").value.trim(),
    year: parseInt(document.getElementById("espn-season").value) || 2024,
    sport: document.getElementById("espn-sport").value,
    swid: document.getElementById("espn-swid").value.trim(),
    espn_s2: document.getElementById("espn-s2").value.trim(),
    super_league_id: appState.currentSuperLeagueId,
  };

  try {
    const res = await fetch("/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "ESPN Authentication failed.");
    }

    showNotification(data.message || "ESPN league successfully ingested!", "success");
    await loadLeagues();
  } catch (err) {
    showNotification(`ESPN Ingestion Error: ${err.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = origText;
  }
}

async function handleSleeperSubmit(e) {
  e.preventDefault();
  const btn = document.getElementById("btn-submit-sleeper");
  const origText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = "Ingesting Sleeper...";
  showNotification("Ingesting Sleeper league...", "info");

  const payload = {
    league_id: document.getElementById("sleeper-league-id").value.trim(),
    super_league_id: appState.currentSuperLeagueId,
    super_league_name: document.getElementById("sleeper-super-league").value.trim() || undefined,
  };

  try {
    const res = await fetch("/api/import/sleeper", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Sleeper Ingestion failed.");
    }

    showNotification(data.message || "Sleeper league successfully ingested!", "success");
    await loadLeagues();
  } catch (err) {
    showNotification(`Sleeper Ingestion Error: ${err.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = origText;
  }
}

function showNotification(msg, type = "info") {
  importNotification.textContent = msg;
  importNotification.className = `notification ${type === "error" ? "error" : "success"}`;
  importNotification.classList.remove("hidden");
  setTimeout(() => {
    importNotification.classList.add("hidden");
  }, 6000);
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

