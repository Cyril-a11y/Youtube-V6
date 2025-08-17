# 06_generate_black_svg.py — version avec dernier coup en SAN via lastMove + FEN

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

# --- Lecture Elo du bot ---
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
last_uci = g.get("lastMove")

print(f"♟️ Partie détectée: {game_id}")
print("FEN actuelle:", fen)
print("Dernier coup UCI brut:", last_uci)

# --- Reconstruction échiquier depuis FEN ---
board = chess.Board(fen)

# --- Conversion dernier coup en SAN ---
last_san = ""
if last_uci:
    move = chess.Move.from_uci(last_uci)
    # pièce qui a bougé (dans la FEN avant coup)
    piece = board.piece_at(move.from_square)
    print("Pièce détectée:", piece.symbol() if piece else "❌ inconnu")

    try:
        # ⚠️ Comme la FEN est après coup, il faut "reculer" pour obtenir le SAN
        board_before = board.copy()
        board_before.pop()  # annule le dernier coup
        last_san = board_before.san(move)
    except Exception as e:
        print("❌ Impossible de reconstruire le SAN:", e)
        last_san = last_uci

print("Dernier coup SAN:", last_san)

# --- Génération échiquier SVG ---
svg_echiquier = chess.svg.board(
    board=board,
    orientation=chess.WHITE,
    size=620,
    lastmove=chess.Move.from_uci(last_uci) if last_uci else None
)
svg_echiquier = _force_board_colors(svg_echiquier)

# --- Construction SVG ---
svg_final = f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg width="1280" height="720" xmlns="http://www.w3.org/2000/svg">
  <rect width="100%" height="100%" fill="#f9fafb"/>

  <!-- Titre -->
  <text x="75%" y="60" text-anchor="middle" font-size="35" font-family="Ubuntu" fill="#1f2937">
    ♟️ Partie Interactive !
  </text>

  <!-- Échiquier -->
  <g transform="translate(40,50)">
    {svg_echiquier}
  </g>

  <!-- Infos partie -->
  <text x="700" y="180" font-size="26" font-family="Ubuntu" fill="#111">
    Dernier coup : {last_san}
  </text>
</svg>
"""

SVG_FILE.write_text(svg_final, encoding="utf-8")
print(f"✅ SVG généré : {SVG_FILE}")

try:
    cairosvg.svg2png(bytestring=svg_final.encode("utf-8"), write_to=str(PNG_FILE))
    print(f"✅ PNG miniature générée : {PNG_FILE}")
except Exception as e:
    print(f"❌ Erreur conversion PNG: {e}")
