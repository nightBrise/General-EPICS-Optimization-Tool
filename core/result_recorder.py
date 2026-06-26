"""通用优化结果记录器（SQLite，批量写入）"""
from __future__ import annotations
import os
import json
import zlib
import sqlite3


def pack(v):
    return zlib.compress(json.dumps(v).encode())


def unpack(b):
    return json.loads(zlib.decompress(b))


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    config_name   TEXT NOT NULL,
    config_json   TEXT,
    algorithm     TEXT NOT NULL,
    budget        INTEGER NOT NULL,
    initial_score REAL,
    best_score    REAL,
    best_params   BLOB,
    best_readings BLOB,
    best_iter     INTEGER,
    early_stop    INTEGER DEFAULT 0,
    stop_iter     INTEGER,
    elapsed_sec   REAL,
    timestamp     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS variables (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id   INTEGER NOT NULL REFERENCES runs(run_id),
    pv_name  TEXT NOT NULL,
    pv_min   REAL,
    pv_max   REAL
);

CREATE TABLE IF NOT EXISTS objectives (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     INTEGER NOT NULL REFERENCES runs(run_id),
    pv_name    TEXT NOT NULL,
    target     REAL DEFAULT 0.0,
    weight     REAL DEFAULT 1.0,
    group_name TEXT
);

CREATE TABLE IF NOT EXISTS group_mapping (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER NOT NULL REFERENCES runs(run_id),
    reading_index INTEGER NOT NULL,
    pv_name       TEXT NOT NULL,
    target        REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS iterations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER NOT NULL REFERENCES runs(run_id),
    iteration    INTEGER NOT NULL,
    score        REAL,
    group_scores BLOB,
    params       BLOB,
    readings     BLOB,
    elapsed_ms   REAL
);

CREATE TABLE IF NOT EXISTS failure_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES runs(run_id),
    iteration   INTEGER NOT NULL,
    pv_name     TEXT NOT NULL,
    target_val  REAL,
    error_msg   TEXT,
    timestamp   TEXT DEFAULT (datetime('now'))
);
"""


def _get_conn(db_path=None):
    if db_path is None:
        db_path = os.path.join('results', 'optimizations.db')
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=None):
    conn = _get_conn(db_path)
    try:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def _init_tables(conn):
    conn.executescript(_SCHEMA_SQL)
    conn.commit()


def _save_run(conn, history_dict, config):
    # type: (sqlite3.Connection, dict, dict) -> int
    config_name = config.get('name', 'optimization')
    config_json_str = json.dumps(config, ensure_ascii=False)
    algorithm = history_dict.get('algorithm', 'unknown')
    budget = history_dict.get('budget', 0)
    initial_score = history_dict.get('scores', [None])[0]
    best_score = history_dict.get('best_score')
    best_params = history_dict.get('best_params')
    best_readings = history_dict.get('best_readings')
    best_it = history_dict.get('best_iteration_index')
    early_stop = 1 if history_dict.get('early_stop') else 0
    stop_iter = history_dict.get('stop_iteration', budget)
    elapsed_sec = history_dict.get('elapsed_sec')

    cur = conn.cursor()
    cur.execute(
        """INSERT INTO runs
           (config_name, config_json, algorithm, budget,
            initial_score, best_score, best_params, best_readings, best_iter,
            early_stop, stop_iter, elapsed_sec)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (config_name, config_json_str, algorithm, budget,
         initial_score, best_score,
         pack(best_params) if best_params else None,
         pack(best_readings) if best_readings else None,
         best_it, early_stop, stop_iter, elapsed_sec)
    )
    run_id = cur.lastrowid

    config_vars = config.get('variables', [])
    device_pvs = history_dict.get('device_pvs', [])
    for i, pv in enumerate(device_pvs):
        vrange = config_vars[i].get('range', [None, None]) if i < len(config_vars) else [None, None]
        cur.execute(
            "INSERT INTO variables (run_id, pv_name, pv_min, pv_max) VALUES (?,?,?,?)",
            (run_id, pv, vrange[0], vrange[1])
        )

    groups = history_dict.get('_groups', [])
    for g in groups:
        pv_list = g.get('pvs', [])
        targets = g.get('targets', [])
        for pv_name, target in zip(pv_list, targets):
            cur.execute(
                "INSERT INTO objectives (run_id, pv_name, target) VALUES (?,?,?)",
                (run_id, pv_name, target)
            )

    group_indices = history_dict.get('_group_indices')
    if group_indices:
        for g_idx, g in enumerate(groups):
            for pv_idx, pv_name in enumerate(g.get('pvs', [])):
                reading_index = group_indices[g_idx][pv_idx]
                target = g.get('targets', [0])[pv_idx] if pv_idx < len(g.get('targets', [])) else 0
                cur.execute(
                    "INSERT INTO group_mapping (run_id, reading_index, pv_name, target) VALUES (?,?,?,?)",
                    (run_id, reading_index, pv_name, target)
                )

    conn.commit()
    return run_id


def _save_iterations_batch(conn, run_id, history_dict):
    # type: (sqlite3.Connection, int, dict) -> None
    iterations = history_dict.get('iterations', [])
    scores = history_dict.get('scores', [])
    grp_scores_list = history_dict.get('group_scores', [])
    params_list = history_dict.get('parameters', [])
    readings_list = history_dict.get('readings', [])
    elapsed_list = history_dict.get('elapsed_ms_list', [])

    rows = []
    for i in range(len(iterations)):
        rows.append((
            run_id,
            iterations[i],
            scores[i] if i < len(scores) else None,
            pack(grp_scores_list[i]) if i < len(grp_scores_list) and grp_scores_list[i] is not None else None,
            pack(params_list[i]) if i < len(params_list) and params_list[i] is not None else None,
            pack(readings_list[i]) if i < len(readings_list) and readings_list[i] is not None else None,
            elapsed_list[i] if i < len(elapsed_list) else None,
        ))

    if not rows:
        return
    cur = conn.cursor()
    cur.executemany(
        """INSERT INTO iterations
           (run_id, iteration, score, group_scores, params, readings, elapsed_ms)
           VALUES (?,?,?,?,?,?,?)""",
        rows
    )
    conn.commit()


def _save_failures_batch(conn, run_id, history_dict):
    # type: (sqlite3.Connection, int, dict) -> None
    entries = history_dict.get('failure_log', [])
    if not entries:
        return
    cur = conn.cursor()
    rows = [(run_id, e.get('iteration', 0), e.get('pv_name', ''),
             e.get('target_val'), e.get('error_msg', '')) for e in entries]
    cur.executemany(
        "INSERT INTO failure_log (run_id, iteration, pv_name, target_val, error_msg) VALUES (?,?,?,?,?)",
        rows
    )
    conn.commit()


def get_run(run_id, db_path=None):
    conn = _get_conn(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM runs WHERE run_id=?", (run_id,))
        row = cur.fetchone()
        if row is None:
            return None
        d = dict(row)
        if d.get('best_params'):
            d['best_params'] = unpack(d['best_params'])
        if d.get('best_readings'):
            d['best_readings'] = unpack(d['best_readings'])
        return d
    finally:
        conn.close()


def get_iterations(run_id, db_path=None):
    conn = _get_conn(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT iteration, score, group_scores, params, readings, elapsed_ms "
            "FROM iterations WHERE run_id=? ORDER BY iteration",
            (run_id,)
        )
        rows = []
        for row in cur.fetchall():
            d = dict(row)
            if d.get('group_scores'):
                d['group_scores'] = unpack(d['group_scores'])
            if d.get('params'):
                d['params'] = unpack(d['params'])
            if d.get('readings'):
                d['readings'] = unpack(d['readings'])
            rows.append(d)
        return rows
    finally:
        conn.close()


def save_results(history_dict, config, results_dir='results'):
    # type: (dict, dict, str) -> tuple
    db_path = os.path.join(results_dir, 'optimizations.db')
    conn = _get_conn(db_path)
    try:
        _init_tables(conn)
        run_id = _save_run(conn, history_dict, config)
        _save_iterations_batch(conn, run_id, history_dict)
        _save_failures_batch(conn, run_id, history_dict)
    finally:
        conn.close()

    print(u"\u2713 run #{} → {}".format(run_id, db_path))
    return db_path, run_id
