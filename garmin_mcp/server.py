"""
Garmin MCP server — exposes health and activity data via FastMCP tools.
"""

import json
import logging
import threading
import traceback
from datetime import date, timedelta

from mcp.server.fastmcp import FastMCP

from .db import get_connection, init_db, query, query_readonly

log = logging.getLogger(__name__)
mcp = FastMCP("garmin")

# Ensure all tables exist on startup
_conn = get_connection()
init_db(_conn)
_conn.close()


# ---------------------------------------------------------------------------
# garmin_schema
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_schema() -> str:
    """Show all tables, their columns, and row counts."""
    conn = get_connection()
    try:
        tables = query(
            conn,
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
        )
        result = {}
        for t in tables:
            table_name = t["name"]
            if not table_name.isidentifier():
                continue
            cols = query(conn, f"PRAGMA table_info([{table_name}])")
            row_count = query(conn, f"SELECT COUNT(*) AS cnt FROM [{table_name}]")[0]["cnt"]
            result[table_name] = {
                "columns": [c["name"] for c in cols],
                "row_count": row_count,
            }
        return json.dumps(result, indent=2)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_query
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_query(sql: str, limit: int = 1000) -> str:
    """Run a read-only SELECT query against the Garmin database.

    The database is opened in SQLite read-only mode at the engine level,
    so writes, ATTACH, and schema changes are impossible regardless of
    the SQL content.  Results are capped at *limit* rows (default 1000).
    """
    try:
        clamped = max(1, min(limit, 10000))
        rows = query_readonly(sql, limit=clamped)
        return json.dumps(rows, indent=2, default=str)
    except Exception as exc:
        log.exception("garmin_query failed")
        return json.dumps({"error": "Query failed. Check that your SQL is a valid SELECT statement."})


# ---------------------------------------------------------------------------
# garmin_health_summary
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_health_summary(start_date: str = "", end_date: str = "", days: int = 7) -> str:
    """Health overview for a date range.

    If start_date/end_date are omitted the most recent *days* days are used.
    Returns averages for steps, HR, stress, body battery, SpO2, respiration,
    calories (daily_summary), sleep metrics (sleep table), and training
    readiness score.
    """
    if not end_date:
        end_date = str(date.today())
    if not start_date:
        start_date = str(date.today() - timedelta(days=days - 1))

    conn = get_connection()
    try:
        daily_rows = query(
            conn,
            """
            SELECT
                ROUND(AVG(total_steps), 0)              AS avg_steps,
                ROUND(AVG(resting_heart_rate), 1)       AS avg_resting_hr,
                ROUND(AVG(average_stress_level), 1)     AS avg_stress,
                ROUND(AVG(body_battery_highest), 1)     AS avg_body_battery_high,
                ROUND(AVG(body_battery_lowest), 1)      AS avg_body_battery_low,
                ROUND(AVG(average_spo2), 1)             AS avg_spo2,
                ROUND(AVG(avg_waking_respiration), 1)   AS avg_respiration,
                ROUND(AVG(total_kilocalories), 0)       AS avg_calories,
                ROUND(AVG(active_kilocalories), 0)      AS avg_active_calories,
                ROUND(AVG(floors_ascended), 1)          AS avg_floors,
                ROUND(AVG(moderate_intensity_minutes + vigorous_intensity_minutes), 0) AS avg_intensity_minutes
            FROM daily_summary
            WHERE calendar_date BETWEEN ? AND ?
            """,
            [start_date, end_date],
        )

        sleep_rows = query(
            conn,
            """
            SELECT
                ROUND(AVG(sleep_time_seconds) / 3600.0, 2)         AS avg_sleep_hours,
                ROUND(AVG(deep_sleep_seconds) / 60.0, 0)           AS avg_deep_min,
                ROUND(AVG(light_sleep_seconds) / 60.0, 0)          AS avg_light_min,
                ROUND(AVG(rem_sleep_seconds) / 60.0, 0)            AS avg_rem_min,
                ROUND(AVG(awake_sleep_seconds) / 60.0, 0)          AS avg_awake_min,
                ROUND(AVG(average_hr_sleep), 1)                    AS avg_sleeping_hr
            FROM sleep
            WHERE calendar_date BETWEEN ? AND ?
            """,
            [start_date, end_date],
        )

        tr_rows = query(
            conn,
            """
            SELECT ROUND(AVG(score), 1) AS avg_training_readiness
            FROM training_readiness
            WHERE calendar_date BETWEEN ? AND ?
            """,
            [start_date, end_date],
        )

        endurance_rows = query(
            conn,
            """
            SELECT
                ROUND(AVG(overall_score), 1) AS avg_endurance_score,
                ROUND(AVG(vo2_max_precise), 1) AS avg_vo2_max
            FROM endurance_score
            WHERE calendar_date BETWEEN ? AND ?
              AND overall_score IS NOT NULL
            """,
            [start_date, end_date],
        )

        hill_rows = query(
            conn,
            """
            SELECT
                ROUND(AVG(overall_score), 1) AS avg_hill_score,
                ROUND(AVG(endurance_score), 1) AS avg_hill_endurance,
                ROUND(AVG(strength_score), 1) AS avg_hill_strength
            FROM hill_score
            WHERE calendar_date BETWEEN ? AND ?
              AND overall_score IS NOT NULL
            """,
            [start_date, end_date],
        )

        race_rows = query(
            conn,
            """
            SELECT
                ROUND(AVG(time_5k), 0) AS avg_time_5k_sec,
                ROUND(AVG(time_10k), 0) AS avg_time_10k_sec,
                ROUND(AVG(time_half_marathon), 0) AS avg_time_half_sec,
                ROUND(AVG(time_marathon), 0) AS avg_time_marathon_sec
            FROM race_predictions
            WHERE calendar_date BETWEEN ? AND ?
              AND time_5k IS NOT NULL
            """,
            [start_date, end_date],
        )

        result = {
            "period": {"start_date": start_date, "end_date": end_date},
            "daily": daily_rows[0] if daily_rows else {},
            "sleep": sleep_rows[0] if sleep_rows else {},
            "training_readiness": tr_rows[0] if tr_rows else {},
            "endurance": endurance_rows[0] if endurance_rows else {},
            "hill_score": hill_rows[0] if hill_rows else {},
            "race_predictions": race_rows[0] if race_rows else {},
        }
        return json.dumps(result, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_activities
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_activities(
    activity_type: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = 20,
) -> str:
    """List activities with optional filters by type and date range.

    Returns key fields: name, type, date, duration_min, distance_km,
    calories, avg_hr, elevation, power, training_load, location.
    """
    conditions = []
    params: list = []

    if activity_type:
        conditions.append("type = ?")
        params.append(activity_type)
    if start_date:
        conditions.append("DATE(start_time_local) >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("DATE(start_time_local) <= ?")
        params.append(end_date)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    conn = get_connection()
    try:
        rows = query(conn, sql, params)
        return json.dumps(rows, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_sync
# ---------------------------------------------------------------------------


_sync_lock = threading.Lock()


def _run_incremental_sync() -> dict:
    """Run the browser-based sync in a thread. Internal helper."""
    import concurrent.futures

    def _go():
        from .sync import incremental_sync

        return incremental_sync()

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(_go)
    try:
        return future.result(timeout=300)
    except concurrent.futures.TimeoutError:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    finally:
        pool.shutdown(wait=False)


def _get_data_freshness() -> dict:
    """Return data freshness info from the database."""
    from datetime import datetime, timezone

    today = str(date.today())
    conn = get_connection()
    try:
        freshness = query(
            conn,
            """SELECT 'daily_summary' AS source, MAX(calendar_date) AS latest FROM daily_summary
               UNION ALL SELECT 'sleep', MAX(calendar_date) FROM sleep
               UNION ALL SELECT 'hrv', MAX(calendar_date) FROM hrv
               UNION ALL SELECT 'activity', MAX(DATE(start_time_local)) FROM activity
                          WHERE start_time_local IS NOT NULL
               ORDER BY latest DESC""",
        )

        last_sync = query(
            conn,
            """SELECT sync_date, sync_type, records_upserted, status
               FROM sync_log ORDER BY created_at DESC LIMIT 1""",
        )

        latest_date = freshness[0]["latest"] if freshness and freshness[0]["latest"] else None

        # Calculate how long ago the last sync was
        last_sync_ago = None
        if last_sync and last_sync[0].get("sync_date"):
            try:
                sync_dt = datetime.fromisoformat(last_sync[0]["sync_date"])
                now = datetime.now(timezone.utc)
                if sync_dt.tzinfo is None:
                    sync_dt = sync_dt.replace(tzinfo=timezone.utc)
                delta = now - sync_dt
                hours = delta.total_seconds() / 3600
                if hours < 1:
                    last_sync_ago = f"{int(delta.total_seconds() / 60)} minutes ago"
                elif hours < 24:
                    last_sync_ago = f"{hours:.1f} hours ago"
                else:
                    last_sync_ago = f"{delta.days} days ago"
            except (ValueError, TypeError):
                pass

        return {
            "today": today,
            "latest_data_date": latest_date,
            "is_stale": latest_date is None or latest_date < today,
            "freshness_by_table": {r["source"]: r["latest"] for r in freshness},
            "last_sync": last_sync[0] if last_sync else None,
            "last_sync_ago": last_sync_ago,
        }
    finally:
        conn.close()


def _do_sync() -> dict:
    """Acquire the lock and sync. Returns sync result or error dict."""
    if not _sync_lock.acquire(blocking=False):
        return {"status": "error", "error": "A sync is already in progress. Try again later."}
    try:
        return {"status": "success", "result": _run_incremental_sync()}
    except Exception as exc:
        tb = traceback.format_exc()
        log.exception("sync failed: %s: %s", exc.__class__.__name__, exc)
        return {
            "status": "error",
            "error": "Sync failed. Check server logs.",
            "exception_type": exc.__class__.__name__,
            "exception_message": str(exc),
            "exception_repr": repr(exc),
            "traceback": tb,
        }
    finally:
        _sync_lock.release()


@mcp.tool()
def garmin_sync(refresh: bool = True) -> str:
    """Sync the latest data from Garmin Connect.

    Always shows when the last sync happened before doing anything.
    Set refresh=False to just check the status without syncing.

    Use this when:
    - You just finished a run/ride and want to see the new data
    - You want to make sure today's health data is loaded
    - The data looks outdated
    """
    status = _get_data_freshness()

    if not refresh:
        if status["is_stale"]:
            status["hint"] = "Data is not current. Call garmin_sync() to refresh."
        return json.dumps(status, indent=2, default=str)

    sync_result = _do_sync()
    status["sync"] = sync_result

    # Refresh freshness info after sync
    if sync_result.get("status") == "success":
        status.update(_get_data_freshness())
        status["sync"] = sync_result

    return json.dumps(status, indent=2, default=str)


# ---------------------------------------------------------------------------
# garmin_today
# ---------------------------------------------------------------------------

