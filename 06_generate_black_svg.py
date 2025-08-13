import os
import json
import time
import chess
import chess.pgn
import chess.svg
import requests
from pathlib import Path
from config import LAST_MOVE_FILE

SVG_FILE = Path("data/thumbnail_black.svg")
PGN_FILE = Path("data/game.pgn")
GAME_ID_FILE = Path("data/game_id.txt")

# --- Récupération du Game ID ---
if not GAME_ID_FILE.exists():
    print("❌ game_id.txt introuvable")
    exit(0)
game_id = GAME_ID_FILE.read_text(encoding="utf-8").strip()

# --- Télécharger toujours le PGN depuis Lichess ---
print("📥 Téléchargement du PGN depuis Lichess…")
token = os.getenv("LICHESS_BOT_TOKEN") or os.getenv("LICHESS_HUMAN_TOKEN")
if not token:
    print("❌ Aucun token Lichess trouvé dans les variables d'environnement.")
    exit(0)

url = f"https://lichess.org/game/export/{game_id}?pgn=1&clocks=0&evals=0&literate=0"
headers = {"Authorization": f"Bearer {token}"}

# On réessaie jusqu'à ce que le dernier coup apparaisse (max 5 tentatives)
for attempt in range(5):
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        print(f"❌ Erreur Lichess: {r.status_code} {r.text}")
        exit(0)

    pgn_text = r.text
    if PGN_FILE.exists():
        old_pgn = PGN_FILE.read_text(encoding="utf-8")
    else:
        old_pgn = ""

    # Si le PGN a changé ou qu'on est à la dernière tentative, on l'enregistre
    if pgn_text != old_pgn or attempt == 4:
        PGN_FILE.write_text(pgn_text, encoding="utf-8")
        print(f"✅ PGN sauvegardé dans {PGN_FILE}")
        break

    print("⏳ Dernier coup pas encore présent, nouvelle tentative dans 1s...")
    time.sleep(1)

# --- Reconstruction du plateau ---
with open(PGN_FILE, "r", encoding="utf-8") as f:
    game = chess.pgn.read_game(f)
if not game:
    print("❌ Impossible de parser le PGN.")
    exit(0)

board = game.board()
moves_list = []
for move in game.mainline_moves():
    moves_list.append(board.san(move))
    board.push(move)

# --- Récupération du dernier coup ---
last_move = None
if LAST_MOVE_FILE.exists():
    try:
        with open(LAST_MOVE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        last_move = data.get("dernier_coup_uci") or data.get("dernier_coup")
    except Exception as e:
        print(f"⚠️ Impossible de lire {LAST_MOVE_FILE} : {e}")

# --- Formatage de l'historique ---
def format_history(moves):
    lines = []
    for i in range(0, len(moves), 4):
        lines.append(" ".join(moves[i:i+4]))
    return "\n".join(lines)

formatted_history = format_history(moves_list)
formatted_history_svg = formatted_history.replace(
    "\n",
    "</text><text x='20' y='" + str(720 - 55) + "' font-size='20' font-family='Arial' fill='black'>"
)

# --- Génération du SVG ---
svg = chess.svg.board(
    board,
    orientation=chess.BLACK,
    size=720,
    lastmove=chess.Move.from_uci(last_move) if last_move else None,
    colors={"light": "#ebf0f7", "dark": "#6095df"},
    borders=False
)

# --- Ajout de l'historique ---
history_box = (
    f"<rect x='10' y='{720 - 110}' width='700' height='100' rx='15' ry='15' fill='white' fill-opacity='0.8'/>"
    f"<text x='20' y='{720 - 80}' font-size='2
