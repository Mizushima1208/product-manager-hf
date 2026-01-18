"""Equipment management endpoints."""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
from pathlib import Path
from services.equipment_parser import process_image_async
from services.llm_extractor import get_available_llm_engines
from core import database

# ローカル画像フォルダのパス
LOCAL_IMAGES_PATH = Path(__file__).parent.parent.parent / "data" / "images"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}

# JSONインポートフォルダのパス
JSON_IMPORT_PATH = Path(__file__).parent.parent.parent / "data" / "json-import"

router = APIRouter(prefix="/api", tags=["equipment"])


class EquipmentUpdate(BaseModel):
    """Schema for equipment update."""
    equipment_name: Optional[str] = None
    model_number: Optional[str] = None
    serial_number: Optional[str] = None
    purchase_date: Optional[str] = None
    tool_category: Optional[str] = None
    manufacturer: Optional[str] = None
    weight: Optional[str] = None
    output_power: Optional[str] = None
    engine_model: Optional[str] = None
    year_manufactured: Optional[str] = None
    specifications: Optional[str] = None


class EquipmentImport(BaseModel):
    """Schema for importing equipment from JSON."""
    equipment_name: Optional[str] = None
    model_number: Optional[str] = None
    serial_number: Optional[str] = None
    manufacturer: Optional[str] = None
    weight: Optional[str] = None
    output_power: Optional[str] = None
    engine_model: Optional[str] = None
    year_manufactured: Optional[str] = None
    specifications: Optional[str] = None
    raw_text: Optional[str] = None
    file_name: Optional[str] = None


class EquipmentImportList(BaseModel):
    """Schema for importing multiple equipment from JSON."""
    equipment: List[EquipmentImport]


@router.get("/llm-engines")
async def get_llm_engines():
    """Get available LLM engines for extraction."""
    return {"engines": await get_available_llm_engines()}


@router.post("/equipment/import-json")
async def import_equipment_from_json(data: EquipmentImportList):
    """Import equipment from JSON data (e.g., from Claude VLM output).

    Expected JSON format:
    {
        "equipment": [
            {
                "equipment_name": "草刈機",
                "model_number": "ABC-123",
                "manufacturer": "メーカー名",
                "serial_number": "SN12345",
                "weight": "5.5 kg",
                "output_power": "1.2 kW",
                "engine_model": "エンジン型式",
                "year_manufactured": "2020",
                "specifications": "その他仕様",
                "raw_text": "OCRで読み取ったテキスト",
                "file_name": "image.jpg"
            }
        ]
    }
    """
    imported = []
    errors = []

    for i, item in enumerate(data.equipment):
        try:
            equipment_data = {
                "equipment_name": item.equipment_name,
                "model_number": item.model_number,
                "serial_number": item.serial_number,
                "manufacturer": item.manufacturer,
                "weight": item.weight,
                "output_power": item.output_power,
                "engine_model": item.engine_model,
                "year_manufactured": item.year_manufactured,
                "specifications": item.specifications,
                "raw_text": item.raw_text or "(JSONインポート)",
                "ocr_engine": "json-import",
                "llm_engine": "claude-vlm",
                "file_name": item.file_name
            }
            equipment = database.create_equipment(equipment_data)
            imported.append(equipment)
        except Exception as e:
            errors.append({"index": i, "error": str(e)})

    return {
        "success": True,
        "imported_count": len(imported),
        "equipment": imported,
        "errors": errors
    }


@router.post("/equipment/import-json-file")
async def import_equipment_from_json_file(file: UploadFile = File(...)):
    """Import equipment from a JSON file upload."""
    import json

    try:
        content = await file.read()
        data = json.loads(content.decode('utf-8'))

        # Handle both single object and array
        if isinstance(data, list):
            equipment_list = data
        elif isinstance(data, dict):
            if "equipment" in data:
                equipment_list = data["equipment"]
            else:
                equipment_list = [data]
        else:
            raise HTTPException(status_code=400, detail="Invalid JSON format")

        imported = []
        errors = []

        for i, item in enumerate(equipment_list):
            try:
                equipment_data = {
                    "equipment_name": item.get("equipment_name"),
                    "model_number": item.get("model_number"),
                    "serial_number": item.get("serial_number"),
                    "manufacturer": item.get("manufacturer"),
                    "weight": item.get("weight"),
                    "output_power": item.get("output_power"),
                    "engine_model": item.get("engine_model"),
                    "year_manufactured": item.get("year_manufactured"),
                    "specifications": item.get("specifications"),
                    "raw_text": item.get("raw_text", "(JSONインポート)"),
                    "ocr_engine": "json-import",
                    "llm_engine": "claude-vlm",
                    "file_name": item.get("file_name")
                }
                equipment = database.create_equipment(equipment_data)
                imported.append(equipment)
            except Exception as e:
                errors.append({"index": i, "error": str(e)})

        return {
            "success": True,
            "imported_count": len(imported),
            "equipment": imported,
            "errors": errors
        }
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")


@router.get("/json-import/files")
async def list_json_import_files():
    """List JSON files in the data/json-import folder."""
    import json

    JSON_IMPORT_PATH.mkdir(parents=True, exist_ok=True)

    files = []
    for file_path in JSON_IMPORT_PATH.iterdir():
        if file_path.is_file() and file_path.suffix.lower() == '.json':
            # Try to peek at content
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                    if isinstance(content, list):
                        count = len(content)
                    elif isinstance(content, dict) and 'equipment' in content:
                        count = len(content['equipment'])
                    else:
                        count = 1
            except:
                count = "?"

            files.append({
                "name": file_path.name,
                "path": str(file_path),
                "size": file_path.stat().st_size,
                "equipment_count": count,
                "modified": file_path.stat().st_mtime
            })

    # Sort by modification time (newest first)
    files.sort(key=lambda x: x['modified'], reverse=True)

    return {
        "files": files,
        "folder": str(JSON_IMPORT_PATH)
    }


@router.post("/json-import/import/{filename}")
async def import_json_from_folder(filename: str):
    """Import a specific JSON file from the data/json-import folder."""
    import json

    file_path = JSON_IMPORT_PATH / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    if not file_path.suffix.lower() == '.json':
        raise HTTPException(status_code=400, detail="File must be a JSON file")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Handle different formats
        if isinstance(data, list):
            equipment_list = data
        elif isinstance(data, dict):
            if "equipment" in data:
                equipment_list = data["equipment"]
            else:
                equipment_list = [data]
        else:
            raise HTTPException(status_code=400, detail="Invalid JSON format")

        imported = []
        errors = []

        for i, item in enumerate(equipment_list):
            try:
                equipment_data = {
                    "equipment_name": item.get("equipment_name"),
                    "model_number": item.get("model_number"),
                    "serial_number": item.get("serial_number"),
                    "manufacturer": item.get("manufacturer"),
                    "weight": item.get("weight"),
                    "output_power": item.get("output_power"),
                    "engine_model": item.get("engine_model"),
                    "year_manufactured": item.get("year_manufactured"),
                    "specifications": item.get("specifications"),
                    "raw_text": item.get("raw_text", f"(JSONインポート: {filename})"),
                    "ocr_engine": "json-import",
                    "llm_engine": "claude-vlm",
                    "file_name": item.get("file_name") or filename
                }
                equipment = database.create_equipment(equipment_data)
                imported.append(equipment)
            except Exception as e:
                errors.append({"index": i, "error": str(e)})

        return {
            "success": True,
            "filename": filename,
            "imported_count": len(imported),
            "equipment": imported,
            "errors": errors
        }

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")


@router.post("/equipment/upload")
async def upload_equipment(
    file: UploadFile = File(...),
    llm_engine: str = Form(default="google-vision-gemini")
):
    """Upload and process an equipment image."""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    image_bytes = await file.read()
    equipment = await process_image_async(image_bytes, file.filename, llm_engine)

    return {"success": True, "equipment": equipment}


@router.get("/equipment")
async def get_equipment_list():
    """Get all equipment."""
    equipment = database.get_all_equipment()
    return {"equipment": equipment}


@router.get("/equipment/{equipment_id}")
async def get_equipment(equipment_id: int):
    """Get a specific equipment."""
    equipment = database.get_equipment(equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return equipment


@router.put("/equipment/{equipment_id}")
async def update_equipment(equipment_id: int, update_data: EquipmentUpdate):
    """Update equipment's editable fields."""
    # Check if equipment exists
    existing = database.get_equipment(equipment_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Equipment not found")

    # Build updates dict from non-None fields
    updates = {}
    if update_data.equipment_name is not None:
        updates["equipment_name"] = update_data.equipment_name
    if update_data.model_number is not None:
        updates["model_number"] = update_data.model_number
    if update_data.serial_number is not None:
        updates["serial_number"] = update_data.serial_number
    if update_data.purchase_date is not None:
        updates["purchase_date"] = update_data.purchase_date
    if update_data.tool_category is not None:
        updates["tool_category"] = update_data.tool_category
    if update_data.manufacturer is not None:
        updates["manufacturer"] = update_data.manufacturer
    if update_data.weight is not None:
        updates["weight"] = update_data.weight
    if update_data.output_power is not None:
        updates["output_power"] = update_data.output_power
    if update_data.engine_model is not None:
        updates["engine_model"] = update_data.engine_model
    if update_data.year_manufactured is not None:
        updates["year_manufactured"] = update_data.year_manufactured
    if update_data.specifications is not None:
        updates["specifications"] = update_data.specifications

    if not updates:
        return {"success": True, "equipment": existing}

    updated = database.update_equipment(equipment_id, updates)
    return {"success": True, "equipment": updated}


@router.delete("/equipment/{equipment_id}")
async def delete_equipment(equipment_id: int):
    """Delete equipment."""
    success = database.delete_equipment(equipment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return {"success": True}


@router.delete("/equipment")
async def delete_all_equipment():
    """Delete all equipment."""
    database.delete_all_equipment()
    return {"success": True}


@router.get("/local-files")
async def get_local_files():
    """Get list of image files in the local data/images folder."""
    LOCAL_IMAGES_PATH.mkdir(parents=True, exist_ok=True)

    files = []
    for file_path in LOCAL_IMAGES_PATH.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append({
                "name": file_path.name,
                "path": str(file_path),
                "size": file_path.stat().st_size
            })

    return {"files": files, "folder": str(LOCAL_IMAGES_PATH)}


@router.post("/local-files/process")
async def process_local_file(
    filename: str = Form(...),
    llm_engine: str = Form(default="google-vision-gemini")
):
    """Process a single file from the local images folder."""
    file_path = LOCAL_IMAGES_PATH / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    image_bytes = file_path.read_bytes()
    equipment = await process_image_async(image_bytes, filename, llm_engine)

    return {"success": True, "equipment": equipment}


@router.post("/local-files/process-all")
async def process_all_local_files(
    background_tasks: BackgroundTasks,
    llm_engine: str = Form(default="google-vision-gemini")
):
    """Start processing all files in the local images folder."""
    LOCAL_IMAGES_PATH.mkdir(parents=True, exist_ok=True)

    files = [
        f.name for f in LOCAL_IMAGES_PATH.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    if not files:
        return {"success": False, "message": "No image files found in folder"}

    # Reset progress
    database.reset_progress()
    database.processing_progress["status"] = "processing"
    database.processing_progress["total"] = len(files)
    database.processing_progress["current"] = 0
    database.processing_progress["errors"] = []

    # Start background processing
    background_tasks.add_task(
        _process_local_files_background,
        files, llm_engine
    )

    return {"success": True, "total": len(files), "message": "Processing started"}


async def _process_local_files_background(
    files: List[str],
    llm_engine: str
):
    """Background task to process all local files."""
    for i, filename in enumerate(files):
        database.processing_progress["current"] = i + 1
        database.processing_progress["current_file"] = filename

        try:
            file_path = LOCAL_IMAGES_PATH / filename
            image_bytes = file_path.read_bytes()
            await process_image_async(image_bytes, filename, llm_engine)
        except Exception as e:
            database.processing_progress["errors"].append({
                "file": filename,
                "error": str(e)
            })

    database.processing_progress["status"] = "completed"
    database.processing_progress["current_file"] = ""


@router.get("/local-files/progress")
async def get_local_processing_progress():
    """Get progress of local file processing."""
    return database.processing_progress


@router.post("/equipment/{equipment_id}/increment")
async def increment_equipment_quantity(equipment_id: int):
    """Increment equipment quantity by 1."""
    existing = database.get_equipment(equipment_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Equipment not found")

    new_quantity = (existing.get("quantity") or 0) + 1
    updated = database.update_equipment(equipment_id, {"quantity": new_quantity})
    return {"success": True, "equipment": updated}


@router.post("/equipment/{equipment_id}/decrement")
async def decrement_equipment_quantity(equipment_id: int):
    """Decrement equipment quantity by 1 (minimum 0)."""
    existing = database.get_equipment(equipment_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Equipment not found")

    current = existing.get("quantity") or 0
    new_quantity = max(0, current - 1)
    updated = database.update_equipment(equipment_id, {"quantity": new_quantity})
    return {"success": True, "equipment": updated}
