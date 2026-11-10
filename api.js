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

// Elements
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
const importAlert = document.getElementById("import-notification");

// Navigation Tabs
document.querySelectorAll(".nav-link").forEach(link => {
  link.addEventListener("click", () => {
    document.querySelectorAll(".nav-link").forEach(l => l.classList.remove("active"));
    document.querySelectorAll(".view-panel").forEach(p => p.classList.remove("active"));

    link.classList.add("active");
    const tabName = link.dataset.tab;
    const panel = document.getElementById(`tab-${tabName}`);
    if (panel) panel.classList.add("active");
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
}

async function loadLeagues() {
  try {
    const res = await fetch(`${getBackendUrl()}/api/leagues`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    appState.leagues = data;

    superLeagueSelect.innerHTML = "";
    if (data.length === 0) {
      superLeagueSelect.innerHTML = `<option value="">No Leagues Imported</option>`;
      historyTableBody.innerHTML = `<tr><td colspan="8" class="empty-state">No leagues imported yet. Use the Import tab to add your league.</td></tr>`;
      historyRecordCount.textContent = "0 records";
      return;
    }

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
    historyTableBody.innerHTML = `<tr><td colspan="8" class="empty-state">Cannot connect to backend: ${err.message}</td></tr>`;
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
    historyTableBody.innerHTML = `<tr><td colspan="8" class="empty-state">Error fetching data: ${err.message}</td></tr>`;
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
    historyTableBody.innerHTML = `<tr><td colspan="8" class="empty-state">No matchups found.</td></tr>`;
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
      <td><span class="tag-platform">${m.platform}</span></td>
      <td>${escapeHtml(m.team_a_name)}</td>
      <td class="${aWon ? 'win-highlight' : 'loss-highlight'}">${m.team_a_score.toFixed(2)}</td>
      <td class="${bWon ? 'win-highlight' : (m.team_b_id ? 'loss-highlight' : '')}">${m.team_b_id ? m.team_b_score.toFixed(2) : '-'}</td>
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
    historyTableBody.innerHTML = `<tr><td colspan="8" class="empty-state">No franchise records found.</td></tr>`;
    return;
  }

  const fragment = document.createDocumentFragment();

  items.forEach((f, idx) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${idx + 1}</td>
      <td class="win-highlight">${escapeHtml(f.name)}</td>
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
    historyTableBody.innerHTML = `<tr><td colspan="7" class="empty-state">No player stats found.</td></tr>`;
    return;
  }

  const fragment = document.createDocumentFragment();

  items.forEach((p, idx) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${idx + 1}</td>
      <td class="win-highlight">${escapeHtml(p.player_name)}</td>
      <td><span class="tag-platform">${escapeHtml(p.position)}</span></td>
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
  showAlert("Connecting to ESPN...", "info");

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

    showAlert(data.message || "ESPN league imported.", "success");
    await loadLeagues();
  } catch (err) {
    showAlert(err.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Import ESPN";
  }
}

async function handleSleeperSubmit(e) {
  e.preventDefault();
  const btn = document.getElementById("btn-submit-sleeper");
  btn.disabled = true;
  btn.textContent = "Importing...";
  showAlert("Connecting to Sleeper...", "info");

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

    showAlert(data.message || "Sleeper league imported.", "success");
    await loadLeagues();
  } catch (err) {
    showAlert(err.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Import Sleeper";
  }
}

function showAlert(msg, type = "info") {
  if (!importAlert) return;
  importAlert.textContent = msg;
  importAlert.className = `alert-bar ${type}`;
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
