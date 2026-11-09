"""
Laiba Project - Configuration & System Registry
Handles platform permissions, API key integration, UI Pure Black theme,
3D engine parameters, and WhatsApp zip packaging export paths.
"""

import os
import json
import sys

# Default Pure Black Theme and System Configuration
DEFAULT_CONFIG = {
    "APP_NAME": "Laiba Assistant",
    "VERSION": "1.0.0",
    "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", ""),
    "GEMINI_API_KEYS": [],
    "GEMINI_MODEL": "",
    "GEMINI_MODEL_CANDIDATES": [],
    "GEMINI_API_BASE": "https://generativelanguage.googleapis.com/v1beta",
    "GEMINI_TIMEOUT": 30,
    "UPDATE_SERVER_URL": "",  # Configure a real JSON manifest URL before enabling update checks.
    "AUTO_UPDATE_CHECK": True,
    
    # Pure Black UI Theme Palette (#000000 as explicitly required)
    "UI_THEME": {
        "BG_COLOR": "#000000",          # Pure black main background
        "SURFACE_COLOR": "#0D0D0D",     # Deep black card surface
        "ACCENT_COLOR": "#00E5FF",      # Cyber cyan highlight
        "ACCENT_SECONDARY": "#7C4DFF",  # Deep purple highlight
        "TEXT_PRIMARY": "#FFFFFF",      # Pure crisp white text
        "TEXT_SECONDARY": "#A0A0A0",    # Muted readable secondary
        "BORDER_COLOR": "#1F1F1F",      # Subtle dark border
        "SUCCESS_COLOR": "#00E676",     # Terminal green for success
        "DANGER_COLOR": "#FF5252"       # Crimson red for warnings
    },
    
    # 3D Engine Configuration
    "THREE_D_ENGINE": {
        "DEFAULT_MODEL": "Laiba_Core_Cube",
        "SUPPORTED_FORMATS": [".obj", ".stl", ".gltf", ".ply"],
        "AUTO_ROTATE": True,
        "ROTATION_SPEED": 2.0,
        "WIREFRAME_COLOR": "#00E5FF",
        "CANVAS_SIZE": [240, 200]
    },
    
    # WhatsApp Zip Packaging & Distribution
    "WHATSAPP_EXPORT": {
        "EXPORT_DIR": "exports",
        "ZIP_FILENAME": "Laiba_Project_WhatsApp.zip",
        "TARGET_PHONE": "",  # Empty default or international format e.g. "919876543210"
        "DEFAULT_MESSAGE": "Here is the Laiba Project source code package ready for Termux Buildozer APK compilation!"
    },
    
    # Buildozer Termux APK Deployment Profiles
    "BUILDOZER_CONFIG": {
        "TITLE": "Laiba AI Assistant",
        "PACKAGE_NAME": "laibaassistant",
        "PACKAGE_DOMAIN": "com.moeen",
        "SOURCE_INCLUDE_EXTS": "py,png,jpg,kv,atlas,json,spec,txt",
        "ANDROID_PERMISSIONS": "INTERNET,ACCESS_NETWORK_STATE"
    },
    
    # Hardware & System Permissions
    "PERMISSIONS": {
        "MICROPHONE": False,  # No Android speech bridge is included yet.
        "CAMERA": False,  # No Android camera bridge is included yet.
        "ACCESSIBILITY": False,
        "STORAGE": False,
        "SYSTEM_MODIFICATION": False
    },
    
    "APP_SHORTCUTS": {
        "browser": "https://google.com",
        "youtube": "https://youtube.com",
        "calculator": "calc",
        "notepad": "notepad"
    }
}

CONFIG_FILE = "laiba_config.json"

def load_config():
    """Loads configuration with persistent custom overrides."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                merged = {**DEFAULT_CONFIG}
                for k, v in saved.items():
                    if isinstance(v, dict) and k in merged and isinstance(merged[k], dict):
                        merged[k] = {**merged[k], **v}
                    else:
                        merged[k] = v
                return merged
        except Exception as e:
            print(f"[Config] Error loading config file, fallback to default: {e}")
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    """Saves updated runtime configuration to disk."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
        return True
    except Exception as e:
        print(f"[Config] Error saving config: {e}")
        return False

# Global runtime state
CURRENT_CONFIG = load_config()
