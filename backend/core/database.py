"""Database module - Supabase or SQLite."""
import os
from typing import List, Optional
from datetime import datetime

# Check for Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)

# Initialize Supabase client if configured
supabase_client = None
STORAGE_BUCKET = "product-images"

if USE_SUPABASE:
    try:
        from supabase import create_client
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✓ Supabase connected")

        # Ensure storage bucket exists
        try:
            supabase_client.storage.get_bucket(STORAGE_BUCKET)
            print(f"✓ Storage bucket '{STORAGE_BUCKET}' ready")
        except Exception:
            try:
                supabase_client.storage.create_bucket(STORAGE_BUCKET, options={"public": True})
                print(f"✓ Storage bucket '{STORAGE_BUCKET}' created")
            except Exception as bucket_error:
                print(f"⚠ Storage bucket setup: {bucket_error}")
    except Exception as e:
        print(f"✗ Supabase connection failed: {e}")
        USE_SUPABASE = False

# SQLite fallback
if not USE_SUPABASE:
    import sqlite3
    from pathlib import Path
    from contextlib import contextmanager

    if os.getenv("SPACE_ID"):
        DB_PATH = Path("/data/equipment.db")
    else:
        DB_PATH = Path(__file__).parent.parent / "data" / "equipment.db"

    print(f"Using SQLite: {DB_PATH}")

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


# ========== SQLite helpers ==========

if not USE_SUPABASE:
    @contextmanager
    def get_connection():
        """Get SQLite database connection."""
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
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

    def init_sqlite_db():
        """Initialize SQLite database and create tables."""
        with get_connection() as conn:
            cursor = conn.cursor()

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
                    image_path TEXT,
                    quantity INTEGER DEFAULT 1,
                    notes TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)

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

            conn.commit()

    init_sqlite_db()


# ========== Tool Category Prediction ==========

TOOL_CATEGORY_RULES = {
    "MVH": "プレートコンパクター",
    "MVC": "プレートコンパクター",
    "MT-": "ランマー",
    "MTX": "ランマー",
    "MRH": "ランマー",
    "MGC": "カッター",
    "MCD": "コアドリル",
    "MSB": "ブレーカー",
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
    """Predict tool category from model number or equipment name."""
    model_upper = (model_number or "").upper()
    name = equipment_name or ""

    for pattern, category in TOOL_CATEGORY_RULES.items():
        if pattern.upper() in model_upper:
            return category

    for keyword, category in TOOL_CATEGORY_RULES.items():
        if keyword in name:
            return category

    return ""


# ========== Equipment CRUD ==========

def create_equipment(equipment_data: dict) -> dict:
    """Create a new equipment record."""
    tool_category = equipment_data.get("tool_category")
    if not tool_category:
        tool_category = predict_tool_category(
            equipment_data.get("model_number"),
            equipment_data.get("equipment_name")
        )

    now = datetime.now().isoformat()

    if USE_SUPABASE:
        data = {
            "equipment_name": equipment_data.get("equipment_name"),
            "model_number": equipment_data.get("model_number"),
            "serial_number": equipment_data.get("serial_number"),
            "purchase_date": equipment_data.get("purchase_date"),
            "tool_category": tool_category,
            "manufacturer": equipment_data.get("manufacturer"),
            "weight": equipment_data.get("weight"),
            "output_power": equipment_data.get("output_power"),
            "engine_model": equipment_data.get("engine_model"),
            "year_manufactured": equipment_data.get("year_manufactured"),
            "specifications": equipment_data.get("specifications"),
            "raw_text": equipment_data.get("raw_text"),
            "ocr_engine": equipment_data.get("ocr_engine"),
            "llm_engine": equipment_data.get("llm_engine"),
            "file_name": equipment_data.get("file_name"),
            "image_path": equipment_data.get("image_path"),
            "quantity": equipment_data.get("quantity", 1),
            "created_at": now,
            "updated_at": now
        }
        result = supabase_client.table("equipment").insert(data).execute()
        return result.data[0] if result.data else None
    else:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO equipment (equipment_name, model_number, serial_number, purchase_date,
                                       tool_category, manufacturer, weight, output_power, engine_model,
                                       year_manufactured, specifications, raw_text, ocr_engine,
                                       llm_engine, file_name, image_path, quantity, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                equipment_data.get("quantity", 1),
                now, now
            ))
            conn.commit()
            return get_equipment(cursor.lastrowid)


def get_equipment(equipment_id: int) -> Optional[dict]:
    """Get equipment by ID."""
    if USE_SUPABASE:
        result = supabase_client.table("equipment").select("*").eq("id", equipment_id).execute()
        return result.data[0] if result.data else None
    else:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM equipment WHERE id = ?", (equipment_id,))
            return row_to_dict(cursor.fetchone())


def get_all_equipment(sort_by: str = "created_at", sort_order: str = "desc") -> List[dict]:
    """Get all equipment with sorting."""
    allowed_columns = ["created_at", "equipment_name", "manufacturer", "model_number", "updated_at"]
    if sort_by not in allowed_columns:
        sort_by = "created_at"

    if USE_SUPABASE:
        query = supabase_client.table("equipment").select("*")
        if sort_order.lower() == "asc":
            query = query.order(sort_by, desc=False)
        else:
            query = query.order(sort_by, desc=True)
        result = query.execute()
        return result.data or []
    else:
        sort_order_sql = "ASC" if sort_order.lower() == "asc" else "DESC"
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM equipment ORDER BY {sort_by} {sort_order_sql}")
            return [row_to_dict(row) for row in cursor.fetchall()]


def update_equipment(equipment_id: int, updates: dict) -> Optional[dict]:
    """Update equipment."""
    allowed_fields = ["equipment_name", "model_number", "serial_number", "purchase_date",
                      "tool_category", "manufacturer", "weight", "output_power", "engine_model",
                      "year_manufactured", "specifications", "image_path", "quantity", "notes"]

    filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}
    if not filtered_updates:
        return get_equipment(equipment_id)

    filtered_updates["updated_at"] = datetime.now().isoformat()

    if USE_SUPABASE:
        result = supabase_client.table("equipment").update(filtered_updates).eq("id", equipment_id).execute()
        return result.data[0] if result.data else None
    else:
        with get_connection() as conn:
            cursor = conn.cursor()
            set_clauses = [f"{k} = ?" for k in filtered_updates.keys()]
            values = list(filtered_updates.values()) + [equipment_id]
            query = f"UPDATE equipment SET {', '.join(set_clauses)} WHERE id = ?"
            cursor.execute(query, values)
            conn.commit()
            return get_equipment(equipment_id)


def delete_equipment(equipment_id: int) -> bool:
    """Delete equipment."""
    if USE_SUPABASE:
        result = supabase_client.table("equipment").delete().eq("id", equipment_id).execute()
        return len(result.data) > 0 if result.data else False
    else:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM equipment WHERE id = ?", (equipment_id,))
            conn.commit()
            return cursor.rowcount > 0


def delete_all_equipment() -> int:
    """Delete all equipment."""
    if USE_SUPABASE:
        result = supabase_client.table("equipment").delete().neq("id", 0).execute()
        return len(result.data) if result.data else 0
    else:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM equipment")
            conn.commit()
            return cursor.rowcount


# ========== Signboards CRUD ==========

def create_signboard(data: dict) -> dict:
    """Create a new signboard record."""
    now = datetime.now().isoformat()

    if USE_SUPABASE:
        insert_data = {
            "comment": data.get("comment"),
            "description": data.get("description"),
            "size": data.get("size"),
            "quantity": data.get("quantity", 1),
            "location": data.get("location"),
            "status": data.get("status", "在庫あり"),
            "notes": data.get("notes"),
            "created_at": now,
            "updated_at": now
        }
        result = supabase_client.table("signboards").insert(insert_data).execute()
        return result.data[0] if result.data else None
    else:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO signboards (comment, description, size, quantity, location, status, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("comment"),
                data.get("description"),
                data.get("size"),
                data.get("quantity", 1),
                data.get("location"),
                data.get("status", "在庫あり"),
                data.get("notes"),
                now, now
            ))
            conn.commit()
            return get_signboard(cursor.lastrowid)


def get_signboard(signboard_id: int) -> Optional[dict]:
    """Get signboard by ID."""
    if USE_SUPABASE:
        result = supabase_client.table("signboards").select("*").eq("id", signboard_id).execute()
        return result.data[0] if result.data else None
    else:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM signboards WHERE id = ?", (signboard_id,))
            return row_to_dict(cursor.fetchone())


def get_all_signboards() -> List[dict]:
    """Get all signboards."""
    if USE_SUPABASE:
        result = supabase_client.table("signboards").select("*").order("created_at", desc=True).execute()
        return result.data or []
    else:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM signboards ORDER BY created_at DESC")
            return [row_to_dict(row) for row in cursor.fetchall()]


def update_signboard(signboard_id: int, updates: dict) -> Optional[dict]:
    """Update signboard."""
    allowed_fields = ["comment", "description", "size", "quantity", "location", "status", "notes", "image_path"]
    filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}

    if not filtered_updates:
        return get_signboard(signboard_id)

    filtered_updates["updated_at"] = datetime.now().isoformat()

    if USE_SUPABASE:
        result = supabase_client.table("signboards").update(filtered_updates).eq("id", signboard_id).execute()
        return result.data[0] if result.data else None
    else:
        with get_connection() as conn:
            cursor = conn.cursor()
            set_clauses = [f"{k} = ?" for k in filtered_updates.keys()]
            values = list(filtered_updates.values()) + [signboard_id]
            query = f"UPDATE signboards SET {', '.join(set_clauses)} WHERE id = ?"
            cursor.execute(query, values)
            conn.commit()
            return get_signboard(signboard_id)


def delete_signboard(signboard_id: int) -> bool:
    """Delete signboard."""
    if USE_SUPABASE:
        result = supabase_client.table("signboards").delete().eq("id", signboard_id).execute()
        return len(result.data) > 0 if result.data else False
    else:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM signboards WHERE id = ?", (signboard_id,))
            conn.commit()
            return cursor.rowcount > 0


def delete_all_signboards() -> int:
    """Delete all signboards."""
    if USE_SUPABASE:
        result = supabase_client.table("signboards").delete().neq("id", 0).execute()
        return len(result.data) if result.data else 0
    else:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM signboards")
            conn.commit()
            return cursor.rowcount


# ========== Signboard Quantity History ==========

def create_quantity_history(signboard_id: int, change_type: str, change_amount: int,
                            quantity_before: int, quantity_after: int, reason: str) -> dict:
    """Create a quantity change history record."""
    now = datetime.now().isoformat()

    if USE_SUPABASE:
        data = {
            "signboard_id": signboard_id,
            "change_type": change_type,
            "change_amount": change_amount,
            "quantity_before": quantity_before,
            "quantity_after": quantity_after,
            "reason": reason,
            "created_at": now
        }
        result = supabase_client.table("signboard_quantity_history").insert(data).execute()
        return result.data[0] if result.data else None
    else:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO signboard_quantity_history
                (signboard_id, change_type, change_amount, quantity_before, quantity_after, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (signboard_id, change_type, change_amount, quantity_before, quantity_after, reason, now))
            conn.commit()
            return get_quantity_history_by_id(cursor.lastrowid)


def get_quantity_history_by_id(history_id: int) -> Optional[dict]:
    """Get history record by ID."""
    if USE_SUPABASE:
        result = supabase_client.table("signboard_quantity_history").select("*").eq("id", history_id).execute()
        return result.data[0] if result.data else None
    else:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM signboard_quantity_history WHERE id = ?", (history_id,))
            return row_to_dict(cursor.fetchone())


def get_quantity_history_by_signboard(signboard_id: int) -> List[dict]:
    """Get all history for a signboard."""
    if USE_SUPABASE:
        result = supabase_client.table("signboard_quantity_history").select("*").eq("signboard_id", signboard_id).order("created_at", desc=True).execute()
        return result.data or []
    else:
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
    if USE_SUPABASE:
        result = supabase_client.table("signboard_quantity_history").select("*, signboards(comment)").order("created_at", desc=True).execute()
        return result.data or []
    else:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT h.*, s.comment as signboard_name
                FROM signboard_quantity_history h
                LEFT JOIN signboards s ON h.signboard_id = s.id
                ORDER BY h.created_at DESC
            """)
            return [row_to_dict(row) for row in cursor.fetchall()]


# ========== API Usage Tracking ==========

def get_current_month() -> str:
    """Get current year-month string (YYYY-MM)."""
    return datetime.now().strftime("%Y-%m")


def increment_api_usage(api_name: str = "cloud-vision") -> dict:
    """Increment API usage counter for current month."""
    year_month = get_current_month()
    now = datetime.now().isoformat()

    if USE_SUPABASE:
        # Check if exists
        result = supabase_client.table("api_usage").select("*").eq("api_name", api_name).eq("year_month", year_month).execute()
        if result.data:
            # Update
            new_count = result.data[0]["usage_count"] + 1
            supabase_client.table("api_usage").update({"usage_count": new_count, "updated_at": now}).eq("id", result.data[0]["id"]).execute()
        else:
            # Insert
            supabase_client.table("api_usage").insert({
                "api_name": api_name,
                "year_month": year_month,
                "usage_count": 1,
                "free_limit": 1000,
                "created_at": now,
                "updated_at": now
            }).execute()
        return get_api_usage(api_name, year_month)
    else:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO api_usage (api_name, year_month, usage_count, free_limit, created_at, updated_at)
                VALUES (?, ?, 1, 1000, ?, ?)
                ON CONFLICT(api_name, year_month) DO UPDATE SET
                    usage_count = usage_count + 1,
                    updated_at = ?
            """, (api_name, year_month, now, now, now))
            conn.commit()
            return get_api_usage(api_name, year_month)


def get_api_usage(api_name: str = "cloud-vision", year_month: str = None) -> dict:
    """Get API usage for a specific month."""
    if year_month is None:
        year_month = get_current_month()

    if USE_SUPABASE:
        result = supabase_client.table("api_usage").select("*").eq("api_name", api_name).eq("year_month", year_month).execute()
        if result.data:
            return result.data[0]
        return {"api_name": api_name, "year_month": year_month, "usage_count": 0, "free_limit": 1000}
    else:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM api_usage WHERE api_name = ? AND year_month = ?", (api_name, year_month))
            row = cursor.fetchone()
            if row:
                return row_to_dict(row)
            return {"api_name": api_name, "year_month": year_month, "usage_count": 0, "free_limit": 1000}


def get_all_api_usage(api_name: str = "cloud-vision") -> List[dict]:
    """Get all API usage history."""
    if USE_SUPABASE:
        result = supabase_client.table("api_usage").select("*").eq("api_name", api_name).order("year_month", desc=True).execute()
        return result.data or []
    else:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM api_usage WHERE api_name = ? ORDER BY year_month DESC", (api_name,))
            return [row_to_dict(row) for row in cursor.fetchall()]


def reset_api_usage(api_name: str = "cloud-vision", year_month: str = None) -> bool:
    """Reset API usage counter."""
    if year_month is None:
        year_month = get_current_month()

    if USE_SUPABASE:
        result = supabase_client.table("api_usage").update({"usage_count": 0, "updated_at": datetime.now().isoformat()}).eq("api_name", api_name).eq("year_month", year_month).execute()
        return len(result.data) > 0 if result.data else False
    else:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE api_usage SET usage_count = 0, updated_at = ? WHERE api_name = ? AND year_month = ?",
                          (datetime.now().isoformat(), api_name, year_month))
            conn.commit()
            return cursor.rowcount > 0


# ========== Image Storage ==========

def upload_image(image_data: bytes, filename: str) -> Optional[str]:
    """Upload image to Supabase Storage and return public URL.

    Falls back to local storage if Supabase is not available.
    """
    import hashlib
    import time
    from pathlib import Path

    # Generate unique filename
    hash_str = hashlib.md5(f"{filename}{time.time()}".encode()).hexdigest()[:8]
    # Get extension from filename
    ext = Path(filename).suffix.lower() or ".jpg"
    unique_filename = f"{hash_str}{ext}"

    if USE_SUPABASE and supabase_client:
        try:
            # Upload to Supabase Storage
            result = supabase_client.storage.from_(STORAGE_BUCKET).upload(
                unique_filename,
                image_data,
                {"content-type": f"image/{ext.replace('.', '')}"}
            )

            # Get public URL
            public_url = supabase_client.storage.from_(STORAGE_BUCKET).get_public_url(unique_filename)
            print(f"✓ Image uploaded to Supabase: {unique_filename}")
            return public_url

        except Exception as e:
            print(f"✗ Supabase storage error: {e}")
            # Fall through to local storage

    # Fallback: save locally
    if os.getenv("SPACE_ID"):
        local_path = Path("/data/product-images")
    else:
        local_path = Path(__file__).parent.parent / "data" / "product-images"

    local_path.mkdir(parents=True, exist_ok=True)
    filepath = local_path / unique_filename

    with open(filepath, "wb") as f:
        f.write(image_data)

    print(f"✓ Image saved locally: {unique_filename}")
    return f"/data/product-images/{unique_filename}"


def get_image_url(image_path: str) -> str:
    """Convert stored image path to accessible URL."""
    if not image_path:
        return ""

    # If already a full URL (Supabase), return as-is
    if image_path.startswith("http"):
        return image_path

    # If local path, return as-is (served by FastAPI)
    return image_path
