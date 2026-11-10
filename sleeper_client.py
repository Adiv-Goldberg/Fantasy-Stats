"""
Sleeper Fantasy Sports API Ingestion Engine.
Connects to Sleeper's public REST API (https://api.sleeper.app/v1/league/),
normalizes users, rosters, and weekly matchups into the standard database schema.
"""

import logging
import requests
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from models import PlatformLeague, Franchise, Matchup, PlayerStat

logger = logging.getLogger("sleeper_client")

SLEEPER_BASE_URL = "https://api.sleeper.app/v1"


def fetch_sleeper_league(league_id: str) -> Dict[str, Any]:
    url = f"{SLEEPER_BASE_URL}/league/{league_id}"
    resp = requests.get(url, timeout=12)
    resp.raise_for_status()
    return resp.json()


def fetch_sleeper_users(league_id: str) -> List[Dict[str, Any]]:
    url = f"{SLEEPER_BASE_URL}/league/{league_id}/users"
    resp = requests.get(url, timeout=12)
    resp.raise_for_status()
    return resp.json()


def fetch_sleeper_rosters(league_id: str) -> List[Dict[str, Any]]:
    url = f"{SLEEPER_BASE_URL}/league/{league_id}/rosters"
    resp = requests.get(url, timeout=12)
    resp.raise_for_status()
    return resp.json()


def fetch_sleeper_matchups(league_id: str, week: int) -> List[Dict[str, Any]]:
    url = f"{SLEEPER_BASE_URL}/league/{league_id}/matchups/{week}"
    resp = requests.get(url, timeout=12)
    resp.raise_for_status()
    return resp.json()


def scrape_sleeper_league(
    league_id: str,
    super_league_id: int,
    db: Session,
    max_weeks: int = 18
) -> Dict[str, Any]:
    league_info = fetch_sleeper_league(league_id)
    users = fetch_sleeper_users(league_id)
    rosters = fetch_sleeper_rosters(league_id)

    season_str = league_info.get("season", "2024")
    year = int(season_str) if str(season_str).isdigit() else 2024
    league_name = league_info.get("name", f"Sleeper League {league_id}")

    platform_league = db.query(PlatformLeague).filter_by(
        platform="Sleeper",
        original_id=str(league_id),
        year=year,
        super_league_id=super_league_id
    ).first()

    if not platform_league:
        platform_league = PlatformLeague(
            platform="Sleeper",
            original_id=str(league_id),
            year=year,
            name=league_name,
            super_league_id=super_league_id
        )
        db.add(platform_league)
        db.flush()

    user_map = {}
    for u in users:
        u_id = u.get("user_id")
        display_name = u.get("display_name") or u.get("metadata", {}).get("team_name") or f"User {u_id}"
        team_name = u.get("metadata", {}).get("team_name") or f"{display_name}'s Team"
        user_map[u_id] = {"display_name": display_name, "team_name": team_name}

    roster_to_franchise: Dict[int, Franchise] = {}
    for r in rosters:
        roster_id = r.get("roster_id")
        owner_id = r.get("owner_id")
        user_data = user_map.get(owner_id, {"display_name": f"Owner {roster_id}", "team_name": f"Team {roster_id}"})
        t_name = user_data["team_name"]
        o_name = user_data["display_name"]

        franchise = db.query(Franchise).filter_by(
            super_league_id=super_league_id,
            name=t_name
        ).first()

        if not franchise:
            franchise = Franchise(
                name=t_name,
                owner_name=o_name,
                super_league_id=super_league_id,
                external_team_id=f"sleeper_roster_{roster_id}"
            )
            db.add(franchise)
            db.flush()

        roster_to_franchise[roster_id] = franchise

    for week in range(1, max_weeks + 1):
        try:
            weekly_matchups = fetch_sleeper_matchups(league_id, week)
            if not weekly_matchups:
                continue

            matchup_groups: Dict[int, List[Dict[str, Any]]] = {}
            for entry in weekly_matchups:
                m_id = entry.get("matchup_id")
                if m_id is not None:
                    matchup_groups.setdefault(m_id, []).append(entry)

            for m_id, sides in matchup_groups.items():
                if len(sides) == 2:
                    side_a, side_b = sides[0], sides[1]
                    f_a = roster_to_franchise.get(side_a.get("roster_id"))
                    f_b = roster_to_franchise.get(side_b.get("roster_id"))
                    score_a = float(side_a.get("points") or 0.0)
                    score_b = float(side_b.get("points") or 0.0)
                elif len(sides) == 1:
                    side_a = sides[0]
                    side_b = None
                    f_a = roster_to_franchise.get(side_a.get("roster_id"))
                    f_b = None
                    score_a = float(side_a.get("points") or 0.0)
                    score_b = 0.0
                else:
                    continue

                if not f_a:
                    continue

                existing_matchup = db.query(Matchup).filter_by(
                    platform_league_id=platform_league.id,
                    week=week,
                    year=year,
                    team_a_id=f_a.id,
                    team_b_id=f_b.id if f_b else None
                ).first()

                if not existing_matchup:
                    matchup = Matchup(
                        week=week,
                        year=year,
                        team_a_id=f_a.id,
                        team_b_id=f_b.id if f_b else None,
                        team_a_score=score_a,
                        team_b_score=score_b,
                        platform_league_id=platform_league.id,
                        is_playoffs=(week >= 15)
                    )
                    db.add(matchup)
                    db.flush()
                else:
                    matchup = existing_matchup
                    matchup.team_a_score = score_a
                    matchup.team_b_score = score_b

                for side, f_obj in [(side_a, f_a), (side_b, f_b)]:
                    if not side or not f_obj:
                        continue
                    players_points = side.get("players_points") or {}
                    starters = set(side.get("starters") or [])

                    for p_id, p_pts in players_points.items():
                        is_starter = p_id in starters
                        p_name = f"Player {p_id}"

                        existing_pstat = db.query(PlayerStat).filter_by(
                            matchup_id=matchup.id,
                            player_name=p_name,
                            franchise_id=f_obj.id
                        ).first()

                        if not existing_pstat:
                            db.add(PlayerStat(
                                player_name=p_name,
                                position="POS",
                                points_scored=float(p_pts or 0.0),
                                matchup_id=matchup.id,
                                franchise_id=f_obj.id,
                                is_starter=is_starter
                            ))

        except Exception as e:
            logger.debug(f"Done or error fetching Sleeper week {week}: {e}")
            break

    db.commit()
    return {
        "status": "success",
        "league_id": league_id,
        "league_name": platform_league.name,
        "super_league_id": super_league_id,
    }
