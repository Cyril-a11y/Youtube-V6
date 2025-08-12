import os
import requests
import json
import re
import unicodedata
import chess
import chess.pgn
import io
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# -----------------------
# Configuration via secrets GitHub Actions
# -----------------------
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_VIDEO_ID = os.getenv("YOUTUBE_VIDEO_ID")
LICHESS_HUMAN_TOKEN = os.getenv("LICHESS_HUMAN_TOKEN")
LAST_MOVE_FILE = "data/dernier_coup.json"
GAME_ID_FILE = "data/game_id.txt"
COUP_BLANCS_FILE = Path("data/coup_blanc.txt")

# Vérification des secrets
missing = []
for var in ["YOUTUBE_API_KEY", "YOUTUBE_VIDEO_ID", "LICHESS_HUMAN_TOKEN"]:
    if not globals()[var]:
        missing.append(var)
if missing:
    raise SystemExit(f"❌ Secrets manquants : {', '.join(missing)}")

# -----------------------
# Utilitaires
# -----------------------
def log(msg, type="info"):
    icons = {"ok": "✅", "err": "❌", "warn": "⚠️", "info": "ℹ️", "find": "🔎", "save": "💾"}
    print(f"{icons.get(type, '•')} {msg}")

def load_game_id():
    try:
        gid = Path(GAME_ID_FILE).read_text(encoding="utf-8").strip()
        log(f"Game ID chargé : {gid}", "ok")
        return gid
    except FileNotFoundError:
        log("game_id.txt introuvable. Lance 01_create_game.py d'abord.", "err")
        return None

def charger_horodatage_dernier_coup():
    try:
        with open(LAST_MOVE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        ts = data.get("horodatage")
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        elif isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            dt = datetime(1970, 1, 1, tzinfo=timezone.utc)
        log(f"Date dernier coup : {dt}", "ok")
        return dt
    except FileNotFoundError:
        log("Aucun fichier dernier_coup.json trouvé, création par défaut…", "warn")
        Path(LAST_MOVE_FILE).parent.mkdir(parents=True, exist_ok=True)
        data = {"horodatage": datetime(1970, 1, 1, tzinfo=timezone.utc).isoformat()}
        Path(LAST_MOVE_FILE).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    except Exception as e:
        log(f"Timestamp illisible ({e}), utilisation d'une date par défaut.", "warn")
        return datetime(1970, 1, 1, tzinfo=timezone.utc)

def recuperer_commentaires(video_id, max_results=100, apres=None):
    commentaires = []
    url = "https://www.googleapis.com/youtube/v3/commentThreads"
    params = {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": max_results,
        "order": "time",
        "key": YOUTUBE_API_KEY
    }
    nb = 0
    while True:
        try:
            r = requests.get(url, params=params, timeout=30)
        except Exception as e:
            log(f"Erreur réseau API YouTube : {e}", "err")
            break
        if r.status_code != 200:
            log(f"Erreur
