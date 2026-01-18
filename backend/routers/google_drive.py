"""Google Drive integration endpoints."""
import io
from fastapi import APIRouter, Form, HTTPException
from services.google_drive import get_google_drive_service
from services.equipment_parser import process_image_async
from core.config import get_folder_id, CREDENTIALS_FILE, TOKEN_FILE
from core.database import processing_progress
import os

router = APIRouter(prefix="/api/google-drive", tags=["google-drive"])

# 工事看板テンプレート画像のフォルダID
SIGNBOARD_TEMPLATE_FOLDER_ID = "1edOp95pJdcpLrfH9yqAIqlGhE0l73y34"

# 機械銘板画像のフォルダID（複数フォルダ対応）
EQUIPMENT_IMAGE_FOLDER_IDS = [
    "1LvO_2p60nOKQvrQP8Apu2-YfQaj2J959",
    "1njruSQ_bVt6H5H0vWDIiLd2XNxdGJ3PY"
]


@router.get("/folder-info")
async def get_folder_info():
    """Get information about configured folders."""
    return {
        "equipment_folders": EQUIPMENT_IMAGE_FOLDER_IDS,
        "signboard_folder": SIGNBOARD_TEMPLATE_FOLDER_ID,
        "equipment_folder_urls": [
            f"https://drive.google.com/drive/folders/{fid}" for fid in EQUIPMENT_IMAGE_FOLDER_IDS
        ]
    }


@router.get("/status")
async def get_status():
    """Check Google Drive connection status."""
    folder_id = get_folder_id()
    try:
        if not os.path.exists(CREDENTIALS_FILE):
            return {
                "connected": False,
                "message": "credentials.json not found. Please upload credentials.",
                "folder_id": folder_id,
                "has_credentials": False
            }

        if os.path.exists(TOKEN_FILE):
            return {
                "connected": True,
                "message": "Google Drive connected",
                "folder_id": folder_id,
                "has_credentials": True
            }

        return {
            "connected": False,
            "message": "Not authenticated. Click 'Connect Google Drive' to authenticate.",
            "folder_id": folder_id,
            "has_credentials": True
        }
    except Exception as e:
        return {
            "connected": False,
            "message": str(e),
            "folder_id": folder_id,
            "has_credentials": os.path.exists(CREDENTIALS_FILE)
        }


@router.post("/connect")
async def connect():
    """Initiate Google Drive authentication."""
    folder_id = get_folder_id()
    try:
        service = get_google_drive_service()
        results = service.files().list(
            q=f"'{folder_id}' in parents and mimeType contains 'image/'",
            pageSize=1,
            fields="files(id, name)"
        ).execute()
        return {"success": True, "message": "Google Drive connected successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files")
async def list_files():
    """List image files in the configured folder."""
    folder_id = get_folder_id()
    try:
        service = get_google_drive_service()
        results = service.files().list(
            q=f"'{folder_id}' in parents and (mimeType contains 'image/' or mimeType = 'application/pdf')",
            pageSize=100,
            fields="files(id, name, mimeType, createdTime, size)"
        ).execute()
        return {"files": results.get('files', [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/progress")
async def get_progress():
    """Get current processing progress."""
    return processing_progress


@router.post("/process")
async def process_all_files(
    llm_engine: str = Form(default="google-vision-gemini")
):
    """Process all image files from Google Drive folder."""
    from core import database
    folder_id = get_folder_id()

    try:
        service = get_google_drive_service()
        results = service.files().list(
            q=f"'{folder_id}' in parents and mimeType contains 'image/'",
            pageSize=100,
            fields="files(id, name, mimeType)"
        ).execute()

        files = results.get('files', [])
        processed = []
        errors = []

        # Initialize progress
        database.processing_progress = {
            "status": "processing",
            "current": 0,
            "total": len(files),
            "current_file": "",
            "errors": []
        }

        for i, file in enumerate(files):
            database.processing_progress["current"] = i + 1
            database.processing_progress["current_file"] = file['name']

            try:
                from googleapiclient.http import MediaIoBaseDownload
                request = service.files().get_media(fileId=file['id'])
                file_buffer = io.BytesIO()
                downloader = MediaIoBaseDownload(file_buffer, request)

                done = False
                while not done:
                    status, done = downloader.next_chunk()

                image_bytes = file_buffer.getvalue()
                equipment = await process_image_async(image_bytes, file['name'], llm_engine)
                processed.append(equipment)

            except Exception as e:
                error_info = {"file": file['name'], "error": str(e)}
                errors.append(error_info)
                database.processing_progress["errors"].append(error_info)

        database.processing_progress["status"] = "complete"
        database.processing_progress["current_file"] = ""

        return {
            "success": True,
            "processed_count": len(processed),
            "equipment": processed,
            "errors": errors
        }
    except Exception as e:
        database.processing_progress["status"] = "error"
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process/{file_id}")
async def process_single_file(
    file_id: str,
    llm_engine: str = Form(default="google-vision-gemini")
):
    """Process a single file from Google Drive."""
    try:
        service = get_google_drive_service()
        from googleapiclient.http import MediaIoBaseDownload

        file_metadata = service.files().get(fileId=file_id, fields="name, mimeType").execute()

        request = service.files().get_media(fileId=file_id)
        file_buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(file_buffer, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        image_bytes = file_buffer.getvalue()
        equipment = await process_image_async(image_bytes, file_metadata['name'], llm_engine)

        return {"success": True, "equipment": equipment}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signboard-templates")
async def list_signboard_templates():
    """List signboard template images from Google Drive."""
    try:
        service = get_google_drive_service()
        results = service.files().list(
            q=f"'{SIGNBOARD_TEMPLATE_FOLDER_ID}' in parents and mimeType contains 'image/'",
            pageSize=100,
            fields="files(id, name, mimeType, thumbnailLink, webContentLink)"
        ).execute()

        files = results.get('files', [])
        # サムネイルURLを生成
        for f in files:
            f['thumbnail_url'] = f'/api/google-drive/image/{f["id"]}/thumbnail'
            f['image_url'] = f'/api/google-drive/image/{f["id"]}'

        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/image/{file_id}")
async def get_image(file_id: str):
    """Get image content from Google Drive."""
    from fastapi.responses import Response
    try:
        service = get_google_drive_service()
        from googleapiclient.http import MediaIoBaseDownload

        file_metadata = service.files().get(fileId=file_id, fields="name, mimeType").execute()

        request = service.files().get_media(fileId=file_id)
        file_buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(file_buffer, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        image_bytes = file_buffer.getvalue()
        return Response(content=image_bytes, media_type=file_metadata.get('mimeType', 'image/jpeg'))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/image/{file_id}/thumbnail")
async def get_image_thumbnail(file_id: str):
    """Get image thumbnail from Google Drive."""
    from fastapi.responses import Response
    from PIL import Image
    try:
        service = get_google_drive_service()
        from googleapiclient.http import MediaIoBaseDownload

        request = service.files().get_media(fileId=file_id)
        file_buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(file_buffer, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        # サムネイル生成
        file_buffer.seek(0)
        img = Image.open(file_buffer)
        img.thumbnail((150, 150))

        output = io.BytesIO()
        img.save(output, format='JPEG', quality=80)
        output.seek(0)

        return Response(content=output.getvalue(), media_type='image/jpeg')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/equipment-images")
async def list_equipment_images():
    """List equipment nameplate images from Google Drive folders."""
    try:
        service = get_google_drive_service()
        all_files = []

        for folder_id in EQUIPMENT_IMAGE_FOLDER_IDS:
            try:
                results = service.files().list(
                    q=f"'{folder_id}' in parents and mimeType contains 'image/'",
                    pageSize=100,
                    fields="files(id, name, mimeType, createdTime, size)"
                ).execute()
                files = results.get('files', [])
                # サムネイルURLを追加
                for f in files:
                    f['thumbnail_url'] = f'/api/google-drive/image/{f["id"]}/thumbnail'
                    f['image_url'] = f'/api/google-drive/image/{f["id"]}'
                    f['folder_id'] = folder_id
                all_files.extend(files)
            except Exception as e:
                # フォルダアクセスエラーは無視して続行
                pass

        return {"files": all_files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/equipment-images/process-all")
async def process_all_equipment_images(
    llm_engine: str = Form(default="google-vision-gemini")
):
    """Process all equipment images from Google Drive folders."""
    from core import database
    from googleapiclient.http import MediaIoBaseDownload

    try:
        service = get_google_drive_service()
        all_files = []

        # 全フォルダからファイルを収集
        for folder_id in EQUIPMENT_IMAGE_FOLDER_IDS:
            try:
                results = service.files().list(
                    q=f"'{folder_id}' in parents and mimeType contains 'image/'",
                    pageSize=100,
                    fields="files(id, name, mimeType)"
                ).execute()
                all_files.extend(results.get('files', []))
            except Exception:
                pass

        processed = []
        errors = []

        # プログレス初期化
        database.processing_progress = {
            "status": "processing",
            "current": 0,
            "total": len(all_files),
            "current_file": "",
            "errors": []
        }

        for i, file in enumerate(all_files):
            database.processing_progress["current"] = i + 1
            database.processing_progress["current_file"] = file['name']

            try:
                request = service.files().get_media(fileId=file['id'])
                file_buffer = io.BytesIO()
                downloader = MediaIoBaseDownload(file_buffer, request)

                done = False
                while not done:
                    status, done = downloader.next_chunk()

                image_bytes = file_buffer.getvalue()
                equipment = await process_image_async(image_bytes, file['name'], llm_engine)
                processed.append(equipment)

            except Exception as e:
                error_info = {"file": file['name'], "error": str(e)}
                errors.append(error_info)
                database.processing_progress["errors"].append(error_info)

        database.processing_progress["status"] = "complete"
        database.processing_progress["current_file"] = ""

        return {
            "success": True,
            "processed_count": len(processed),
            "equipment": processed,
            "errors": errors
        }
    except Exception as e:
        database.processing_progress["status"] = "error"
        raise HTTPException(status_code=500, detail=str(e))
