# 05_play_black.py — version "account/playing" fiable

import os
import requests

# ----- Config -----
REPO = "Cyril-a11y/Youtube-V6"
WORKFLOW_FILENAME = "run_bot.yml"
GITHUB_TOKEN = os.getenv("GH_WORKFLOW_TOKEN")
LICHESS_BOT_TOKEN = os.getenv("LICHESS_BOT_TOKEN")

def log(msg, tag="ℹ️"):
    print(f"{tag} {msg}")

def get_current_game_bot():
    """Trouve la partie en cours du bot via /api/account/playing"""
    if not LICHESS_BOT_TOKEN:
        log("❌ LICHESS_BOT_TOKEN manquant", "❌")
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
        if g.get("isMyTurn") and g.get("color") == "black":
            return {
                "game_id": g["gameId"],
                "fen": g["fen"]
            }

    log("⚠️ Aucune partie où c'est au bot (noirs) de jouer.")
    return None

def is_black_to_move(fen: str) -> bool:
    try:
        return fen.split()[1] == "b"
    except Exception:
        return False

def _gh_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def trigger_bot_workflow(game_id: str, elo: str = "1500"):
    if not GITHUB_TOKEN:
        log("❌ Pas de GH_WORKFLOW_TOKEN défini.", "❌")
        return False
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW_FILENAME}/dispatches"
    payload = {"ref": "main", "inputs": {"game_id": game_id, "elo": elo}}
    r = requests.post(url, headers=_gh_headers(), json=payload, timeout=20)
    if r.status_code == 204:
        log("✅ Workflow bot déclenché.")
        return True
    log(f"❌ Erreur dispatch ({r.status_code}): {r.text}")
    return False

# -----------------------
# Main
# -----------------------
if __name__ == "__main__":
    game_info = get_current_game_bot()
    if not game_info:
        raise SystemExit(0)  # Pas de partie à jouer

    game_id = game_info["game_id"]
    fen = game_info["fen"]

    log(f"Game ID détecté : {game_id}")
    log(f"Trait actuel : {'noirs' if is_black_to_move(fen) else 'blancs'}")

    if not is_black_to_move(fen):
        log("ℹ️ Ce n'est pas aux Noirs de jouer — arrêt.")
        raise SystemExit(0)

    trigger_bot_workflow(game_id, elo="1500")
