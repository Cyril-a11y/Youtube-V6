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
# Configuration via secrets GitHub Actions
# -----------------------
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_VIDEO_ID = os.getenv("YOUTUBE_VIDEO_ID")
LICHESS_HUMAN_TOKEN = os.getenv("LICHESS_HUMAN_TOKEN")
LICHESS_BOT_TOKEN = os.getenv("LICHESS_BOT_TOKEN")
LAST_MOVE_FILE = "data/dernier_coup.json"
GAME_ID_FILE = "data/game_id.txt"
COUP_BLANCS_FILE = Path("data/coup_blanc.txt")

# Vérification des secrets
missing = []
for var in ["YOUTUBE_API_KEY", "YOUTUBE_VIDEO_ID", "LICHESS_BOT_TOKEN"]:
    if not globals()[var]:
        missing.append(var)
if missing:
    raise SystemExit(f"❌ Secrets manquants : {', '.join(missing)}")

# -----------------------
# Utilitaires
# -----------------------
def log(msg, type="info"):
    icons = {"ok": "✅", "err": "❌", "warn": "⚠️", "info": "ℹ️", "find": "🔎", "save": "💾"}
    print(f"{icons.get(type, '•')} {msg}")

def load_game_id():
    try:
        gid = Path(GAME_ID_FILE).read_text(encoding="utf-8").strip()
        log(f"Game ID chargé : {gid}", "ok")
        return gid
    except FileNotFoundError:
        log("game_id.txt introuvable. Lance 01_create_game.py d'abord.", "err")
        return None

def charger_horodatage_dernier_coup():
    try:
        with open(LAST_MOVE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        ts = data.get("horodatage")
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        elif isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            dt = datetime(1970, 1, 1, tzinfo=timezone.utc)
        log(f"Date dernier coup : {dt}", "ok")
        return dt
    except FileNotFoundError:
        log("Aucun fichier dernier_coup.json trouvé, création par défaut…", "warn")
        Path(LAST_MOVE_FILE).parent.mkdir(parents=True, exist_ok=True)
        data = {"horodatage": datetime(1970, 1, 1, tzinfo=timezone.utc).isoformat()}
        Path(LAST_MOVE_FILE).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return datetime(1970, 1, 1, tzinfo=timezone.utc)

def recuperer_commentaires(video_id, max_results=100, apres=None):
    commentaires = []
    url = "https://www.googleapis.com/youtube/v3/commentThreads"
    params = {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": max_results,
        "order": "time",
        "key": YOUTUBE_API_KEY
    }
    nb = 0
    while True:
        try:
            r = requests.get(url, params=params, timeout=30)
        except Exception as e:
            log(f"Erreur réseau API YouTube : {e}", "err")
            break
        if r.status_code != 200:
            log(f"Erreur API YouTube : {r.status_code} {r.text[:200]}", "err")
            break
        data = r.json()
        for item in data.get("items", []):
            snippet = item["snippet"]["topLevelComment"]["snippet"]
            texte = snippet["textDisplay"]
            date_pub = datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00"))
            if apres and date_pub <= apres:
                continue
            commentaires.append(texte)
            nb += 1
        log(f"Page récupérée, total commentaires valides : {nb}", "find")
        if "nextPageToken" in data:
            params["pageToken"] = data["nextPageToken"]
        else:
            break
    log(f"{len(commentaires)} commentaire(s) récupéré(s) au total", "ok")
    return commentaires

def _sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def nettoyer_et_corriger_san(commentaire: str) -> str:
    raw = commentaire.strip()
    raw = (raw.replace("×", "x").replace("–", "-").replace("—", "-")
               .replace("0-0-0", "O-O-O").replace("o-o-o", "O-O-O")
               .replace("0-0", "O-O").replace("o-o", "O-O"))
    txt = _sans_accents(raw.lower())
    if re.search(r"\b(grand\s*roque|roque\s*long|cote\s*dame|rochade\s*longue)\b", txt):
        return "O-O-O"
    if re.search(r"\b(petit\s*roque|roque\s*court|cote\s*roi|rochade\s*courte)\b", txt) or re.fullmatch(r"\s*roque\s*", txt):
        return "O-O"
    if re.fullmatch(r"[A-H][1-8]", raw):
        raw = raw.lower()
    cleaned = re.sub(r"[^a-hA-H1-8NBRQKCTFDRxXO\-+=#]", "", raw)
    trad = {"C": "N", "F": "B", "T": "R", "D": "Q", "R": "K"}
    if cleaned[:1] in trad:
        cleaned = trad[cleaned[0]] + cleaned[1:]
    if "x" in cleaned and cleaned[:1] in trad:
        cleaned = trad[cleaned[0]] + cleaned[1:]
    if re.fullmatch(r"[a-h][1-8][QRBNqrbn]", cleaned):
        cleaned = f"{cleaned[:2]}={cleaned[2:]}"
    return cleaned

UCI_REGEX = re.compile(r"^[a-h][1-8][a-h][1-8][qrbn]?$")

def _parse_move_any(board: chess.Board, token: str) -> chess.Move | None:
    try:
        return board.parse_san(token)
    except Exception:
        pass
    tok = token.lower()
    if UCI_REGEX.fullmatch(tok):
        try:
            m = chess.Move.from_uci(tok)
            if m in board.legal_moves:
                return m
        except Exception:
            pass
    if re.fullmatch(r"[a-h][1-8]", tok):
        to_sq = chess.parse_square(tok)
        candidates = [m for m in board.legal_moves if m.to_square == to_sq]
        if len(candidates) == 1:
            return candidates[0]
    return None

def extraire_coups_valides(board: chess.Board, commentaires):
    valides_uci = []
    for com in commentaires:
        token = nettoyer_et_corriger_san(com)
        log(f"Commentaire brut: '{com}' → nettoyé: '{token}'", "info")
        if not token:
            log("Ignoré: vide après nettoyage", "warn")
            continue
        move = _parse_move_any(board, token)
        if move and move in board.legal_moves:
            san = board.san(move)
            uci = move.uci()
            valides_uci.append(uci)
            log(f"Coup valide: SAN='{san}' | UCI='{uci}'", "ok")
        else:
            log(f"Coup illégal ou non reconnu: '{token}'", "err")
    log(f"Liste finale coups valides (UCI): {valides_uci}", "find")
    return valides_uci

def choisir_coup_majoritaire(coups_uci):
    if not coups_uci:
        log("Aucun coup majoritaire possible (liste vide)", "err")
        return None
    coup, nb = Counter(coups_uci).most_common(1)[0]
    log(f"Coup majoritaire: {coup} ({nb} vote(s))", "ok")
    return coup

def sauvegarder_coup_blanc(coup_uci: str | None):
    COUP_BLANCS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if coup_uci:
        COUP_BLANCS_FILE.write_text(coup_uci, encoding="utf-8")
        log(f"coup_blanc.txt mis à jour: '{coup_uci}'", "save")
    else:
        log("Aucun coup à sauvegarder, fichier non modifié.", "warn")

def fetch_current_board_from_lichess(game_id):
    """
    Utilise le flux bot pour récupérer la position exacte à jour.
    """
    url = f"https://lichess.org/api/bot/game/stream/{game_id}"
    headers = {
        "Authorization": f"Bearer {LICHESS_BOT_TOKEN}",
        "Accept": "application/x-ndjson"
    }
    try:
        r = requests.get(url, headers=headers, stream=True, timeout=30)
    except Exception as e:
        log(f"Erreur réseau Lichess : {e}", "err")
        return None
    if r.status_code != 200:
        log(f"Erreur API Lichess : {r.status_code} {r.text[:200]}", "err")
        return None

    last_moves = None
    for line in r.iter_lines():
        if not line:
            continue
        try:
            event = json.loads(line.decode("utf-8"))
        except:
            continue
        if "moves" in event:
            last_moves = event["moves"].strip().split()
    r.close()

    board = chess.Board()
    if last_moves:
        for m in last_moves:
            board.push_uci(m)
    log(f"Plateau reconstruit depuis flux bot, trait: {'blancs' if board.turn == chess.WHITE else 'noirs'}", "ok")
    return board

# -----------------------
# Main
# -----------------------
if __name__ == "__main__":
    try:
        print("=== DÉBUT DU SCRIPT ===")
        dernier_coup_time = charger_horodatage_dernier_coup()
        commentaires = recuperer_commentaires(YOUTUBE_VIDEO_ID, apres=dernier_coup_time)
        if not commentaires:
            sauvegarder_coup_blanc(None)
            sys.exit(0)
        game_id = load_game_id()
        if not game_id:
            sauvegarder_coup_blanc(None)
            sys.exit(0)
        board = fetch_current_board_from_lichess(game_id)
        if not board:
            sauvegarder_coup_blanc(None)
            sys.exit(0)
        coups_valides_uci = extraire_coups_valides(board, commentaires)
        coup_choisi_uci = choisir_coup_majoritaire(coups_valides_uci)
        sauvegarder_coup_blanc(coup_choisi_uci)
        print("=== FIN DU SCRIPT ===")
    except Exception as e:
        log(f"Erreur non bloquante: {e}", "err")
        try:
            sauvegarder_coup_blanc(None)
        except Exception:
            pass
        sys.exit(0)
