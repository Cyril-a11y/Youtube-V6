# 05_play_black.py — déclenchement du workflow

import os
import requests
import io
import chess.pgn
from pathlib import Path

# ----- Config -----
REPO = "Cyril-a11y/Youtube-V6"
WORKFLOW_FILENAME = "run_bot.yml"
GITHUB_TOKEN = os.getenv("GH_WORKFLOW_TOKEN")
LICHESS_BOT_TOKEN = os.getenv("LICHESS_BOT_TOKEN")
GAME_ID_FILE = Path("data/game_id.txt")

def log(msg, tag="ℹ️"):
    print(f"{tag} {msg}")

def load_game_id():
    if not GAME_ID_FILE.exists():
        log("game_id.txt introuvable", "❌")
        return None
    gid = GAME_ID_FILE.read_text(encoding="utf-8").strip()
    log(f"✅ Game ID chargé : {gid}")
    return gid

def fetch_fen_from_pgn(game_id):
    url = f"https://lichess.org/game/export/{game_id}"
    params = {"pgn": "1"}
    headers = {"Authorization": f"Bearer {LICHESS_BOT_TOKEN}"} if LICHESS_BOT_TOKEN else {}
    log(f"📤 GET {url}?pgn=1")
    r = requests.get(url, params=params, headers=headers, timeout=20)
    if r.status_code != 200:
        log(f"❌ Erreur {r.status_code}: {r.text[:200]}")
        return None
    pgn_io = io.StringIO(r.text.strip())
    game = chess.pgn.read_game(pgn_io)
    board = game.board()
    for move in game.mainline_moves():
        board.push(move)
    return board.fen()

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
        log("Pas de GH_WORKFLOW_TOKEN défini.", "❌")
        return False
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW_FILENAME}/dispatches"
    payload = {"ref": "main", "inputs": {"game_id": game_id, "elo": elo}}
    r = requests.post(url, headers=_gh_headers(), json=payload, timeout=20)
    if r.status_code == 204:
        log("✅ Workflow bot déclenché.")
        return True
    log(f"❌ Erreur dispatch ({r.status_code}): {r.text}")
    return False

if __name__ == "__main__":
    gid = load_game_id()
    if not gid:
        raise SystemExit(1)

    fen = fetch_fen_from_pgn(gid)
    if not fen:
        raise SystemExit(1)

    log(f"Trait actuel: {'noirs' if is_black_to_move(fen) else 'blancs'}")
    if not is_black_to_move(fen):
        log("ℹ️ Ce n'est pas aux Noirs de jouer — arrêt.")
        raise SystemExit(0)

    trigger_bot_workflow(gid, elo="1500")
