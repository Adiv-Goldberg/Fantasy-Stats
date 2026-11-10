"""
Unit and Integration Test Suite for Fantasy-Stats.
"""

import unittest
from fastapi.testclient import TestClient

from database import engine, Base, SessionLocal
from models import SuperLeague, PlatformLeague, Franchise, Matchup, PlayerStat
from main import app


class TestFantasyStatsBackend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def setUp(self):
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_01_models_and_database(self):
        sl = SuperLeague(name="My Super League", sport="NFL")
        self.db.add(sl)
        self.db.commit()
        self.db.refresh(sl)

        pl = PlatformLeague(
            platform="ESPN",
            original_id="99999",
            year=2024,
            name="ESPN Season",
            super_league_id=sl.id
        )
        self.db.add(pl)
        self.db.commit()

        f1 = Franchise(name="Team One", owner_name="Owner A", super_league_id=sl.id)
        f2 = Franchise(name="Team Two", owner_name="Owner B", super_league_id=sl.id)
        self.db.add_all([f1, f2])
        self.db.commit()

        m = Matchup(
            week=1,
            year=2024,
            team_a_id=f1.id,
            team_b_id=f2.id,
            team_a_score=110.5,
            team_b_score=98.2,
            platform_league_id=pl.id
        )
        self.db.add(m)
        self.db.commit()
        self.db.refresh(m)

        ps = PlayerStat(
            player_name="Patrick Mahomes",
            position="QB",
            points_scored=24.5,
            matchup_id=m.id,
            franchise_id=f1.id,
            is_starter=True
        )
        self.db.add(ps)
        self.db.commit()

        m_dict = m.to_dict()
        self.assertEqual(m_dict["team_a_name"], "Team One")
        self.assertEqual(m_dict["winner_id"], f1.id)

    def test_02_static_endpoints(self):
        res_index = self.client.get("/")
        self.assertEqual(res_index.status_code, 200)
        self.assertIn("Fantasy Stats", res_index.text)

        res_css = self.client.get("/styles.css")
        self.assertEqual(res_css.status_code, 200)
        self.assertIn("--bg: #000000", res_css.text)

        res_api_js = self.client.get("/api.js")
        self.assertEqual(res_api_js.status_code, 200)
        self.assertIn("fantasy-stats-backend.onrender.com", res_api_js.text)

        res_ws_js = self.client.get("/websocket.js")
        self.assertEqual(res_ws_js.status_code, 200)
        self.assertIn("wss://fantasy-stats-backend.onrender.com/ws/live", res_ws_js.text)

    def test_03_rest_api_endpoints(self):
        res_health = self.client.get("/api/health")
        self.assertEqual(res_health.status_code, 200)

        res_leagues = self.client.get("/api/leagues")
        self.assertEqual(res_leagues.status_code, 200)
        leagues = res_leagues.json()
        self.assertIsInstance(leagues, list)

        if leagues:
            sl_id = leagues[0]["id"]
            res_m = self.client.get(f"/api/history?super_league_id={sl_id}&group_by=matchup")
            self.assertEqual(res_m.status_code, 200)

            res_f = self.client.get(f"/api/history?super_league_id={sl_id}&group_by=franchise")
            self.assertEqual(res_f.status_code, 200)

            res_p = self.client.get(f"/api/history?super_league_id={sl_id}&group_by=players")
            self.assertEqual(res_p.status_code, 200)

    def test_04_websocket_connection(self):
        with self.client.websocket_connect("/ws/live") as websocket:
            init_msg = websocket.receive_json()
            self.assertEqual(init_msg["type"], "connection_established")


if __name__ == "__main__":
    unittest.main()
