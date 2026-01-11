"""Core module for configuration and shared state."""
from .config import load_config, save_config, get_folder_id, DATA_DIR, CONFIG_FILE, CREDENTIALS_FILE, TOKEN_FILE
from .database import (
    processing_progress, reset_progress,
    create_equipment, get_equipment, get_all_equipment,
    update_equipment, delete_equipment, delete_all_equipment
)
