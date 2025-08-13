# 04_play_white.py — version fiable avec PGN
import os
import requests
import json
import chess
import chess.pgn
import io
import time
from datetime import datetime, timezone
from pathlib import Path

# -----------------------
# Config et fichiers
# -----------------------
LICHESS_HUMAN_TOKEN = os.getenv("LICHESS_HUMAN_TOKEN")
GAME_ID_FILE = Path("data/game_id.txt")
LAST_MOVE_FILE = Path("data/dernier_coup.json")
FEN_FILE = Path("data/position.fen")
COUP_BLANCS_FILE = Path("data/coup_blanc.txt")
POSITION_BEFORE_FILE = Path("data/position_before_white.json")
MOVE_HISTORY_FILE = Path("data/move_history.json")

if not LICHESS_HUMAN_TOKEN:
    raise SystemExit("❌ LICHESS_HUMAN_TOKEN manquant.")

# -----------------------
# Utilitaires
# -----------------------
def log(msg, type="info"):
    icons = {"ok": "✅", "err": "❌", "warn": "⚠️", "info": "ℹ️", "find": "🔎", "save": "💾", "send": "📤", "recv": "📥"}
    print(f"{icons.get(type, '•')} {msg}")

def load_game_id():
    if not GAME_ID_FILE.exists():
        log("game_id.txt introuvable", "err")
        return None
    gid = GAME_ID_FILE.read_text(encoding="utf-8").strip()
    log(f"Game ID chargé : {gid}", "ok")
    return gid

def load_white_move():
    if not COUP_BLANCS_FILE.exists():
        log("coup_blanc.txt introuvable.", "err")
        return None
    return COUP_BLANCS_FILE.read_text(encoding="utf-8").strip()

def download_pgn(game_id):
    url = f"https://lichess.org/game/export/{game_id}?pgn=1&clocks=0&evals=0&literate=0"
    headers = {"Authorization": f"Bearer {LICHESS_HUMAN_TOKEN}"}
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code != 200:
        log(f"Erreur API Lichess : {r.status_code} {r.text[:200]}", "err")
        return None
    return r.text

def save_position_before_move(fen):
    payload = {"fen": fen, "horodatage": datetime.now(timezone.utc).isoformat()}
    POSITION_BEFORE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Position avant coup sauvegardée dans {POSITION_BEFORE_FILE}", "save")

def update_position_files(fen, last_move):
    FEN_FILE.write_text(fen or "", encoding="utf-8")
    payload = {
        "dernier_coup": last_move,
        "fen": fen,
        "horodatage": datetime.now(timezone.utc).isoformat(),
    }
    LAST_MOVE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
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

def to_uci(board, move_str):
    move_str = move_str.strip()
    try:
        mv = board.parse_san(move_str)
        if mv in board.legal_moves:
            return mv.uci()
    except Exception:
        pass
    try:
        mv = chess.Move.from_uci(move_str.lower())
        if mv in board.legal_moves:
            return mv.uci()
    except Exception:
        pass
    return None

def play_move(game_id, move_uci):
    url = f"https://lichess.org/api/board/game/{game_id}/move/{move_uci}"
    headers = {"Authorization": f"Bearer {LICHESS_HUMAN_TOKEN}"}
    log(f"Envoi du coup {move_uci} à Lichess pour {game_id}", "send")
    r = requests.post(url, headers=headers, timeout=30)
    log(f"Réponse Lichess : {r.status_code} {r.text}", "recv")
    return r.status_code == 200

# -----------------------
# Main
# -----------------------
if __name__ == "__main__":
    game_id = load_game_id()
    if not game_id:
        raise SystemExit(1)

    # 🔹 Télécharger et parser le PGN pour savoir si c'est aux blancs
    pgn_str = download_pgn(game_id)
    if not pgn_str:
        raise SystemExit(1)

    game = chess.pgn.read_game(io.StringIO(pgn_str))
    if not game:
        log("Impossible de parser le PGN.", "err")
        raise SystemExit(1)

    board = game.board()
    last_move = None
    for move in game.mainline_moves():
        last_move = move.uci()
        board.push(move)

    save_position_before_move(board.fen())

    if board.turn != chess.WHITE:
        log("Ce n'est pas aux Blancs de jouer.", "warn")
        raise SystemExit(0)

    move_str = load_white_move()
    if not move_str:
        log("Aucun coup blanc à jouer.", "warn")
        raise SystemExit(0)

    move_uci = to_uci(board, move_str)
    if not move_uci:
        log(f"Coup illégal : {move_str}", "err")
        raise SystemExit(1)

    san_str = board.san(chess.Move.from_uci(move_uci))
    if not play_move(game_id, move_uci):
        raise SystemExit(1)

    log(f"Coup joué : {move_uci} ({san_str})", "ok")

    # 🕒 Re-télécharger après le coup
    time.sleep(2)
    pgn_after = download_pgn(game_id)
    if pgn_after:
        game_after = chess.pgn.read_game(io.StringIO(pgn_after))
        board_after = game_after.board()
        last_move_after = None
        for move in game_after.mainline_moves():
            last_move_after = move.uci()
            board_after.push(move)
        update_position_files(board_after.fen(), last_move_after)
        append_move_to_history("blanc", last_move_after, board_after.fen())
