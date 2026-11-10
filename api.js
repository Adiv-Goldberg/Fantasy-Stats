/**
 * api.js - Data Fetcher and DOM Controller
 * Default Backend: https://fantasy-stats-backend.onrender.com
 */

const RENDER_BACKEND_URL = "https://fantasy-stats-backend.onrender.com";

function getBackendUrl() {
  const host = window.location.hostname;
  if (host === "localhost" || host === "127.0.0.1") {
    return "";
  }
  return RENDER_BACKEND_URL;
}

const appState = {
  currentSuperLeagueId: null,
  currentGroupBy: "matchup",
  leagues: [],
  historicalData: [],
  filterYear: "",
  filterWeek: "",
  filterFranchise: "",
  searchQuery: "",
};

// DOM References
const historyEmptyCard = document.getElementById("history-empty-card");
const historyDataView = document.getElementById("history-data-view");

const superLeagueSelect = document.getElementById("super-league-select");
const filterYearSelect = document.getElementById("filter-year");
const filterWeekSelect = document.getElementById("filter-week");
const filterFranchiseSelect = document.getElementById("filter-franchise");
const filterSearchInput = document.getElementById("filter-search-input");

const btnGroupMatchup = document.getElementById("btn-group-matchup");
const btnGroupFranchise = document.getElementById("btn-group-franchise");
const btnGroupPlayers = document.getElementById("btn-group-players");

const historyTableHeaders = document.getElementById("history-table-headers");
const historyTableBody = document.getElementById("history-table-body");
const historyRecordCount = document.getElementById("history-record-count");

const espnForm = document.getElementById("espn-import-form");
const sleeperForm = document.getElementById("sleeper-import-form");
const yahooForm = document.getElementById("yahoo-import-form");
const importAlert = document.getElementById("import-notification");

// Navigation Tabs Switcher
window.switchToTab = function(tabName) {
  document.querySelectorAll(".nav-btn").forEach(l => l.classList.remove("active"));
  document.querySelectorAll(".view").forEach(p => p.classList.remove("active"));

  const targetLink = document.querySelector(`.nav-btn[data-tab="${tabName}"]`);
  if (targetLink) targetLink.classList.add("active");

  const panel = document.getElementById(`tab-${tabName}`);
  if (panel) panel.classList.add("active");
};

document.querySelectorAll(".nav-btn").forEach(link => {
  link.addEventListener("click", () => {
    window.switchToTab(link.dataset.tab);
  });
});

document.addEventListener("DOMContentLoaded", () => {
  initEventListeners();
  populateWeeksDropdown();
  loadLeagues();
});

function initEventListeners() {
  superLeagueSelect.addEventListener("change", (e) => {
    appState.currentSuperLeagueId = e.target.value ? parseInt(e.target.value) : null;
    updateFiltersForCurrentLeague();
    fetchHistoryData();
  });

  btnGroupMatchup.addEventListener("click", () => switchGroupBy("matchup"));
  btnGroupFranchise.addEventListener("click", () => switchGroupBy("franchise"));
  btnGroupPlayers.addEventListener("click", () => switchGroupBy("players"));

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

  if (espnForm) espnForm.addEventListener("submit", handleESPNSubmit);
  if (sleeperForm) sleeperForm.addEventListener("submit", handleSleeperSubmit);
  if (yahooForm) yahooForm.addEventListener("submit", handleYahooSubmit);
}

async function loadLeagues() {
  try {
    const res = await fetch(`${getBackendUrl()}/api/leagues`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    appState.leagues = data;

    // IF NO DATA IMPORTED, PROMINENTLY SHOW EMPTY STATE
    if (!data || data.length === 0) {
      if (historyDataView) historyDataView.style.display = "none";
      if (historyEmptyCard) historyEmptyCard.style.display = "flex";
      return;
    }

    // DATA EXISTS: SHOW TABLE VIEW
    if (historyEmptyCard) historyEmptyCard.style.display = "none";
    if (historyDataView) historyDataView.style.display = "block";

    superLeagueSelect.innerHTML = "";
    data.forEach(league => {
      const opt = document.createElement("option");
      opt.value = league.id;
      opt.textContent = `${league.name} (${league.sport})`;
      superLeagueSelect.appendChild(opt);
    });

    if (!appState.currentSuperLeagueId || !data.some(l => l.id === appState.currentSuperLeagueId)) {
      appState.currentSuperLeagueId = data[0].id;
    }
    superLeagueSelect.value = appState.currentSuperLeagueId;

    updateFiltersForCurrentLeague();
    await fetchHistoryData();
  } catch (err) {
    if (historyDataView) historyDataView.style.display = "none";
    if (historyEmptyCard) {
      historyEmptyCard.style.display = "flex";
      const title = historyEmptyCard.querySelector(".empty-title");
      if (title) title.textContent = "Backend Connecting";
      const sub = historyEmptyCard.querySelector(".empty-sub");
      if (sub) sub.textContent = "Connecting to backend service. If the server is waking up, refresh in a few moments.";
    }
  }
}

function updateFiltersForCurrentLeague() {
  const current = appState.leagues.find(l => l.id === appState.currentSuperLeagueId);
  if (!current) return;

  const years = new Set();
  (current.platform_leagues || []).forEach(pl => years.add(pl.year));
  const sortedYears = Array.from(years).sort((a, b) => b - a);

  filterYearSelect.innerHTML = `<option value="">All Seasons</option>`;
  sortedYears.forEach(yr => {
    const opt = document.createElement("option");
    opt.value = yr;
    opt.textContent = `${yr}`;
    filterYearSelect.appendChild(opt);
  });

  filterFranchiseSelect.innerHTML = `<option value="">All Franchises</option>`;
  (current.franchises || []).forEach(f => {
    const opt = document.createElement("option");
    opt.value = f.id;
    opt.textContent = f.name;
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

function switchGroupBy(newGroupBy) {
  appState.currentGroupBy = newGroupBy;

  [btnGroupMatchup, btnGroupFranchise, btnGroupPlayers].forEach(btn => btn.classList.remove("active"));
  if (newGroupBy === "matchup") btnGroupMatchup.classList.add("active");
  if (newGroupBy === "franchise") btnGroupFranchise.classList.add("active");
  if (newGroupBy === "players") btnGroupPlayers.classList.add("active");

  filterWeekSelect.style.display = (newGroupBy === "franchise") ? "none" : "block";

  fetchHistoryData();
}

async function fetchHistoryData() {
  if (!appState.currentSuperLeagueId) return;

  const params = new URLSearchParams({
    super_league_id: appState.currentSuperLeagueId,
    group_by: appState.currentGroupBy,
  });

  if (appState.filterYear) params.append("year", appState.filterYear);
  if (appState.filterWeek && appState.currentGroupBy !== "franchise") params.append("week", appState.filterWeek);
  if (appState.filterFranchise) params.append("franchise_id", appState.filterFranchise);

  try {
    const res = await fetch(`${getBackendUrl()}/api/history?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const result = await res.json();
    appState.historicalData = result.data || [];
    renderCurrentData();
  } catch (err) {
    historyTableBody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-mid); padding: 3rem;">Error querying history: ${err.message}</td></tr>`;
  }
}

function renderCurrentData() {
  if (appState.currentGroupBy === "matchup") {
    renderMatchupsTable();
  } else if (appState.currentGroupBy === "franchise") {
    renderFranchiseTable();
  } else if (appState.currentGroupBy === "players") {
    renderPlayersTable();
  }
}

function renderMatchupsTable() {
  historyTableHeaders.innerHTML = `
    <tr>
      <th>Season</th>
      <th>Week</th>
      <th>Platform</th>
      <th>Team A</th>
      <th>Score</th>
      <th>Score</th>
      <th>Team B</th>
      <th>Winner</th>
    </tr>
  `;

  let items = appState.historicalData;
  if (appState.searchQuery) {
    items = items.filter(m =>
      (m.team_a_name && m.team_a_name.toLowerCase().includes(appState.searchQuery)) ||
      (m.team_b_name && m.team_b_name.toLowerCase().includes(appState.searchQuery))
    );
  }

  historyRecordCount.textContent = `${items.length} records`;
  historyTableBody.innerHTML = "";

  if (items.length === 0) {
    historyTableBody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-mid); padding: 3rem;">No matchups found matching filters.</td></tr>`;
    return;
  }

  const fragment = document.createDocumentFragment();

  items.forEach(m => {
    const tr = document.createElement("tr");

    const aWon = m.team_a_score > m.team_b_score;
    const bWon = m.team_b_score > m.team_a_score;

    tr.innerHTML = `
      <td>${m.year}</td>
      <td>Week ${m.week}${m.is_playoffs ? ' (Playoffs)' : ''}</td>
      <td><span class="tag">${m.platform}</span></td>
      <td>${escapeHtml(m.team_a_name)}</td>
      <td class="${aWon ? 'bold-win' : 'muted-loss'}">${m.team_a_score.toFixed(2)}</td>
      <td class="${bWon ? 'bold-win' : (m.team_b_id ? 'muted-loss' : '')}">${m.team_b_id ? m.team_b_score.toFixed(2) : '-'}</td>
      <td>${m.team_b_id ? escapeHtml(m.team_b_name) : 'BYE'}</td>
      <td>${aWon ? escapeHtml(m.team_a_name) : (bWon ? escapeHtml(m.team_b_name) : 'Tie')}</td>
    `;

    fragment.appendChild(tr);
  });

  historyTableBody.appendChild(fragment);
}

function renderFranchiseTable() {
  historyTableHeaders.innerHTML = `
    <tr>
      <th>Rank</th>
      <th>Franchise</th>
      <th>Owner</th>
      <th>Record</th>
      <th>Win %</th>
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

  historyRecordCount.textContent = `${items.length} records`;
  historyTableBody.innerHTML = "";

  if (items.length === 0) {
    historyTableBody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-mid); padding: 3rem;">No franchise records found.</td></tr>`;
    return;
  }

  const fragment = document.createDocumentFragment();

  items.forEach((f, idx) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${idx + 1}</td>
      <td class="bold-win">${escapeHtml(f.name)}</td>
      <td>${f.owner_name ? escapeHtml(f.owner_name) : '-'}</td>
      <td>${f.wins}-${f.losses}-${f.ties}</td>
      <td>${(f.win_pct * 100).toFixed(1)}%</td>
      <td>${f.points_for.toFixed(2)}</td>
      <td>${f.points_against.toFixed(2)}</td>
      <td>${f.ppg.toFixed(2)}</td>
    `;
    fragment.appendChild(tr);
  });

  historyTableBody.appendChild(fragment);
}

function renderPlayersTable() {
  historyTableHeaders.innerHTML = `
    <tr>
      <th>Rank</th>
      <th>Player</th>
      <th>Position</th>
      <th>Starts</th>
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

  historyRecordCount.textContent = `${items.length} records`;
  historyTableBody.innerHTML = "";

  if (items.length === 0) {
    historyTableBody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-mid); padding: 3rem;">No player stats found.</td></tr>`;
    return;
  }

  const fragment = document.createDocumentFragment();

  items.forEach((p, idx) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${idx + 1}</td>
      <td class="bold-win">${escapeHtml(p.player_name)}</td>
      <td><span class="tag">${escapeHtml(p.position)}</span></td>
      <td>${p.appearances}</td>
      <td>${p.total_points.toFixed(2)}</td>
      <td>${p.avg_points.toFixed(2)}</td>
      <td>${p.max_points.toFixed(2)}</td>
    `;
    fragment.appendChild(tr);
  });

  historyTableBody.appendChild(fragment);
}

async function handleESPNSubmit(e) {
  e.preventDefault();
  const btn = document.getElementById("btn-submit-espn");
  btn.disabled = true;
  btn.textContent = "Importing...";
  showAlert("Connecting to ESPN API...", "info");

  const payload = {
    league_id: document.getElementById("espn-league-id").value.trim(),
    year: parseInt(document.getElementById("espn-season").value) || 2024,
    sport: document.getElementById("espn-sport").value,
    swid: document.getElementById("espn-swid").value.trim(),
    espn_s2: document.getElementById("espn-s2").value.trim(),
    super_league_id: appState.currentSuperLeagueId,
  };

  try {
    const res = await fetch(`${getBackendUrl()}/auth`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "ESPN import failed.");

    showAlert(data.message || "ESPN league imported successfully.", "success");
    await loadLeagues();
    switchToTab("history");
  } catch (err) {
    showAlert(err.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Import ESPN League";
  }
}

async function handleSleeperSubmit(e) {
  e.preventDefault();
  const btn = document.getElementById("btn-submit-sleeper");
  btn.disabled = true;
  btn.textContent = "Importing...";
  showAlert("Connecting to Sleeper API...", "info");

  const payload = {
    league_id: document.getElementById("sleeper-league-id").value.trim(),
    super_league_id: appState.currentSuperLeagueId,
    super_league_name: document.getElementById("sleeper-super-league").value.trim() || undefined,
  };

  try {
    const res = await fetch(`${getBackendUrl()}/api/import/sleeper`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Sleeper import failed.");

    showAlert(data.message || "Sleeper league imported successfully.", "success");
    await loadLeagues();
    switchToTab("history");
  } catch (err) {
    showAlert(err.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Import Sleeper League";
  }
}

async function handleYahooSubmit(e) {
  e.preventDefault();
  const btn = document.getElementById("btn-submit-yahoo");
  btn.disabled = true;
  btn.textContent = "Importing...";
  showAlert("Connecting to Yahoo Fantasy API...", "info");

  const payload = {
    league_id: document.getElementById("yahoo-league-id").value.trim(),
    year: parseInt(document.getElementById("yahoo-season").value) || 2024,
    sport: document.getElementById("yahoo-sport").value,
    access_token: document.getElementById("yahoo-access-token").value.trim(),
    super_league_id: appState.currentSuperLeagueId,
  };

  try {
    const res = await fetch(`${getBackendUrl()}/api/import/yahoo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Yahoo import failed.");

    showAlert(data.message || "Yahoo league imported successfully.", "success");
    await loadLeagues();
    switchToTab("history");
  } catch (err) {
    showAlert(err.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Import Yahoo League";
  }
}

function showAlert(msg, type = "info") {
  if (!importAlert) return;
  importAlert.textContent = msg;
  importAlert.className = `alert ${type}`;
  importAlert.style.display = "block";
  if (type !== "info") {
    setTimeout(() => {
      importAlert.style.display = "none";
    }, 6000);
  }
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
