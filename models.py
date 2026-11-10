"""
Relational database schema using SQLAlchemy ORM.
Defines tables for SuperLeagues, PlatformLeagues, Franchises, Matchups, and PlayerStats.
"""

from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class SuperLeague(Base):
    """
    Top-level organizational league grouping multiple seasons and platform instances.
    Example: 'The Dynasty League' across 2018-2024 on ESPN and Sleeper.
    """
    __tablename__ = "super_leagues"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    sport = Column(String(50), default="NFL", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    platform_leagues = relationship("PlatformLeague", back_populates="super_league", cascade="all, delete-orphan")
    franchises = relationship("Franchise", back_populates="super_league", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "sport": self.sport,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "platform_leagues_count": len(self.platform_leagues) if self.platform_leagues else 0,
            "franchises_count": len(self.franchises) if self.franchises else 0,
        }


class PlatformLeague(Base):
    """
    Represents an imported league instance on a specific platform (ESPN or Sleeper) for a given year.
    """
    __tablename__ = "platform_leagues"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    platform = Column(String(50), nullable=False)  # "ESPN" or "Sleeper"
    original_id = Column(String(100), nullable=False)  # External League ID from ESPN or Sleeper
    year = Column(Integer, nullable=False)
    name = Column(String(150), nullable=True)
    super_league_id = Column(Integer, ForeignKey("super_leagues.id"), nullable=False)

    # Relationships
    super_league = relationship("SuperLeague", back_populates="platform_leagues")
    matchups = relationship("Matchup", back_populates="platform_league", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "platform": self.platform,
            "original_id": self.original_id,
            "year": self.year,
            "name": self.name,
            "super_league_id": self.super_league_id,
        }


class Franchise(Base):
    """
    Universal team mapping to a specific owner/user across all platforms and seasons.
    """
    __tablename__ = "franchises"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    owner_name = Column(String(100), nullable=True)
    super_league_id = Column(Integer, ForeignKey("super_leagues.id"), nullable=False)
    external_team_id = Column(String(100), nullable=True)  # Associated external platform ID if any

    # Relationships
    super_league = relationship("SuperLeague", back_populates="franchises")
    matchups_as_a = relationship("Matchup", foreign_keys="Matchup.team_a_id", back_populates="team_a")
    matchups_as_b = relationship("Matchup", foreign_keys="Matchup.team_b_id", back_populates="team_b")
    player_stats = relationship("PlayerStat", back_populates="franchise")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "owner_name": self.owner_name,
            "super_league_id": self.super_league_id,
            "external_team_id": self.external_team_id,
        }


class Matchup(Base):
    """
    A single head-to-head matchup between Team A and Team B in a given week and season.
    """
    __tablename__ = "matchups"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    week = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    team_a_id = Column(Integer, ForeignKey("franchises.id"), nullable=False)
    team_b_id = Column(Integer, ForeignKey("franchises.id"), nullable=True)  # Nullable for bye weeks
    team_a_score = Column(Float, default=0.0, nullable=False)
    team_b_score = Column(Float, default=0.0, nullable=False)
    platform_league_id = Column(Integer, ForeignKey("platform_leagues.id"), nullable=False)
    is_playoffs = Column(Boolean, default=False)

    # Relationships
    platform_league = relationship("PlatformLeague", back_populates="matchups")
    team_a = relationship("Franchise", foreign_keys=[team_a_id], back_populates="matchups_as_a")
    team_b = relationship("Franchise", foreign_keys=[team_b_id], back_populates="matchups_as_b")
    player_stats = relationship("PlayerStat", back_populates="matchup", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "week": self.week,
            "year": self.year,
            "team_a_id": self.team_a_id,
            "team_a_name": self.team_a.name if self.team_a else f"Team {self.team_a_id}",
            "team_a_owner": self.team_a.owner_name if self.team_a else "",
            "team_a_score": round(self.team_a_score, 2),
            "team_b_id": self.team_b_id,
            "team_b_name": self.team_b.name if self.team_b else ("BYE" if self.team_b_id is None else f"Team {self.team_b_id}"),
            "team_b_owner": self.team_b.owner_name if self.team_b else "",
            "team_b_score": round(self.team_b_score, 2),
            "platform_league_id": self.platform_league_id,
            "platform": self.platform_league.platform if self.platform_league else "Unknown",
            "is_playoffs": self.is_playoffs,
            "winner_id": (
                self.team_a_id if self.team_a_score > self.team_b_score
                else (self.team_b_id if self.team_b_score > self.team_a_score else None)
            ) if self.team_b_id is not None else self.team_a_id
        }


class PlayerStat(Base):
    """
    Performance stat for an individual player in a specific matchup and roster slot.
    """
    __tablename__ = "player_stats"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    player_name = Column(String(100), nullable=False)
    position = Column(String(20), nullable=False)
    points_scored = Column(Float, default=0.0, nullable=False)
    matchup_id = Column(Integer, ForeignKey("matchups.id"), nullable=False)
    franchise_id = Column(Integer, ForeignKey("franchises.id"), nullable=True)
    is_starter = Column(Boolean, default=True)

    # Relationships
    matchup = relationship("Matchup", back_populates="player_stats")
    franchise = relationship("Franchise", back_populates="player_stats")

    def to_dict(self):
        return {
            "id": self.id,
            "player_name": self.player_name,
            "position": self.position,
            "points_scored": round(self.points_scored, 2),
            "matchup_id": self.matchup_id,
            "franchise_id": self.franchise_id,
            "franchise_name": self.franchise.name if self.franchise else None,
            "is_starter": self.is_starter,
        }

