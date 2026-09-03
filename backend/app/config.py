import os
from pathlib import Path

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/tmp/music_story_video_ai_uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MODES = [
    "musique_clip",
    "paroles_images",
    "paroles_musique_film",
    "image_musique_clip",
]
