import os
import json
import re
import io
import chess
import chess.pgn
import chess.svg
import requests
from pathlib import Path
from wand.image import Image
from wand.color import Color

DATA_DIR = Path("data")
SVG_FILE = DATA_DIR / "thumbnail_black.svg"
PNG_FILE = DATA_DIR / "thumbnail_black.png"
PGN_FILE = DATA_DIR / "game.pgn"
BOT_ELO_FILE = DATA_DIR / "bot_elo.txt"

# --- Lecture Elo ---
try:
    ELO_APPROX = int(BOT_ELO_FILE.read_text(encoding="utf-8").strip())
except Exception:
    ELO_APPROX = 1500

NOM_BLANCS = "Communauté PriseEnPassant"
NOM_NOIRS = f"Stockfish {ELO_APPROX} Elo"

# --- Récupération du PGN via /api/account/playing ---
print("📥 Récupération du PGN en cours…")
token = os.getenv("LICHESS_BOT_TOKEN")
if not token:
    print("❌ LICHESS_BOT_TOKEN manquant.")
    exit(1)

# Trouver la partie courante
r = requests.get("https://lichess.org/api/account/playing",
                 headers={"Authorization": f"Bearer {token}"}, timeout=10)
if r.status_code != 200:
    print(f"❌ Erreur Lichess account/playing: {r.status_code} {r.text[:200]}")
    exit(1)

data = r.json()
games = data.get("nowPlaying", [])
if not games:
    print("⚠️ Aucune partie en cours trouvée.")
    exit(0)

# On prend la 1ère partie active
game_id = games[0]["gameId"]

# Télécharger le PGN + FEN serveur
url = f"https://lichess.org/game/export/{game_id}?pgn=1&fen=1&moves=1&clocks=0&evals=0&literate=0"
resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
if resp.status_code != 200:
    print(f"❌ Erreur téléchargement PGN: {resp.status_code} {resp.text[:200]}")
    exit(1)

pgn_text = resp.text
PGN_FILE.write_text(pgn_text, encoding="utf-8")
print(f"✅ PGN sauvegardé dans {PGN_FILE}")

# --- Reconstruction échiquier ---
game = chess.pgn.read_game(io.StringIO(pgn_text))
if not game:
    print("❌ Impossible de parser le PGN.")
    exit(1)

board = game.board()
moves_list = []
for move in game.mainline_moves():
    moves_list.append(board.san(move))
    board.push(move)

last_san = moves_list[-1] if moves_list else "?"

# 🔑 Vérification avec FEN serveur
fen_match = re.search(r'\[FEN "(.*?)"\]', pgn_text)
if fen_match:
    fen_serveur = fen_match.group(1)
    if board.fen() != fen_serveur:
        print(f"⚠️ Décalage détecté : PGN={board.fen()} vs serveur={fen_serveur}")
        board = chess.Board(fen_serveur)

# --- Historique en colonnes ---
def format_history_lines(moves):
    lignes = []
    for i in range(0, len(moves), 8):
        bloc = moves[i:i+8]
        bloc_num = []
        for j, coup in enumerate(bloc):
            if j % 2 == 0:
                tour_num = (i + j) // 2 + 1
                bloc_num.append(f'<tspan fill="red" font-weight="bold">{tour_num}.</tspan> {coup}')
            else:
                bloc_num.append(coup)
        lignes.append(" ".join(bloc_num))
    return lignes

historique_lignes = format_history_lines(moves_list)

# --- SVG échiquier ---
svg_echiquier = chess.svg.board(
    board=board,
    orientation=chess.WHITE,
    size=620,
    lastmove=board.peek() if board.move_stack else None
)

# --- Construction SVG complet ---
historique_svg = ""
for i, ligne in enumerate(historique_lignes):
    y = 375 + i * 34
    historique_svg += f"""
    <text x="700" y="{y}" font-size="22" font-family="Ubuntu" fill="#333">
        {ligne}
    </text>"""

tour = (len(moves_list) // 2) + 1

svg_final = f"""<svg width="1280" height="720" xmlns="http://www.w3.org/2000/svg">
  <rect width="100%" height="100%" fill="#f9fafb"/>
  <g transform="translate(40,50)">
    {svg_echiquier}
  </g>
  <text x="700" y="180" font-size="28" font-family="Ubuntu" fill="#111">
    Dernier coup : {last_san}
  </text>
  <text x="700" y="280" font-size="24" font-family="Ubuntu" fill="#555">
    🕒 Tour : {tour}
  </text>
  <rect x="680" y="295" width="540" height="340" fill="#fff" stroke="#d1d5db" stroke-width="1" rx="8" ry="8"/>
  {historique_svg}
</svg>"""

SVG_FILE.write_text(svg_final, encoding="utf-8")
print(f"✅ SVG généré : {SVG_FILE}")

# --- Conversion PNG robuste ---
try:
    with Image(filename=str(SVG_FILE), resolution=144) as img:
        img.format = 'png'
        img.background_color = Color("white")
        img.alpha_channel = 'remove'
        img.save(filename=str(PNG_FILE))
    print(f"✅ PNG miniature générée : {PNG_FILE}")
except Exception as e:
    print(f"❌ Erreur conversion PNG: {e}")
