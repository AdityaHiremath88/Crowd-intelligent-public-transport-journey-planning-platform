from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.config import (
    COMMUNITY_DB_PATH,
    COMMUNITY_RATE_LIMIT_PER_HOUR,
    COMMUNITY_NETWORK_RATE_LIMIT_PER_HOUR,
    COMMUNITY_REPORT_TTL_SECONDS,
    PRESENCE_TTL_SECONDS,
    REPORT_HMAC_SECRET,
)

class DuplicateSubmission(Exception):
    pass


class RateLimitExceeded(Exception):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


def _dt(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


class CommunityStore:
    """Separate transactional store for short-lived community signals.

    Raw IP addresses, precise coordinates, names and account identifiers are never
    persisted. A keyed digest is retained only until the signal expires.
    """

    def __init__(
        self,
        path: Path = COMMUNITY_DB_PATH,
        *,
        secret: str = REPORT_HMAC_SECRET,
        report_ttl_seconds: int = COMMUNITY_REPORT_TTL_SECONDS,
        presence_ttl_seconds: int = PRESENCE_TTL_SECONDS,
        rate_limit_per_hour: int = COMMUNITY_RATE_LIMIT_PER_HOUR,
        network_rate_limit_per_hour: int = COMMUNITY_NETWORK_RATE_LIMIT_PER_HOUR,
    ) -> None:
        self.path = Path(path)
        self.report_ttl_seconds = report_ttl_seconds
        self.presence_ttl_seconds = presence_ttl_seconds
        self.rate_limit_per_hour = rate_limit_per_hour
        self.network_rate_limit_per_hour = network_rate_limit_per_hour
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if secret:
            self.secret = secret.encode("utf-8")
            self.secret_is_persistent = True
        else:
            secret_path = self.path.with_suffix(self.path.suffix + ".hmac-key")
            try:
                with secret_path.open("x", encoding="ascii") as secret_file:
                    secret_file.write(secrets.token_hex(32))
                try:
                    os.chmod(secret_path, 0o600)
                except OSError:
                    pass
            except FileExistsError:
                pass
            self.secret = secret_path.read_text(encoding="ascii").strip().encode("ascii")
            if len(self.secret) < 32:
                raise RuntimeError("Community HMAC key file is invalid")
            self.secret_is_persistent = True
        with self._session() as con:
            con.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS community_reports (
                    report_id TEXT PRIMARY KEY,
                    stop_id TEXT NOT NULL,
                    stop_name TEXT NOT NULL,
                    route_id TEXT,
                    category TEXT NOT NULL,
                    feedback_code TEXT,
                    observed_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    reporter_key TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_reports_stop_expiry
                    ON community_reports(stop_id, expires_at);
                CREATE INDEX IF NOT EXISTS idx_reports_reporter_created
                    ON community_reports(reporter_key, created_at);
                CREATE TABLE IF NOT EXISTS presence_signals (
                    signal_id TEXT PRIMARY KEY,
                    stop_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    participant_key TEXT NOT NULL,
                    UNIQUE(stop_id, participant_key)
                );
                CREATE INDEX IF NOT EXISTS idx_presence_stop_expiry
                    ON presence_signals(stop_id, expires_at);
                CREATE INDEX IF NOT EXISTS idx_presence_participant_created
                    ON presence_signals(participant_key, created_at);
            """)
            for table in ("community_reports", "presence_signals"):
                columns = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
                if "network_key" not in columns:
                    con.execute(f"ALTER TABLE {table} ADD COLUMN network_key TEXT")
            con.execute("CREATE INDEX IF NOT EXISTS idx_reports_network_created ON community_reports(network_key,created_at)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_presence_network_created ON presence_signals(network_key,created_at)")

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=5.0)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=5000")
        return con

    @contextmanager
    def _session(self):
        con = self._connect()
        try:
            with con:
                yield con
        finally:
            con.close()

    def privacy_key(self, remote_addr: str, user_agent: str, scope: str) -> str:
        message = f"{scope}\0{remote_addr}\0{user_agent[:160]}".encode("utf-8")
        return hmac.new(self.secret, message, hashlib.sha256).hexdigest()

    @staticmethod
    def _expire(con: sqlite3.Connection, now: datetime) -> None:
        stamp = _dt(now)
        con.execute("DELETE FROM community_reports WHERE expires_at <= ?", (stamp,))
        con.execute("DELETE FROM presence_signals WHERE expires_at <= ?", (stamp,))

    def _rate_check(self, con: sqlite3.Connection, key: str, network_key: str, now: datetime) -> None:
        cutoff = _dt(now - timedelta(hours=1))
        reports = con.execute(
            "SELECT count(*) FROM community_reports WHERE reporter_key=? AND created_at>=?",
            (key, cutoff),
        ).fetchone()[0]
        presence = con.execute(
            "SELECT count(*) FROM presence_signals WHERE participant_key=? AND created_at>=?",
            (key, cutoff),
        ).fetchone()[0]
        network_reports = con.execute(
            "SELECT count(*) FROM community_reports WHERE network_key=? AND created_at>=?",
            (network_key, cutoff),
        ).fetchone()[0]
        network_presence = con.execute(
            "SELECT count(*) FROM presence_signals WHERE network_key=? AND created_at>=?",
            (network_key, cutoff),
        ).fetchone()[0]
        if reports + presence >= self.rate_limit_per_hour or network_reports + network_presence >= self.network_rate_limit_per_hour:
            raise RateLimitExceeded

    def submit_report(
        self, *, stop_id: str, stop_name: str, route_id: str | None, category: str,
        feedback_code: str | None, observed_at: datetime, reporter_key: str, network_key: str,
        now: datetime | None = None,
    ) -> dict:
        now = now or utc_now()
        created = _dt(now)
        expires_at = min(now + timedelta(seconds=self.report_ttl_seconds),
                         observed_at.astimezone(UTC) + timedelta(seconds=self.report_ttl_seconds))
        expires = _dt(expires_at)
        with self._session() as con:
            con.execute("BEGIN IMMEDIATE")
            self._expire(con, now)
            self._rate_check(con, reporter_key, network_key, now)
            existing = con.execute(
                "SELECT 1 FROM community_reports WHERE stop_id=? AND reporter_key=? LIMIT 1",
                (stop_id, reporter_key),
            ).fetchone()
            if existing:
                raise DuplicateSubmission
            report_id = secrets.token_urlsafe(18)
            con.execute(
                """INSERT INTO community_reports
                   (report_id,stop_id,stop_name,route_id,category,feedback_code,observed_at,created_at,expires_at,reporter_key,network_key)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (report_id, stop_id, stop_name, route_id, category, feedback_code,
                 _dt(observed_at), created, expires, reporter_key, network_key),
            )
            return {"report_id": report_id, "created_at": created, "expires_at": expires}

    def recent_reports(self, stop_id: str, *, now: datetime | None = None) -> list[dict]:
        now = now or utc_now()
        with self._session() as con:
            con.execute("BEGIN IMMEDIATE")
            self._expire(con, now)
            rows = con.execute(
                """SELECT report_id,stop_id,stop_name,route_id,category,feedback_code,
                          observed_at,created_at,expires_at
                   FROM community_reports WHERE stop_id=? AND expires_at>? ORDER BY created_at DESC""",
                (stop_id, _dt(now)),
            ).fetchall()
        return [dict(row) for row in rows]

    def submit_presence(self, *, stop_id: str, participant_key: str, network_key: str, now: datetime | None = None) -> dict:
        now = now or utc_now()
        created = _dt(now)
        expires = _dt(now + timedelta(seconds=self.presence_ttl_seconds))
        with self._session() as con:
            con.execute("BEGIN IMMEDIATE")
            self._expire(con, now)
            self._rate_check(con, participant_key, network_key, now)
            existing = con.execute(
                "SELECT 1 FROM presence_signals WHERE stop_id=? AND participant_key=?",
                (stop_id, participant_key),
            ).fetchone()
            if existing:
                raise DuplicateSubmission
            signal_id = secrets.token_urlsafe(18)
            con.execute(
                "INSERT INTO presence_signals(signal_id,stop_id,created_at,expires_at,participant_key,network_key) VALUES(?,?,?,?,?,?)",
                (signal_id, stop_id, created, expires, participant_key, network_key),
            )
            return {"signal_id": signal_id, "created_at": created, "expires_at": expires}

    def presence_count(self, stop_id: str, *, now: datetime | None = None) -> int:
        now = now or utc_now()
        with self._session() as con:
            con.execute("BEGIN IMMEDIATE")
            self._expire(con, now)
            return int(con.execute(
                "SELECT count(DISTINCT participant_key) FROM presence_signals WHERE stop_id=? AND expires_at>?",
                (stop_id, _dt(now)),
            ).fetchone()[0])

    def purge_expired(self, *, now: datetime | None = None) -> int:
        now = now or utc_now()
        with self._session() as con:
            con.execute("BEGIN IMMEDIATE")
            before = con.total_changes
            self._expire(con, now)
            return con.total_changes - before


store = CommunityStore()
