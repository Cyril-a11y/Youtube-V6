import os
import json
import requests
from datetime import datetime, timezone
from pathlib import Path
import chess

LICHESS_BOT_TOKEN = os.getenv("LICHESS_BOT_TOKEN")
GAME_ID_FILE = Path("data/game_id.txt")
LAST_MOVE_FILE = Path("data/dernier_coup.json")
FEN_FILE = Path("data/position.fen")
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

    log(f"📤 Appel API pour récupérer FEN: {url}", "info")
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
    except Exception as e:
        log(f"Erreur de connexion API: {e}", "err")
        return None

    log(f"📥 Réponse API: HTTP {r.status_code}", "info")
    if r.status_code != 200:
        log(f"Réponse erreur: {r.text}", "err")
        return None

    try:
        data = r.json()
    except Exception as e:
        log(f"Erreur parsing JSON: {e}", "err")
        return None

    fen = data.get("fen")
    log(f"FEN récupéré: {fen}", "info")
    return fen

def is_black_to_move(fen):
    return fen and fen.split()[1] == "b"

def play_black_move(game_id, fen):
    board = chess.Board(fen)
    move = list(board.legal_moves)[0].uci()  # Premier coup légal
    url = f"https://lichess.org/api/bot/game/{game_id}/move/{move}"
    headers = {"Authorization": f"Bearer {LICHESS_BOT_TOKEN}"}
    log(f"📤 Tentative de jouer le coup noir: {move}", "info")
    r = requests.post(url, headers=headers)
    log(f"📥 Réponse API move: HTTP {r.status_code}", "info")
    if r.status_code != 200:
        log(f"Erreur en jouant: {r.text}", "err")
        return None
    log(f"Coup noir joué: {move}", "send")
    return move

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

    fen = fetch_current_fen(game_id)
    if not fen:
        raise SystemExit(1)

    if not is_black_to_move(fen):
        log("Ce n'est pas aux Noirs de jouer, arrêt.", "info")
        raise SystemExit(0)

    move_played = play_black_move(game_id, fen)
    if move_played:
        new_fen = fetch_current_fen(game_id)
        if new_fen:
            update_data_files(new_fen, move_played)
            log("Coup noir joué et fichiers mis à jour.", "ok")
