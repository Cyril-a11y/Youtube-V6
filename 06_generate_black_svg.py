import os
import json
import re
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

# --- Téléchargement du PGN ---
print("📥 Téléchargement du PGN depuis Lichess…")
token = os.getenv("LICHESS_BOT_TOKEN") or os.getenv("LICHESS_HUMAN_TOKEN")
if not token:
    print("❌ Aucun token Lichess trouvé dans les variables d'environnement.")
    exit(0)

url = f"https://lichess.org/game/export/{game_id}?pgn=1&clocks=0&evals=0&literate=0"
headers = {"Authorization": f"Bearer {token}"}
r = requests.get(url, headers=headers)
if r.status_code != 200:
    print(f"❌ Erreur Lichess: {r.status_code} {r.text}")
    exit(0)

PGN_FILE.write_text(r.text, encoding="utf-8")
print(f"✅ PGN sauvegardé dans {PGN_FILE}")

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

# --- Dernier coup ---
last_move = None
if LAST_MOVE_FILE.exists():
    try:
        with open(LAST_MOVE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        last_move = data.get("dernier_coup_uci") or data.get("dernier_coup")
    except Exception:
        pass

# --- Formatage historique ---
def format_history_lines(moves):
    return [" ".join(moves[i:i+4]) for i in range(0, len(moves), 4)]

historique_lignes = format_history_lines(moves_list)

# --- Fonction pour forcer les couleurs ---
def _force_board_colors(svg_str, light="#ebf0f7", dark="#6095df"):
    svg_str = re.sub(r'(\.square\.light\s*\{\s*fill:\s*)#[0-9a-fA-F]{3,6}', r'\1' + light, svg_str)
    svg_str = re.sub(r'(\.square\.dark\s*\{\s*fill:\s*)#[0-9a-fA-F]{3,6}', r'\1' + dark, svg_str)
    svg_str = re.sub(r'(<rect[^>]*class="square light"[^>]*?)\s*fill="[^"]+"', r'\1', svg_str)
    svg_str = re.sub(r'(<rect[^>]*class="square dark"[^>]*?)\s*fill="[^"]+"', r'\1', svg_str)
    svg_str = re.sub(r'(<rect[^>]*class="square light"[^>]*)(/?>)', rf'\1 fill="{light}"\2', svg_str)
    svg_str = re.sub(r'(<rect[^>]*class="square dark"[^>]*)(/?>)', rf'\1 fill="{dark}"\2', svg_str)
    svg_str = re.sub(r'(<svg[^>]*>)',
                     r'\1<style>.square.light{fill:' + light + r' !important}.square.dark{fill:' + dark + r' !important}</style>',
                     svg_str, count=1)
    return svg_str

# --- Génération échiquier ---
svg_echiquier = chess.svg.board(
    board=board,
    orientation=chess.BLACK,
    size=620,
    lastmove=chess.Move.from_uci(last_move) if last_move else None
)
svg_echiquier = _force_board_colors(svg_echiquier)

# --- Construction SVG final ---
historique_svg = ""
for i, ligne in enumerate(historique_lignes):
    y = 375 + i * 34
    ligne_modifiee = re.sub(r"(\d+\.)", r'<tspan fill="red" font-weight="bold">\1</tspan>', ligne)
    historique_svg += f"""
    <text x="700" y="{y}" font-size="22" font-family="Ubuntu" fill="#333">
        {ligne_modifiee}
    </text>"""

svg_final = f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg width="1280" height="720" xmlns="http://www.w3.org/2000/svg">
  <rect width="100%" height="100%" fill="#f9fafb"/>
  <text x="75%" y="60" text-anchor="middle" font-size="35" font-family="Ubuntu" fill="#1f2937">
    ♟️ Partie Interactive !
  </text>
  <g transform="translate(40,50)">
    {svg_echiquier}
  </g>
  <text x="700" y="180" font-size="28" font-family="Ubuntu" fill="#111">
    Dernier coup : {last_move or "?"}
  </text>
  <rect x="680" y="295" width="540" height="340" fill="#ffffff" stroke="#d1d5db" stroke-width="1" rx="8" ry="8"/>
  <text x="700" y="330" font-size="26" font-family="Ubuntu" fill="#1f2937">
    📜 Historique des coups :
  </text>
  {historique_svg}
  <text x="50" y="40" font-size="24" font-family="Ubuntu" fill="#1f2937">
    ♟️ Noirs
  </text>
  <text x="50" y="700" font-size="24" font-family="Ubuntu" fill="#1f2937">
    ♟️ Blancs
  </text>
</svg>
"""

# --- Sauvegarde ---
SVG_FILE.write_text(svg_final, encoding="utf-8")
print(f"✅ SVG généré avec esthétique améliorée : {SVG_FILE}")
