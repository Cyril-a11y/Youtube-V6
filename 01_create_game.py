# 01_create_game.py
import os
import json
import requests
import chess
from pathlib import Path
from datetime import datetime, timezone

# --- Chargement des variables d'environnement ---
HUMAN_TOKEN = os.getenv("LICHESS_HUMAN_TOKEN")
BOT_TOKEN = os.getenv("LICHESS_BOT_TOKEN")
BOT_USERNAME = os.getenv("LICHESS_BOT_USERNAME")
COLOR = "white"  # "white" | "black" | "random"

# --- Vérification des secrets ---
missing = []
if not HUMAN_TOKEN:
    missing.append("LICHESS_HUMAN_TOKEN")
if not BOT_TOKEN:
    missing.append("LICHESS_BOT_TOKEN")
if not BOT_USERNAME:
    missing.append("LICHESS_BOT_USERNAME")

if missing:
    raise SystemExit(f"❌ Secrets manquants : {', '.join(missing)}")

# --- Headers API ---
H_HUMAN = {"Authorization": f"Bearer {HUMAN_TOKEN}"}
H_BOT = {"Authorization": f"Bearer {BOT_TOKEN}"}

# --- Fichiers locaux ---
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
GAME_ID_FILE = DATA_DIR / "game_id.txt"
POSITION_FILE = DATA_DIR / "position.fen"
LAST_MOVE_FILE = DATA_DIR / "dernier_coup.json"
COUP_BLANCS_FILE = DATA_DIR / "coup_blanc.txt"


def creer_defi_correspondance():
    """
    Crée un défi en mode correspondance (14 jours max par coup).
    Avec les bots, c'est l'option la plus proche d'un temps illimité.
    """
    url = f"https://lichess.org/api/challenge/{BOT_USERNAME}"
    data = {
        "rated": "false",
        "color": COLOR,
        "variant": "standard",
        "days": 14
    }
    print(f"📡 Envoi du défi au bot {BOT_USERNAME}...")
    r = requests.post(url, headers=H_HUMAN, data=data, timeout=30)
    if r.status_code != 200:
        print("⚠️ Réponse brute de Lichess:", r.text)
        raise SystemExit(f"❌ Création défi KO: {r.status_code}")
    js = r.json()
    return js.get("challenge", {}).get("id", js.get("id"))


def accepter_defi_bot(challenge_id):
    """Accepte le défi côté bot."""
    url = f"https://lichess.org/api/challenge/{challenge_id}/accept"
    print("🤖 Bot accepte le défi...")
    r = requests.post(url, headers=H_BOT, timeout=30)
    if r.status_code != 200:
        print("⚠️ Réponse brute de Lichess:", r.text)
        raise SystemExit(f"❌ Acceptation KO: {r.status_code}")
    print("✅ Bot a accepté le défi.")


if __name__ == "__main__":
    # Affichage info bot (optionnel)
    try:
        who_bot = requests.get("https://lichess.org/api/account", headers=H_BOT, timeout=30).json()
        print(f"🤖 BOT détecté : {who_bot.get('username')} (titre: {who_bot.get('title')})")
    except Exception as e:
        print("⚠️ Impossible de récupérer les infos du bot:", e)

    # Création + acceptation du défi
    cid = creer_defi_correspondance()
    print(f"🎯 Défi créé avec ID: {cid}")

    accepter_defi_bot(cid)
    print(f"🎯 Partie prête : https://lichess.org/{cid}")

    # Sauvegardes locales initiales
    starting_fen = chess.STARTING_FEN
    GAME_ID_FILE.write_text(cid, encoding="utf-8")
    POSITION_FILE.write_text(starting_fen, encoding="utf-8")
    COUP_BLANCS_FILE.write_text("", encoding="utf-8")
    LAST_MOVE_FILE.write_text(
        json.dumps(
            {"dernier_coup": None, "fen": starting_fen, "horodatage": datetime.now(timezone.utc).isoformat()},
            ensure_ascii=False, indent=2
        ),
        encoding="utf-8"
    )

    print(f"💾 Données initiales sauvegardées dans {DATA_DIR}")
