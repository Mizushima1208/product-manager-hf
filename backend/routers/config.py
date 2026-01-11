"""Configuration management endpoints."""
import os
import re
import json
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from core.config import load_config, save_config, CREDENTIALS_FILE, TOKEN_FILE, VISION_CREDENTIALS_FILE

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config")
async def get_config():
    """Get current configuration."""
    config = load_config()
    return {
        "google_drive_folder_id": config.get("google_drive_folder_id", ""),
        "has_credentials": os.path.exists(CREDENTIALS_FILE)
    }


@router.post("/config")
async def update_config(folder_id: str = Form(None)):
    """Update configuration."""
    config = load_config()
    if folder_id is not None:
        if "drive.google.com" in folder_id:
            match = re.search(r'/folders/([a-zA-Z0-9_-]+)', folder_id)
            if match:
                folder_id = match.group(1)
        config["google_drive_folder_id"] = folder_id
    save_config(config)
    return {"success": True, "config": config}


@router.post("/config/credentials")
async def upload_credentials(file: UploadFile = File(...)):
    """Upload Google API credentials.json."""
    try:
        content = await file.read()
        json.loads(content)  # Validate JSON

        with open(CREDENTIALS_FILE, 'wb') as f:
            f.write(content)

        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)

        return {"success": True, "message": "Credentials saved successfully"}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config/vision")
async def get_vision_config():
    """Get Google Vision API configuration status."""
    result = {
        "configured": False,
        "client_email": None,
        "project_id": None,
        "credentials_path": VISION_CREDENTIALS_FILE
    }

    # Check environment variable first
    env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path and os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                creds = json.load(f)
                result["configured"] = True
                result["client_email"] = creds.get("client_email", "不明")
                result["project_id"] = creds.get("project_id", "不明")
                result["source"] = "環境変数"
                return result
        except:
            pass

    # Check local credentials file
    if os.path.exists(VISION_CREDENTIALS_FILE):
        try:
            with open(VISION_CREDENTIALS_FILE, 'r', encoding='utf-8') as f:
                creds = json.load(f)
                result["configured"] = True
                result["client_email"] = creds.get("client_email", "不明")
                result["project_id"] = creds.get("project_id", "不明")
                result["source"] = "アップロード済み"
        except:
            pass

    return result


@router.post("/config/vision/credentials")
async def upload_vision_credentials(file: UploadFile = File(...)):
    """Upload Google Vision API service account credentials."""
    try:
        content = await file.read()
        creds = json.loads(content)

        # Validate it's a service account key
        if "type" not in creds or creds["type"] != "service_account":
            raise HTTPException(
                status_code=400,
                detail="サービスアカウントのJSONキーファイルをアップロードしてください"
            )

        if "client_email" not in creds or "private_key" not in creds:
            raise HTTPException(
                status_code=400,
                detail="無効なサービスアカウントキーです"
            )

        # Save credentials
        with open(VISION_CREDENTIALS_FILE, 'wb') as f:
            f.write(content)

        # Set environment variable for current session
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = VISION_CREDENTIALS_FILE

        return {
            "success": True,
            "message": "Vision API認証情報を保存しました",
            "client_email": creds.get("client_email"),
            "project_id": creds.get("project_id")
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="無効なJSONファイルです")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
