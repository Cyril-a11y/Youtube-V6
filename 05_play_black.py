# 05_play_black.py
import os
import json
import requests
import chess
import chess.engine
import time
from datetime import datetime, timezone
from pathlib import Path
from config import LICHESS_BOT_TOKEN, GAME_ID_FILE, LAST_MOVE_FILE, FEN_FILE

# === Fichiers ===
POSITION_BEFORE_FILE = Path("data/position_before_black.json")
MOVE_HISTORY_FILE = Path("data/move_history.json")

# === Réglages Stockfish ===
STOCKFISH_PATH = os.getenv("STOCKFISH_PATH", "stockfish")
ELO_NIVEAU = 1800
LIMIT_STRENGTH = True
ENGINE_OPTIONS = {
    "Threads": 4,
    "Hash": 512,
    "UCI_LimitStrength": LIMIT_STRENGTH,
    "UCI_Elo": ELO_NIVEAU,
    "Move Overhead": 200,
}
SEARCH_LIMIT = chess.engine.Limit(time=1.0)


def load_game_id():
    try:
        gid = Path(GAME_ID_FILE).read_text(encoding="utf-8").strip()
        print(f"✅ Game ID chargé : {gid}")
        return gid
    except FileNotFoundError:
        print("❌ game_id.txt introuvable.")
        return None


def fetch_current_state(game_id):
    url = f"https://lichess.org/game/export/{game_id}"
    params = {"fen": "1", "moves": "1"}
    headers = {"Authorization": f"Bearer {LICHESS_BOT_TOKEN}", "Accept": "application/json"}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"❌ Erreur API Lichess : {e}")
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
            print("⚠️ Coup illisible:", tok)

    return board.fen(), last_uci, moves_str


def save_position_before_move(fen):
    payload = {"fen": fen, "horodatage": datetime.now(timezone.utc).isoformat()}
    POSITION_BEFORE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📂 Position avant coup noir sauvegardée dans {POSITION_BEFORE_FILE}")


def update_position_files(fen, last_move):
    Path(FEN_FILE).write_text(fen or "", encoding="utf-8")
    payload = {"dernier_coup": last_move, "fen": fen, "horodatage": datetime.now(timezone.utc).isoformat()}
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


def choose_move_uci_from_fen(fen):
    board = chess.Board(fen)
    if board.is_game_over():
        raise RuntimeError("Position terminée, aucun coup à jouer.")
    with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
        engine.configure(ENGINE_OPTIONS)
        result = engine.play(board, SEARCH_LIMIT)
        return result.move.uci()


def bot_play_move(game_id, uci):
    url = f"https://lichess.org/api/bot/game/{game_id}/move/{uci}"
    headers = {"Authorization": f"Bearer {LICHESS_BOT_TOKEN}"}
    r = requests.post(url, headers=headers, timeout=30)
    if r.status_code not in (200, 202):
        print(f"❌ Erreur coup bot : {r.status_code} {r.text}")
        return False
    print(f"♟️ Coup du bot envoyé: {uci}")
    return True


def is_black_to_move(fen):
    try:
        return fen.split()[1] == "b"
    except Exception:
        return False


if __name__ == "__main__":
    game_id = load_game_id()
    if not game_id:
        raise SystemExit(1)

    fen, last_uci, moves_uci = fetch_current_state(game_id)
    if not fen:
        raise SystemExit(1)

    save_position_before_move(fen)

    if not is_black_to_move(fen):
        print("⏳ Ce n'est pas aux Noirs de jouer.")
        raise SystemExit(0)

    uci = choose_move_uci_from_fen(fen)
    if not bot_play_move(game_id, uci):
        raise SystemExit(1)

    # 🕒 Attendre mise à jour Lichess
    time.sleep(2)

    fen_after, last_after, _ = fetch_current_state(game_id)
    if fen_after:
        update_position_files(fen_after, last_after)
        append_move_to_history("noir", last_after, fen_after)
    else:
        print("⚠️ Coup joué mais FEN après coup introuvable.")
