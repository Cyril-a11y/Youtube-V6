import os
import json
import chess
import chess.svg
import requests
from pathlib import Path
from wand.image import Image
from wand.color import Color

# -----------------------
# Fichiers et chemins
# -----------------------
DATA_DIR = Path("data")
SVG_FILE = DATA_DIR / "thumbnail_black.svg"
PNG_FILE = DATA_DIR / "thumbnail_black.png"
BOT_ELO_FILE = DATA_DIR / "bot_elo.txt"

# -----------------------
# Lecture Elo du bot (pour affichage Stockfish)
# -----------------------
try:
    ELO_APPROX = int(BOT_ELO_FILE.read_text(encoding="utf-8").strip())
except Exception:
    ELO_APPROX = 1500

NOM_BLANCS = "Communauté PriseEnPassant"
NOM_NOIRS = f"Stockfish {ELO_APPROX} Elo"

# -----------------------
# Récupération de la partie en cours via API account/playing
# -----------------------
print("📥 Récupération de l'état de la partie en cours (live)…")
token = os.getenv("LICHESS_BOT_TOKEN")
if not token:
    print("❌ LICHESS_BOT_TOKEN manquant.")
    exit(1)

url = "https://lichess.org/api/account/playing"
resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
if resp.status_code != 200:
    print(f"❌ Erreur Lichess account/playing: {resp.status_code} {resp.text[:200]}")
    exit(1)

data = resp.json()
games = data.get("nowPlaying", [])
if not games:
    print("⚠️ Aucune partie en cours trouvée.")
    exit(0)

# On prend la 1ère partie active
g = games[0]
game_id = g["gameId"]
fen = g["fen"]
moves = g.get("moves", "").split()  # historique en UCI
last_move = g.get("lastMove")

print(f"♟️ Partie détectée: {game_id}")
print("FEN actuelle:", fen)
print("Dernier coup:", last_move)
print("Nb coups joués:", len(moves))

# -----------------------
# Reconstruction échiquier
# -----------------------
board = chess.Board(fen)

# Convertir l'historique UCI en SAN pour affichage lisible
moves_list = []
tmp_board = chess.Board()
for uci in moves:
    mv = chess.Move.from_uci(uci)
    san = tmp_board.san(mv)
    moves_list.append(san)
    tmp_board.push(mv)

last_san = moves_list[-1] if moves_list else "?"

# -----------------------
# Mise en forme historique (retour à la ligne toutes les 4 paires de coups)
# -----------------------
def format_history_lines(moves):
    lignes = []
    for i in range(0, len(moves), 8):  # 8 = 4 tours (blanc+noir)
        bloc = moves[i:i+8]
        bloc_num = []
        for j, coup in enumerate(bloc):
            if j % 2 == 0:  # numérotation des tours
                tour_num = (i + j) // 2 + 1
                bloc_num.append(f'<tspan fill="red" font-weight="bold">{tour_num}.</tspan> {coup}')
            else:
                bloc_num.append(coup)
        lignes.append(" ".join(bloc_num))
    return lignes

historique_lignes = format_history_lines(moves_list)

# -----------------------
# Génération échiquier SVG (plateau seul)
# -----------------------
svg_echiquier = chess.svg.board(
    board=board,
    orientation=chess.WHITE,
    size=620,
    lastmove=board.peek() if board.move_stack else None
)

# -----------------------
# Construction SVG final avec :
#  - fond clair
#  - échiquier à gauche
#  - infos partie à droite
#  - historique des coups dans une boîte arrondie
# -----------------------
historique_svg = ""
for i, ligne in enumerate(historique_lignes):
    y = 400 + i * 34
    historique_svg += f"""
    <text x="700" y="{y}" font-size="22" font-family="Ubuntu" fill="#333">
        {ligne}
    </text>"""

tour = (len(moves_list) // 2) + 1

svg_final = f"""<svg width="1280" height="720" xmlns="http://www.w3.org/2000/svg">
  <!-- Fond -->
  <rect width="100%" height="100%" fill="#f9fafb"/>

  <!-- Échiquier -->
  <g transform="translate(40,50)">
    {svg_echiquier}
  </g>

  <!-- Titre -->
  <text x="700" y="80" font-size="32" font-family="Ubuntu" font-weight="bold" fill="#111">
    Partie en cours : {NOM_BLANCS} vs {NOM_NOIRS}
  </text>

  <!-- FEN (debug optionnel) -->
  <text x="700" y="130" font-size="20" font-family="Ubuntu" fill="#777">
    FEN : {fen}
  </text>

  <!-- Infos partie -->
  <text x="700" y="180" font-size="26" font-family="Ubuntu" fill="#111">
    Dernier coup : {last_san}
  </text>
  <text x="700" y="220" font-size="22" font-family="Ubuntu" fill="#555">
    🕒 Tour : {tour}
  </text>

  <!-- Boîte historique -->
  <rect x="680" y="260" width="560" height="400" fill="#fff" stroke="#d1d5db" stroke-width="1" rx="12" ry="12"/>
  {historique_svg}
</svg>"""

SVG_FILE.write_text(svg_final, encoding="utf-8")
print(f"✅ SVG généré : {SVG_FILE}")

# -----------------------
# Conversion PNG avec Wand
# -----------------------
try:
    with Image(filename=str(SVG_FILE), resolution=144) as img:
        img.format = 'png'
        img.background_color = Color("white")
        img.alpha_channel = 'remove'
        img.save(filename=str(PNG_FILE))
    print(f"✅ PNG miniature générée : {PNG_FILE}")
except Exception as e:
    print(f"❌ Erreur conversion PNG: {e}")
