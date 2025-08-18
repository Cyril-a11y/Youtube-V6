import os
import requests
import json
import re
import unicodedata
import chess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# -----------------------
# Config
# -----------------------
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_VIDEO_ID = os.getenv("YOUTUBE_VIDEO_ID")
LICHESS_BOT_TOKEN = os.getenv("LICHESS_BOT_TOKEN")
LAST_MOVE_FILE = Path("data/dernier_coup.json")
GAME_ID_FILE = Path("data/game_id.txt")
COUP_BLANCS_FILE = Path("data/coup_blanc.txt")

missing = [v for v in ["YOUTUBE_API_KEY", "YOUTUBE_VIDEO_ID", "LICHESS_BOT_TOKEN"] if not globals()[v]]
if missing:
    raise SystemExit(f"❌ Secrets manquants : {', '.join(missing)}")

# -----------------------
# Utilitaires
# -----------------------
def log(msg, type="info"):
    icons = {"ok": "✅", "err": "❌", "warn": "⚠️", "info": "ℹ️", "find": "🔎", "save": "💾"}
    print(f"{icons.get(type, '•')} {msg}")

def charger_horodatage_dernier_coup():
    """Lit l'horodatage du dernier coup depuis dernier_coup.json."""
    if LAST_MOVE_FILE.exists():
        try:
            data = json.loads(LAST_MOVE_FILE.read_text(encoding="utf-8"))
            ts = data.get("horodatage")
            if ts:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                log(f"Date dernier coup (dernier_coup.json) : {dt}", "ok")
                return dt
        except Exception as e:
            log(f"Erreur lecture dernier_coup.json : {e}", "warn")
    return datetime(1970, 1, 1, tzinfo=timezone.utc)

def load_game_id():
    try:
        gid = GAME_ID_FILE.read_text(encoding="utf-8").strip()
        log(f"Game ID chargé : {gid}", "ok")
        return gid
    except FileNotFoundError:
        log("game_id.txt introuvable", "err")
        return None

def recuperer_commentaires(video_id, apres=None):
    """Récupère les commentaires YouTube plus récents que 'apres'."""
    commentaires = []
    url = "https://www.googleapis.com/youtube/v3/commentThreads"
    params = {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": 50,
        "order": "time",
        "key": YOUTUBE_API_KEY
    }
    stop = False
    while True:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            log(f"Erreur API YouTube : {r.status_code} {r.text}", "err")
            break

        data = r.json()
        for item in data.get("items", []):
            snippet = item["snippet"]["topLevelComment"]["snippet"]
            texte = snippet["textDisplay"]
            date_pub = datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00"))
            if apres and date_pub <= apres:
                stop = True
                continue
            commentaires.append(texte)

        if stop or "nextPageToken" not in data:
            break
        params["pageToken"] = data["nextPageToken"]

    log(f"{len(commentaires)} commentaire(s) récupéré(s) après filtrage temporel", "ok")
    return commentaires

def _sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def nettoyer_et_corriger_san(commentaire: str) -> str:
    raw = commentaire.strip()
    raw = (raw.replace("×", "x").replace("–", "-").replace("—", "-")
               .replace("0-0-0", "O-O-O").replace("o-o-o", "O-O-O")
               .replace("0-0", "O-O").replace("o-o", "O-O"))

    txt = _sans_accents(raw)

    # Expressions de roque
    txt_lower = txt.lower()
    if re.search(r"grand\s*roque|roque\s*long|cote\s*dame|rochade\s*longue", txt_lower):
        return "O-O-O"
    if re.search(r"petit\s*roque|roque\s*court|cote\s*roi|rochade\s*courte", txt_lower) or re.fullmatch(r"roque", txt_lower):
        return "O-O"

    # Traduction initiales FR → SAN anglais (uniquement si majuscule)
    trad = {"P": "", "T": "R", "C": "N", "F": "B", "D": "Q", "R": "K"}
    if raw and raw[0].isupper() and raw[0] in trad:
        return trad[raw[0]] + raw[1:]

    # Cas spéciaux pions
    if re.fullmatch(r"[a-h][1-8]", txt_lower):
        # ex: f4 → pion en f4
        return txt_lower
    if re.fullmatch(r"[a-h]x[a-h][1-8]", txt_lower):
        # ex: fxe5 → pion prend en e5
        return txt_lower

    # Sinon nettoyage basique
    cleaned = re.sub(r"[^a-h1-8nbrqkx=+#]", "", txt_lower)
    return cleaned

def extraire_coups_valides(board, commentaires):
    valides = []

    def try_parse(board, token):
        # Essai direct en SAN
        try:
            return board.parse_san(token)
        except Exception:
            pass

        # Essai direct en UCI
        try:
            mv = chess.Move.from_uci(token.lower())
            if mv in board.legal_moves:
                return mv
        except Exception:
            pass

        # Fallback : comparer les SAN des coups légaux
        candidates = []
        for mv in board.legal_moves:
            san = board.san(mv)
            if san.endswith(token[-3:]):  # ex: "xa4"
                candidates.append(mv)

        if len(candidates) == 1:
            return candidates[0]
        return None

    for com in commentaires:
        log(f"📝 Commentaire brut : {com}", "info")
        token = nettoyer_et_corriger_san(com)
        log(f"   ↳ Token nettoyé : {token}", "info")

        move = try_parse(board, token)

        if move and move in board.legal_moves:
            log(f"   ✅ Coup retenu : {board.san(move)} ({move.uci()})", "ok")
            valides.append(move.uci())
        else:
            log(f"   ❌ Coup rejeté : {token}", "warn")

    return valides

def choisir_coup_majoritaire(coups):
    return Counter(coups).most_common(1)[0][0] if coups else None

def sauvegarder_coup_blanc(coup, horodatage):
    COUP_BLANCS_FILE.write_text(coup or "", encoding="utf-8")
    LAST_MOVE_FILE.write_text(json.dumps(
        {"horodatage": horodatage.isoformat()},
        ensure_ascii=False, indent=2
    ), encoding="utf-8")
    log(f"coup_blanc.txt mis à jour: '{coup}'", "save")

def fetch_current_board_from_lichess():
    """Récupère l'état de la partie en cours via /api/account/playing"""
    url = "https://lichess.org/api/account/playing"
    headers = {"Authorization": f"Bearer {LICHESS_BOT_TOKEN}"}
    r = requests.get(url, headers=headers, timeout=10)
    if r.status_code != 200:
        log(f"Erreur API account/playing: {r.status_code} {r.text[:200]}", "err")
        return None, None

    data = r.json()
    games = data.get("nowPlaying", [])
    if not games:
        log("⚠️ Aucune partie en cours pour le bot", "warn")
        return None, None

    g = games[0]  # prend la première partie active
    fen = g["fen"]

    # État actuel du board depuis FEN
    board = chess.Board(fen)

    last_move_time = None
    if "lastMoveAt" in g:
        last_move_time = datetime.fromtimestamp(g["lastMoveAt"]/1000, tz=timezone.utc)

    return board, last_move_time

# -----------------------
# Main
# -----------------------
if __name__ == "__main__":
    log("=== DÉBUT DU SCRIPT ===", "info")
    dernier_coup_time = charger_horodatage_dernier_coup()
    commentaires = recuperer_commentaires(YOUTUBE_VIDEO_ID, apres=dernier_coup_time)
    if not commentaires:
        log("Aucun commentaire reçu → on ne fait rien", "warn")
        sys.exit(0)

    game_id = load_game_id()
    if not game_id:
        sys.exit(0)

    board, last_move_time = fetch_current_board_from_lichess()
    if not board:
        sys.exit(0)

    coups_valides = extraire_coups_valides(board, commentaires)
    coup_choisi = choisir_coup_majoritaire(coups_valides)

    if coup_choisi:
        # ✅ Met à jour uniquement si coup valide
        sauvegarder_coup_blanc(coup_choisi, last_move_time or datetime.now(tz=timezone.utc))
    else:
        # ⚠️ Ne change rien à dernier_coup.json
        log("Aucun coup valide trouvé → horodatage conservé", "warn")

    log("=== FIN DU SCRIPT ===", "info")
