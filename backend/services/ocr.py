"""OCR engine implementation - Google Vision API only."""
import os
import io
from PIL import Image
from fastapi import HTTPException

# Register HEIC support
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass


def ocr_with_google_vision(image_bytes: bytes) -> str:
    """Perform OCR using Google Cloud Vision API (high accuracy, pay-per-use)."""
    try:
        from google.cloud import vision
        from google.oauth2 import service_account
        from core.config import VISION_CREDENTIALS_FILE
        import json

        client = None

        # 1. 環境変数からJSON直接読み込み（HuggingFace Secrets用）
        service_account_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        if service_account_json:
            try:
                credentials_info = json.loads(service_account_json)
                credentials = service_account.Credentials.from_service_account_info(credentials_info)
                client = vision.ImageAnnotatorClient(credentials=credentials)
            except Exception as e:
                print(f"Failed to use GOOGLE_SERVICE_ACCOUNT_JSON: {e}")

        # 2. GOOGLE_APPLICATION_CREDENTIALS環境変数
        if not client and os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            client = vision.ImageAnnotatorClient()

        # 3. ローカルファイル
        if not client and os.path.exists(VISION_CREDENTIALS_FILE):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = VISION_CREDENTIALS_FILE
            client = vision.ImageAnnotatorClient()

        if not client:
            raise HTTPException(
                status_code=500,
                detail="Google Vision API認証情報が設定されていません。HuggingFace SecretsにGOOGLE_SERVICE_ACCOUNT_JSONを設定してください。"
            )
        image = vision.Image(content=image_bytes)

        # Use document_text_detection for better Japanese text recognition
        response = client.document_text_detection(
            image=image,
            image_context=vision.ImageContext(
                language_hints=['ja', 'en']
            )
        )

        if response.error.message:
            raise HTTPException(
                status_code=500,
                detail=f"Google Vision API error: {response.error.message}"
            )

        # API使用量をカウント
        from core import database
        try:
            usage = database.increment_api_usage("cloud-vision")
            print(f"Cloud Vision API usage incremented: {usage}")
        except Exception as e:
            print(f"Failed to increment API usage: {e}")

        # Get full text annotation
        if response.full_text_annotation:
            return response.full_text_annotation.text

        # Fallback to text_annotations
        if response.text_annotations:
            return response.text_annotations[0].description

        return ""
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="google-cloud-vision is not installed. Run: pip install google-cloud-vision"
        )
    except Exception as e:
        error_msg = str(e)
        if "Could not automatically determine credentials" in error_msg:
            raise HTTPException(
                status_code=500,
                detail="Google Cloud credentials not found. Set GOOGLE_APPLICATION_CREDENTIALS environment variable."
            )
        raise HTTPException(status_code=500, detail=f"Google Vision API error: {error_msg}")


def get_available_engines() -> list:
    """Get list of available OCR engines (Google Vision only)."""
    engines = []

    # Check Google Cloud Vision
    try:
        from google.cloud import vision
        from core.config import VISION_CREDENTIALS_FILE
        # Check if credentials are available (env var or local file)
        creds_available = (
            os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") is not None or
            os.path.exists(VISION_CREDENTIALS_FILE)
        )
        engines.append({
            "id": "google-vision",
            "name": "Google Vision",
            "description": "高精度クラウドOCR" if creds_available else "認証設定が必要",
            "available": creds_available
        })
    except:
        engines.append({
            "id": "google-vision",
            "name": "Google Vision",
            "description": "未インストール（pip install google-cloud-vision）",
            "available": False
        })

    return engines
