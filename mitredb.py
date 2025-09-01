import os
import json
import sqlite3
from contextlib import contextmanager
from typing import Optional, Dict, Any

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'mitre.db')


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


def init_db(drop: bool = False) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        if drop:
            cur.execute('DROP TABLE IF EXISTS mitre_dataset')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS mitre_dataset (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                uploaded_at TEXT,
                chart_data TEXT NOT NULL,
                all_parameters_data TEXT NOT NULL
            )
        ''')


def save_dataset(filename: str, chart_data: Any, all_parameters_data: Any) -> None:
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO mitre_dataset (filename, uploaded_at, chart_data, all_parameters_data) VALUES (?, datetime("now"), ?, ?)',
            (filename, json.dumps(chart_data), json.dumps(all_parameters_data))
        )


def get_latest_dataset() -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute('SELECT filename, uploaded_at, chart_data, all_parameters_data FROM mitre_dataset ORDER BY id DESC LIMIT 1').fetchone()
        if not row:
            return None
        return {
            'filename': row['filename'],
            'uploadedAt': row['uploaded_at'],
            'chartData': json.loads(row['chart_data'] or '[]'),
            'allParametersData': json.loads(row['all_parameters_data'] or '[]'),
        }