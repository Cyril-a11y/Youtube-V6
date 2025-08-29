# 06_generate_black_svg.py — Dessin via FEN live, historique via move_history.json (fallback txt), notation française

import os
import re
import json
import chess
import requests
import chess.svg
from pathlib import Path
import cairosvg

# --- Fichiers ---
DATA_DIR = Path("data")
SVG_FILE = DATA_DIR / "thumbnail_black.svg"
PNG_FILE = DATA_DIR / "thumbnail_black.png"
BOT_ELO_FILE = DATA_DIR / "bot_elo.txt"
MOVE_HISTORY_FILE = DATA_DIR / "move_history.json"
HISTORY_FILE = DATA_DIR / "historique.txt"

# --- Lecture Elo du bot ---
if not BOT_ELO_FILE.exists():
    raise SystemExit("❌ bot_elo.txt introuvable — le workflow doit l'écrire avant.")
try:
    ELO_APPROX = int(BOT_ELO_FILE.read_text(encoding="utf-8").strip())
except Exception:
    raise SystemExit("❌ Contenu de bot_elo.txt invalide.")
NOM_BLANCS = "Communauté PriseEnPassant"
NOM_NOIRS = f"Stockfish {ELO_APPROX} Elo"

# --- Conversion SAN en notation française ---
def san_to_french(san: str) -> str:
    mapping = {
        "K": "R",  # King → Roi
        "Q": "D",  # Queen → Dame
        "R": "T",  # Rook → Tour
        "B": "F",  # Bishop → Fou
        "N": "C",  # Knight → Cavalier
    }
    for eng, fr in mapping.items():
        san = san.replace(eng, fr)
    return san

# --- Couleurs échiquier + flèche + surbrillance du dernier coup ---
def _force_board_colors(svg_str, light="#ebf0f7", dark="#6095df", highlight="#305080"):
    # Cases standard
    svg_str = re.sub(r'(\.square\.light\s*\{\s*fill:\s*)#[0-9a-fA-F]{3,6}', r'\1' + light, svg_str)
    svg_str = re.sub(r'(\.square\.dark\s*\{\s*fill:\s*)#[0-9a-fA-F]{3,6}', r'\1' + dark, svg_str)

    # Injection style CSS
    svg_str = re.sub(
        r'(<svg[^>]*>)',
        r'''\1<style>
            .square.light{fill:''' + light + r''' !important}
            .square.dark{fill:''' + dark + r''' !important}
            .lastmove{fill:''' + highlight + r''' !important}
            .arrow{fill:red;stroke:red;stroke-width:3;opacity:1;stroke-linecap:round;}
        </style>''',
        svg_str, count=1
    )

    # Flèche custom : nette et bien proportionnée
    svg_str = svg_str.replace(
        '<marker id="arrowhead"',
        '<marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">'
    ).replace(
        '<polygon points="0,0 10,3.5 0,7"',
        '<path d="M1,1 Q0,3.5 1,6 L9,3.5 Z"'
    )

    return svg_str

# --- Charger historique ---
def load_history_json():
    if not MOVE_HISTORY_FILE.exists():
        return []
    try:
        return json.loads(MOVE_HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

def load_history_txt():
    if not HISTORY_FILE.exists():
        return []
    try:
        txt = HISTORY_FILE.read_text(encoding="utf-8").strip()
        return [tok for tok in re.split(r"\s+", txt) if tok and not tok.endswith(".")]
    except Exception:
        return []

# --- Construire moves_san (FR) ---
history = load_history_json()
board_tmp = chess.Board()
moves_san, last_move_uci = [], None

if history:  # ✅ utiliser move_history.json
    for entry in history:
        try:
            move = chess.Move.from_uci(entry["coup"])
            san = board_tmp.san(move)
            san_fr = san_to_french(san)
            moves_san.append(san_fr)
            board_tmp.push(move)
            last_move_uci = entry["coup"]
        except Exception:
            continue
else:  # 🔄 fallback sur historique.txt
    moves_txt = load_history_txt()
    for uci in moves_txt:
        try:
            move = chess.Move.from_uci(uci)
            san = board_tmp.san(move)
            san_fr = san_to_french(san)
            moves_san.append(san_fr)
            board_tmp.push(move)
            last_move_uci = uci
        except Exception:
            continue

tour = (len(moves_san) + 1) // 2

# --- Récupération FEN live (pour dessin) ---
fen = None
token = os.getenv("LICHESS_BOT_TOKEN")
if token:
    try:
        resp = requests.get("https://lichess.org/api/account/playing",
                            headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            games = data.get("nowPlaying", [])
            if games:
                fen = games[0]["fen"]
    except Exception as e:
        print("⚠️ Erreur parsing JSON Lichess:", e)

if not fen:
    print("❌ Impossible de récupérer la FEN live.")
    exit(1)

board = chess.Board(fen)
last_move_obj = chess.Move.from_uci(last_move_uci) if last_move_uci else None

# --- SVG échiquier ---
svg_echiquier = chess.svg.board(
    board=board,
    orientation=chess.WHITE,
    size=620,
    lastmove=last_move_obj,
    arrows=[(last_move_obj.from_square, last_move_obj.to_square)] if last_move_obj else []
)
svg_echiquier = _force_board_colors(svg_echiquier)

# --- Historique formaté ---
def format_history_lines(moves, dernier):
    lignes = []
    nb_coups = (len(moves) + 1) // 2
    for i in range(nb_coups):
        num = i + 1
        coup_blanc = moves[i*2] if i*2 < len(moves) else "—"
        coup_noir = moves[i*2+1] if i*2+1 < len(moves) else "—"
        if coup_blanc == dernier: coup_blanc = f'<tspan>{coup_blanc}</tspan>'
        if coup_noir == dernier: coup_noir = f'<tspan>{coup_noir}</tspan>'
        lignes.append(f'<tspan fill="red" font-weight="bold">{num}.</tspan> {coup_blanc} {coup_noir}')
    return [" ".join(lignes[j:j+5]) for j in range(0, len(lignes), 5)]

historique_lignes = format_history_lines(moves_san, moves_san[-1] if moves_san else "")
if not historique_lignes:
    historique_lignes = ["(aucun coup pour le moment)"]

historique_svg = "".join(
    f'<text x="700" y="{370+i*34}" font-size="15" font-family="Ubuntu" fill="#333">{ligne}</text>'
    for i, ligne in enumerate(historique_lignes)
)

# --- SVG final ---
svg_final = f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg width="1280" height="720" xmlns="http://www.w3.org/2000/svg">
  <rect width="100%" height="100%" fill="#f9fafb"/>
  <text x="75%" y="55" text-anchor="middle" font-size="32" font-family="Ubuntu" fill="#1f2937">♟️ Partie interactive en cours !</text>
  <text x="700" y="115" font-size="22" font-family="Ubuntu" fill="#1f2937">1. Postez votre coup en commentaire.</text>
  <text x="700" y="145" font-size="22" font-family="Ubuntu" fill="#1f2937">2. Le coup majoritaire sera joué automatiquement !</text>
  <g transform="translate(40,50)">{svg_echiquier}</g>
  <text x="700" y="200" font-size="26" font-family="Ubuntu" fill="#111">Dernier coup : {moves_san[-1] if moves_san else "(aucun)"}</text>
  <text x="700" y="240" font-size="28" font-family="Ubuntu" fill="#111">➤ Choisissez le prochain coup !</text>
  <text x="700" y="280" font-size="22" font-family="Ubuntu" fill="#555">Tour : {tour}</text>
  <rect x="680" y="295" width="580" height="340" fill="#fff" stroke="#d1d5db" stroke-width="1" rx="8" ry="8"/>
  <text x="700" y="330" font-size="24" font-family="Ubuntu" fill="#1f2937" font-weight="bold">☰ Historique des coups :</text>
  {historique_svg}
  <text x="750" y="700" font-size="25" font-family="Ubuntu" fill="#1f2937" font-weight="bold">Chaîne YOUTUBE : PriseEnPassant</text>
  <text x="50" y="40" font-size="22" font-family="Ubuntu" fill="#1f2937">♟️ {NOM_NOIRS}</text>
  <text x="50" y="700" font-size="22" font-family="Ubuntu" fill="#1f2937">♟️ {NOM_BLANCS}</text>
</svg>"""

SVG_FILE.write_text(svg_final, encoding="utf-8")
print(f"✅ SVG généré : {SVG_FILE}")
try:
    cairosvg.svg2png(bytestring=svg_final.encode("utf-8"), write_to=str(PNG_FILE))
    print(f"✅ PNG miniature générée : {PNG_FILE}")
except Exception as e:
    print(f"❌ Erreur conversion PNG: {e}")
