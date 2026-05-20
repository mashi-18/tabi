"""Tabi - 旅のしおりアプリのデータベース操作モジュール。

Streamlit に依存せず、標準ライブラリの sqlite3 だけで動きます。

テーブル構成:
    trips           … 旅行の基本情報（一覧・詳細の親）
    schedule_items  … 旅程（Dayごとのタイムライン）
    details         … 詳細情報（移動・宿泊・食事・その他のカテゴリ別）
    photos          … アルバム（1つの旅行に複数枚）
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "travel.db"

# 旅行のステータス
STATUS_CHOICES = ["行きたい", "計画中", "行った"]
# 詳細情報のカテゴリ
DETAIL_CATEGORIES = ["移動", "宿泊", "食事", "その他"]


def get_connection():
    """DB接続を返す。結果を辞書のように扱えるようにする。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_columns(conn, table, columns):
    """既存テーブルに不足カラムを ALTER で安全に追加する（データは保持）。"""
    existing = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
    for col, ddl in columns.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def init_db():
    """テーブルが無ければ作成する。古い形式の trips があれば退避する。"""
    with get_connection() as conn:
        # 旧バージョン（tag列を持つ）の trips があれば退避してから作り直す
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(trips)")]
        if cols and ("tag" in cols or "map_link" in cols):
            conn.execute("DROP TABLE IF EXISTS trips_legacy")
            conn.execute("ALTER TABLE trips RENAME TO trips_legacy")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                destination TEXT NOT NULL,
                start_date TEXT,
                end_date TEXT,
                budget INTEGER,
                status TEXT,
                memo TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schedule_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id INTEGER NOT NULL,
                day INTEGER NOT NULL DEFAULT 1,
                time TEXT,
                activity TEXT NOT NULL,
                FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS details (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                info TEXT,
                cost INTEGER,
                url TEXT,
                subtype TEXT,
                place_from TEXT,
                place_to TEXT,
                time_from TEXT,
                time_to TEXT,
                FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                caption TEXT,
                FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE
            )
            """
        )

        # 既存DBへの後付け：details に新カラムを安全に追加
        _ensure_columns(conn, "details", {
            "subtype": "TEXT", "place_from": "TEXT", "place_to": "TEXT",
            "time_from": "TEXT", "time_to": "TEXT",
        })


# ----- trips（旅行の基本情報） -----

def add_trip(title, destination, start_date="", end_date="",
             budget=0, status="行きたい", memo=""):
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO trips
                (title, destination, start_date, end_date, budget, status, memo)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (title, destination, start_date, end_date,
             int(budget or 0), status, memo),
        )
        return cur.lastrowid


def get_trips(q=None, status=None):
    """旅行一覧を新しい順で返す。q で全文っぽい検索、status で絞り込み。

    各行に cover（先頭写真のファイル名）を含める。
    """
    where = []
    params = []
    joins = ""

    if q:
        like = f"%{q}%"
        joins = (
            " LEFT JOIN schedule_items s ON s.trip_id = t.id"
            " LEFT JOIN details d ON d.trip_id = t.id"
        )
        where.append(
            "(t.title LIKE ? OR t.destination LIKE ? OR t.memo LIKE ?"
            " OR s.activity LIKE ? OR d.name LIKE ? OR d.info LIKE ?)"
        )
        params += [like, like, like, like, like, like]

    if status:
        where.append("t.status = ?")
        params.append(status)

    sql = (
        "SELECT t.*, "
        "(SELECT filename FROM photos p WHERE p.trip_id = t.id ORDER BY p.id LIMIT 1) AS cover "
        "FROM trips t" + joins
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " GROUP BY t.id ORDER BY t.id DESC"

    with get_connection() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_trip(trip_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM trips WHERE id = ?", (trip_id,)
        ).fetchone()
        return dict(row) if row else None


def update_trip(trip_id, **fields):
    allowed = {"title", "destination", "start_date", "end_date",
               "budget", "status", "memo"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    if "budget" in updates:
        updates["budget"] = int(updates["budget"] or 0)
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [trip_id]
    with get_connection() as conn:
        cur = conn.execute(
            f"UPDATE trips SET {set_clause} WHERE id = ?", values
        )
        return cur.rowcount > 0


def delete_trip(trip_id):
    """旅行と関連データを削除。消すべき写真ファイル名のリストを返す。"""
    with get_connection() as conn:
        files = [r["filename"] for r in conn.execute(
            "SELECT filename FROM photos WHERE trip_id = ?", (trip_id,)
        )]
        conn.execute("DELETE FROM trips WHERE id = ?", (trip_id,))
        return files


# ----- schedule_items（旅程） -----

def add_schedule(trip_id, day, time, activity):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO schedule_items (trip_id, day, time, activity)"
            " VALUES (?, ?, ?, ?)",
            (trip_id, int(day or 1), time, activity),
        )


def get_schedule(trip_id):
    """旅程を {day: [items...]} の辞書（dayの昇順）で返す。"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM schedule_items WHERE trip_id = ?"
            " ORDER BY day, time, id",
            (trip_id,),
        ).fetchall()
    grouped = {}
    for r in rows:
        grouped.setdefault(r["day"], []).append(dict(r))
    return dict(sorted(grouped.items()))


def delete_schedule(item_id):
    """旅程アイテムを削除し、親の trip_id を返す。"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT trip_id FROM schedule_items WHERE id = ?", (item_id,)
        ).fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM schedule_items WHERE id = ?", (item_id,))
        return row["trip_id"]


def get_schedule_item(item_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM schedule_items WHERE id = ?", (item_id,)
        ).fetchone()
        return dict(row) if row else None


def update_schedule(item_id, **fields):
    allowed = {"day", "time", "activity"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    if "day" in updates:
        updates["day"] = int(updates["day"] or 1)
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [item_id]
    with get_connection() as conn:
        cur = conn.execute(
            f"UPDATE schedule_items SET {set_clause} WHERE id = ?", values
        )
        return cur.rowcount > 0


# ----- details（詳細情報） -----

def add_detail(trip_id, category, name, info="", cost=0, url="",
               subtype="", place_from="", place_to="", time_from="", time_to=""):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO details (trip_id, category, name, info, cost, url,"
            " subtype, place_from, place_to, time_from, time_to)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (trip_id, category, name, info, int(cost or 0), url,
             subtype, place_from, place_to, time_from, time_to),
        )


def get_details(trip_id):
    """詳細情報を {category: [items...]} の辞書で返す（カテゴリ順）。"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM details WHERE trip_id = ? ORDER BY id", (trip_id,)
        ).fetchall()
    grouped = {}
    for r in rows:
        grouped.setdefault(r["category"], []).append(dict(r))
    # DETAIL_CATEGORIES の順に並べる
    return {c: grouped[c] for c in DETAIL_CATEGORIES if c in grouped}


def delete_detail(item_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT trip_id FROM details WHERE id = ?", (item_id,)
        ).fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM details WHERE id = ?", (item_id,))
        return row["trip_id"]


def get_detail(item_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM details WHERE id = ?", (item_id,)
        ).fetchone()
        return dict(row) if row else None


def update_detail(item_id, **fields):
    allowed = {"category", "name", "info", "cost", "url",
               "subtype", "place_from", "place_to", "time_from", "time_to"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    if "cost" in updates:
        updates["cost"] = int(updates["cost"] or 0)
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [item_id]
    with get_connection() as conn:
        cur = conn.execute(
            f"UPDATE details SET {set_clause} WHERE id = ?", values
        )
        return cur.rowcount > 0


# ----- photos（アルバム） -----

def add_photo(trip_id, filename, caption=""):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO photos (trip_id, filename, caption) VALUES (?, ?, ?)",
            (trip_id, filename, caption),
        )


def get_photos(trip_id):
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM photos WHERE trip_id = ? ORDER BY id", (trip_id,)
        )]


def delete_photo(photo_id):
    """写真を削除し、(trip_id, filename) を返す。"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT trip_id, filename FROM photos WHERE id = ?", (photo_id,)
        ).fetchone()
        if not row:
            return None, None
        conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
        return row["trip_id"], row["filename"]


if __name__ == "__main__":
    init_db()
    print(f"データベースを初期化しました: {DB_PATH}")
