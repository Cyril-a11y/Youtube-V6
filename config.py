import os
from pathlib import Path

# --- Création du dossier data ---
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# Lichess
LICHESS_HUMAN_TOKEN = os.getenv("LICHESS_HUMAN_TOKEN")
LICHESS_BOT_TOKEN = os.getenv("LICHESS_BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")

# YouTube API
YOUTUBE_CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_VIDEO_ID = os.getenv("YOUTUBE_VIDEO_ID")

# OAuth 2.0
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")

# Fichiers de données
GAME_ID_FILE = DATA_DIR / "game_id.txt"
POSITION_FILE = DATA_DIR / "position.fen"
LAST_MOVE_FILE = DATA_DIR / "dernier_coup.json"
COUP_BLANCS_FILE = DATA_DIR / "coup_blanc.txt"

# Alias pour compatibilité
FEN_FILE = POSITION_FILE
