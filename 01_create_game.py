# 01_create_game.py
import os
import time
import json
import requests
import chess
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

# Chargement des variables depuis .env
load_dotenv()

# --- Config ---
HUMAN_TOKEN = os.getenv("LICHESS_HUMAN_TOKEN")
BOT_TOKEN = os.getenv("LICHESS_BOT_TOKEN")
BOT_USERNAME = os.getenv("LICHESS_BOT_USERNAME", "PriseEnPassantBot")
COLOR = "white"  # "white" | "black" | "random"

if not HUMAN_TOKEN:
    raise SystemExit("LICHESS_HUMAN_TOKEN manquant dans .env")
if not BOT_TOKEN:
    raise SystemExit("LICHESS_BOT_TOKEN manquant dans .env")

H_HUMAN = {"Authorization": f"Bearer {HUMAN_TOKEN}"}
H_BOT = {"Authorization": f"Bearer {BOT_TOKEN}"}

# --- Fichiers ---
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
GAME_ID_FILE = DATA_DIR / "game_id.txt"
POSITION_FILE = DATA_DIR / "position.fen"
LAST_MOVE_FILE = DATA_DIR / "dernier_coup.json"
COUP_BLANCS_FILE = DATA_DIR / "coup_blanc.txt"

def creer_defi_illimite():
    """Crée un défi sans limite de temps / correspondance."""
    url = f"https://lichess.org/api/challenge/{BOT_USERNAME}"
    data = {
        "rated": "false",
        "color": COLOR,
        "variant": "standard",
        "days": 14  # Mode correspondance
    }
    r = requests.post(url, headers=H_HUMAN, data=data, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"Création défi KO: {r.status_code} {r.text}")
    js = r.json()
    if "challenge" in js and "id" in js["challenge"]:
        return js["challenge"]["id"]
    return js.get("id")

def accepter_defi_bot(challenge_id):
    url = f"https://lichess.org/api/challenge/{challenge_id}/accept"
    r = requests.post(url, headers=H_BOT, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"Acceptation KO: {r.status_code} {r.text}")
    print("Bot a accepté le défi.")

def recuperer_fen_initiale(game_id, timeout=15, delay=2):
    """
    Attend que la partie soit démarrée et récupère la FEN initiale.
    Timeout total = timeout secondes.
    """
    url = f"https://lichess.org/game/export/{game_id}?moves=0&fen=1"
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = requests.get(url, headers=H_HUMAN, timeout=30)
        if r.status_code == 200:
            try:
                data = r.json()
                fen = data.get("fen")
                if fen and fen.strip():
                    print(f"✅ FEN récupérée : {fen}")
                    return fen
            except Exception as e:
                print(f"⚠️ Erreur parsing JSON : {e}")
        print("⏳ FEN non encore dispo, nouvelle tentative…")
        time.sleep(delay)

    print("⚠️ FEN introuvable après attente, utilisation position standard.")
    return chess.STARTING_FEN

if __name__ == "__main__":
    # (Optionnel) info bot
    try:
        who_bot = requests.get("https://lichess.org/api/account", headers=H_BOT, timeout=30).json()
        print("BOT:", who_bot.get("username"), "title:", who_bot.get("title"))
    except Exception:
        pass

    cid = creer_defi_illimite()
    print(f"Défi créé: {cid}")

    accepter_defi_bot(cid)
    print(f"Partie prête: https://lichess.org/{cid}")

    # 💾 Sauvegardes locales initiales
    GAME_ID_FILE.write_text(cid, encoding="utf-8")

    # Récupération FEN réelle ou fallback
    fen_initiale = recuperer_fen_initiale(cid)
    POSITION_FILE.write_text(fen_initiale, encoding="utf-8")

    # Réinitialisation coup_blanc.txt
    COUP_BLANCS_FILE.write_text("", encoding="utf-8")

    # Dernier coup : rien encore, mais horodatage "maintenant"
    now_iso = datetime.now(timezone.utc).isoformat()
    LAST_MOVE_FILE.write_text(
        json.dumps({"dernier_coup": None, "fen": fen_initiale, "horodatage": now_iso}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"ID sauvegardé dans {GAME_ID_FILE}")
    print(f"FEN initiale sauvegardée dans {POSITION_FILE}")
    print(f"coup_blanc.txt vidé")
    print(f"dernier_coup.json initialisé avec date et FEN")
