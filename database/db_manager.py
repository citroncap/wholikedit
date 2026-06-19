"""SQLite database – liked video cache and game history only.
No user accounts; player identity is handled by local_player.py.
"""
from __future__ import annotations
import sqlite3
import json
import logging
from typing import Optional, List
from utils.config import DB_PATH
from models.game import GameVideo

log = logging.getLogger(__name__)

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS liked_videos (
    video_id        TEXT PRIMARY KEY,
    description     TEXT NOT NULL DEFAULT '',
    thumbnail_url   TEXT NOT NULL DEFAULT '',
    thumbnail_path  TEXT,
    author_username TEXT NOT NULL DEFAULT '',
    view_count      INTEGER NOT NULL DEFAULT 0,
    like_count      INTEGER NOT NULL DEFAULT 0,
    fetched_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS game_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    room_code    TEXT    NOT NULL,
    played_at    TEXT    NOT NULL,
    player_count INTEGER NOT NULL DEFAULT 0,
    total_rounds INTEGER NOT NULL DEFAULT 0,
    my_score     INTEGER NOT NULL DEFAULT 0,
    my_rank      INTEGER NOT NULL DEFAULT 0,
    won          INTEGER NOT NULL DEFAULT 0,
    result_json  TEXT
);
"""


class DatabaseManager:
    def __init__(self) -> None:
        self._path = DB_PATH

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
        log.info("DB initialized at %s", self._path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        return conn

    # ── Liked video cache ────────────────────────────────────────────────────

    def upsert_video(self, video: GameVideo, fetched_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO liked_videos
                   (video_id, description, thumbnail_url, thumbnail_path,
                    author_username, view_count, like_count, fetched_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    video.video_id, video.description, video.thumbnail_url,
                    video.thumbnail_path, video.author_username,
                    video.view_count, video.like_count, fetched_at,
                ),
            )

    def get_all_videos(self) -> List[GameVideo]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM liked_videos ORDER BY fetched_at DESC"
            ).fetchall()
        return [self._row_to_video(r) for r in rows]

    def get_video_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM liked_videos").fetchone()
        return row[0]

    def clear_videos(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM liked_videos")

    def _row_to_video(self, row: sqlite3.Row) -> GameVideo:
        return GameVideo(
            video_id=row["video_id"],
            description=row["description"],
            thumbnail_url=row["thumbnail_url"],
            thumbnail_path=row["thumbnail_path"],
            author_username=row["author_username"],
            view_count=row["view_count"],
            like_count=row["like_count"],
            owner_player_id="",  # filled at game time
        )

    # ── Game history ─────────────────────────────────────────────────────────

    def record_game(
        self,
        room_code: str,
        played_at: str,
        player_count: int,
        total_rounds: int,
        my_score: int,
        my_rank: int,
        won: bool,
        result: dict,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO game_history
                   (room_code, played_at, player_count, total_rounds,
                    my_score, my_rank, won, result_json)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    room_code, played_at, player_count, total_rounds,
                    my_score, my_rank, int(won), json.dumps(result),
                ),
            )

    def get_history(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM game_history ORDER BY played_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT COUNT(*) AS games,
                          SUM(won) AS wins,
                          SUM(my_score) AS total_score,
                          AVG(CASE WHEN total_rounds > 0
                              THEN CAST(my_score AS REAL)/total_rounds ELSE 0 END) AS avg_score
                   FROM game_history"""
            ).fetchone()
        return dict(row) if row else {"games": 0, "wins": 0, "total_score": 0, "avg_score": 0}
