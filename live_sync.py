"""
Background Polling Service for Live Updates and Draft Sync.
Executes an asynchronous loop that polls ESPN or live sources every 30 seconds,
detects score/stat discrepancies against local memory cache, and broadcasts updates over WebSockets.
"""

import asyncio
import logging
import random
from typing import Dict, Any, Callable, List, Optional
from datetime import datetime

logger = logging.getLogger("live_sync")
logging.basicConfig(level=logging.INFO)


class LiveSyncService:
    def __init__(self, broadcast_callback: Optional[Callable[[Dict[str, Any]], Any]] = None):
        self.broadcast_callback = broadcast_callback
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self.poll_interval = 30  # seconds
        # In-memory score cache: key is (league_id, team_id), value is current score
        self.cached_scores: Dict[str, float] = {}
        # Monitored leagues configuration
        self.monitored_leagues: List[Dict[str, Any]] = []
        # Simulation mode enabled when no live games are taking place
        self.simulation_mode = True

    def register_league(self, league_id: str, platform: str = "ESPN", swid: str = None, espn_s2: str = None):
        """Add a league to live monitoring."""
        for item in self.monitored_leagues:
            if item["league_id"] == str(league_id):
                return
        self.monitored_leagues.append({
            "league_id": str(league_id),
            "platform": platform,
            "swid": swid,
            "espn_s2": espn_s2
        })
        logger.info(f"Registered league {league_id} for live sync.")

    def set_broadcast_callback(self, callback: Callable[[Dict[str, Any]], Any]):
        self.broadcast_callback = callback

    async def start(self):
        """Starts the background polling task."""
        if self.is_running:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("LiveSyncService started.")

    async def stop(self):
        """Stops the background polling task."""
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("LiveSyncService stopped.")

    async def _poll_loop(self):
        """Periodic loop that executes every poll_interval seconds."""
        logger.info(f"Polling loop initiated with interval={self.poll_interval}s")
        while self.is_running:
            try:
                await self.poll_and_broadcast()
            except Exception as e:
                logger.error(f"Error in LiveSyncService poll: {e}")

            # Wait for next tick
            await asyncio.sleep(self.poll_interval)

    async def poll_and_broadcast(self):
        """
        Polls active matchups and broadcasts diffs.
        If real game is in session, queries ESPN mMatchup view.
        Otherwise, if simulation_mode is enabled, simulates live in-game scoring updates.
        """
        # Simulated live updates for active demonstration
        if self.simulation_mode or not self.monitored_leagues:
            await self._run_simulated_tick()
            return

        for league in self.monitored_leagues:
            await self._poll_espn_live(league)

    async def _poll_espn_live(self, league: Dict[str, Any]):
        """Polls ESPN live mMatchup endpoint."""
        import requests
        from espn_scraper import get_espn_cookies, get_espn_headers

        league_id = league["league_id"]
        swid = league.get("swid")
        espn_s2 = league.get("espn_s2")
        year = datetime.utcnow().year

        url = f"https://fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{league_id}"
        cookies = get_espn_cookies(swid, espn_s2)
        headers = get_espn_headers(swid, espn_s2)
        params = [("view", "mMatchup")]

        try:
            # Run blocking request in thread pool
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: requests.get(url, headers=headers, cookies=cookies, params=params, timeout=10)
            )
            if resp.status_code == 200:
                data = resp.json()
                schedule = data.get("schedule", [])
                for m in schedule:
                    m_id = m.get("id")
                    for side in ["home", "away"]:
                        team_data = m.get(side)
                        if not team_data:
                            continue
                        team_id = team_data.get("teamId")
                        new_score = round(float(team_data.get("totalPoints", 0.0)), 2)
                        cache_key = f"{league_id}:{team_id}"
                        prev_score = self.cached_scores.get(cache_key)

                        if prev_score is None:
                            self.cached_scores[cache_key] = new_score
                        elif abs(new_score - prev_score) > 0.01:
                            delta = round(new_score - prev_score, 2)
                            self.cached_scores[cache_key] = new_score
                            payload = {
                                "type": "score_update",
                                "league_id": league_id,
                                "matchup_id": m_id,
                                "team_id": team_id,
                                "new_score": new_score,
                                "score_delta": delta,
                                "timestamp": datetime.utcnow().isoformat(),
                            }
                            if self.broadcast_callback:
                                await self.broadcast_callback(payload)
        except Exception as e:
            logger.warning(f"Live ESPN poll failed for league {league_id}: {e}")

    async def _run_simulated_tick(self):
        """
        Emits realistic live updates to demonstrate real-time WebSocket dashboard functionality.
        """
        sample_teams = [
            {"team_id": 1, "name": "Gotham Rogues", "base": 118.4},
            {"team_id": 2, "name": "Metropolis Monarchs", "base": 121.2},
            {"team_id": 3, "name": "Central City Speedsters", "base": 105.7},
            {"team_id": 4, "name": "Atlantis Tritons", "base": 99.8},
            {"team_id": 5, "name": "Apex Predators", "base": 114.1},
            {"team_id": 6, "name": "Gridiron Titans", "base": 110.6},
        ]

        target = random.choice(sample_teams)
        team_id = target["team_id"]
        cache_key = f"demo:{team_id}"

        current_score = self.cached_scores.get(cache_key, target["base"])
        pts_delta = round(random.choice([1.0, 2.5, 4.0, 6.0, -1.0]), 2)
        new_score = round(max(0.0, current_score + pts_delta), 2)
        self.cached_scores[cache_key] = new_score

        events = [
            f"{target['name']} completes 24-yard pass (+2.4 pts)",
            f"{target['name']} rushes for 12 yards (+1.2 pts)",
            f"{target['name']} catches 18-yard TD pass (+7.8 pts)",
            f"{target['name']} kicker hits 43-yard field goal (+4.0 pts)",
            f"{target['name']} defense records a sack (+1.0 pt)",
        ]

        payload = {
            "type": "score_update",
            "league_id": "demo",
            "team_id": team_id,
            "team_name": target["name"],
            "new_score": new_score,
            "score_delta": pts_delta,
            "event_description": random.choice(events),
            "quarter": random.choice(["Q2 03:45", "Q3 11:20", "Q4 05:14", "Q4 01:02"]),
            "timestamp": datetime.utcnow().strftime("%H:%M:%S")
        }

        if self.broadcast_callback:
            await self.broadcast_callback(payload)

