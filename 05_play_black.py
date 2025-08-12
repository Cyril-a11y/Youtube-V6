import os
import json
import requests
import chess
import time
from datetime import datetime, timezone
from pathlib import Path

# -----------------------
# Secrets et chemins
# -----------------------
LICHESS_BOT_TOKEN = os.getenv("LICHESS_BOT_TOKEN")
GAME_ID_FILE = "data/game_id.txt"
LAST_MOVE_FILE = "data/dernier_coup.json"
FEN_FILE = "data/position.fen"

POSITION_BEFORE_FILE = Path("data/position_before_black.json")
MOVE_HISTORY_FILE = Path("data/move_history.json")

# Vérification du secret
if not LICHESS_BOT_TOKEN:
    raise SystemExit("❌ LICHESS_BOT_TOKEN manquant. Définis-le dans les secrets GitHub Actions.")

# -----------------------
# Utilitaires
# -----------------------
def log(msg, type="info"):
    icons = {"ok": "✅", "err": "❌", "warn": "⚠️", "info": "ℹ️", "save": "💾", "send": "📤", "recv": "📥", "wait": "⏳"}
    print(f"{icons.get(type, '•')} {msg}")

def load_game_id():
    try:
        gid = Path(GAME_ID_FILE).read_text(encoding="utf-8").strip()
        log(f"Game ID chargé : {gid}", "ok")
        return gid
    except FileNotFoundError:
        log("game_id.txt introuvable. Lance 01_create_game.py d'abord.", "err")
        return None

def fetch_current_state(game_id):
    url = f"https://lichess.org/game/export/{game_id}"
    params = {"fen": "1", "moves": "1"}
    headers = {"Authorization": f"Bearer {LICHESS_BOT_TOKEN}", "Accept": "application/json"}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=30)
        if r.status_code != 200:
            log(f"Erreur API Lichess : {r.status_code} {r.text[:200]}", "err")
            return None, None, None
        data = r.json()
    except Exception as e:
        log(f"Erreur API Lichess : {e}", "err")
        return None, None, None

    moves_str = (data.get("moves") or "").strip()
    init_fen = data.get("initialFen") or chess.STARTING_FEN

    board = chess.Board(init_fen)
    last_uci = None
    for tok in moves_str.split():
        try:
            mv = chess.Move.from_uci(tok)
            if mv in board.legal_moves:
                board.push(mv)
                last_uci = mv.uci()
                continue
        except Exception:
            pass
        try:
            mv = board.parse_san(tok)
            board.push(mv)
            last_uci = mv.uci()
        except Exception:
            log(f"Coup illisible: {tok}", "warn")

    return board.fen(), last_uci, moves_str

def save_position_before_move(fen):
    payload = {"fen": fen, "horodatage": datetime.now(timezone.utc).isoformat()}
    POSITION_BEFORE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Position avant coup noir sauvegardée dans {POSITION_BEFORE_FILE}", "save")

def update_position_files(fen, last_move):
    Path(FEN_FILE).write_text(fen or "", encoding="utf-8")
    payload = {"dernier_coup": last_move, "fen": fen, "horodatage": datetime.now(timezone.utc).isoformat()}
    Path(LAST_MOVE_FILE).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log("position.fen et dernier_coup.json mis à jour", "ok")

def append_move_to_history(couleur, coup, fen):
    history = []
    if MOVE_HISTORY_FILE.exists():
        try:
            history = json.loads(MOVE_HISTORY_FILE.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = []
        except Exception:
            pass
    history.append({
        "couleur": couleur,
        "coup": coup,
        "fen_apres": fen,
        "horodatage": datetime.now(timezone.utc).isoformat()
    })
    MOVE_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Coup {couleur} ajouté à {MOVE_HISTORY_FILE}", "save")

def is_black_to_move(fen):
    try:
        return fen.split()[1] == "b"
    except Exception:
        return False

# -----------------------
# Main
# -----------------------
if __name__ == "__main__":
    game_id = load_game_id()
    if not game_id:
        raise SystemExit(1)

    fen, last_uci, _ = fetch_current_state(game_id)
    if not fen:
        raise SystemExit(1)

    # ✅ On vérifie AVANT toute sauvegarde si c'est aux noirs
    if not is_black_to_move(fen):
        log("Ce n'est pas aux Noirs de jouer, arrêt du script.", "info")
        raise SystemExit(0)

    save_position_before_move(fen)

    log("Attente du coup noir...", "wait")
    for _ in range(30):  # 30 x 2s = max 1 minute
        time.sleep(2)
        fen_after, last_after, _ = fetch_current_state(game_id)
        if fen_after and not is_black_to_move(fen_after):
            update_position_files(fen_after, last_after)
            append_move_to_history("noir", last_after, fen_after)
            log("Coup noir détecté et fichiers mis à jour.", "ok")
            break
    else:
        log("Aucun coup noir détecté dans le délai imparti.", "warn")
