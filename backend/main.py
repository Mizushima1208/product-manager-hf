"""Equipment Manager API - Main Entry Point."""
import os
import secrets
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from routers import equipment_router, google_drive_router, config_router, signboards_router, search_router

app = FastAPI(title="Equipment Manager API", version="1.0.0")

# 認証設定
security = HTTPBasic()

# 環境変数から認証情報を取得（デフォルト値は開発用）
AUTH_USERNAME = os.environ.get("AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "mizushima2024")


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Basic認証の検証."""
    correct_username = secrets.compare_digest(credentials.username, AUTH_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, AUTH_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証に失敗しました",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# フロントエンドの静的ファイル配信
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
IMAGES_DIR = FRONTEND_DIR / "images"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(equipment_router)
app.include_router(google_drive_router)
app.include_router(config_router)
app.include_router(signboards_router)
app.include_router(search_router)


@app.get("/")
async def root(username: str = Depends(verify_credentials)):
    """Serve frontend index.html (認証必須)."""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/images/signboards/{filename}")
async def get_signboard_image(filename: str):
    """Serve signboard images."""
    file_path = IMAGES_DIR / "signboards" / filename
    if file_path.exists():
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Image not found")


@app.get("/images/equipment/{filename}")
async def get_equipment_image(filename: str):
    """Serve equipment images."""
    file_path = IMAGES_DIR / "equipment" / filename
    if file_path.exists():
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Image not found")


# 静的ファイル（CSS, JS, Images）をマウント - ルートの後に配置
app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")
app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
