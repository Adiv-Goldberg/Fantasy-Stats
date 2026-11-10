/**
 * websocket.js - Live Sync Listener
 * Connects to wss://fantasy-stats-backend.onrender.com/ws/live
 */

class LiveSyncClient {
  constructor() {
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectDelay = 10000;
    this.wsDot = document.getElementById("ws-dot");
    this.wsStatusText = document.getElementById("ws-status-text");
    this.scoreboardsContainer = document.getElementById("live-scoreboards-container");
    this.tickerFeed = document.getElementById("live-ticker-feed");
    this.tickerContainer = document.getElementById("live-ticker-container");

    this.connect();
  }

  getWebSocketUrl() {
    const host = window.location.hostname;
    if (host === "localhost" || host === "127.0.0.1") {
      const port = window.location.port ? `:${window.location.port}` : ":8000";
      return `ws://${host}${port}/ws/live`;
    }
    return "wss://fantasy-stats-backend.onrender.com/ws/live";
  }

  connect() {
    const url = this.getWebSocketUrl();
    this.updateStatus("connecting", "Connecting");

    try {
      this.ws = new WebSocket(url);
    } catch (err) {
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.updateStatus("connected", "Live");
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.handleMessage(data);
      } catch (err) {
        console.warn("WS error:", err);
      }
    };

    this.ws.onclose = () => {
      this.updateStatus("disconnected", "Offline");
      this.scheduleReconnect();
    };

    this.ws.onerror = () => {
      this.updateStatus("disconnected", "Offline");
      this.ws.close();
    };
  }

  scheduleReconnect() {
    this.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), this.maxReconnectDelay);
    setTimeout(() => this.connect(), delay);
  }

  updateStatus(state, text) {
    if (this.wsDot) {
      this.wsDot.className = `status-dot ${state}`;
    }
    if (this.wsStatusText) {
      this.wsStatusText.textContent = text;
    }
  }

  handleMessage(data) {
    if (data.type === "score_update") {
      const teamId = data.team_id;
      const newScore = parseFloat(data.new_score);
      const teamName = data.team_name || `Team ${teamId}`;
      const delta = data.score_delta;
      const timestamp = data.timestamp || new Date().toLocaleTimeString();

      const scoreEl = document.getElementById(`team-${teamId}-live-score`);
      if (scoreEl) {
        scoreEl.innerText = newScore.toFixed(2);
      } else {
        this.addLiveMatchupCard(teamId, teamName, newScore);
      }

      if (this.tickerFeed && this.tickerContainer) {
        this.tickerContainer.style.display = "block";
        const deltaSign = delta > 0 ? `+${delta.toFixed(1)}` : `${delta.toFixed(1)}`;
        const item = document.createElement("div");
        item.className = "ticker-item";
        item.textContent = `[${timestamp}] ${teamName} ${deltaSign} pts -> ${newScore.toFixed(2)}`;
        this.tickerFeed.insertBefore(item, this.tickerFeed.firstChild);

        while (this.tickerFeed.children.length > 10) {
          this.tickerFeed.removeChild(this.tickerFeed.lastChild);
        }
      }
    }
  }

  addLiveMatchupCard(teamId, teamName, score) {
    if (!this.scoreboardsContainer) return;

    const existingEmpty = this.scoreboardsContainer.querySelector(".empty-state");
    if (existingEmpty) {
      this.scoreboardsContainer.innerHTML = "";
    }

    const card = document.createElement("div");
    card.className = "live-card";
    card.id = `card-team-${teamId}`;
    card.innerHTML = `
      <div class="live-card-top">
        <span>Active</span>
      </div>
      <div class="live-matchup-row">
        <div class="live-team-side">
          <span class="live-name">${teamName}</span>
          <span class="live-pts" id="team-${teamId}-live-score">${score.toFixed(2)}</span>
        </div>
      </div>
    `;
    this.scoreboardsContainer.appendChild(card);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  window.liveSyncClient = new LiveSyncClient();
});
