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


@router.get("/config/api-status")
async def get_api_status():
    """Check API keys status for debugging."""
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    google_sa = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")

    return {
        "gemini_api_key": {
            "configured": bool(gemini_key),
            "prefix": gemini_key[:10] + "..." if gemini_key else None
        },
        "google_service_account": {
            "configured": bool(google_sa),
            "length": len(google_sa) if google_sa else 0
        }
    }


@router.get("/config/test-gemini")
async def test_gemini_api():
    """Test Gemini API connection and list available models."""
    import httpx

    gemini_key = os.environ.get("GEMINI_API_KEY", "")

    if not gemini_key:
        return {
            "success": False,
            "error": "GEMINI_API_KEY が設定されていません",
            "models": []
        }

    results = {
        "api_key_prefix": gemini_key[:10] + "...",
        "models": [],
        "test_result": None
    }

    # Step 1: List available models
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={gemini_key}"
            response = await client.get(list_url)

            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                # Vision対応モデルをフィルタ
                vision_models = []
                for m in models:
                    name = m.get("name", "")
                    methods = m.get("supportedGenerationMethods", [])
                    if "generateContent" in methods:
                        vision_models.append({
                            "name": name,
                            "displayName": m.get("displayName", ""),
                            "methods": methods
                        })
                results["models"] = vision_models
            else:
                results["models_error"] = f"HTTP {response.status_code}: {response.text[:200]}"
    except Exception as e:
        results["models_error"] = str(e)

    # Step 2: Test simple text generation
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Try different model names (based on available models list)
            # gemini-2.0-flash-lite has better free tier limits
            test_models = [
                "gemini-2.0-flash-lite",
                "gemini-flash-lite-latest",
                "gemini-2.0-flash",
                "gemini-flash-latest"
            ]

            for model_name in test_models:
                test_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}"
                payload = {
                    "contents": [{"parts": [{"text": "Say hello in Japanese"}]}],
                    "generationConfig": {"maxOutputTokens": 50}
                }

                response = await client.post(test_url, json=payload)

                if response.status_code == 200:
                    data = response.json()
                    text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    results["test_result"] = {
                        "success": True,
                        "model": model_name,
                        "response": text[:100]
                    }
                    break
                else:
                    results["test_result"] = {
                        "success": False,
                        "model": model_name,
                        "error": f"HTTP {response.status_code}: {response.text[:200]}"
                    }
    except Exception as e:
        results["test_result"] = {"success": False, "error": str(e)}

    return results


@router.get("/config/api-usage")
async def get_api_usage_stats():
    """Get Cloud Vision API usage statistics."""
    from core import database

    current = database.get_api_usage("cloud-vision")
    history = database.get_all_api_usage("cloud-vision")

    print(f"API Usage - current: {current}, history count: {len(history)}")

    return {
        "current_month": current,
        "usage_count": current.get("usage_count", 0),
        "free_limit": current.get("free_limit", 1000),
        "remaining": max(0, current.get("free_limit", 1000) - current.get("usage_count", 0)),
        "history": history[:12]  # 過去12ヶ月分
    }


@router.post("/config/api-usage/reset")
async def reset_api_usage_stats():
    """Reset current month's API usage counter."""
    from core import database
    database.reset_api_usage("cloud-vision")
    return {"success": True, "message": "使用量カウンターをリセットしました"}


@router.get("/config/test-vision")
async def test_vision_api():
    """Test Cloud Vision API connection."""
    import os
    import json

    result = {
        "service_account_configured": False,
        "api_enabled": False,
        "error": None
    }

    # Check if service account is configured
    service_account_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if service_account_json:
        try:
            creds_info = json.loads(service_account_json)
            result["service_account_configured"] = True
            result["project_id"] = creds_info.get("project_id")
            result["client_email"] = creds_info.get("client_email")
        except Exception as e:
            result["error"] = f"Invalid JSON: {str(e)}"
            return result
    else:
        result["error"] = "GOOGLE_SERVICE_ACCOUNT_JSON not set"
        return result

    # Try to use Vision API
    try:
        from google.cloud import vision
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_info(creds_info)
        client = vision.ImageAnnotatorClient(credentials=credentials)

        # Create a simple test image (1x1 white pixel)
        import base64
        test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        test_image_bytes = base64.b64decode(test_image_base64)

        image = vision.Image(content=test_image_bytes)
        response = client.text_detection(image=image)

        if response.error.message:
            result["error"] = f"Vision API error: {response.error.message}"
        else:
            result["api_enabled"] = True
            result["message"] = "Cloud Vision API is working!"

    except Exception as e:
        error_str = str(e)
        if "403" in error_str or "has not been used" in error_str or "disabled" in error_str:
            result["error"] = "Cloud Vision API が有効になっていません。Google Cloud Consoleで有効化してください。"
            result["enable_url"] = "https://console.cloud.google.com/apis/library/vision.googleapis.com"
        elif "401" in error_str or "permission" in error_str.lower():
            result["error"] = "サービスアカウントにCloud Vision APIの権限がありません。"
        else:
            result["error"] = f"API error: {error_str}"

    return result


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
