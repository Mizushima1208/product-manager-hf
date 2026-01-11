"""Configuration management."""
import os
import json

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
CREDENTIALS_FILE = os.path.join(DATA_DIR, "credentials.json")
TOKEN_FILE = os.path.join(DATA_DIR, "token.json")
VISION_CREDENTIALS_FILE = os.path.join(DATA_DIR, "vision_credentials.json")

DEFAULT_CONFIG = {
    "google_drive_folder_id": "1x1tU_QrwiyXCKr10sWWf7Ej99BYsWLah"
}


def load_config() -> dict:
    """Load configuration from file."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    """Save configuration to file."""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_folder_id() -> str:
    """Get the current Google Drive folder ID."""
    config = load_config()
    return config.get("google_drive_folder_id", DEFAULT_CONFIG["google_drive_folder_id"])
