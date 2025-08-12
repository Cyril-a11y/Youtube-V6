import os
import json
import requests
from datetime import datetime, timezone
from pathlib import Path

# -----------------------
# Config
# -----------------------
REPO = "Cyril-a11y/Youtube-V6"
BOT_WORKFLOW_FILE = "run-bot.yml"

GH_TOKEN = os.getenv("GH_PAT")  # Token GitHub avec permission workflow
LICHESS_BOT_TOKEN = os.getenv("LICHESS_BOT_TOKEN")

GAME_ID_FILE = Path("data/game_id.txt")
FEN_FILE = Path("data/position.fen")
LAST_MOVE_FILE = Path("data/dernier_coup.json")
MOVE_HISTORY_FILE = Path("data/move_history.json")

def log(msg, type="info"):
    icons = {"ok": "✅", "err": "❌", "warn": "⚠️", "info": "ℹ️", "send": "📤", "save": "💾"}
    print(f"{icons.get(type, '•')} {msg}")

def load_game_id():
    if not GAME_ID_FILE.exists():
        log("game_id.txt introuvable", "err")
        return None
    gid = GAME_ID_FILE.read_text(encoding="utf-8").strip()
    log(f"Game ID chargé : {gid}", "ok")
    return gid

def fetch_current_fen(game_id):
    url = f"https://lichess.org/game/export/{game_id}"
    params = {"fen": "1"}
    headers = {"Authorization": f"Bearer {LICHESS_BOT_TOKEN}", "Accept": "application/json"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
    except Exception as e:
        log(f"Erreur API Lichess : {e}", "err")
        return None
    if r.status_code != 200:
        log(f"Erreur API {r.status_code}: {r.text}", "err")
        return None
    data = r.json()
    return data.get("fen"), data.get("lastMove", None)

def is_black_to_move(fen):
    return fen and fen.split()[1] == "b"

def trigger_bot_workflow():
    """Déclenche le workflow GitHub Actions du bot."""
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{BOT_WORKFLOW_FILE}/dispatches"
    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    payload = {"ref": "main"}
    r = requests.post(url, headers=headers, json=payload)
    if r.status_code == 204:
        log("Workflow bot déclenché avec succès", "ok")
    else:
        log(f"Erreur déclenchement workflow bot: {r.status_code} {r.text}", "err")

def update_data_files(fen, move):
    FEN_FILE.write_text(fen or "", encoding="utf-8")
    payload = {
        "dernier_coup": move,
        "fen": fen,
        "horodatage": datetime.now(timezone.utc).isoformat()
    }
    LAST_MOVE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    history = []
    if MOVE_HISTORY_FILE.exists():
        try:
            history = json.loads(MOVE_HISTORY_FILE.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []
    history.append({
        "couleur": "noir",
        "coup": move,
        "fen_apres": fen,
        "horodatage": datetime.now(timezone.utc).isoformat()
    })
    MOVE_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    log("Fichiers data mis à jour", "save")

if __name__ == "__main__":
    game_id = load_game_id()
    if not game_id:
        raise SystemExit(1)

    fen, last_move = fetch_current_fen(game_id)
    if not fen:
        raise SystemExit(1)

    if not is_black_to_move(fen):
        log("Ce n'est pas aux Noirs de jouer, arrêt.", "info")
        raise SystemExit(0)

    # On déclenche le bot
    trigger_bot_workflow()

    # Petit délai pour qu'il joue
    import time
    log("⏳ Attente que le bot joue...", "wait")
    time.sleep(15)  # Ajuster si nécessaire

    # On relit la position et on met à jour les fichiers
    fen_after, last_move_after = fetch_current_fen(game_id)
    if fen_after and last_move_after != last_move:
        update_data_files(fen_after, last_move_after)
        log("Coup noir joué et fichiers mis à jour.", "ok")
    else:
        log("⚠️ Aucun nouveau coup détecté après passage du bot.", "warn")
