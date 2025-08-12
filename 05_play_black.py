import os
import json
import requests
import chess
from datetime import datetime, timezone
from pathlib import Path
import subprocess

# -----------------------
# Config & paths
# -----------------------
LICHESS_BOT_TOKEN = os.getenv("LICHESS_BOT_TOKEN")
GAME_ID_FILE = Path("data/game_id.txt")
FEN_FILE = Path("data/position.fen")
LAST_MOVE_FILE = Path("data/dernier_coup.json")
MOVE_HISTORY_FILE = Path("data/move_history.json")

if not LICHESS_BOT_TOKEN:
    print("❌ LICHESS_BOT_TOKEN manquant.")
    exit(1)

# -----------------------
# Utils
# -----------------------
def log(msg, icon="ℹ️"):
    print(f"{icon} {msg}")

def load_game_id():
    if not GAME_ID_FILE.exists():
        log("game_id.txt introuvable.", "❌")
        return None
    gid = GAME_ID_FILE.read_text(encoding="utf-8").strip()
    log(f"Game ID chargé : {gid}", "✅")
    return gid

def fetch_current_state(game_id):
    url = f"https://lichess.org/game/export/{game_id}"
    params = {"fen": "1", "moves": "1"}
    headers = {
        "Authorization": f"Bearer {LICHESS_BOT_TOKEN}",
        "Accept": "application/json"
    }

    log(f"Requête API → {url}?fen=1&moves=1", "📤")
    r = requests.get(url, params=params, headers=headers)
    log(f"Réponse API brut : {r.status_code}", "📥")
    try:
        log(json.dumps(r.json(), indent=2)[:500] + "...", "📄")
    except Exception:
        log(r.text[:500] + "...", "📄")

    if r.status_code != 200:
        log(f"Erreur API Lichess : {r.status_code} {r.text}", "❌")
        return None, None

    data = r.json()
    moves_str = (data.get("moves") or "").strip()
    init_fen = data.get("initialFen") or chess.STARTING_FEN

    board = chess.Board(init_fen)
    last_move = None
    for mv_str in moves_str.split():
        try:
            mv = chess.Move.from_uci(mv_str)
            board.push(mv)
            last_move = mv.uci()
        except Exception:
            log(f"Coup illisible: {mv_str}", "⚠️")

    return board.fen(), last_move

def is_black_to_move(fen):
    return fen.split()[1] == "b"

def update_files(couleur, coup, fen):
    # position.fen
    FEN_FILE.write_text(fen, encoding="utf-8")
    # dernier_coup.json
    payload = {
        "dernier_coup": coup,
        "fen": fen,
        "horodatage": datetime.now(timezone.utc).isoformat()
    }
    LAST_MOVE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    # move_history.json
    history = []
    if MOVE_HISTORY_FILE.exists():
        try:
            history = json.loads(MOVE_HISTORY_FILE.read_text(encoding="utf-8"))
        except:
            pass
    history.append({
        "couleur": couleur,
        "coup": coup,
        "fen_apres": fen,
        "horodatage": datetime.now(timezone.utc).isoformat()
    })
    MOVE_HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
    log(f"Fichiers mis à jour après coup {couleur}", "💾")

# -----------------------
# Main
# -----------------------
if __name__ == "__main__":
    game_id = load_game_id()
    if not game_id:
        exit(1)

    fen, last_move = fetch_current_state(game_id)
    if not fen:
        log("Impossible de récupérer la FEN", "❌")
        exit(1)

    if not is_black_to_move(fen):
        log("Ce n'est pas aux Noirs de jouer. Arrêt.", "ℹ️")
        exit(0)

    log("C'est aux Noirs de jouer → lancement du bot...", "🤖")

    # Lancer le workflow run-bot.yml
    result = subprocess.run(
        [
            "gh", "workflow", "run", "run-bot.yml",
            "--ref", "main"
        ],
        capture_output=True,
        text=True
    )
    log("Sortie du déclenchement bot:", "📜")
    print(result.stdout)
    print(result.stderr)

    # Relecture après coup noir
    fen_after, last_after = fetch_current_state(game_id)
    if fen_after and not is_black_to_move(fen_after):
        update_files("noir", last_after, fen_after)
        log("Coup noir joué et fichiers mis à jour", "✅")
    else:
        log("Le bot n'a pas encore joué.", "⚠️")
