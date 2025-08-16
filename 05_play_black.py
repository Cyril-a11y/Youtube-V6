# 05_play_black.py — version robuste avec account/playing (sans game_id)

import os
import requests
from pathlib import Path

# ----- Config -----
REPO = "Cyril-a11y/Youtube-V6"
WORKFLOW_FILENAME = "run_bot.yml"
GITHUB_TOKEN = os.getenv("GH_WORKFLOW_TOKEN")
LICHESS_BOT_TOKEN = os.getenv("LICHESS_BOT_TOKEN")
BOT_ELO_FILE = Path("data/bot_elo.txt")

def log(msg, tag="ℹ️"):
    print(f"{tag} {msg}")

def get_current_game_bot():
    """Trouve la partie en cours du bot via /api/account/playing"""
    if not LICHESS_BOT_TOKEN:
        log("LICHESS_BOT_TOKEN manquant", "❌")
        return None

    url = "https://lichess.org/api/account/playing"
    headers = {"Authorization": f"Bearer {LICHESS_BOT_TOKEN}"}
    r = requests.get(url, headers=headers, timeout=10)
    if r.status_code != 200:
        log(f"Erreur API account/playing : {r.status_code} {r.text[:200]}", "❌")
        return None

    data = r.json()
    games = data.get("nowPlaying", [])
    if not games:
        log("⚠️ Aucune partie en cours trouvée pour le bot.")
        return None

    for g in games:
        log(f"🎯 Partie détectée: {g.get('gameId')} | trait: {g.get('fen')} | isMyTurn={g.get('isMyTurn')} | couleur={g.get('color')}")
        if g.get("isMyTurn") and g.get("color") == "black":
            return {
                "fen": g["fen"]
            }

    log("⚠️ Aucune partie où c'est au bot (noirs) de jouer.")
    return None

def _gh_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def trigger_bot_workflow(elo: str = "1500"):
    if not GITHUB_TOKEN:
        log("Pas de GH_WORKFLOW_TOKEN défini.", "❌")
        return False
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW_FILENAME}/dispatches"
    payload = {"ref": "main", "inputs": {"elo": elo}}
    r = requests.post(url, headers=_gh_headers(), json=payload, timeout=20)
    if r.status_code == 204:
        log(f"✅ Workflow bot déclenché avec Elo={elo}.")
        return True
    log(f"Erreur dispatch ({r.status_code}): {r.text}", "❌")
    return False

# -----------------------
# Main
# -----------------------
if __name__ == "__main__":
    game_info = get_current_game_bot()
    if not game_info:
        raise SystemExit(0)  # Pas de partie à jouer

    fen = game_info["fen"]
    log(f"FEN serveur : {fen}")

    if " b " not in fen:
        log("ℹ️ Ce n'est pas aux Noirs de jouer — arrêt.")
        raise SystemExit(0)

    # Lire Elo depuis le fichier bot_elo.txt (sinon fallback 1500)
    try:
        BOT_ELO = BOT_ELO_FILE.read_text(encoding="utf-8").strip()
        if not BOT_ELO.isdigit():
            BOT_ELO = "1500"
    except Exception:
        BOT_ELO = "1500"

    log(f"Elo actuel choisi : {BOT_ELO}")
    trigger_bot_workflow(elo=BOT_ELO)
