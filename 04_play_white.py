import requests
import json
import chess
import chess.pgn
import io
from datetime import datetime, timezone
from pathlib import Path
from config import LICHESS_HUMAN_TOKEN, GAME_ID_FILE, LAST_MOVE_FILE, FEN_FILE

COUP_BLANCS_FILE = Path("data/coup_blanc.txt")
POSITION_BEFORE_FILE = Path("data/position_before_white.json")
MOVE_HISTORY_FILE = Path("data/move_history.json")


def load_game_id():
    try:
        return Path(GAME_ID_FILE).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        print("❌ game_id.txt introuvable. Lance 01_create_game.py d'abord.")
        return None


def load_white_move():
    if not COUP_BLANCS_FILE.exists():
        print("❌ coup_blanc.txt introuvable. Lance 03_process_comments.py d'abord.")
        return None
    return COUP_BLANCS_FILE.read_text(encoding="utf-8").strip()


def fetch_current_state(game_id):
    """
    Récupère la FEN et le dernier coup depuis Lichess.
    Si 'fen' est absent, reconstruit à partir du PGN.
    """
    url = f"https://lichess.org/game/export/{game_id}?moves=1&tags=1&pgnInJson=1&clocks=0"
    headers = {
        "Authorization": f"Bearer {LICHESS_HUMAN_TOKEN}",
        "Accept": "application/json"
    }

    try:
        r = requests.get(url, headers=headers, timeout=30)
    except Exception as e:
        print(f"❌ Erreur réseau Lichess : {e}")
        return None, None

    if r.status_code != 200:
        print(f"❌ Erreur API Lichess : {r.status_code} {r.text[:200]}")
        return None, None

    try:
        data = r.json()
    except Exception as e:
        print(f"❌ Réponse non-JSON : {e}")
        return None, None

    # Cas simple : Lichess fournit déjà la FEN
    if data.get("fen"):
        fen = data["fen"]
        moves = data.get("moves", "").split()
        last_move = moves[-1] if moves else None
        return fen, last_move

    # Sinon, on reconstruit à partir du PGN
    pgn_str = data.get("pgn")
    if not pgn_str:
        print("❌ Aucun PGN dans la réponse")
        return None, None

    game = chess.pgn.read_game(io.StringIO(pgn_str))
    if not game:
        print("❌ Impossible de parser le PGN")
        return None, None

    board = game.board()
    last_move = None
    for move in game.mainline_moves():
        last_move = move.uci()
        board.push(move)

    return board.fen(), last_move


def save_position_before_move(fen):
    payload = {
        "fen": fen,
        "horodatage": datetime.now(timezone.utc).isoformat()
    }
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
    print("✅ Position et dernier coup sauvegardés.")


def append_move_to_history(couleur: str, coup: str, fen: str):
    if MOVE_HISTORY_FILE.exists():
        try:
            history = json.loads(MOVE_HISTORY_FILE.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []
    else:
        history = []

    history.append({
        "couleur": couleur,
        "coup": coup,
        "fen_apres": fen,
        "horodatage": datetime.now(timezone.utc).isoformat()
    })

    MOVE_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📝 Coup {couleur} ajouté à {MOVE_HISTORY_FILE}")


def to_uci(board: chess.Board, move_str: str):
    move_str = move_str.strip()

    # Tolère "A4" → "a4"
    if len(move_str) == 2 and move_str[0].isalpha() and move_str[1].isdigit():
        move_str = move_str[0].lower() + move_str[1]

    # 1) Essai SAN
    try:
        mv = board.parse_san(move_str)
        if mv in board.legal_moves:
            return mv.uci()
    except Exception:
        pass

    # 2) Essai UCI
    try:
        mv = chess.Move.from_uci(move_str.lower())
        if mv in board.legal_moves:
            return mv.uci()
    except Exception:
        pass

    # 3) Essai par case seule
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
    print(f"📤 Envoi du coup {move_uci} à Lichess pour la partie {game_id}")
    r = requests.post(url, headers=headers, timeout=30)
    print(f"📥 Réponse Lichess : {r.status_code} {r.text}")
    return r.status_code == 200


if __name__ == "__main__":
    game_id = load_game_id()
    if not game_id:
        raise SystemExit(1)

    # 1️⃣ Récupération position actuelle
    fen, last_move = fetch_current_state(game_id)
    if not fen:
        raise SystemExit(1)
    print(f"🔍 FEN actuelle : {fen}")
    print(f"🔍 Dernier coup joué sur Lichess : {last_move}")
    save_position_before_move(fen)

    board = chess.Board(fen)

    # 1b) Vérifier que c'est bien aux Blancs
    if board.turn != chess.WHITE:
        print("⏳ Ce n'est pas aux Blancs de jouer. Arrêt.")
        raise SystemExit(0)

    # 2️⃣ Charger le coup blanc
    move_str = load_white_move()
    print(f"🔍 Coup brut lu depuis coup_blanc.txt : {repr(move_str)}")
    if not move_str:
        print("⚠️ Aucun coup blanc à jouer.")
        raise SystemExit(0)

    move_uci = to_uci(board, move_str)
    print(f"🔍 Coup converti en UCI : {move_uci}")
    if not move_uci:
        print(f"❌ Coup illégal pour la position actuelle : {move_str}")
        raise SystemExit(1)

    san_str = board.san(chess.Move.from_uci(move_uci))
    print(f"♟️ Coup à jouer : SAN='{san_str}' | UCI='{move_uci}'")

    # 3️⃣ Envoi à Lichess
    if not play_move(game_id, move_uci):
        print("❌ Lichess a refusé le coup.")
        raise SystemExit(1)

    print(f"✅ Coup joué avec succès : {move_uci} ({san_str})")

    # 4️⃣ Sauvegarde après coup
    fen, last_move = fetch_current_state(game_id)
    if fen:
        update_position_files(fen, last_move)
        append_move_to_history("blanc", last_move, fen)
