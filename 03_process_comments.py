import requests
import json
import re
import unicodedata
import chess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from config import (
    YOUTUBE_API_KEY,
    YOUTUBE_VIDEO_ID,
    LAST_MOVE_FILE,
    LICHESS_HUMAN_TOKEN,
    GAME_ID_FILE
)

COUP_BLANCS_FILE = Path("data/coup_blanc.txt")

# -----------------------
# Utilitaires généraux
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
    except Exception as e:
        log(f"Timestamp illisible ({e}), utilisation d'une date par défaut.", "warn")
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
            log(f"Erreur API YouTube : {r.status_code} {r.text}", "err")
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
    raw = (raw.replace("×", "x")
               .replace("–", "-").replace("—", "-")
               .replace("0-0-0", "O-O-O").replace("o-o-o", "O-O-O")
               .replace("0-0", "O-O").replace("o-o", "O-O"))
    txt = _sans_accents(raw.lower())

    # Traduction roques
    if re.search(r"\b(grand\s*roque|roque\s*long|cote\s*dame|rochade\s*longue)\b", txt):
        return "O-O-O"
    if re.search(r"\b(petit\s*roque|roque\s*court|cote\s*roi|rochade\s*courte)\b", txt) or re.fullmatch(r"\s*roque\s*", txt):
        return "O-O"

    # Si c'est juste une case, on force en minuscule
    if re.fullmatch(r"[A-H][1-8]", raw):
        raw = raw.lower()

    cleaned = re.sub(r"[^a-hA-H1-8NBRQKCTFDRxXO\-+=#]", "", raw)

    # Traduction pièces FR → EN
    trad = {"C": "N", "F": "B", "T": "R", "D": "Q", "R": "K"}
    if cleaned[:1] in trad:
        cleaned = trad[cleaned[0]] + cleaned[1:]
    if "x" in cleaned and cleaned[:1] in trad:
        cleaned = trad[cleaned[0]] + cleaned[1:]

    # Promotion
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

def fetch_current_fen_from_lichess(game_id):
    url = f"https://lichess.org/game/export/{game_id}?fen=1"
    headers = {
        "Authorization": f"Bearer {LICHESS_HUMAN_TOKEN}",
        "Accept": "application/json"
    }
    try:
        r = requests.get(url, headers=headers, timeout=30)
    except Exception as e:
        log(f"Erreur réseau Lichess : {e}", "err")
        return None
    if r.status_code != 200:
        log(f"Erreur API Lichess : {r.status_code} {r.text[:200]}", "err")
        return None
    try:
        data = r.json()
    except Exception as e:
        log(f"Réponse non-JSON : {e}", "err")
        return None
    fen = data.get("fen")
    log(f"FEN récupérée : {fen}", "ok")
    return fen

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

        fen = fetch_current_fen_from_lichess(game_id)
        if not fen:
            sauvegarder_coup_blanc(None)
            sys.exit(0)

        board = chess.Board(fen)
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
