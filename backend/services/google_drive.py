"""Google Drive integration service."""
import os
import json
from fastapi import HTTPException
from core.config import CREDENTIALS_FILE, TOKEN_FILE


def get_google_drive_service():
    """Get authenticated Google Drive service."""
    from googleapiclient.discovery import build

    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

    # 1. サービスアカウント（環境変数）を優先
    service_account_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if service_account_json:
        from google.oauth2 import service_account
        try:
            service_account_info = json.loads(service_account_json)
            creds = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=SCOPES
            )
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Service account authentication failed: {str(e)}"
            )

    # 2. ローカル環境用：OAuth認証（従来の方式）
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise HTTPException(
                    status_code=500,
                    detail="Google Drive not configured. Set GOOGLE_SERVICE_ACCOUNT_JSON or credentials.json"
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=8080)

        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return build('drive', 'v3', credentials=creds)
