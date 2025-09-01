import os
import json
import sqlite3
from contextlib import contextmanager
from typing import Dict, Any, Optional, List, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'kri.db')
JSON_SEED = os.path.join(BASE_DIR, 'kri-data.json')

APP_BASED_KRIS = {'kri8', 'kri10', 'kri12', 'kri13', 'kri19'}
VALUE_FIELD_MAP: Dict[str, str] = {
    'kri2': 'percentage',
    'kri3': 'percentage',
    'kri4': 'count',
    'kri5': 'percentage',
    'kri6': 'percentage',
    'kri8': 'value',
    'kri9': 'count',
    'kri10': 'incidents',
    'kri12': 'incidents',
    'kri13': 'value',
    'kri15': 'percentage',
    'kri18': 'percentage',
    'kri19': 'value',
    'kri20': 'count',
    'kri21': 'count',
    'kri22': 'percentage',
    'kri27': 'percentage',
    'kri28': 'percentage',
}


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


def _recreate_table_without_date(conn: sqlite3.Connection, table: str, create_sql: str, copy_sql: str) -> None:
    conn.execute(f'ALTER TABLE {table} RENAME TO {table}_old')
    conn.execute(create_sql)
    conn.execute(copy_sql)
    conn.execute(f'DROP TABLE {table}_old')


def init_db(drop: bool = False) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        if drop:
            cur.execute('DROP TABLE IF EXISTS kri_points')
            cur.execute('DROP TABLE IF EXISTS kri_app_points')
            cur.execute('DROP TABLE IF EXISTS kri_app_systems')

        # Create with new schema (no date columns)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS kri_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kri_id TEXT NOT NULL,
                period TEXT NOT NULL,
                value REAL NOT NULL,
                UNIQUE(kri_id, period)
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS kri_app_systems (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kri_id TEXT NOT NULL,
                system_name TEXT NOT NULL,
                UNIQUE(kri_id, system_name)
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS kri_app_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kri_id TEXT NOT NULL,
                system_name TEXT NOT NULL,
                period TEXT NOT NULL,
                value REAL NOT NULL,
                UNIQUE(kri_id, system_name, period)
            )
        ''')

        # Migrate old schema (with date) to new by dropping date column
        cols_points = _table_columns(conn, 'kri_points')
        if 'date' in cols_points:
            _recreate_table_without_date(
                conn,
                'kri_points',
                '''CREATE TABLE kri_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kri_id TEXT NOT NULL,
                    period TEXT NOT NULL,
                    value REAL NOT NULL,
                    UNIQUE(kri_id, period)
                )''',
                'INSERT INTO kri_points (id, kri_id, period, value) SELECT id, kri_id, period, value FROM kri_points_old'
            )
        cols_app_points = _table_columns(conn, 'kri_app_points')
        if 'date' in cols_app_points:
            _recreate_table_without_date(
                conn,
                'kri_app_points',
                '''CREATE TABLE kri_app_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kri_id TEXT NOT NULL,
                    system_name TEXT NOT NULL,
                    period TEXT NOT NULL,
                    value REAL NOT NULL,
                    UNIQUE(kri_id, system_name, period)
                )''',
                'INSERT INTO kri_app_points (id, kri_id, system_name, period, value) SELECT id, kri_id, system_name, period, value FROM kri_app_points_old'
            )


def _insert_point(conn: sqlite3.Connection, kri_id: str, period: str, value: float) -> None:
    conn.execute(
        'INSERT INTO kri_points (kri_id, period, value) VALUES (?, ?, ?)\n\t\tON CONFLICT(kri_id, period) DO UPDATE SET value=excluded.value',
        (kri_id, period, value),
    )


def _insert_app_point(conn: sqlite3.Connection, kri_id: str, system_name: str, period: str, value: float) -> None:
    conn.execute('INSERT OR IGNORE INTO kri_app_systems (kri_id, system_name) VALUES (?, ?)', (kri_id, system_name))
    conn.execute(
        'INSERT INTO kri_app_points (kri_id, system_name, period, value) VALUES (?, ?, ?, ?)\n\t\tON CONFLICT(kri_id, system_name, period) DO UPDATE SET value=excluded.value',
        (kri_id, system_name, period, value),
    )


def seed_from_json(file_path: Optional[str] = None, clear_existing: bool = True) -> None:
    path = file_path or JSON_SEED
    if not os.path.exists(path):
        return
    with open(path, 'r', encoding='utf-8') as f:
        payload = json.load(f)
    with get_conn() as conn:
        if clear_existing:
            conn.execute('DELETE FROM kri_points')
            conn.execute('DELETE FROM kri_app_points')
            conn.execute('DELETE FROM kri_app_systems')
        for kri_id, content in payload.items():
            if kri_id in APP_BASED_KRIS:
                apps = content.get('applications', {})
                for system_name, items in apps.items():
                    for item in items:
                        _insert_app_point(conn, kri_id, system_name, item['period'], float(item.get('incidents') or item.get('value') or 0.0))
            else:
                for item in content.get('data', []):
                    _insert_point(conn, kri_id, item['period'], float(item.get('percentage') or item.get('count') or 0.0))


def add_system(kri_id: str, system_name: str) -> None:
    with get_conn() as conn:
        conn.execute('INSERT OR IGNORE INTO kri_app_systems (kri_id, system_name) VALUES (?, ?)', (kri_id, system_name))


def upsert_data_point(kri_id: str, period: str, value: float, system_name: Optional[str] = None) -> None:
    with get_conn() as conn:
        if kri_id in APP_BASED_KRIS:
            if not system_name:
                raise ValueError('systemName is required for applications-based KRI')
            _insert_app_point(conn, kri_id, system_name, period, value)
        else:
            _insert_point(conn, kri_id, period, value)


def update_data_point(
    kri_id: str,
    period: str,
    value: Optional[float] = None,
    system_name: Optional[str] = None,
) -> int:
    """Update an existing data point's value. Returns number of rows changed."""
    with get_conn() as conn:
        if kri_id in APP_BASED_KRIS:
            if not system_name:
                raise ValueError('systemName is required for applications-based KRI')
            row = conn.execute('SELECT id FROM kri_app_points WHERE kri_id=? AND system_name=? AND period=?', (kri_id, system_name, period)).fetchone()
            if not row:
                return 0
            if value is None:
                return 0
            conn.execute('UPDATE kri_app_points SET value=? WHERE id=?', (value, row['id']))
            return 1
        else:
            row = conn.execute('SELECT id FROM kri_points WHERE kri_id=? AND period=?', (kri_id, period)).fetchone()
            if not row:
                return 0
            if value is None:
                return 0
            conn.execute('UPDATE kri_points SET value=? WHERE id=?', (value, row['id']))
            return 1


def delete_data_point(kri_id: str, period: str, system_name: Optional[str] = None) -> int:
    with get_conn() as conn:
        if kri_id in APP_BASED_KRIS:
            if not system_name:
                raise ValueError('systemName is required for applications-based KRI')
            res = conn.execute('DELETE FROM kri_app_points WHERE kri_id=? AND system_name=? AND period=?', (kri_id, system_name, period))
            return res.rowcount
        else:
            res = conn.execute('DELETE FROM kri_points WHERE kri_id=? AND period=?', (kri_id, period))
            return res.rowcount


def delete_system(kri_id: str, system_name: str) -> Tuple[int, int]:
    with get_conn() as conn:
        pts = conn.execute('DELETE FROM kri_app_points WHERE kri_id=? AND system_name=?', (kri_id, system_name)).rowcount
        sys = conn.execute('DELETE FROM kri_app_systems WHERE kri_id=? AND system_name=?', (kri_id, system_name)).rowcount
        return pts, sys


def _order_clause_for_kri(kri_id: str) -> str:
    # Monthly periods use MM-YYYY (only kri10). Others use Qx-YYYY
    if kri_id == 'kri10':
        return 'CAST(SUBSTR(period, 4, 4) AS INTEGER), CAST(SUBSTR(period, 1, 2) AS INTEGER)'
    else:
        return 'CAST(SUBSTR(period, 4, 4) AS INTEGER), CAST(SUBSTR(period, 2, 1) AS INTEGER)'


def _collect_kri(conn: sqlite3.Connection, kri_id: str) -> Dict[str, Any]:
    field = VALUE_FIELD_MAP[kri_id]
    order_clause = _order_clause_for_kri(kri_id)
    if kri_id in APP_BASED_KRIS:
        apps: Dict[str, List[Dict[str, Any]]] = {}
        rows = conn.execute(f'SELECT system_name, period, value FROM kri_app_points WHERE kri_id=? ORDER BY system_name, {order_clause}', (kri_id,)).fetchall()
        for r in rows:
            apps.setdefault(r['system_name'], []).append({'period': r['period'], field: r['value']})
        # Ensure empty systems appear
        sys_rows = conn.execute('SELECT system_name FROM kri_app_systems WHERE kri_id=? ORDER BY system_name', (kri_id,)).fetchall()
        for s in sys_rows:
            apps.setdefault(s['system_name'], apps.get(s['system_name'], []))
        return {'applications': apps}
    else:
        rows = conn.execute(f'SELECT period, value FROM kri_points WHERE kri_id=? ORDER BY {order_clause}', (kri_id,)).fetchall()
        return {'data': [{'period': r['period'], field: r['value']} for r in rows]}


def fetch_all_data() -> Dict[str, Any]:
    with get_conn() as conn:
        result: Dict[str, Any] = {}
        # Collect all KRIs that exist in tables
        kri_ids = set()
        for (kri_id,) in conn.execute('SELECT DISTINCT kri_id FROM kri_points'):
            kri_ids.add(kri_id)
        for (kri_id,) in conn.execute('SELECT DISTINCT kri_id FROM kri_app_points'):
            kri_ids.add(kri_id)
        for (kri_id,) in conn.execute('SELECT DISTINCT kri_id FROM kri_app_systems'):
            kri_ids.add(kri_id)
        # Also include KRIs from VALUE_FIELD_MAP with no data yet
        kri_ids.update(VALUE_FIELD_MAP.keys())
        for kri_id in sorted(kri_ids):
            result[kri_id] = _collect_kri(conn, kri_id)
        return result


def get_kri(kri_id: str) -> Dict[str, Any]:
    with get_conn() as conn:
        return _collect_kri(conn, kri_id)


def list_systems(kri_id: str) -> List[str]:
    with get_conn() as conn:
        rows = conn.execute('SELECT system_name FROM kri_app_systems WHERE kri_id=? ORDER BY system_name', (kri_id,)).fetchall()
        return [r['system_name'] for r in rows]