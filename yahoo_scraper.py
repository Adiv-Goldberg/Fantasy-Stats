"""
Yahoo Fantasy Sports API Ingestion Engine.
Connects to Yahoo Fantasy REST API (https://fantasysports.yahooapis.com/fantasy/v2/),
automatically discovers and imports all historical seasons via renew keys or historical game IDs,
parses league metadata, standings, and weekly scoreboards, and normalizes into the relational database schema.
"""

import logging
import requests
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from models import PlatformLeague, Franchise, Matchup, PlayerStat

logger = logging.getLogger("yahoo_scraper")

YAHOO_BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Historical Game IDs by Sport
HISTORICAL_GAME_IDS = {
    "nfl": {
        2024: "449",
        2023: "423",
        2022: "414",
        2021: "406",
        2020: "399",
        2019: "390",
        2018: "380",
    },
    "mlb": {
        2024: "434",
        2023: "416",
        2022: "404",
        2021: "398",
        2020: "396",
    },
    "nba": {
        2024: "454",
        2023: "428",
        2022: "418",
        2021: "410",
        2020: "402",
    },
    "nhl": {
        2024: "453",
        2023: "427",
        2022: "419",
        2021: "411",
    }
}


def format_yahoo_league_key(league_id: str, sport: str = "nfl") -> str:
    lid = str(league_id).strip()
    if ".l." in lid or "_" in lid:
        return lid.replace("_", ".l.") if "_" in lid and ".l." not in lid else lid
    sport_key = sport.lower()
    return f"{sport_key}.l.{lid}"


def extract_numeric_id(league_key: str) -> str:
    if ".l." in league_key:
        return league_key.split(".l.")[-1]
    if "_" in league_key:
        return league_key.split("_")[-1]
    return league_key


def get_yahoo_headers_and_cookies(
    access_token: Optional[str] = None,
    cookie: Optional[str] = None
) -> Tuple[Dict[str, str], Dict[str, str]]:
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json",
    }
    cookies = {}

    if access_token and access_token.strip():
        tok = access_token.strip()
        if not tok.lower().startswith("bearer "):
            tok = f"Bearer {tok}"
        headers["Authorization"] = tok

    if cookie and cookie.strip():
        for part in cookie.strip().split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                cookies[k.strip()] = v.strip()

    return headers, cookies


def fetch_yahoo_endpoint(
    endpoint_path: str,
    access_token: Optional[str] = None,
    cookie: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    url = f"{YAHOO_BASE_URL}/{endpoint_path.lstrip('/')}"
    headers, cookies = get_yahoo_headers_and_cookies(access_token, cookie)
    p = {"format": "json"}
    if params:
        p.update(params)

    resp = requests.get(url, headers=headers, cookies=cookies, params=p, timeout=15)

    if resp.status_code in [401, 403]:
        raise PermissionError(
            "Yahoo authentication failed. Please provide a valid Yahoo OAuth Access Token or session cookie."
        )
    elif resp.status_code == 404:
        raise ValueError(f"Yahoo endpoint '{endpoint_path}' not found. Check your League ID.")

    resp.raise_for_status()
    return resp.json()


def parse_and_store_yahoo_season(
    league_key: str,
    year: int,
    super_league_id: int,
    db: Session,
    access_token: Optional[str] = None,
    cookie: Optional[str] = None,
    max_weeks: int = 18
) -> Tuple[PlatformLeague, Optional[str]]:
    """
    Scrapes a single season of a Yahoo league and returns (platform_league, renew_previous_key).
    """
    data = fetch_yahoo_endpoint(f"league/{league_key}", access_token=access_token, cookie=cookie)

    fantasy_content = data.get("fantasy_content", {})
    league_data = fantasy_content.get("league", [])

    meta = {}
    if isinstance(league_data, list) and len(league_data) > 0:
        meta = league_data[0]
    elif isinstance(league_data, dict):
        meta = league_data

    league_name = meta.get("name", f"Yahoo League {league_key}")
    season_val = meta.get("season", year)
    renew_key = meta.get("renew")

    try:
        season_year = int(season_val)
    except Exception:
        season_year = year

    # 1. PlatformLeague
    platform_league = db.query(PlatformLeague).filter_by(
        platform="Yahoo",
        original_id=league_key,
        year=season_year,
        super_league_id=super_league_id
    ).first()

    if not platform_league:
        platform_league = PlatformLeague(
            platform="Yahoo",
            original_id=league_key,
            year=season_year,
            name=league_name,
            super_league_id=super_league_id
        )
        db.add(platform_league)
        db.flush()

    # 2. Standings & Franchises
    team_franchise_map: Dict[str, Franchise] = {}
    try:
        standings_data = fetch_yahoo_endpoint(
            f"league/{league_key}/standings",
            access_token=access_token,
            cookie=cookie
        )
        fc_standings = standings_data.get("fantasy_content", {}).get("league", [])
        teams_wrapper = None
        for item in fc_standings:
            if isinstance(item, dict) and "standings" in item:
                teams_wrapper = item.get("standings", [{}])[0].get("teams", {})
                break

        if isinstance(teams_wrapper, dict):
            for k, val in teams_wrapper.items():
                if k == "count":
                    continue
                team_info = val.get("team", [])
                team_key = ""
                team_name = ""
                owner_name = ""
                for part in team_info:
                    if isinstance(part, list):
                        for sub in part:
                            if isinstance(sub, dict):
                                if "team_key" in sub:
                                    team_key = sub["team_key"]
                                if "name" in sub:
                                    team_name = sub["name"]
                                if "managers" in sub:
                                    mgrs = sub["managers"]
                                    if isinstance(mgrs, list) and len(mgrs) > 0:
                                        owner_name = mgrs[0].get("manager", {}).get("nickname", "")
                    elif isinstance(part, dict):
                        if "team_key" in part:
                            team_key = part["team_key"]
                        if "name" in part:
                            team_name = part["name"]

                if not team_name:
                    team_name = f"Team {team_key}"

                franchise = db.query(Franchise).filter_by(
                    super_league_id=super_league_id,
                    name=team_name
                ).first()

                if not franchise:
                    franchise = Franchise(
                        name=team_name,
                        owner_name=owner_name or "Manager",
                        super_league_id=super_league_id,
                        external_team_id=f"yahoo_{team_key}"
                    )
                    db.add(franchise)
                    db.flush()

                team_franchise_map[team_key] = franchise
    except Exception as e:
        logger.warning(f"Could not load Yahoo standings for {league_key}: {e}")

    # 3. Weekly Matchups
    for week in range(1, max_weeks + 1):
        try:
            scoreboard_data = fetch_yahoo_endpoint(
                f"league/{league_key}/scoreboard;week={week}",
                access_token=access_token,
                cookie=cookie
            )
            fc_sb = scoreboard_data.get("fantasy_content", {}).get("league", [])
            sb_wrapper = None
            for item in fc_sb:
                if isinstance(item, dict) and "scoreboard" in item:
                    sb_wrapper = item.get("scoreboard", {}).get("0", {}).get("matchups", {})
                    break

            if not isinstance(sb_wrapper, dict):
                continue

            for k, val in sb_wrapper.items():
                if k == "count":
                    continue
                matchup_meta = val.get("matchup", {})
                is_playoff = bool(matchup_meta.get("is_playoffs") == "1")
                teams_data = matchup_meta.get("0", {}).get("teams", {})

                if not isinstance(teams_data, dict) or "0" not in teams_data:
                    continue

                t0 = teams_data.get("0", {}).get("team", [])
                t1 = teams_data.get("1", {}).get("team", []) if "1" in teams_data else None

                def extract_team_data(team_parts):
                    key = ""
                    name = ""
                    points = 0.0
                    for elem in team_parts:
                        if isinstance(elem, list):
                            for sub in elem:
                                if isinstance(sub, dict):
                                    if "team_key" in sub: key = sub["team_key"]
                                    if "name" in sub: name = sub["name"]
                        elif isinstance(elem, dict):
                            if "team_key" in elem: key = elem["team_key"]
                            if "name" in elem: name = elem["name"]
                            if "team_points" in elem:
                                try: points = float(elem["team_points"].get("total", 0.0))
                                except: pass
                    return key, name, points

                t0_key, t0_name, t0_pts = extract_team_data(t0)
                t1_key, t1_name, t1_pts = extract_team_data(t1) if t1 else ("", "", 0.0)

                f_a = team_franchise_map.get(t0_key)
                if not f_a and t0_name:
                    f_a = Franchise(name=t0_name, super_league_id=super_league_id, external_team_id=f"yahoo_{t0_key}")
                    db.add(f_a)
                    db.flush()
                    team_franchise_map[t0_key] = f_a

                f_b = team_franchise_map.get(t1_key) if t1_key else None
                if not f_b and t1_name:
                    f_b = Franchise(name=t1_name, super_league_id=super_league_id, external_team_id=f"yahoo_{t1_key}")
                    db.add(f_b)
                    db.flush()
                    team_franchise_map[t1_key] = f_b

                if not f_a:
                    continue

                existing_m = db.query(Matchup).filter_by(
                    platform_league_id=platform_league.id,
                    week=week,
                    year=season_year,
                    team_a_id=f_a.id,
                    team_b_id=f_b.id if f_b else None
                ).first()

                if not existing_m:
                    m_obj = Matchup(
                        week=week,
                        year=season_year,
                        team_a_id=f_a.id,
                        team_b_id=f_b.id if f_b else None,
                        team_a_score=t0_pts,
                        team_b_score=t1_pts,
                        platform_league_id=platform_league.id,
                        is_playoffs=is_playoff
                    )
                    db.add(m_obj)
                    db.flush()
                else:
                    existing_m.team_a_score = t0_pts
                    existing_m.team_b_score = t1_pts
        except Exception as e:
            logger.debug(f"Done or error fetching Yahoo week {week}: {e}")
            break

    db.commit()
    return platform_league, renew_key


def scrape_yahoo_league(
    league_id: str,
    super_league_id: int,
    db: Session,
    year: int = 2024,
    sport: str = "nfl",
    access_token: Optional[str] = None,
    cookie: Optional[str] = None,
    max_weeks: int = 18,
    import_all_years: bool = True
) -> Dict[str, Any]:
    """
    Main ingestion entry point for Yahoo Fantasy Sports.
    Traverses historical seasons via renew keys and historical game IDs.
    """
    initial_key = format_yahoo_league_key(league_id, sport)
    current_key = initial_key
    imported_seasons = []
    visited_keys = set()

    # 1. Primary season and follow renew chain backwards
    while current_key and current_key not in visited_keys:
        visited_keys.add(current_key)
        try:
            pl, renew_prev = parse_and_store_yahoo_season(
                league_key=current_key,
                year=year,
                super_league_id=super_league_id,
                db=db,
                access_token=access_token,
                cookie=cookie,
                max_weeks=max_weeks
            )
            imported_seasons.append({"year": pl.year, "league_name": pl.name, "key": current_key})

            if not import_all_years or not renew_prev:
                break

            current_key = format_yahoo_league_key(renew_prev, sport)
        except Exception as e:
            if len(imported_seasons) == 0:
                raise
            logger.warning(f"Stopped traversing Yahoo renew keys at {current_key}: {e}")
            break

    # 2. If renew key wasn't available, check historical game IDs for bare league IDs
    if import_all_years and len(imported_seasons) <= 1:
        raw_num = extract_numeric_id(initial_key)
        hist_map = HISTORICAL_GAME_IDS.get(sport.lower(), {})
        for hist_year, game_id in sorted(hist_map.items(), reverse=True):
            if any(s["year"] == hist_year for s in imported_seasons):
                continue
            hist_key = f"{game_id}.l.{raw_num}"
            if hist_key in visited_keys:
                continue
            visited_keys.add(hist_key)
            try:
                pl, _ = parse_and_store_yahoo_season(
                    league_key=hist_key,
                    year=hist_year,
                    super_league_id=super_league_id,
                    db=db,
                    access_token=access_token,
                    cookie=cookie,
                    max_weeks=max_weeks
                )
                imported_seasons.append({"year": pl.year, "league_name": pl.name, "key": hist_key})
            except Exception:
                # Historical year not present for this league ID
                pass

    return {
        "status": "success",
        "platform": "Yahoo",
        "league_key": initial_key,
        "super_league_id": super_league_id,
        "imported_seasons": imported_seasons
    }
