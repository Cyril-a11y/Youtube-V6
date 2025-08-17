# 06_generate_black_svg.py — version finale avec icônes compatibles PNG
# FEN via account/playing, historique via game/export, vainqueur si terminé

import os
import re
import chess
import requests
import chess.svg
from pathlib import Path
import cairosvg   # ✅ rendu SVG → PNG plus fiable

# --- Fichiers ---
DATA_DIR = Path("data")
SVG_FILE = DATA_DIR / "thumbnail_black.svg"
PNG_FILE = DATA_DIR / "thumbnail_black.png"
BOT_ELO_FILE = DATA_DIR / "bot_elo.txt"

# --- Lecture Elo du bot (obligatoire, sans fallback) ---
if not BOT_ELO_FILE.exists():
    raise SystemExit("❌ bot_elo.txt introuvable — le workflow doit l'écrire avant.")

try:
    ELO_APPROX = int(BOT_ELO_FILE.read_text(encoding="utf-8").strip())
except Exception:
    raise SystemExit("❌ Contenu de bot_elo.txt invalide.")

NOM_BLANCS = "Communauté PriseEnPassant"
NOM_NOIRS = f"Stockfish {ELO_APPROX} Elo"

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

# --- API Lichess (account/playing live) ---
print("📥 Récupération de l'état de la partie en cours (live)…")
token = os.getenv("LICHESS_BOT_TOKEN")
if not token:
    print("❌ LICHESS_BOT_TOKEN manquant.")
    exit(1)

resp = requests.get("https://lichess.org/api/account/playing",
                    headers={"Authorization": f"Bearer {token}"}, timeout=10)
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

print(f"♟️ Partie détectée: {game_id}")
print("FEN actuelle:", fen)

# --- Reconstruction échiquier depuis FEN ---
board = chess.Board(fen)

# --- Récupération historique via game/export ---
moves_list = []
game_status = "ongoing"
winner = None

try:
    export_url = f"https://lichess.org/game/export/{game_id}?moves=1&tags=0&pgnInJson=1"
    resp_pgn = requests.get(
        export_url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},  # ✅ JSON direct
        timeout=10
    )
    if resp_pgn.status_code == 200:
        game_data = resp_pgn.json()

        # --- Historique des coups (déjà en SAN !) ---
        pgn_moves = game_data.get("moves", "").strip().split()
        moves_list = pgn_moves
        print("Historique SAN (via game/export):", moves_list)

        # --- Vérifier si partie terminée ---
        if game_data.get("status") != "started":
            game_status = game_data.get("status")
            winner = game_data.get("winner")  # "white" | "black" | None
    else:
        print(f"⚠️ Impossible de récupérer le PGN complet ({resp_pgn.status_code})")
except Exception as e:
    print(f"⚠️ Erreur lors du fetch game/export: {e}")

# --- Dernier coup SAN basé uniquement sur l'historique ---
last_san = moves_list[-1] if moves_list else ""

# --- Historique formaté ---
def format_history_lines(moves):
    lignes = []
    for i in range(0, len(moves), 2):  # chaque tour = 2 demi-coups
        num = (i // 2) + 1
        bloc = moves[i:i+2]
        if len(bloc) == 1:
            lignes.append(f'<tspan fill="red">{num}.</tspan> {bloc[0]}')
        else:
            lignes.append(f'<tspan fill="red">{num}.</tspan> {bloc[0]} {bloc[1]}')
    # retour à la ligne toutes les 4 paires de coups (soit 8 demi-coups)
    lignes_split = []
    for j in range(0, len(lignes), 5):
        lignes_split.append(" ".join(lignes[j:j+5]))
    return lignes_split

if not moves_list:
    historique_lignes = ["(aucun coup pour le moment)"]
else:
    historique_lignes = format_history_lines(moves_list)

# --- Génération échiquier SVG ---
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
    y = 360 + i * 34
    historique_svg += f"""
    <text x="670" y="{y}" font-size="14" font-family="Ubuntu" fill="#333">
        {ligne}
    </text>"""

# numéro du tour basé sur moves_list (correct)
tour = (len(moves_list) // 2) + 1

# --- Message fin de partie ---
end_text = ""
if game_status != "ongoing":
    if winner == "white":
        end_text = f"✅ Partie terminée — Vainqueur : {NOM_BLANCS}"
    elif winner == "black":
        end_text = f"✅ Partie terminée — Vainqueur : {NOM_NOIRS}"
    else:
        end_text = f"🤝 Partie terminée — Résultat : {game_status}"

svg_final = f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg width="1280" height="720" xmlns="http://www.w3.org/2000/svg">
  <!-- Fond général -->
  <rect width="100%" height="100%" fill="#f9fafb"/>

  <!-- Titre et instructions -->
  <text x="75%" y="60" text-anchor="middle" font-size="35" font-family="Ubuntu" fill="#1f2937">
    ♟️ Partie Interactive !
  </text>
  <text x="700" y="105" font-size="22" font-family="Ubuntu" fill="#1f2937">
    1. Postez votre coup en commentaire.
  </text>
  <text x="700" y="135" font-size="22" font-family="Ubuntu" fill="#1f2937">
    2. Le coup majoritaire sera joué automatiquement !
  </text>

  <!-- Échiquier -->
  <g transform="translate(40,50)">
    {svg_echiquier}
  </g>

  <!-- Infos partie -->
  <text x="700" y="180" font-size="26" font-family="Ubuntu" fill="#111">
    Dernier coup : {last_san}
  </text>
  <text x="700" y="230" font-size="28" font-family="Ubuntu" fill="#111">
    ➤ Choisissez le prochain coup !
  </text>
  <text x="700" y="280" font-size="22" font-family="Ubuntu" fill="#555">
    Tour : {tour}
  </text>

  <!-- Historique -->
  <rect x="680" y="295" width="540" height="340" fill="#fff" stroke="#d1d5db" stroke-width="1" rx="8" ry="8"/>
  <text x="700" y="330" font-size="24" font-family="Ubuntu" fill="#1f2937" font-weight="bold">
    ☰ Historique des coups :
  </text>
  {historique_svg}

  <!-- Fin de partie -->
  <text x="700" y="660" font-size="28" font-family="Ubuntu" fill="#dc2626" font-weight="bold">
    {end_text}
  </text>

  <!-- Footer -->
  <text x="750" y="700" font-size="25" font-family="Ubuntu" fill="#1f2937" font-weight="bold">
    Chaîne YOUTUBE : PriseEnPassant
  </text>

  <!-- Légende joueurs -->
  <text x="50" y="40" font-size="22" font-family="Ubuntu" fill="#1f2937">
    ♟️ {NOM_NOIRS}
  </text>
  <text x="50" y="700" font-size="22" font-family="Ubuntu" fill="#1f2937">
    ♟️ {NOM_BLANCS}
  </text>
</svg>
"""

SVG_FILE.write_text(svg_final, encoding="utf-8")
print(f"✅ SVG généré : {SVG_FILE}")

# --- Conversion PNG robuste ---
try:
    cairosvg.svg2png(bytestring=svg_final.encode("utf-8"), write_to=str(PNG_FILE))
    print(f"✅ PNG miniature générée : {PNG_FILE}")
except Exception as e:
    print(f"❌ Erreur conversion PNG: {e}")
