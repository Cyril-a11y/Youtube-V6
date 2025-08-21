# 06_generate_black_svg.py — Historique complet avec trous remplis par un trait noir + date fin (corrigé et robuste)

import os
import re
import chess
import requests
import chess.svg
from pathlib import Path
import cairosvg
from datetime import datetime

# --- Fichiers ---
DATA_DIR = Path("data")
SVG_FILE = DATA_DIR / "thumbnail_black.svg"
PNG_FILE = DATA_DIR / "thumbnail_black.png"
BOT_ELO_FILE = DATA_DIR / "bot_elo.txt"
HISTORY_FILE = DATA_DIR / "historique.txt"
GAME_ID_FILE = DATA_DIR / "game_id.txt"

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

# --- API Lichess ---
print("📥 Récupération de l'état de la partie en cours (live)…")
token = os.getenv("LICHESS_BOT_TOKEN")
if not token:
    print("❌ LICHESS_BOT_TOKEN manquant.")
    exit(1)

resp = requests.get("https://lichess.org/api/account/playing",
                    headers={"Authorization": f"Bearer {token}"}, timeout=10)

titre_principal = "♟️ Partie interactive en cours !"
titre_secondaire = ""
fen = None
last_move_uci = ""
game_id = None
date_fin_str = ""
partie_terminee = False

if resp.status_code == 200 and resp.text.strip():
    try:
        data = resp.json()
    except Exception:
        print("⚠️ Réponse Lichess non-JSON, brut =", resp.text[:200])
        data = {}
    games = data.get("nowPlaying", [])
    if games:
        g = games[0]
        game_id = g["gameId"]
        fen = g["fen"]
        last_move_uci = g.get("lastMove", "")
        print(f"♟️ Partie détectée: {game_id}")
        print("FEN actuelle:", fen)
        print("Dernier coup (UCI brut):", last_move_uci)
    else:
        print("⚠️ Aucune partie en cours trouvée → tentative via game/export")
else:
    print(f"❌ Erreur Lichess account/playing: {resp.status_code}, contenu vide ou invalide")

# --- Si aucune partie active : fallback sur game/export ---
if not fen and GAME_ID_FILE.exists():
    game_id = GAME_ID_FILE.read_text(encoding="utf-8").strip()
    url = f"https://lichess.org/game/export/{game_id}?moves=1&fen=1&pgn=1"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
    if resp.status_code == 200 and resp.text.strip():
        try:
            data = resp.json()
            # partie encore exportable en JSON
            fen = data.get("fen")
            moves = data.get("moves", "").split()
            last_move_uci = moves[-1] if moves else None
            result = data.get("status", "")
        except Exception:
            # Partie finie → PGN brut
            text = resp.text
            print("⚠️ Réponse non-JSON sur game/export, brut =", text[:200])
            result_match = re.search(r'\[Result "([^"]+)"\]', text)
            result = result_match.group(1) if result_match else "inconnu"
            titre_principal = "♟️ Partie terminée"
            titre_secondaire = f"Résultat : {result}"
            partie_terminee = True
            print("📌 Partie terminée :", titre_secondaire)

# --- Si partie terminée sans FEN : utiliser plateau vide ---
if not fen and partie_terminee:
    board = chess.Board()  # échiquier initial, faute de mieux
    fen = board.fen()
else:
    if not fen:
        print("❌ Impossible de récupérer la FEN.")
        exit(1)
    board = chess.Board(fen)

# --- Historique ---
def load_history():
    if not HISTORY_FILE.exists():
        return []
    try:
        text = HISTORY_FILE.read_text(encoding="utf-8").strip()
        tokens = re.split(r"\s+", text)
        moves = [tok for tok in tokens if not tok.endswith(".")]
        return moves
    except Exception:
        return []

moves_list = load_history()

# --- Formatage avec numéros complets ---
def format_history_lines(moves):
    lignes = []
    nb_coups = (len(moves) + 1) // 2
    max_num = max(nb_coups, 1)
    for i in range(max_num):
        num = i + 1
        coup_blanc = moves[i*2] if i*2 < len(moves) else "—"
        coup_noir = moves[i*2+1] if i*2+1 < len(moves) else "—"
        valid_regex = r"^[a-hKQRBN][a-h1-8x=QRBN\+#=]{1,5}$"
        if not re.match(valid_regex, coup_blanc):
            coup_blanc = "—"
        if not re.match(valid_regex, coup_noir):
            coup_noir = "—"
        lignes.append(f'<tspan fill="red">{num}.</tspan> {coup_blanc} {coup_noir}')
    lignes_split = []
    for j in range(0, len(lignes), 5):
        lignes_split.append(" ".join(lignes[j:j+5]))
    return lignes_split

if not moves_list:
    historique_lignes = ["(aucun coup pour le moment)"]
else:
    historique_lignes = format_history_lines(moves_list)

historique_svg = ""
for i, ligne in enumerate(historique_lignes):
    y = 370 + i * 34
    historique_svg += f"""
    <text x="700" y="{y}" font-size="15" font-family="Ubuntu" fill="#333">
        {ligne}
    </text>"""

tour = (len(moves_list) // 2) + 1

# --- Génération échiquier SVG ---
svg_echiquier = chess.svg.board(
    board=board,
    orientation=chess.WHITE,
    size=620,
    lastmove=chess.Move.from_uci(last_move_uci) if last_move_uci else None
)
svg_echiquier = _force_board_colors(svg_echiquier)

# --- Construction SVG complet ---
svg_final = f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg width="1280" height="720" xmlns="http://www.w3.org/2000/svg">
  <rect width="100%" height="100%" fill="#f9fafb"/>
  <text x="75%" y="55" text-anchor="middle" font-size="32" font-family="Ubuntu" fill="#1f2937">
    {titre_principal}
  </text>"""

if titre_secondaire:
    svg_final += f"""
  <text x="75%" y="85" text-anchor="middle" font-size="22" font-family="Ubuntu" fill="#374151">
    {titre_secondaire}
  </text>"""

svg_final += f"""
  <text x="700" y="135" font-size="22" font-family="Ubuntu" fill="#1f2937">
    1. Postez votre coup en commentaire.
  </text>
  <text x="700" y="165" font-size="22" font-family="Ubuntu" fill="#1f2937">
    2. Le coup majoritaire sera joué automatiquement !
  </text>
  <g transform="translate(40,50)">
    {svg_echiquier}
  </g>
  <text x="700" y="200" font-size="26" font-family="Ubuntu" fill="#111">
    Dernier coup : {last_move_uci if last_move_uci else "(aucun)"}
  </text>
  <text x="700" y="240" font-size="28" font-family="Ubuntu" fill="#111">
    ➤ Choisissez le prochain coup !
  </text>
  <text x="700" y="280" font-size="22" font-family="Ubuntu" fill="#555">
    Tour : {tour}
  </text>
  <rect x="680" y="295" width="580" height="340" fill="#fff" stroke="#d1d5db" stroke-width="1" rx="8" ry="8"/>
  <text x="700" y="330" font-size="24" font-family="Ubuntu" fill="#1f2937" font-weight="bold">
    ☰ Historique des coups :
  </text>
  {historique_svg}
  <text x="750" y="700" font-size="25" font-family="Ubuntu" fill="#1f2937" font-weight="bold">
    Chaîne YOUTUBE : PriseEnPassant
  </text>"""

if date_fin_str:
    svg_final += f"""
  <text x="400" y="700" font-size="20" font-family="Ubuntu" fill="#374151">
    {date_fin_str}
  </text>"""

svg_final += f"""
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

try:
    cairosvg.svg2png(bytestring=svg_final.encode("utf-8"), write_to=str(PNG_FILE))
    print(f"✅ PNG miniature générée : {PNG_FILE}")
except Exception as e:
    print(f"❌ Erreur conversion PNG: {e}")
