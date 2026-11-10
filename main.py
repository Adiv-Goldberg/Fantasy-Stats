"""
Main Application Entry Point for FastAPI and WebSocket Manager.
Configures CORS, registers routes (/auth, /api/leagues, /api/history, /ws/live),
serves frontend assets, and manages real-time WebSocket client broadcasts.
"""

import os
import json
import logging
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from database import engine, get_db, init_db
from models import SuperLeague, PlatformLeague, Franchise, Matchup, PlayerStat
from espn_scraper import scrape_espn_league, validate_espn_session, generate_mock_espn_data
from sleeper_client import scrape_sleeper_league, generate_mock_sleeper_data
from live_sync import LiveSyncService

logger = logging.getLogger("main")
logging.basicConfig(level=logging.INFO)


# --- WebSocket Connection Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Remaining clients: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcasts a JSON dictionary payload to all connected clients."""
        payload_str = json.dumps(message)
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_text(payload_str)
            except Exception as e:
                logger.warning(f"Error broadcasting to client: {e}")
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead)


ws_manager = ConnectionManager()
live_sync_service = LiveSyncService(broadcast_callback=ws_manager.broadcast)


# --- Application Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB schema
    init_db()
    logger.info("Database initialized.")

    # Seed demo data if database is empty so initial load has stats
    from database import SessionLocal
    db = SessionLocal()
    try:
        super_league = db.query(SuperLeague).first()
        if not super_league:
            logger.info("Database is empty. Seeding initial SuperLeague with sample ESPN & Sleeper data...")
            sl = SuperLeague(name="Ultimate Champions SuperLeague", sport="NFL")
            db.add(sl)
            db.commit()
            db.refresh(sl)
            # Seed sample historical data
            generate_mock_espn_data("demo-espn", 2023, sl.id, db)
            generate_mock_espn_data("demo-espn", 2024, sl.id, db)
            generate_mock_sleeper_data("demo-sleeper", sl.id, db, year=2024)
            logger.info("Demo data seeded successfully.")
    except Exception as e:
        logger.error(f"Error seeding demo data: {e}")
    finally:
        db.close()

    # Start live sync service
    await live_sync_service.start()
    yield
    # Stop live sync service on shutdown
    await live_sync_service.stop()


app = FastAPI(
    title="Fantasy-Stats API",
    description="Cross-Platform Fantasy Sports History & Real-Time Live Sync Engine",
    version="1.0.0",
    lifespan=lifespan
)

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic Request Models ---
class ESPNAuthRequest(BaseModel):
    league_id: str
    year: int = 2024
    years: Optional[List[int]] = None
    swid: Optional[str] = ""
    espn_s2: Optional[str] = ""
    super_league_id: Optional[int] = None
    super_league_name: Optional[str] = "My Fantasy SuperLeague"
    sport: Optional[str] = "ffl"


class SleeperImportRequest(BaseModel):
    league_id: str
    super_league_id: Optional[int] = None
    super_league_name: Optional[str] = "My Fantasy SuperLeague"


class CreateSuperLeagueRequest(BaseModel):
    name: str
    sport: str = "NFL"


# --- REST Routes ---

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "Fantasy-Stats API", "active_ws_clients": len(ws_manager.active_connections)}


@app.post("/auth")
async def authenticate_and_import_espn(payload: ESPNAuthRequest, db: Session = Depends(get_db)):
    """
    Receives user ESPN cookies, validates session, fetches historical data,
    and returns a success response while registering the league for live updates.
    """
    # 1. Resolve or create SuperLeague
    super_league_id = payload.super_league_id
    if not super_league_id:
        sl = db.query(SuperLeague).filter_by(name=payload.super_league_name).first()
        if not sl:
            sl = SuperLeague(name=payload.super_league_name, sport=payload.sport.upper() if payload.sport else "NFL")
            db.add(sl)
            db.commit()
            db.refresh(sl)
        super_league_id = sl.id

    # 2. Validate session
    validation = validate_espn_session(
        league_id=payload.league_id,
        year=payload.year,
        swid=payload.swid,
        espn_s2=payload.espn_s2,
        sport=payload.sport or "ffl"
    )

    if not validation.get("success"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=validation.get("message", "ESPN validation failed")
        )

    # 3. Determine years to import
    years_to_import = payload.years or [payload.year]
    if payload.year not in years_to_import:
        years_to_import.append(payload.year)
    years_to_import = sorted(list(set(years_to_import)))

    # 4. Scrape ESPN data
    scrape_result = scrape_espn_league(
        league_id=payload.league_id,
        years=years_to_import,
        swid=payload.swid,
        espn_s2=payload.espn_s2,
        super_league_id=super_league_id,
        db=db,
        sport=payload.sport or "ffl"
    )

    # 5. Register for live sync monitoring
    live_sync_service.register_league(
        league_id=payload.league_id,
        platform="ESPN",
        swid=payload.swid,
        espn_s2=payload.espn_s2
    )

    return {
        "status": "success",
        "message": f"Successfully imported ESPN league {payload.league_id} for {len(years_to_import)} season(s).",
        "super_league_id": super_league_id,
        "details": scrape_result
    }


@app.post("/api/import/sleeper")
async def import_sleeper(payload: SleeperImportRequest, db: Session = Depends(get_db)):
    """
    Imports a public Sleeper league by league ID and normalizes it to the schema.
    """
    super_league_id = payload.super_league_id
    if not super_league_id:
        sl = db.query(SuperLeague).filter_by(name=payload.super_league_name).first()
        if not sl:
            sl = SuperLeague(name=payload.super_league_name, sport="NFL")
            db.add(sl)
            db.commit()
            db.refresh(sl)
        super_league_id = sl.id

    result = scrape_sleeper_league(
        league_id=payload.league_id,
        super_league_id=super_league_id,
        db=db
    )

    return {
        "status": "success",
        "message": f"Successfully imported Sleeper league {payload.league_id}.",
        "super_league_id": super_league_id,
        "details": result
    }


@app.get("/api/leagues")
async def list_leagues(db: Session = Depends(get_db)):
    """
    Lists all SuperLeagues, their associated platform leagues, and franchise totals.
    """
    super_leagues = db.query(SuperLeague).all()
    output = []
    for sl in super_leagues:
        data = sl.to_dict()
        data["platform_leagues"] = [pl.to_dict() for pl in sl.platform_leagues]
        data["franchises"] = [f.to_dict() for f in sl.franchises]
        output.append(data)
    return output


@app.post("/api/leagues")
async def create_super_league(payload: CreateSuperLeagueRequest, db: Session = Depends(get_db)):
    """Create a new SuperLeague container."""
    sl = SuperLeague(name=payload.name, sport=payload.sport)
    db.add(sl)
    db.commit()
    db.refresh(sl)
    return sl.to_dict()


@app.get("/api/history")
async def get_history(
    super_league_id: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    week: Optional[int] = Query(None),
    franchise_id: Optional[int] = Query(None),
    group_by: str = Query("matchup"),  # "matchup", "franchise", "players"
    db: Session = Depends(get_db)
):
    """
    Fetches historical data filtered and grouped according to the request parameters.
    """
    query = db.query(Matchup).join(PlatformLeague)

    if super_league_id:
        query = query.filter(PlatformLeague.super_league_id == super_league_id)
    if year:
        query = query.filter(Matchup.year == year)
    if week:
        query = query.filter(Matchup.week == week)
    if franchise_id:
        query = query.filter(or_(Matchup.team_a_id == franchise_id, Matchup.team_b_id == franchise_id))

    matchups = query.order_by(Matchup.year.desc(), Matchup.week.desc(), Matchup.id.asc()).all()

    if group_by == "franchise":
        # Group stats by franchise for all-time record & scoring averages
        franchises_query = db.query(Franchise)
        if super_league_id:
            franchises_query = franchises_query.filter_by(super_league_id=super_league_id)
        franchises = franchises_query.all()

        records: Dict[int, Dict[str, Any]] = {}
        for f in franchises:
            records[f.id] = {
                "franchise_id": f.id,
                "name": f.name,
                "owner_name": f.owner_name,
                "wins": 0,
                "losses": 0,
                "ties": 0,
                "points_for": 0.0,
                "points_against": 0.0,
                "games_played": 0,
            }

        for m in matchups:
            # Process team A
            if m.team_a_id in records:
                rec = records[m.team_a_id]
                rec["games_played"] += 1
                rec["points_for"] += m.team_a_score
                rec["points_against"] += m.team_b_score
                if m.team_b_id is None or m.team_a_score > m.team_b_score:
                    rec["wins"] += 1
                elif m.team_a_score < m.team_b_score:
                    rec["losses"] += 1
                else:
                    rec["ties"] += 1

            # Process team B
            if m.team_b_id and m.team_b_id in records:
                rec = records[m.team_b_id]
                rec["games_played"] += 1
                rec["points_for"] += m.team_b_score
                rec["points_against"] += m.team_a_score
                if m.team_b_score > m.team_a_score:
                    rec["wins"] += 1
                elif m.team_b_score < m.team_a_score:
                    rec["losses"] += 1
                else:
                    rec["ties"] += 1

        summary = list(records.values())
        for s in summary:
            total_g = s["games_played"]
            s["win_pct"] = round((s["wins"] + (0.5 * s["ties"])) / total_g, 3) if total_g > 0 else 0.0
            s["ppg"] = round(s["points_for"] / total_g, 2) if total_g > 0 else 0.0
            s["points_for"] = round(s["points_for"], 2)
            s["points_against"] = round(s["points_against"], 2)

        summary.sort(key=lambda x: (x["wins"], x["win_pct"], x["points_for"]), reverse=True)
        return {"group_by": "franchise", "count": len(summary), "data": summary}

    elif group_by == "players":
        # Aggregate top performing players across matching matchups
        m_ids = [m.id for m in matchups]
        player_stats = db.query(
            PlayerStat.player_name,
            PlayerStat.position,
            func.count(PlayerStat.id).label("appearances"),
            func.sum(PlayerStat.points_scored).label("total_points"),
            func.avg(PlayerStat.points_scored).label("avg_points"),
            func.max(PlayerStat.points_scored).label("max_points")
        ).filter(PlayerStat.matchup_id.in_(m_ids) if m_ids else False)\
         .group_by(PlayerStat.player_name, PlayerStat.position)\
         .order_by(func.sum(PlayerStat.points_scored).desc())\
         .limit(50)\
         .all()

        p_data = [
            {
                "player_name": row[0],
                "position": row[1],
                "appearances": row[2],
                "total_points": round(float(row[3]), 2),
                "avg_points": round(float(row[4]), 2),
                "max_points": round(float(row[5]), 2),
            }
            for row in player_stats
        ]
        return {"group_by": "players", "count": len(p_data), "data": p_data}

    else:
        # Default: list of matchups
        result = [m.to_dict() for m in matchups]
        return {"group_by": "matchup", "count": len(result), "data": result}


@app.get("/api/live/scores")
async def get_live_scores():
    """Returns the current cached scores for live scoreboards."""
    scores = []
    for key, val in live_sync_service.cached_scores.items():
        parts = key.split(":")
        team_id = parts[1] if len(parts) > 1 else parts[0]
        scores.append({
            "key": key,
            "team_id": team_id,
            "score": val
        })
    return {"status": "ok", "scores": scores}


@app.post("/api/live/trigger-demo-tick")
async def trigger_demo_tick():
    """Manual trigger to push a live score update over the WebSocket for testing."""
    await live_sync_service._run_simulated_tick()
    return {"status": "success", "message": "Simulated live score update broadcasted."}


# --- WebSocket Endpoint ---
@app.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket):
    """
    Maintains persistent WebSocket connection for real-time live score updates.
    """
    await ws_manager.connect(websocket)
    # Send welcome handshake with connection status
    await websocket.send_text(json.dumps({
        "type": "connection_established",
        "status": "connected",
        "message": "Connected to Fantasy-Stats Live Sync Stream"
    }))
    try:
        while True:
            # Keep connection open and receive any client ping or filter requests
            data_text = await websocket.receive_text()
            try:
                data = json.loads(data_text)
                if data.get("action") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong", "timestamp": "now"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


# --- Serve Static Frontend Files ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@app.get("/favicon.ico")
async def get_favicon():
    fav_path = os.path.join(BASE_DIR, "favicon.svg")
    if os.path.exists(fav_path):
        return FileResponse(fav_path, media_type="image/svg+xml")
    raise HTTPException(status_code=404)


@app.get("/favicon.svg")
async def get_favicon_svg():
    return FileResponse(os.path.join(BASE_DIR, "favicon.svg"), media_type="image/svg+xml")


@app.get("/styles.css")
async def get_styles():
    return FileResponse(os.path.join(BASE_DIR, "styles.css"), media_type="text/css")


@app.get("/api.js")
async def get_api_js():
    return FileResponse(os.path.join(BASE_DIR, "api.js"), media_type="application/javascript")


@app.get("/websocket.js")
async def get_websocket_js():
    return FileResponse(os.path.join(BASE_DIR, "websocket.js"), media_type="application/javascript")


@app.get("/")
async def get_index():
    return FileResponse(os.path.join(BASE_DIR, "index.html"), media_type="text/html")

