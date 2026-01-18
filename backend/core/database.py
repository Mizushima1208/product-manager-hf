"""SQLite database for equipment."""
import sqlite3
import os
from pathlib import Path
from typing import List, Optional
from contextlib import contextmanager

# Database file path
# HuggingFace Spacesでは /data が永続ストレージとして使用可能
if os.getenv("SPACE_ID"):
    # HuggingFace Spaces環境 - 永続ストレージを使用
    DB_PATH = Path("/data/equipment.db")
    PRODUCT_IMAGES_PATH = Path("/data/product-images")
else:
    # ローカル開発環境
    DB_PATH = Path(__file__).parent.parent / "data" / "equipment.db"
    PRODUCT_IMAGES_PATH = Path(__file__).parent.parent / "data" / "product-images"

# Progress tracking for batch operations (in-memory)
processing_progress = {
    "status": "idle",
    "current": 0,
    "total": 0,
    "current_file": "",
    "errors": []
}


def reset_progress():
    """Reset progress tracking."""
    global processing_progress
    processing_progress = {
        "status": "idle",
        "current": 0,
        "total": 0,
        "current_file": "",
        "errors": []
    }


def init_db():
    """Initialize the database and create tables."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        cursor = conn.cursor()

        # Equipment table - 建設機械・産業機器用
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS equipment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                equipment_name TEXT,
                model_number TEXT,
                serial_number TEXT,
                purchase_date TEXT,
                tool_category TEXT,
                manufacturer TEXT,
                weight TEXT,
                output_power TEXT,
                engine_model TEXT,
                year_manufactured TEXT,
                specifications TEXT,
                raw_text TEXT,
                ocr_engine TEXT,
                llm_engine TEXT,
                file_name TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        # 既存テーブルに新カラムを追加（マイグレーション）
        try:
            cursor.execute("ALTER TABLE equipment ADD COLUMN purchase_date TEXT")
        except sqlite3.OperationalError:
            pass  # カラムが既に存在
        try:
            cursor.execute("ALTER TABLE equipment ADD COLUMN tool_category TEXT")
        except sqlite3.OperationalError:
            pass  # カラムが既に存在
        try:
            cursor.execute("ALTER TABLE equipment ADD COLUMN image_path TEXT")
        except sqlite3.OperationalError:
            pass  # カラムが既に存在
        try:
            cursor.execute("ALTER TABLE equipment ADD COLUMN quantity INTEGER DEFAULT 1")
        except sqlite3.OperationalError:
            pass  # カラムが既に存在
        try:
            cursor.execute("ALTER TABLE equipment ADD COLUMN notes TEXT")
        except sqlite3.OperationalError:
            pass  # カラムが既に存在

        # 工事看板テーブル - 在庫管理用
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signboards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                comment TEXT,
                description TEXT,
                size TEXT,
                quantity INTEGER DEFAULT 1,
                location TEXT,
                status TEXT DEFAULT '在庫あり',
                notes TEXT,
                image_path TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        # signboards に image_path カラムを追加（マイグレーション）
        try:
            cursor.execute("ALTER TABLE signboards ADD COLUMN image_path TEXT")
        except sqlite3.OperationalError:
            pass  # カラムが既に存在

        # 看板数量変更履歴テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signboard_quantity_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signboard_id INTEGER NOT NULL,
                change_type TEXT NOT NULL,
                change_amount INTEGER NOT NULL,
                quantity_before INTEGER NOT NULL,
                quantity_after INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT,
                FOREIGN KEY (signboard_id) REFERENCES signboards(id)
            )
        """)

        # API使用量追跡テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_name TEXT NOT NULL,
                year_month TEXT NOT NULL,
                usage_count INTEGER DEFAULT 0,
                free_limit INTEGER DEFAULT 1000,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(api_name, year_month)
            )
        """)

        # 初期データを挿入（存在しない場合のみ）
        from datetime import datetime
        current_month = datetime.now().strftime("%Y-%m")
        cursor.execute("""
            INSERT OR IGNORE INTO api_usage (api_name, year_month, usage_count, free_limit, created_at, updated_at)
            VALUES ('cloud-vision', ?, 0, 1000, datetime('now'), datetime('now'))
        """, (current_month,))

        conn.commit()


@contextmanager
def get_connection():
    """Get database connection."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def row_to_dict(row) -> dict:
    """Convert sqlite3.Row to dict."""
    if row is None:
        return None
    return dict(row)


# 工具種別の予測
TOOL_CATEGORY_RULES = {
    # 型番パターン → 工具種別
    "MVH": "プレートコンパクター",
    "MVC": "プレートコンパクター",
    "MT-": "ランマー",
    "MTX": "ランマー",
    "MRH": "ランマー",
    "MGC": "カッター",
    "MCD": "コアドリル",
    "MSB": "ブレーカー",
    # 製品名キーワード → 工具種別
    "プレート": "プレートコンパクター",
    "コンパクター": "プレートコンパクター",
    "ランマ": "ランマー",
    "タンパ": "ランマー",
    "バイブレータ": "バイブレーター",
    "発電機": "発電機",
    "溶接機": "溶接機",
    "コンプレッサ": "コンプレッサー",
    "ブレーカ": "ブレーカー",
    "ドリル": "ドリル",
    "カッター": "カッター",
    "ポンプ": "ポンプ",
    "チェーンソー": "チェーンソー",
    "草刈": "草刈機",
    "刈払": "草刈機",
}


def predict_tool_category(model_number: str, equipment_name: str) -> str:
    """型番や製品名から工具種別を予測"""
    model_upper = (model_number or "").upper()
    name = equipment_name or ""

    # 型番から予測
    for pattern, category in TOOL_CATEGORY_RULES.items():
        if pattern.upper() in model_upper:
            return category

    # 製品名から予測
    for keyword, category in TOOL_CATEGORY_RULES.items():
        if keyword in name:
            return category

    return ""  # 予測できない場合は空


# Equipment CRUD operations
def create_equipment(equipment_data: dict) -> dict:
    """Create a new equipment record."""
    # 工具種別が未設定なら予測
    tool_category = equipment_data.get("tool_category")
    if not tool_category:
        tool_category = predict_tool_category(
            equipment_data.get("model_number"),
            equipment_data.get("equipment_name")
        )

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO equipment (equipment_name, model_number, serial_number, purchase_date,
                                   tool_category, manufacturer, weight, output_power, engine_model,
                                   year_manufactured, specifications, raw_text, ocr_engine,
                                   llm_engine, file_name, image_path, quantity, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (
            equipment_data.get("equipment_name"),
            equipment_data.get("model_number"),
            equipment_data.get("serial_number"),
            equipment_data.get("purchase_date"),
            tool_category,
            equipment_data.get("manufacturer"),
            equipment_data.get("weight"),
            equipment_data.get("output_power"),
            equipment_data.get("engine_model"),
            equipment_data.get("year_manufactured"),
            equipment_data.get("specifications"),
            equipment_data.get("raw_text"),
            equipment_data.get("ocr_engine"),
            equipment_data.get("llm_engine"),
            equipment_data.get("file_name"),
            equipment_data.get("image_path"),
            equipment_data.get("quantity", 1)
        ))

        conn.commit()
        equipment_id = cursor.lastrowid

        return get_equipment(equipment_id)


def get_equipment(equipment_id: int) -> Optional[dict]:
    """Get equipment by ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM equipment WHERE id = ?", (equipment_id,))
        row = cursor.fetchone()
        return row_to_dict(row)


def get_all_equipment(sort_by: str = "created_at", sort_order: str = "desc") -> List[dict]:
    """Get all equipment with sorting.

    Args:
        sort_by: Column to sort by (created_at, equipment_name, manufacturer, model_number)
        sort_order: Sort order (asc, desc)
    """
    # Validate sort_by to prevent SQL injection
    allowed_columns = ["created_at", "equipment_name", "manufacturer", "model_number", "updated_at"]
    if sort_by not in allowed_columns:
        sort_by = "created_at"

    # Validate sort_order
    sort_order = "ASC" if sort_order.lower() == "asc" else "DESC"

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM equipment ORDER BY {sort_by} {sort_order}")
        rows = cursor.fetchall()
        return [row_to_dict(row) for row in rows]


def update_equipment(equipment_id: int, updates: dict) -> Optional[dict]:
    """Update equipment."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Build update query dynamically
        allowed_fields = ["equipment_name", "model_number", "serial_number", "purchase_date",
                          "tool_category", "manufacturer", "weight", "output_power", "engine_model",
                          "year_manufactured", "specifications", "image_path", "quantity", "notes"]
        set_clauses = []
        values = []

        for field in allowed_fields:
            if field in updates:
                set_clauses.append(f"{field} = ?")
                values.append(updates[field])

        if not set_clauses:
            return get_equipment(equipment_id)

        set_clauses.append("updated_at = datetime('now')")
        values.append(equipment_id)

        query = f"UPDATE equipment SET {', '.join(set_clauses)} WHERE id = ?"
        cursor.execute(query, values)
        conn.commit()

        return get_equipment(equipment_id)


def delete_equipment(equipment_id: int) -> bool:
    """Delete equipment."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM equipment WHERE id = ?", (equipment_id,))
        conn.commit()
        return cursor.rowcount > 0


def delete_all_equipment() -> int:
    """Delete all equipment."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM equipment")
        conn.commit()
        return cursor.rowcount


# ========== 工事看板 CRUD ==========

def create_signboard(data: dict) -> dict:
    """Create a new signboard record."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO signboards (comment, description, size, quantity, location, status, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (
            data.get("comment"),
            data.get("description"),
            data.get("size"),
            data.get("quantity", 1),
            data.get("location"),
            data.get("status", "在庫あり"),
            data.get("notes")
        ))
        conn.commit()
        return get_signboard(cursor.lastrowid)


def get_signboard(signboard_id: int) -> Optional[dict]:
    """Get signboard by ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM signboards WHERE id = ?", (signboard_id,))
        return row_to_dict(cursor.fetchone())


def get_all_signboards() -> List[dict]:
    """Get all signboards."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM signboards ORDER BY created_at DESC")
        return [row_to_dict(row) for row in cursor.fetchall()]


def update_signboard(signboard_id: int, updates: dict) -> Optional[dict]:
    """Update signboard."""
    with get_connection() as conn:
        cursor = conn.cursor()
        allowed_fields = ["comment", "description", "size", "quantity", "location", "status", "notes"]
        set_clauses = []
        values = []

        for field in allowed_fields:
            if field in updates:
                set_clauses.append(f"{field} = ?")
                values.append(updates[field])

        if not set_clauses:
            return get_signboard(signboard_id)

        set_clauses.append("updated_at = datetime('now')")
        values.append(signboard_id)

        query = f"UPDATE signboards SET {', '.join(set_clauses)} WHERE id = ?"
        cursor.execute(query, values)
        conn.commit()
        return get_signboard(signboard_id)


def delete_signboard(signboard_id: int) -> bool:
    """Delete signboard."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM signboards WHERE id = ?", (signboard_id,))
        conn.commit()
        return cursor.rowcount > 0


def delete_all_signboards() -> int:
    """Delete all signboards."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM signboards")
        conn.commit()
        return cursor.rowcount


# ========== 看板数量変更履歴 ==========

def create_quantity_history(signboard_id: int, change_type: str, change_amount: int,
                            quantity_before: int, quantity_after: int, reason: str) -> dict:
    """Create a quantity change history record."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO signboard_quantity_history
            (signboard_id, change_type, change_amount, quantity_before, quantity_after, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (signboard_id, change_type, change_amount, quantity_before, quantity_after, reason))
        conn.commit()
        return get_quantity_history_by_id(cursor.lastrowid)


def get_quantity_history_by_id(history_id: int) -> Optional[dict]:
    """Get history record by ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM signboard_quantity_history WHERE id = ?", (history_id,))
        return row_to_dict(cursor.fetchone())


def get_quantity_history_by_signboard(signboard_id: int) -> List[dict]:
    """Get all history for a signboard."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM signboard_quantity_history
            WHERE signboard_id = ?
            ORDER BY created_at DESC
        """, (signboard_id,))
        return [row_to_dict(row) for row in cursor.fetchall()]


def get_all_quantity_history() -> List[dict]:
    """Get all quantity change history."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT h.*, s.comment as signboard_name
            FROM signboard_quantity_history h
            LEFT JOIN signboards s ON h.signboard_id = s.id
            ORDER BY h.created_at DESC
        """)
        return [row_to_dict(row) for row in cursor.fetchall()]


# ========== API使用量追跡 ==========

def get_current_month() -> str:
    """Get current year-month string (YYYY-MM)."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m")


def increment_api_usage(api_name: str = "cloud-vision") -> dict:
    """Increment API usage counter for current month."""
    year_month = get_current_month()

    with get_connection() as conn:
        cursor = conn.cursor()

        # Try to insert or update
        cursor.execute("""
            INSERT INTO api_usage (api_name, year_month, usage_count, free_limit, created_at, updated_at)
            VALUES (?, ?, 1, 1000, datetime('now'), datetime('now'))
            ON CONFLICT(api_name, year_month) DO UPDATE SET
                usage_count = usage_count + 1,
                updated_at = datetime('now')
        """, (api_name, year_month))

        conn.commit()
        return get_api_usage(api_name, year_month)


def get_api_usage(api_name: str = "cloud-vision", year_month: str = None) -> dict:
    """Get API usage for a specific month."""
    if year_month is None:
        year_month = get_current_month()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM api_usage WHERE api_name = ? AND year_month = ?
        """, (api_name, year_month))
        row = cursor.fetchone()

        if row:
            return row_to_dict(row)
        else:
            return {
                "api_name": api_name,
                "year_month": year_month,
                "usage_count": 0,
                "free_limit": 1000
            }


def get_all_api_usage(api_name: str = "cloud-vision") -> List[dict]:
    """Get all API usage history."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM api_usage WHERE api_name = ? ORDER BY year_month DESC
        """, (api_name,))
        return [row_to_dict(row) for row in cursor.fetchall()]


def reset_api_usage(api_name: str = "cloud-vision", year_month: str = None) -> bool:
    """Reset API usage counter."""
    if year_month is None:
        year_month = get_current_month()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE api_usage SET usage_count = 0, updated_at = datetime('now')
            WHERE api_name = ? AND year_month = ?
        """, (api_name, year_month))
        conn.commit()
        return cursor.rowcount > 0


# Initialize database on module load
init_db()
