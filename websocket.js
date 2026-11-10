/**
 * websocket.js - Real-Time Live Sync Listener
 * Connects to FastAPI WebSocket endpoint (ws://localhost:8000/ws/live),
 * listens for push notifications, updates DOM elements (e.g. #team-X-live-score),
 * and handles live ticker feed and automatic reconnections.
 */

class LiveSyncClient {
  constructor() {
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectDelay = 10000;
    this.wsDot = document.getElementById("ws-dot");
    this.wsStatusText = document.getElementById("ws-status-text");
    this.tickerFeed = document.getElementById("live-ticker-feed");
    this.scoreboardsContainer = document.getElementById("live-scoreboards-container");
    this.lastUpdateTime = document.getElementById("last-update-time");

    this.sampleMatchupsInitialized = false;
    this.init();
  }

  getWebSocketUrl() {
    // Connect to ws://localhost:8000/ws/live or dynamic host
    const host = window.location.host || "localhost:8000";
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${host}/ws/live`;
  }

  init() {
    this.renderInitialScoreboards();
    this.connect();
  }

  connect() {
    const url = this.getWebSocketUrl();
    console.log(`[WebSocket] Connecting to ${url}...`);

    this.updateStatus("connecting", "Connecting...");

    try {
      this.ws = new WebSocket(url);
    } catch (err) {
      console.error("[WebSocket] Construction failed:", err);
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      console.log("[WebSocket] Connection established.");
      this.reconnectAttempts = 0;
      this.updateStatus("connected", "Live Stream Connected");
      this.addTickerMessage("WebSocket connected to live score polling engine", "highlight");
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.handleMessage(data);
      } catch (err) {
        console.warn("[WebSocket] Failed to parse message:", event.data, err);
      }
    };

    this.ws.onclose = (event) => {
      console.warn(`[WebSocket] Connection closed (code: ${event.code}).`);
      this.updateStatus("disconnected", "Reconnecting...");
      this.scheduleReconnect();
    };

    this.ws.onerror = (err) => {
      console.error("[WebSocket] Error occurred:", err);
      this.updateStatus("disconnected", "Connection Error");
      this.ws.close();
    };
  }

  scheduleReconnect() {
    this.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), this.maxReconnectDelay);
    console.log(`[WebSocket] Reconnecting in ${(delay / 1000).toFixed(1)}s...`);
    setTimeout(() => this.connect(), delay);
  }

  updateStatus(state, text) {
    if (!this.wsDot || !this.wsStatusText) return;
    this.wsDot.className = `status-indicator ${state}`;
    this.wsStatusText.textContent = text;
  }

  handleMessage(data) {
    // 1. Connection established greeting
    if (data.type === "connection_established") {
      this.updateStatus("connected", "Live Stream Active");
      return;
    }

    // 2. Score update push message
    if (data.type === "score_update") {
      const teamId = data.team_id;
      const newScore = parseFloat(data.new_score);
      const teamName = data.team_name || `Team ${teamId}`;
      const delta = data.score_delta;
      const quarter = data.quarter || "Live";
      const timestamp = data.timestamp || new Date().toLocaleTimeString();

      // Update specific DOM score element using document.getElementById()
      const scoreElementId = `team-${teamId}-live-score`;
      let scoreEl = document.getElementById(scoreElementId);

      // If card doesn't exist yet, insert dynamically
      if (!scoreEl) {
        this.createOrUpdateLiveCard(teamId, teamName, newScore, quarter);
        scoreEl = document.getElementById(scoreElementId);
      }

      if (scoreEl) {
        // Instant innerText update required by plan
        scoreEl.innerText = newScore.toFixed(2);

        // Flash animation to highlight live score change
        scoreEl.classList.add("score-flash");
        setTimeout(() => {
          scoreEl.classList.remove("score-flash");
        }, 800);
      }

      // Update quarter badge if present
      const quarterEl = document.getElementById(`team-${teamId}-quarter`);
      if (quarterEl && quarter) {
        quarterEl.innerText = quarter;
      }

      // Update header meta timestamp
      if (this.lastUpdateTime) {
        this.lastUpdateTime.innerText = `Last Event: ${timestamp}`;
      }

      // Append to play-by-play ticker feed
      const deltaSign = delta > 0 ? `+${delta.toFixed(1)}` : `${delta.toFixed(1)}`;
      const desc = data.event_description || `${teamName} score updated (${deltaSign} pts) -> ${newScore.toFixed(2)}`;
      this.addTickerMessage(`[${timestamp}] ${desc}`, "highlight");
    }
  }

  addTickerMessage(message, className = "") {
    if (!this.tickerFeed) return;
    const item = document.createElement("div");
    item.className = `ticker-item ${className}`;
    item.textContent = message;
    this.tickerFeed.insertBefore(item, this.tickerFeed.firstChild);

    // Limit to last 20 messages
    while (this.tickerFeed.children.length > 20) {
      this.tickerFeed.removeChild(this.tickerFeed.lastChild);
    }
  }

  renderInitialScoreboards() {
    if (!this.scoreboardsContainer) return;

    // Render baseline active matchup cards for teams 1..6
    const initialMatchups = [
      {
        id: "m1",
        quarter: "Q3 04:12",
        teamA: { id: 1, name: "Gotham Rogues", owner: "Bruce Wayne", score: 118.40 },
        teamB: { id: 2, name: "Metropolis Monarchs", owner: "Clark Kent", score: 121.20 }
      },
      {
        id: "m2",
        quarter: "Q4 01:45",
        teamA: { id: 3, name: "Central City Speedsters", owner: "Barry Allen", score: 105.70 },
        teamB: { id: 4, name: "Atlantis Tritons", owner: "Arthur Curry", score: 99.80 }
      },
      {
        id: "m3",
        quarter: "Q2 10:30",
        teamA: { id: 5, name: "Apex Predators", owner: "Alex Hunter", score: 114.10 },
        teamB: { id: 6, name: "Gridiron Titans", owner: "Sarah Connor", score: 110.60 }
      }
    ];

    this.scoreboardsContainer.innerHTML = "";

    initialMatchups.forEach(m => {
      const card = document.createElement("div");
      card.className = "live-matchup-card";
      card.id = `matchup-card-${m.id}`;

      card.innerHTML = `
        <div class="live-matchup-header">
          <span class="live-matchup-title">Active Matchup</span>
          <span class="live-matchup-quarter" id="team-${m.teamA.id}-quarter">${m.quarter}</span>
        </div>
        <div class="live-teams-row">
          <div class="live-team home">
            <span class="live-team-name">${m.teamA.name}</span>
            <span class="live-team-owner">${m.teamA.owner}</span>
            <div class="live-score" id="team-${m.teamA.id}-live-score">${m.teamA.score.toFixed(2)}</div>
          </div>
          <div class="live-vs">VS</div>
          <div class="live-team away">
            <span class="live-team-name">${m.teamB.name}</span>
            <span class="live-team-owner">${m.teamB.owner}</span>
            <div class="live-score" id="team-${m.teamB.id}-live-score">${m.teamB.score.toFixed(2)}</div>
          </div>
        </div>
        <div class="live-matchup-footer">
          <span>Live Sync: Active</span>
          <span>Week 8 • In Progress</span>
        </div>
      `;

      this.scoreboardsContainer.appendChild(card);
    });

    this.sampleMatchupsInitialized = true;
  }

  createOrUpdateLiveCard(teamId, teamName, score, quarter) {
    if (!this.scoreboardsContainer) return;

    const card = document.createElement("div");
    card.className = "live-matchup-card";
    card.innerHTML = `
      <div class="live-matchup-header">
        <span class="live-matchup-title">Live Team</span>
        <span class="live-matchup-quarter" id="team-${teamId}-quarter">${quarter}</span>
      </div>
      <div class="live-teams-row">
        <div class="live-team home">
          <span class="live-team-name">${teamName}</span>
          <span class="live-team-owner">ID: ${teamId}</span>
          <div class="live-score" id="team-${teamId}-live-score">${score.toFixed(2)}</div>
        </div>
      </div>
    `;
    this.scoreboardsContainer.appendChild(card);
  }
}

// Instantiate client when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  window.liveSyncClient = new LiveSyncClient();
});

