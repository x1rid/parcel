import os
import sys
import json
from pathlib import Path

# Resolve base dir next to the app
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_DIR = os.path.join(BASE_DIR, "config")
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")

class SettingsManager:
    def __init__(self):
        default_watch_folders = [
            str(Path.home() / "Videos"),
            str(Path.home() / "Downloads"),
            str(Path.home() / "Documents")
        ]
        self.settings = {
            "target_size_mb": "25",
            "encoder": "NVIDIA NVENC",
            "codec": "H264",
            "resolution": "Original",
            "fps": "Original",
            "quality": "Balanced",
            "audio_bitrate": "128",
            "output_format": "MP4",
            "output_mode": "Same Folder",
            "custom_output_folder": "",
            "naming_pattern": "{name}_compressed",
            "ffmpeg_path": "",
            "ffprobe_path": "",
            "recent_sort_mode": "Date",
            "watch_folders": default_watch_folders,
            "preview_quality": "1/2",
            "auto_open": True,
            "verify_output": True,
            "always_on_top": False
        }
        self.load()

    def load(self):
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR)
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    loaded = json.load(f)
                    # Remove deprecated keys
                    loaded.pop("recent_folders_1", None)
                    loaded.pop("recent_folders_2", None)
                    self.settings.update(loaded)
            except Exception as e:
                print(f"Error loading settings: {e}")

    def save(self):
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR)
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def get(self, key, default=None):
        return self.settings.get(key, default)
        
    def get_list(self, key, default=None) -> list:
        val = self.get(key, default)
        if isinstance(val, list):
            return val
        return default if default is not None else []

    def set(self, key, value):
        self.settings[key] = value
        self.save()

    def get_watch_folders(self) -> list[str]:
        return self.get_list("watch_folders", [])

    def add_watch_folder(self, path: str):
        folders = self.get_watch_folders()
        if path not in folders:
            folders.append(path)
            self.set("watch_folders", folders)

    def remove_watch_folder(self, path: str):
        folders = self.get_watch_folders()
        if path in folders:
            folders.remove(path)
            self.set("watch_folders", folders)
