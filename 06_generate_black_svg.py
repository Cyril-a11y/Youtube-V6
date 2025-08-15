import os
import json
import re
import chess
import chess.pgn
import chess.svg
import requests
from pathlib import Path
from wand.image import Image
from wand.color import Color

# --- Fichiers ---
DATA_DIR = Path("data")
SVG_FILE = DATA_DIR / "thumbnail_black.svg"
PNG_FILE = DATA_DIR / "thumbnail_black.png"
PGN_FILE = DATA_DIR / "game.pgn"
GAME_ID_FILE = DATA_DIR / "game_id.txt"

# --- Paramètres joueurs ---
NIVEAU_STOCKFISH = os.getenv("STOCKFISH_LEVEL", "8")  # valeur par défaut
NOM_BLANCS = "Communauté PriseEnPassant"
NOM_NOIRS = f"Stockfish Niveau : {NIVEAU_STOCKFISH}"

# --- Couleurs échiquier ---
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

# --- Récupération Game ID ---
if not GAME_ID_FILE.exists():
    print("❌ game_id.txt introuvable")
    exit(0)
game_id = GAME_ID_FILE.read_text(encoding="utf-8").strip()

# --- Téléchargement PGN ---
print("📥 Téléchargement du PGN depuis Lichess…")
token = os.getenv("LICHESS_BOT_TOKEN") or os.getenv("LICHESS_HUMAN_TOKEN")
if not token:
    print("❌ Aucun token Lichess trouvé.")
    exit(0)

url = f"https://lichess.org/game/export/{game_id}?pgn=1&clocks=0&evals=0&literate=0"
headers = {"Authorization": f"Bearer {token}"}
r = requests.get(url, headers=headers)
if r.status_code != 200:
    print(f"❌ Erreur Lichess: {r.status_code} {r.text}")
    exit(0)

PGN_FILE.write_text(r.text, encoding="utf-8")
print(f"✅ PGN sauvegardé dans {PGN_FILE}")

# --- Reconstruction plateau ---
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

# --- Dernier coup depuis PGN ---
last_san = moves_list[-1] if moves_list else "?"

# --- Historique formaté ---
def format_history_lines(moves):
    lignes = []
    for i in range(0, len(moves), 8):  # ⬅️ maintenant on coupe tous les 8 demi-coups
        bloc = moves[i:i+8]
        bloc_num = []
        for j, coup in enumerate(bloc):
            if j % 2 == 0:  # coup des Blancs => numéro de tour
                tour_num = (i + j) // 2 + 1
                bloc_num.append(f'<tspan fill="red" font-weight="bold">{tour_num}.</tspan> {coup}')
            else:
                bloc_num.append(coup)
        lignes.append(" ".join(bloc_num))
    return lignes

historique_lignes = format_history_lines(moves_list)

# --- Génération échiquier (Blancs toujours en bas) ---
svg_echiquier = chess.svg.board(
    board=board,
    orientation=chess.WHITE,
    size=620,
    lastmove=board.peek() if board.move_stack else None
)
svg_echiquier = _force_board_colors(svg_echiquier)

# --- Construction SVG esthétique complet ---
historique_svg = ""
for i, ligne in enumerate(historique_lignes):
    y = 375 + i * 34
    historique_svg += f"""
    <text x="700" y="{y}" font-size="22" font-family="Ubuntu" fill="#333">
        {ligne}
    </text>"""

tour = (len(moves_list) // 2) + 1

svg_final = f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg width="1280" height="720" xmlns="http://www.w3.org/2000/svg">
  <rect width="100%" height="100%" fill="#f9fafb"/>
  <text x="75%" y="60" text-anchor="middle" font-size="35" font-family="Ubuntu" fill="#1f2937">
    ♟️ Partie Interactive !
  </text>
  <text x="700" y="105" font-size="22" font-family="Ubuntu" fill="#1f2937">
    1. Postez votre coup en commentaire.
  </text>
  <text x="700" y="135" font-size="22" font-family="Ubuntu" fill="#1f2937">
    2. Le coup majoritaire sera joué automatiquement !
  </text>
  <g transform="translate(40,50)">
    {svg_echiquier}
  </g>
  <text x="700" y="180" font-size="28" font-family="Ubuntu" fill="#111">
    Dernier coup : {last_san}
  </text>
  <text x="700" y="230" font-size="30" font-family="Ubuntu" fill="#111">
    🧠 Choisissez le prochain coup !
  </text>
  <text x="700" y="280" font-size="24" font-family="Ubuntu" fill="#555">
    🕒 Tour : {tour}
  </text>
  <rect x="680" y="295" width="540" height="340" fill="#ffffff" stroke="#d1d5db" stroke-width="1" rx="8" ry="8"/>
  <text x="700" y="330" font-size="26" font-family="Ubuntu" fill="#1f2937">
    📜 Historique des coups :
  </text>
  {historique_svg}
  <text x="750" y="675" font-size="25" font-family="Ubuntu" fill="#1f2937" font-weight="bold">
    Chaîne YOUTUBE : PriseEnPassant
  </text>
  <text x="50" y="40" font-size="24" font-family="Ubuntu" fill="#1f2937">
    ♟️ {NOM_NOIRS}
  </text>
  <text x="50" y="700" font-size="24" font-family="Ubuntu" fill="#1f2937">
    ♟️ {NOM_BLANCS}
  </text>
</svg>
"""

SVG_FILE.write_text(svg_final, encoding="utf-8")
print(f"✅ SVG généré : {SVG_FILE}")

# --- Conversion PNG ---
with Image(blob=SVG_FILE.read_bytes(), format='svg', background=Color("white")) as img:
    img.format = 'png'
    img.save(filename=str(PNG_FILE))

print(f"✅ PNG miniature générée : {PNG_FILE}")
