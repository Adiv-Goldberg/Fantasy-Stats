"""
ESPN Fantasy Sports API v3 Scraper and Ingestion Engine.
Connects to ESPN Fantasy endpoints using SWID and espn_s2 session cookies,
automatically discovers all historical seasons via previousSeasons,
parses mMatchupScore, mRoster, and mTeam views, and populates the database models.
"""

import logging
import requests
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from models import PlatformLeague, Franchise, Matchup, PlayerStat

logger = logging.getLogger("espn_scraper")

ESPN_POSITION_MAP = {
    0: "QB",
    1: "TQB",
    2: "RB",
    3: "RB/WR",
    4: "WR",
    5: "WR/TE",
    6: "TE",
    7: "OP",
    8: "DT",
    9: "DE",
    10: "LB",
    11: "DL",
    12: "CB",
    13: "S",
    14: "DB",
    15: "DP",
    16: "D/ST",
    17: "K",
    18: "P",
    19: "HC",
    20: "BE",
    21: "IR",
    23: "FLEX",
}

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def get_espn_headers(swid: Optional[str] = None, espn_s2: Optional[str] = None) -> Dict[str, str]:
    return {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json",
    }


def get_espn_cookies(swid: Optional[str] = None, espn_s2: Optional[str] = None) -> Dict[str, str]:
    cookies = {}
    if swid:
        cleaned_swid = swid.strip()
        if not cleaned_swid.startswith("{") and "-" in cleaned_swid:
            cleaned_swid = "{" + cleaned_swid + "}"
        cookies["SWID"] = cleaned_swid
    if espn_s2:
        cookies["espn_s2"] = espn_s2.strip()
    return cookies


def validate_espn_session(league_id: str, year: int, swid: str, espn_s2: str, sport: str = "ffl") -> Dict[str, Any]:
    url = f"https://fantasy.espn.com/apis/v3/games/{sport}/seasons/{year}/segments/0/leagues/{league_id}"
    cookies = get_espn_cookies(swid, espn_s2)
    headers = get_espn_headers(swid, espn_s2)
    params = {"view": "mSettings"}

    try:
        response = requests.get(url, headers=headers, cookies=cookies, params=params, timeout=12)
        if response.status_code == 200:
            data = response.json()
            league_name = data.get("settings", {}).get("name", f"ESPN League {league_id}")
            return {"success": True, "league_name": league_name}
        elif response.status_code in [401, 403]:
            return {"success": False, "message": "ESPN authentication failed. Verify your SWID and espn_s2 cookies."}
        elif response.status_code == 404:
            return {"success": False, "message": f"League {league_id} not found for season {year}."}
        else:
            return {"success": False, "message": f"ESPN returned HTTP {response.status_code}"}
    except Exception as e:
        logger.error(f"Error validating ESPN session: {e}")
        return {"success": False, "message": f"Connection error: {str(e)}"}


def fetch_espn_season_data(
    league_id: str,
    year: int,
    swid: Optional[str] = None,
    espn_s2: Optional[str] = None,
    sport: str = "ffl"
) -> Dict[str, Any]:
    url = f"https://fantasy.espn.com/apis/v3/games/{sport}/seasons/{year}/segments/0/leagues/{league_id}"
    cookies = get_espn_cookies(swid, espn_s2)
    headers = get_espn_headers(swid, espn_s2)
    params = [
        ("view", "mMatchupScore"),
        ("view", "mRoster"),
        ("view", "mTeam"),
        ("view", "mSettings"),
    ]

    response = requests.get(url, headers=headers, cookies=cookies, params=params, timeout=20)
    if response.status_code in [401, 403]:
        raise PermissionError("ESPN authentication failed. Please verify your SWID and espn_s2 cookies for private leagues.")
    elif response.status_code == 404:
        raise ValueError(f"League ID '{league_id}' was not found on ESPN for season {year}.")
    response.raise_for_status()
    return response.json()


def parse_and_store_espn_data(
    data: Dict[str, Any],
    league_id: str,
    year: int,
    super_league_id: int,
    db: Session
) -> PlatformLeague:
    settings = data.get("settings", {})
    league_name = settings.get("name", f"ESPN League {league_id} ({year})")

    platform_league = db.query(PlatformLeague).filter_by(
        platform="ESPN",
        original_id=str(league_id),
        year=year,
        super_league_id=super_league_id
    ).first()

    if not platform_league:
        platform_league = PlatformLeague(
            platform="ESPN",
            original_id=str(league_id),
            year=year,
            name=league_name,
            super_league_id=super_league_id
        )
        db.add(platform_league)
        db.flush()

    members = {m.get("id"): f"{m.get('firstName', '')} {m.get('lastName', '')}".strip() for m in data.get("members", [])}
    teams = data.get("teams", [])
    team_franchise_map: Dict[int, Franchise] = {}

    for t in teams:
        t_id = t.get("id")
        t_name = f"{t.get('location', '')} {t.get('nickname', '')}".strip() or t.get("name") or f"Team {t_id}"
        owner_id = (t.get("owners") or [None])[0]
        owner_name = members.get(owner_id) or t.get("abbrev") or f"Owner {t_id}"

        franchise = db.query(Franchise).filter_by(
            super_league_id=super_league_id,
            name=t_name
        ).first()

        if not franchise:
            franchise = Franchise(
                name=t_name,
                owner_name=owner_name,
                super_league_id=super_league_id,
                external_team_id=f"espn_{t_id}"
            )
            db.add(franchise)
            db.flush()

        team_franchise_map[t_id] = franchise

    schedule = data.get("schedule", [])
    for m in schedule:
        matchup_period = m.get("matchupPeriodId", 1)
        home = m.get("home", {})
        away = m.get("away", {})

        home_team_id = home.get("teamId") if home else None
        away_team_id = away.get("teamId") if away else None

        if not home_team_id and not away_team_id:
            continue

        team_a_franchise = team_franchise_map.get(home_team_id)
        team_b_franchise = team_franchise_map.get(away_team_id) if away_team_id else None

        if not team_a_franchise and team_b_franchise:
            team_a_franchise, team_b_franchise = team_b_franchise, None
            home, away = away, home

        if not team_a_franchise:
            continue

        team_a_score = float(home.get("totalPoints", 0.0)) if home else 0.0
        team_b_score = float(away.get("totalPoints", 0.0)) if away else 0.0
        is_playoff = bool(m.get("playoffTierType") not in [None, "NONE", 0])

        matchup = db.query(Matchup).filter_by(
            platform_league_id=platform_league.id,
            week=matchup_period,
            year=year,
            team_a_id=team_a_franchise.id,
            team_b_id=team_b_franchise.id if team_b_franchise else None
        ).first()

        if not matchup:
            matchup = Matchup(
                week=matchup_period,
                year=year,
                team_a_id=team_a_franchise.id,
                team_b_id=team_b_franchise.id if team_b_franchise else None,
                team_a_score=team_a_score,
                team_b_score=team_b_score,
                platform_league_id=platform_league.id,
                is_playoffs=is_playoff
            )
            db.add(matchup)
            db.flush()
        else:
            matchup.team_a_score = team_a_score
            matchup.team_b_score = team_b_score

        for side, franchise_obj in [(home, team_a_franchise), (away, team_b_franchise)]:
            if not side or not franchise_obj:
                continue
            roster = side.get("rosterForCurrentScoringPeriod", {}) or side.get("roster", {})
            entries = roster.get("entries", [])
            for entry in entries:
                player_pool_entry = entry.get("playerPoolEntry", {})
                player = player_pool_entry.get("player", {})
                p_name = player.get("fullName", "Unknown Player")
                lineup_slot_id = entry.get("lineupSlotId", 20)
                pos = ESPN_POSITION_MAP.get(lineup_slot_id, "FLEX")
                points = float(player_pool_entry.get("appliedStatTotal", 0.0))
                is_starter = lineup_slot_id not in [20, 21]

                existing_stat = db.query(PlayerStat).filter_by(
                    matchup_id=matchup.id,
                    player_name=p_name,
                    franchise_id=franchise_obj.id
                ).first()

                if not existing_stat:
                    p_stat = PlayerStat(
                        player_name=p_name,
                        position=pos,
                        points_scored=points,
                        matchup_id=matchup.id,
                        franchise_id=franchise_obj.id,
                        is_starter=is_starter
                    )
                    db.add(p_stat)
                else:
                    existing_stat.points_scored = points
                    existing_stat.is_starter = is_starter

    db.commit()
    return platform_league


def scrape_espn_league(
    league_id: str,
    years: List[int],
    swid: str,
    espn_s2: str,
    super_league_id: int,
    db: Session,
    sport: str = "ffl",
    import_all_years: bool = True
) -> Dict[str, Any]:
    """
    Scrapes an ESPN league across all historical years.
    Automatically discovers past seasons via ESPN's previousSeasons or scans backwards.
    """
    discovered_years = set(years)
    primary_year = max(years) if years else 2024

    # 1. Fetch primary year to discover all historical seasons
    try:
        primary_data = fetch_espn_season_data(league_id, primary_year, swid, espn_s2, sport=sport)
        status_info = primary_data.get("status", {})
        prev_seasons = status_info.get("previousSeasons", [])
        if isinstance(prev_seasons, list):
            for y in prev_seasons:
                if isinstance(y, int) and 2000 <= y <= 2030:
                    discovered_years.add(y)

        # Store primary year data
        parse_and_store_espn_data(primary_data, league_id, primary_year, super_league_id, db)
    except Exception as e:
        raise ValueError(f"Could not load primary ESPN season {primary_year}: {str(e)}")

    # 2. If import_all_years is True and previousSeasons didn't find much, scan backwards
    if import_all_years and len(discovered_years) <= 1:
        # Scan backwards up to 8 years
        for yr in range(primary_year - 1, max(2018, primary_year - 8), -1):
            try:
                data = fetch_espn_season_data(league_id, yr, swid, espn_s2, sport=sport)
                parse_and_store_espn_data(data, league_id, yr, super_league_id, db)
                discovered_years.add(yr)
            except Exception:
                # Season doesn't exist for this league ID; stop scanning
                break

    # 3. Process any other discovered seasons not yet processed
    for yr in sorted(discovered_years):
        if yr == primary_year:
            continue
        try:
            data = fetch_espn_season_data(league_id, yr, swid, espn_s2, sport=sport)
            parse_and_store_espn_data(data, league_id, yr, super_league_id, db)
        except Exception as e:
            logger.debug(f"Could not fetch historical season {yr} for ESPN league {league_id}: {e}")

    return {
        "status": "success",
        "league_id": league_id,
        "super_league_id": super_league_id,
        "imported_years": sorted(list(discovered_years))
    }
