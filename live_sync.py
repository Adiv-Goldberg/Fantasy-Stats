"""
Background Polling Service for Live Updates.
Executes an asynchronous loop that polls ESPN for live matchups,
detects score differences, and broadcasts updates over WebSockets.
"""

import asyncio
import logging
from typing import Dict, Any, Callable, List, Optional
from datetime import datetime

logger = logging.getLogger("live_sync")


class LiveSyncService:
    def __init__(self, broadcast_callback: Optional[Callable[[Dict[str, Any]], Any]] = None):
        self.broadcast_callback = broadcast_callback
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self.poll_interval = 30
        self.cached_scores: Dict[str, float] = {}
        self.monitored_leagues: List[Dict[str, Any]] = []

    def register_league(self, league_id: str, platform: str = "ESPN", swid: str = None, espn_s2: str = None):
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
        if self.is_running:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("LiveSyncService started.")

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("LiveSyncService stopped.")

    async def _poll_loop(self):
        while self.is_running:
            try:
                await self.poll_and_broadcast()
            except Exception as e:
                logger.error(f"Error in LiveSyncService: {e}")

            await asyncio.sleep(self.poll_interval)

    async def poll_and_broadcast(self):
        if not self.monitored_leagues:
            return

        for league in self.monitored_leagues:
            await self._poll_espn_live(league)

    async def _poll_espn_live(self, league: Dict[str, Any]):
        import requests
        from espn_scraper import get_espn_cookies, get_espn_headers

        league_id = league["league_id"]
        swid = league.get("swid")
        espn_s2 = league.get("espn_s2")
        year = datetime.now().year

        url = f"https://fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{league_id}"
        cookies = get_espn_cookies(swid, espn_s2)
        headers = get_espn_headers(swid, espn_s2)
        params = [("view", "mMatchup")]

        try:
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
                                "timestamp": datetime.now().strftime("%H:%M:%S")
                            }
                            if self.broadcast_callback:
                                await self.broadcast_callback(payload)
        except Exception as e:
            logger.debug(f"Live poll for {league_id}: {e}")
