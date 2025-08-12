# 05_play_black.py — version robuste avec reconstruction FEN depuis PGN

import os
import json
import time
import requests
import io
import chess.pgn
from pathlib import Path
from datetime import datetime, timezone

# ----- Config / chemins
REPO = "Cyril-a11y/Youtube-V6"             # <-- adapte si besoin
BOT_WORKFLOW_FILE = "run-lichess-bot.yml"  # nom exact du fichier .yml du bot
GITHUB_TOKEN = os.getenv("GH_WORKFLOW_TOKEN")  # On force le secret perso

LICHESS_BOT_TOKEN = os.getenv("LICHESS_BOT_TOKEN")
GAME_ID_FILE      = Path("data/game_id.txt")
FEN_FILE          = Path("data/position.fen")
LAST_MOVE_FILE    = Path("data/dernier_coup.json")
MOVE_HISTORY_FILE = Path("data/move_history.json")

def log(msg, tag="ℹ️"):
    print(f"{tag} {msg}")

# ----- Helpers
def load_game_id():
    if not GAME_ID_FILE.exists():
        log("game_id.txt introuvable", "❌")
        return None
    gid = GAME_ID_FILE.read_text(encoding="utf-8").strip()
    log(f"Game ID chargé : {gid}", "✅")
    return gid

def fetch_game_state(game_id):
    """Retourne (fen, moves_str) en se basant sur la FEN ou en la reconstruisant via le PGN."""
    url = f"https://lichess.org/game/export/{game_id}"
    params = {"fen": "1", "moves": "1", "pgn": "1"}
    headers = {"Authorization": f"Bearer {LICHESS_BOT_TOKEN}", "Accept": "application/json"}
    log(f"📤 GET {url}?fen=1&moves=1&pgn=1")
    r = requests.get(url, params=params, headers=headers, timeout=20)
    log(f"📥 HTTP {r.status_code}")
    if r.status_code != 200:
        log(f"Réponse: {r.text[:300]}", "❌")
        return None, None

    try:
        data = r.json()
    except Exception as e:
        log(f"JSON invalide: {e}", "❌")
        return None, None

    fen = data.get("fen")
    moves_str = data.get("moves") or ""

    # Si Lichess ne renvoie pas la FEN, on la reconstruit depuis le PGN
    if not fen and "pgn" in data:
        try:
            pgn_io = io.StringIO(data["pgn"])
            game = chess.pgn.read_game(pgn_io)
            board = game.board()
            for move in game.mainline_moves():
                board.push(move)
            fen = board.fen()
            log("FEN reconstruite depuis le PGN", "🔄")
        except Exception as e:
            log(f"Impossible de reconstruire la FEN depuis le PGN: {e}", "❌")
            return None, None

    log(f"FEN: {fen}")
    log(f"Moves (taille): {len(moves_str.split())}")
    return fen, moves_str

def is_black_to_move(fen: str) -> bool:
    try:
        return fen.split()[1] == "b"
    except Exception:
        return False

def trigger_bot_workflow():
    """Déclenche le workflow bot via API GitHub."""
    if not GITHUB_TOKEN:
        log("Pas de GH_WORKFLOW_TOKEN défini dans les secrets GitHub.", "❌")
        return False
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{BOT_WORKFLOW_FILE}/dispatches"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    payload = {"ref": "main"}
    log(f"🚀 Dispatch workflow: {BOT_WORKFLOW_FILE} sur main")
    r = requests.post(url, headers=headers, json=payload, timeout=20)
    if r.status_code == 204:
        log("Workflow bot déclenché.", "✅")
        return True
    log(f"Échec dispatch ({r.status_code}): {r.text}", "❌")
    return False

def update_files_after_black(move_san_or_uci: str, fen: str):
    FEN_FILE.write_text(fen or "", encoding="utf-8")
    LAST_MOVE_FILE.write_text(
        json.dumps({
            "dernier_coup": move_san_or_uci,
            "fen": fen,
            "horodatage": datetime.now(timezone.utc).isoformat()
        }, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
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
        "coup": move_san_or_uci,
        "fen_apres": fen,
        "horodatage": datetime.now(timezone.utc).isoformat()
    })
    MOVE_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    log("💾 position.fen, dernier_coup.json, move_history.json mis à jour", "✅")

def last_token(moves_str: str) -> str | None:
    toks = (moves_str or "").split()
    return toks[-1] if toks else None

# ----- Main
if __name__ == "__main__":
    if not LICHESS_BOT_TOKEN:
        log("LICHESS_BOT_TOKEN manquant.", "❌")
        raise SystemExit(1)

    gid = load_game_id()
    if not gid:
        raise SystemExit(1)

    fen_before, moves_before = fetch_game_state(gid)
    if not fen_before:
        raise SystemExit(1)

    log(f"Trait initial: {'noirs' if is_black_to_move(fen_before) else 'blancs'}")

    if not is_black_to_move(fen_before):
        log("Ce n'est pas aux Noirs de jouer — arrêt propre.", "ℹ️")
        raise SystemExit(0)

    if not trigger_bot_workflow():
        raise SystemExit(0)

    for i in range(10):  # ~ 10 * 3s = 30s max
        time.sleep(3)
        fen_after, moves_after = fetch_game_state(gid)
        if not fen_after:
            continue
        if moves_after != moves_before:
            coup = last_token(moves_after) or "unknown"
            log(f"Nouveau coup détecté: {coup}")
            update_files_after_black(coup, fen_after)
            break
        else:
            log("Pas encore de nouveau coup… on réessaie.", "⏳")
    else:
        log("⚠️ Le bot n'a pas joué dans le délai imparti. Vérifie le workflow du bot.", "⚠️")
