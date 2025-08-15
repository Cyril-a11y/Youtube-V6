# 04_play_white.py — version "account/playing" fiable sans position_before_white.json
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
LAST_MOVE_FILE = Path("data/dernier_coup.json")
FEN_FILE = Path("data/position.fen")
COUP_BLANCS_FILE = Path("data/coup_blanc.txt")
MOVE_HISTORY_FILE = Path("data/move_history.json")
PGN_FILE = Path("data/game.pgn")

if not LICHESS_HUMAN_TOKEN:
    raise SystemExit("❌ LICHESS_HUMAN_TOKEN manquant.")

# -----------------------
# Utilitaires
# -----------------------
def log(msg, type="info"):
    icons = {
        "ok": "✅", "err": "❌", "warn": "⚠️",
        "info": "ℹ️", "find": "🔎", "save": "💾",
        "send": "📤", "recv": "📥"
    }
    print(f"{icons.get(type, '•')} {msg}")

def load_white_move():
    if not COUP_BLANCS_FILE.exists():
        log("coup_blanc.txt introuvable.", "err")
        return None
    return COUP_BLANCS_FILE.read_text(encoding="utf-8").strip()

def get_current_game():
    """Trouve la partie en cours via /api/account/playing"""
    url = "https://lichess.org/api/account/playing"
    headers = {"Authorization": f"Bearer {LICHESS_HUMAN_TOKEN}"}
    r = requests.get(url, headers=headers, timeout=10)
    if r.status_code != 200:
        log(f"Erreur API account/playing : {r.status_code} {r.text[:200]}", "err")
        return None

    data = r.json()
    games = data.get("nowPlaying", [])
    if not games:
        log("Aucune partie en cours trouvée.", "warn")
        return None

    for g in games:
        if g.get("isMyTurn") and g.get("color") == "white":
            return {
                "game_id": g["gameId"],
                "fen": g["fen"],
                "moves": g.get("lastMove", ""),
                "full_moves": g.get("moves", "").split()
            }

    log("Aucune partie où c'est à toi (blancs) de jouer.", "warn")
    return None

def download_pgn(game_id):
    """Télécharge le PGN brut pour archive/historique."""
    url = f"https://lichess.org/game/export/{game_id}?pgn=1&clocks=0&evals=0&literate=0"
    headers = {"Authorization": f"Bearer {LICHESS_HUMAN_TOKEN}"}
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code != 200:
        log(f"Erreur API Lichess : {r.status_code} {r.text[:200]}", "err")
        return None
    PGN_FILE.write_text(r.text, encoding="utf-8")
    return r.text

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
    if len(move_str) == 2 and move_str[0] in "abcdefgh" and move_str[1] in "12345678":
        try:
            to_sq = chess.parse_square(move_str.lower())
            candidates = [m for m in board.legal_moves if m.to_square == to_sq]
            if len(candidates) == 1:
                return candidates[0].uci()
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
    game_info = get_current_game()
    if not game_info:
        raise SystemExit(0)  # Pas de partie à jouer

    game_id = game_info["game_id"]
    board = chess.Board(game_info["fen"])

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

    COUP_BLANCS_FILE.unlink(missing_ok=True)
