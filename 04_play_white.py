# 04_play_white.py
import requests
import json
import chess
import chess.pgn
import io
import time
from datetime import datetime, timezone
from pathlib import Path
from config import LICHESS_HUMAN_TOKEN, GAME_ID_FILE, LAST_MOVE_FILE, FEN_FILE

COUP_BLANCS_FILE = Path("data/coup_blanc.txt")
POSITION_BEFORE_FILE = Path("data/position_before_white.json")
MOVE_HISTORY_FILE = Path("data/move_history.json")


def load_game_id():
    try:
        path = Path(GAME_ID_FILE).resolve()
        if not path.exists():
            print(f"❌ {path} introuvable. Lance 01_create_game.py d'abord.")
            return None
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        print(f"📂 Lecture de {path} (modifié le {mtime.isoformat()})")
        gid = path.read_text(encoding="utf-8").strip()
        print(f"✅ Game ID chargé : {gid}")
        return gid
    except Exception as e:
        print(f"❌ Impossible de lire le Game ID : {e}")
        return None


def load_white_move():
    if not COUP_BLANCS_FILE.exists():
        print("❌ coup_blanc.txt introuvable.")
        return None
    return COUP_BLANCS_FILE.read_text(encoding="utf-8").strip()


def fetch_current_state(game_id):
    url = f"https://lichess.org/game/export/{game_id}?moves=1&tags=1&pgnInJson=1&clocks=0&fen=1"
    headers = {
        "Authorization": f"Bearer {LICHESS_HUMAN_TOKEN}",
        "Accept": "application/json"
    }
    try:
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code != 200:
            print(f"❌ Erreur API Lichess : {r.status_code} {r.text[:200]}")
            return None, None
        data = r.json()
    except Exception as e:
        print(f"❌ Erreur lecture JSON Lichess : {e}")
        return None, None

    if data.get("fen"):
        fen = data["fen"]
        moves = data.get("moves", "").split()
        return fen, (moves[-1] if moves else None)

    # Fallback PGN
    pgn_str = data.get("pgn")
    if not pgn_str:
        return None, None

    game = chess.pgn.read_game(io.StringIO(pgn_str))
    board = game.board()
    last_move = None
    for move in game.mainline_moves():
        last_move = move.uci()
        board.push(move)
    return board.fen(), last_move


def save_position_before_move(fen):
    payload = {"fen": fen, "horodatage": datetime.now(timezone.utc).isoformat()}
    POSITION_BEFORE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📂 Position avant coup sauvegardée dans {POSITION_BEFORE_FILE}")


def update_position_files(fen, last_move):
    Path(FEN_FILE).write_text(fen or "", encoding="utf-8")
    payload = {
        "dernier_coup": last_move,
        "fen": fen,
        "horodatage": datetime.now(timezone.utc).isoformat(),
    }
    Path(LAST_MOVE_FILE).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("✅ position.fen et dernier_coup.json mis à jour")


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
    print(f"📝 Coup {couleur} ajouté à {MOVE_HISTORY_FILE}")


def to_uci(board, move_str):
    move_str = move_str.strip()
    if len(move_str) == 2 and move_str[0].isalpha() and move_str[1].isdigit():
        move_str = move_str[0].lower() + move_str[1]

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
    print(f"📤 Envoi du coup {move_uci} à Lichess pour {game_id}")
    r = requests.post(url, headers=headers, timeout=30)
    print(f"📥 Réponse Lichess : {r.status_code} {r.text}")
    return r.status_code == 200


if __name__ == "__main__":
    game_id = load_game_id()
    if not game_id:
        raise SystemExit(1)

    fen, last_move = fetch_current_state(game_id)
    if not fen:
        raise SystemExit(1)
    save_position_before_move(fen)

    board = chess.Board(fen)
    if board.turn != chess.WHITE:
        print("⏳ Ce n'est pas aux Blancs de jouer.")
        raise SystemExit(0)

    move_str = load_white_move()
    if not move_str:
        print("⚠️ Aucun coup blanc à jouer.")
        raise SystemExit(0)

    move_uci = to_uci(board, move_str)
    if not move_uci:
        print(f"❌ Coup illégal : {move_str}")
        raise SystemExit(1)

    san_str = board.san(chess.Move.from_uci(move_uci))
    if not play_move(game_id, move_uci):
        raise SystemExit(1)
    print(f"✅ Coup joué : {move_uci} ({san_str})")

    # 🕒 Attendre que Lichess mette à jour la FEN
    time.sleep(2)
    fen_after, last_move_after = fetch_current_state(game_id)
    if fen_after:
        update_position_files(fen_after, last_move_after)
        append_move_to_history("blanc", last_move_after, fen_after)
