import os
import json
import sqlite3
from contextlib import contextmanager
from typing import Dict, Any, Optional, List

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'rhi.db')
JSON_SEED = os.path.join(BASE_DIR, 'rhi-data.json')

RHI_VALUE_FIELD_MAP: Dict[str, str] = {
    'rhi96': 'value',
    'rhi97': 'value',
    'rhi98': 'value',
    'rhi100': 'value',  # ratio (numerator/denominator -> value%)
    'rhi101': 'value',  # ratio quarterly
    'rhi102': 'value',
    'rhi103': 'value',
    'rhi104': 'value',
    'rhi105': 'value',  # ratio yearly
    'rhi106': 'value',
    'rhi107': 'value',  # special: stores hours/minutes/seconds; value=hours (float)
    'rhi108': 'value',  # ratio yearly
    'rhi109': 'value',  # ratio monthly
    'rhi110': 'value',  # ratio quarterly
    'rhi111': 'value',
    'rhi112': 'value',
    'rhi113': 'value',
    'rhi121': 'value',  # ratio quarterly
    'rhi122': 'value',  # ratio monthly
    'rhi123': 'value',  # ratio monthly
    'rhi158': 'value',  # ratio quarterly
}

QUARTERLY_RHIS = {'rhi100', 'rhi101', 'rhi110', 'rhi121', 'rhi158'}
YEARLY_RHIS = {'rhi105', 'rhi108'}
RATIO_RHIS = {'rhi100', 'rhi101', 'rhi105', 'rhi108', 'rhi109', 'rhi110', 'rhi121', 'rhi122', 'rhi123', 'rhi158'}


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return [r['name'] for r in rows]
    except Exception:
        return []


def init_db(drop: bool = False) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        if drop:
            cur.execute('DROP TABLE IF EXISTS rhi_points')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS rhi_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rhi_id TEXT NOT NULL,
                period TEXT NOT NULL,
                value REAL NOT NULL,
                days INTEGER,
                hours INTEGER,
                minutes INTEGER,
                seconds INTEGER,
                numerator INTEGER,
                denominator INTEGER,
                UNIQUE(rhi_id, period)
            )
        ''')

        cols = _table_columns(conn, 'rhi_points')
        if 'days' not in cols:
            cur.execute('ALTER TABLE rhi_points ADD COLUMN days INTEGER')
        if 'hours' not in cols:
            cur.execute('ALTER TABLE rhi_points ADD COLUMN hours INTEGER')
        if 'minutes' not in cols:
            cur.execute('ALTER TABLE rhi_points ADD COLUMN minutes INTEGER')
        if 'seconds' not in cols:
            cur.execute('ALTER TABLE rhi_points ADD COLUMN seconds INTEGER')
        if 'numerator' not in cols:
            cur.execute('ALTER TABLE rhi_points ADD COLUMN numerator INTEGER')
        if 'denominator' not in cols:
            cur.execute('ALTER TABLE rhi_points ADD COLUMN denominator INTEGER')


def _insert_point(conn: sqlite3.Connection, rhi_id: str, period: str, value: float) -> None:
    conn.execute(
        'INSERT INTO rhi_points (rhi_id, period, value) VALUES (?, ?, ?)\n\t\tON CONFLICT(rhi_id, period) DO UPDATE SET value=excluded.value',
        (rhi_id, period, value),
    )


def _insert_duration_point(conn: sqlite3.Connection, rhi_id: str, period: str, hours: int, minutes: int, seconds: int) -> None:
    total_seconds = int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    hours_float = float(total_seconds) / 3600.0
    conn.execute(
        'INSERT INTO rhi_points (rhi_id, period, value, hours, minutes, seconds) VALUES (?, ?, ?, ?, ?, ?)\n\t\tON CONFLICT(rhi_id, period) DO UPDATE SET value=excluded.value, hours=excluded.hours, minutes=excluded.minutes, seconds=excluded.seconds',
        (rhi_id, period, hours_float, int(hours), int(minutes), int(seconds)),
    )


def _insert_ratio_point(conn: sqlite3.Connection, rhi_id: str, period: str, numerator: int, denominator: int) -> None:
    percentage = 0.0 if denominator == 0 else (float(numerator) / float(denominator)) * 100.0
    conn.execute(
        'INSERT INTO rhi_points (rhi_id, period, value, numerator, denominator) VALUES (?, ?, ?, ?, ?)\n\t\tON CONFLICT(rhi_id, period) DO UPDATE SET value=excluded.value, numerator=excluded.numerator, denominator=excluded.denominator',
        (rhi_id, period, float(percentage), int(numerator), int(denominator)),
    )


def seed_from_json(file_path: Optional[str] = None, clear_existing: bool = True) -> None:
    path = file_path or JSON_SEED
    if not os.path.exists(path):
        return
    with open(path, 'r', encoding='utf-8') as f:
        payload = json.load(f)
    with get_conn() as conn:
        if clear_existing:
            conn.execute('DELETE FROM rhi_points')
        for rhi_id, content in payload.items():
            for item in content.get('data', []):
                if rhi_id == 'rhi107':
                    # Support both legacy (days/hours/minutes) and new (hours/minutes/seconds) seed formats
                    if all(k in item for k in ('hours', 'minutes', 'seconds')):
                        _insert_duration_point(conn, rhi_id, item['period'],
                                               int(item.get('hours', 0)), int(item.get('minutes', 0)), int(item.get('seconds', 0)))
                    elif all(k in item for k in ('days', 'hours', 'minutes')):
                        total_seconds = int(item.get('days', 0)) * 86400 + int(item.get('hours', 0)) * 3600 + int(item.get('minutes', 0)) * 60
                        h = total_seconds // 3600
                        m = (total_seconds % 3600) // 60
                        s = total_seconds % 60
                        _insert_duration_point(conn, rhi_id, item['period'], h, m, s)
                    else:
                        _insert_duration_point(conn, rhi_id, item['period'], 0, 0, 0)
                elif all(k in item for k in ('numerator', 'denominator')):
                    _insert_ratio_point(conn, rhi_id, item['period'], int(item.get('numerator', 0)), int(item.get('denominator', 0)))
                else:
                    _insert_point(conn, rhi_id, item['period'], float(item.get('value') or 0.0))


def upsert_data_point(rhi_id: str, period: str, value: float) -> None:
    with get_conn() as conn:
        _insert_point(conn, rhi_id, period, value)


def upsert_duration_point(rhi_id: str, period: str, hours: int, minutes: int, seconds: int) -> None:
    with get_conn() as conn:
        _insert_duration_point(conn, rhi_id, period, hours, minutes, seconds)


def upsert_ratio_point(rhi_id: str, period: str, numerator: int, denominator: int) -> None:
    with get_conn() as conn:
        _insert_ratio_point(conn, rhi_id, period, numerator, denominator)


def update_data_point(rhi_id: str, period: str, value: Optional[float] = None) -> int:
    with get_conn() as conn:
        row = conn.execute('SELECT id FROM rhi_points WHERE rhi_id=? AND period=?', (rhi_id, period)).fetchone()
        if not row or value is None:
            return 0
        conn.execute('UPDATE rhi_points SET value=? WHERE id=?', (value, row['id']))
        return 1


def update_duration_point(rhi_id: str, period: str, hours: Optional[int] = None, minutes: Optional[int] = None, seconds: Optional[int] = None) -> int:
    with get_conn() as conn:
        row = conn.execute('SELECT id, hours, minutes, seconds FROM rhi_points WHERE rhi_id=? AND period=?', (rhi_id, period)).fetchone()
        if not row:
            return 0
        cur_hours = int(row['hours'] or 0)
        cur_minutes = int(row['minutes'] or 0)
        cur_seconds = int(row['seconds'] or 0)
        new_hours = cur_hours if hours is None else int(hours)
        new_minutes = cur_minutes if minutes is None else int(minutes)
        new_seconds = cur_seconds if seconds is None else int(seconds)
        total_seconds = new_hours * 3600 + new_minutes * 60 + new_seconds
        hours_float = float(total_seconds) / 3600.0
        conn.execute('UPDATE rhi_points SET hours=?, minutes=?, seconds=?, value=? WHERE id=?',
                     (new_hours, new_minutes, new_seconds, hours_float, row['id']))
        return 1


def update_ratio_point(rhi_id: str, period: str, numerator: Optional[int] = None, denominator: Optional[int] = None) -> int:
    with get_conn() as conn:
        row = conn.execute('SELECT id, numerator, denominator FROM rhi_points WHERE rhi_id=? AND period=?', (rhi_id, period)).fetchone()
        if not row:
            return 0
        cur_num = int(row['numerator'] or 0)
        cur_den = int(row['denominator'] or 0)
        new_num = cur_num if numerator is None else int(numerator)
        new_den = cur_den if denominator is None else int(denominator)
        if new_den <= 0:
            new_den = 1
        percentage = (float(new_num) / float(new_den)) * 100.0
        conn.execute('UPDATE rhi_points SET numerator=?, denominator=?, value=? WHERE id=?', (new_num, new_den, float(percentage), row['id']))
        return 1


def delete_data_point(rhi_id: str, period: str) -> int:
    with get_conn() as conn:
        res = conn.execute('DELETE FROM rhi_points WHERE rhi_id=? AND period=?', (rhi_id, period))
        return res.rowcount


def _order_clause(rhi_id: str) -> str:
    # Monthly: MM-YYYY; Quarterly: Qx-YYYY; Yearly: YYYY
    if rhi_id in QUARTERLY_RHIS:
        return 'CAST(SUBSTR(period, 4, 4) AS INTEGER), CAST(SUBSTR(period, 2, 1) AS INTEGER)'
    if rhi_id in YEARLY_RHIS:
        return 'CAST(period AS INTEGER)'
    return 'CAST(SUBSTR(period, 4, 4) AS INTEGER), CAST(SUBSTR(period, 1, 2) AS INTEGER)'


def _collect_rhi(conn: sqlite3.Connection, rhi_id: str) -> Dict[str, Any]:
    rows = conn.execute(f'SELECT period, value, hours, minutes, seconds, numerator, denominator FROM rhi_points WHERE rhi_id=? ORDER BY {_order_clause(rhi_id)}', (rhi_id,)).fetchall()
    if rhi_id == 'rhi107':
        return {'data': [{'period': r['period'], 'hours': r['hours'] or 0, 'minutes': r['minutes'] or 0, 'seconds': r['seconds'] or 0, 'value': r['value'] or 0.0} for r in rows]}
    if rhi_id in RATIO_RHIS:
        return {'data': [{'period': r['period'], 'numerator': r['numerator'] or 0, 'denominator': r['denominator'] or 0, 'value': r['value'] or 0.0} for r in rows]}
    return {'data': [{'period': r['period'], 'value': r['value']} for r in rows]}


def fetch_all_data() -> Dict[str, Any]:
    with get_conn() as conn:
        result: Dict[str, Any] = {}
        rhi_ids = set(RHI_VALUE_FIELD_MAP.keys())
        for (rid,) in conn.execute('SELECT DISTINCT rhi_id FROM rhi_points'):
            rhi_ids.add(rid)
        for rhi_id in sorted(rhi_ids):
            result[rhi_id] = _collect_rhi(conn, rhi_id)
        return result


def get_rhi(rhi_id: str) -> Dict[str, Any]:
    with get_conn() as conn:
        return _collect_rhi(conn, rhi_id)