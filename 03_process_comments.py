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

def load_game_id():
    try:
        gid = Path(GAME_ID_FILE).read_text(encoding="utf-8").strip()
        print(f"✅ Game ID chargé : {gid}")
        return gid
    except FileNotFoundError:
        print("❌ game_id.txt introuvable. Lance 01_create_game.py d'abord.")
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
        print(f"✅ Date dernier coup : {dt}")
        return dt
    except FileNotFoundError:
        print("Info: aucun fichier dernier_coup.json trouvé, création par défaut…")
        Path(LAST_MOVE_FILE).parent.mkdir(parents=True, exist_ok=True)
        data = {"horodatage": datetime(1970, 1, 1, tzinfo=timezone.utc).isoformat()}
        Path(LAST_MOVE_FILE).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    except Exception as e:
        print(f"Info: timestamp illisible ({e}), utilisation d'une date par défaut.")
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
            print(f"❌ Erreur réseau API YouTube : {e}")
            break
        if r.status_code != 200:
            print(f"❌ Erreur API YouTube : {r.status_code} {r.text}")
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
        print(f"🔎 Page récupérée, total commentaires valides : {nb}")
        if "nextPageToken" in data:
            params["pageToken"] = data["nextPageToken"]
        else:
            break
    print(f"✅ {len(commentaires)} commentaire(s) récupéré(s) au total")
    return commentaires

def _sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

# -----------------------
# Normalisation du texte
# -----------------------

def nettoyer_et_corriger_san(commentaire: str) -> str:
    raw = commentaire.strip()
    raw = (raw.replace("×", "x")
               .replace("–", "-").replace("—", "-")
               .replace("0-0-0", "O-O-O").replace("o-o-o", "O-O-O")
               .replace("0-0", "O-O").replace("o-o", "O-O"))
    txt = _sans_accents(raw.lower())

    if re.search(r"\b(grand\s*roque|roque\s*long|roque\s*cote\s*dame|roque\s*dame|rochade\s*longue)\b", txt):
        return "O-O-O"
    if re.search(r"\b(petit\s*roque|roque\s*court|roque\s*cote\s*roi|roque\s*roi|rochade\s*courte)\b", txt) or re.fullmatch(r"\s*roque\s*", txt):
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

# -----------------------
# Parsing des coups
# -----------------------

UCI_REGEX = re.compile(r"^[a-h][1-8][a-h][1-8][qrbn]?$")

def _parse_move_any(board: chess.Board, token: str) -> chess.Move | None:
    try:
        m = board.parse_san(token)
        return m
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
        print(f"📝 Commentaire brut: '{com}' → nettoyé: '{token}'")
        if not token:
            print("⛔ Ignoré: vide après nettoyage")
            continue
        move = _parse_move_any(board, token)
        if move and move in board.legal_moves:
            san = board.san(move)
            uci = move.uci()
            valides_uci.append(uci)
            print(f"✅ Coup valide trouvé: SAN='{san}' | UCI='{uci}'")
        else:
            print(f"❌ Coup illégal ou non reconnu: '{token}'")
    print(f"📋 Liste finale coups valides (UCI): {valides_uci}")
    return valides_uci

def choisir_coup_majoritaire(coups_uci):
    if not coups_uci:
        print("❌ Aucun coup majoritaire possible (liste vide)")
        return None
    coup, nb = Counter(coups_uci).most_common(1)[0]
    print(f"🏆 Coup majoritaire: {coup} ({nb} votes)")
    return coup

def sauvegarder_coup_blanc(coup_uci: str | None):
    COUP_BLANCS_FILE.parent.mkdir(parents=True, exist_ok=True)
    COUP_BLANCS_FILE.write_text(coup_uci or "", encoding="utf-8")
    print(f"💾 coup_blanc.txt mis à jour: '{coup_uci or ''}'")

# -----------------------
# Lichess
# -----------------------

def fetch_current_fen_from_lichess(game_id):
    url = f"https://lichess.org/game/export/{game_id}?fen=1"
    headers = {
        "Authorization": f"Bearer {LICHESS_HUMAN_TOKEN}",
        "Accept": "application/json"
    }
    try:
        r = requests.get(url, headers=headers, timeout=30)
    except Exception as e:
        print(f"❌ Erreur réseau Lichess : {e}")
        return None
    if r.status_code != 200:
        print(f"❌ Erreur API Lichess : {r.status_code} {r.text}")
        return None
    data = r.json()
    return data.get("fen")

# -----------------------
# Main
# -----------------------

if __name__ == "__main__":
    try:
        print("=== DÉBUT DU SCRIPT ===")
        dernier_coup_time = charger_horodatage_dernier_coup()
        commentaires = recuperer_commentaires(YOUTUBE_VIDEO_ID, apres=dernier_coup_time)

        if not commentaires:
            print("⛔ Aucun commentaire récupéré")
            sauvegarder_coup_blanc("")
            sys.exit(0)  # pas d'erreur

        game_id = load_game_id()
        if not game_id:
            sauvegarder_coup_blanc("")
            sys.exit(0)

        fen = fetch_current_fen_from_lichess(game_id)
        if not fen:
            print("⛔ Impossible de récupérer la FEN")
            sauvegarder_coup_blanc("")
            sys.exit(0)

        board = chess.Board(fen)
        coups_valides_uci = extraire_coups_valides(board, commentaires)
        coup_choisi_uci = choisir_coup_majoritaire(coups_valides_uci)

        sauvegarder_coup_blanc(coup_choisi_uci)
        print("=== FIN DU SCRIPT ===")
        # sortie normale => code 0
    except Exception as e:
        print(f"⚠️ Erreur non bloquante: {e}")
        try:
            sauvegarder_coup_blanc("")
        except Exception:
            pass
        sys.exit(0)
