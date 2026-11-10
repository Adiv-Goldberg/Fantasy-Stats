"""
Automated Integration and Unit Test Suite for Fantasy-Stats Architecture.
Tests models, database, ESPN scraper, Sleeper client, live sync, REST endpoints, and WebSocket.
"""

import sys
import unittest
from fastapi.testclient import TestClient

from database import engine, Base, SessionLocal
from models import SuperLeague, PlatformLeague, Franchise, Matchup, PlayerStat
from espn_scraper import generate_mock_espn_data, validate_espn_session
from sleeper_client import generate_mock_sleeper_data
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
        """Test database model creation and foreign key associations."""
        sl = SuperLeague(name="Test Super League", sport="NFL")
        self.db.add(sl)
        self.db.commit()
        self.db.refresh(sl)
        self.assertIsNotNone(sl.id)

        pl = PlatformLeague(
            platform="ESPN",
            original_id="11111",
            year=2024,
            name="Test ESPN",
            super_league_id=sl.id
        )
        self.db.add(pl)
        self.db.commit()

        f1 = Franchise(name="Alpha Wolves", owner_name="Alice", super_league_id=sl.id)
        f2 = Franchise(name="Beta Bears", owner_name="Bob", super_league_id=sl.id)
        self.db.add_all([f1, f2])
        self.db.commit()

        m = Matchup(
            week=1,
            year=2024,
            team_a_id=f1.id,
            team_b_id=f2.id,
            team_a_score=115.5,
            team_b_score=102.3,
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

        # Check dictionary conversion
        m_dict = m.to_dict()
        self.assertEqual(m_dict["team_a_name"], "Alpha Wolves")
        self.assertEqual(m_dict["winner_id"], f1.id)
        self.assertEqual(m_dict["team_a_score"], 115.5)

    def test_02_espn_and_sleeper_mock_ingestion(self):
        """Test ESPN and Sleeper data generators and normalization."""
        sl = SuperLeague(name="Scraper Test League", sport="NFL")
        self.db.add(sl)
        self.db.commit()
        self.db.refresh(sl)

        espn_pl = generate_mock_espn_data("espn_test", 2024, sl.id, self.db)
        self.assertIsNotNone(espn_pl.id)

        sleeper_pl = generate_mock_sleeper_data("sleeper_test", sl.id, self.db, year=2024)
        self.assertIsNotNone(sleeper_pl.id)

        # Verify matchups count
        matchups = self.db.query(Matchup).filter(
            Matchup.platform_league_id.in_([espn_pl.id, sleeper_pl.id])
        ).all()
        self.assertGreater(len(matchups), 0)

    def test_03_static_frontend_endpoints(self):
        """Verify frontend assets are served correctly."""
        res_index = self.client.get("/")
        self.assertEqual(res_index.status_code, 200)
        self.assertIn("Fantasy-Stats", res_index.text)
        self.assertIn("favicon.svg", res_index.text)

        res_css = self.client.get("/styles.css")
        self.assertEqual(res_css.status_code, 200)
        self.assertIn(".win-highlight", res_css.text)
        self.assertIn(".loss-highlight", res_css.text)

        res_api_js = self.client.get("/api.js")
        self.assertEqual(res_api_js.status_code, 200)
        self.assertIn("/api/history", res_api_js.text)

        res_ws_js = self.client.get("/websocket.js")
        self.assertEqual(res_ws_js.status_code, 200)
        self.assertIn("/ws/live", res_ws_js.text)

        res_fav = self.client.get("/favicon.svg")
        self.assertEqual(res_fav.status_code, 200)

    def test_04_rest_api_endpoints(self):
        """Test REST API routes /auth, /api/leagues, /api/history."""
        # 1. Health check
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)

        # 2. List leagues
        res = self.client.get("/api/leagues")
        self.assertEqual(res.status_code, 200)
        leagues = res.json()
        self.assertIsInstance(leagues, list)
        self.assertGreater(len(leagues), 0)

        super_league_id = leagues[0]["id"]

        # 3. ESPN Auth endpoint (with mock flag)
        auth_payload = {
            "league_id": "demo",
            "year": 2024,
            "swid": "{MOCK-SWID}",
            "espn_s2": "MOCK_S2",
            "super_league_id": super_league_id,
            "sport": "ffl"
        }
        res_auth = self.client.post("/auth", json=auth_payload)
        self.assertEqual(res_auth.status_code, 200)
        self.assertEqual(res_auth.json()["status"], "success")

        # 4. Sleeper Import endpoint (with mock flag)
        sleeper_payload = {
            "league_id": "demo",
            "super_league_id": super_league_id
        }
        res_sleeper = self.client.post("/api/import/sleeper", json=sleeper_payload)
        self.assertEqual(res_sleeper.status_code, 200)

        # 5. History grouped by matchup
        res_m = self.client.get(f"/api/history?super_league_id={super_league_id}&group_by=matchup")
        self.assertEqual(res_m.status_code, 200)
        self.assertEqual(res_m.json()["group_by"], "matchup")
        self.assertGreater(len(res_m.json()["data"]), 0)

        # 6. History grouped by franchise
        res_f = self.client.get(f"/api/history?super_league_id={super_league_id}&group_by=franchise")
        self.assertEqual(res_f.status_code, 200)
        self.assertEqual(res_f.json()["group_by"], "franchise")
        self.assertGreater(len(res_f.json()["data"]), 0)

        # 7. History grouped by players
        res_p = self.client.get(f"/api/history?super_league_id={super_league_id}&group_by=players")
        self.assertEqual(res_p.status_code, 200)
        self.assertEqual(res_p.json()["group_by"], "players")

        # 8. Live tick trigger
        res_tick = self.client.post("/api/live/trigger-demo-tick")
        self.assertEqual(res_tick.status_code, 200)

    def test_05_websocket_connection(self):
        """Test real-time WebSocket connection and messages."""
        with self.client.websocket_connect("/ws/live") as websocket:
            init_msg = websocket.receive_json()
            self.assertEqual(init_msg["type"], "connection_established")

            # Send ping
            websocket.send_json({"action": "ping"})
            pong_msg = websocket.receive_json()
            self.assertEqual(pong_msg["type"], "pong")


if __name__ == "__main__":
    unittest.main()

