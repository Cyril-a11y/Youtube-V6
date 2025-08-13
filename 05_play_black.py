# 05_play_black.py — version robuste et définitive (dispatch par nom de fichier avec repli par ID)

import os
import json
import time
import requests
import io
import chess.pgn
from pathlib import Path
from datetime import datetime, timezone

# ----- Config / chemins -----
REPO = "Cyril-a11y/Youtube-V6"                 # <== adapte si besoin
WORKFLOW_FILENAME = "run_bot.yml"              # on déclenche par NOM DE FICHIER (pas de chemin)
GITHUB_TOKEN = os.getenv("GH_WORKFLOW_TOKEN")  # PAT avec 'workflow' (Actions: write)

LICHESS_BOT_TOKEN = os.getenv("LICHESS_BOT_TOKEN")
GAME_ID_FILE      = Path("data/game_id.txt")
FEN_FILE          = Path("data/position.fen")
LAST_MOVE_FILE    = Path("data/dernier_coup.json")
MOVE_HISTORY_FILE = Path("data/move_history.json")

def log(msg, tag="ℹ️"):
    print(f"{tag} {msg}")

# ----- Helpers -----
def load_game_id():
    if not GAME_ID_FILE.exists():
        log("game_id.txt introuvable", "❌")
        return None
    gid = GAME_ID_FILE.read_text(encoding="utf-8").strip()
    log(f"Game ID chargé : {gid}", "✅")
    return gid

def fetch_game_state(game_id):
    """Retourne (fen, moves_str) depuis JSON si dispo, sinon reconstruit depuis le PGN brut."""
    url = f"https://lichess.org/game/export/{game_id}"
    params = {"fen": "1", "moves": "1", "pgn": "1"}
    headers = {"Authorization": f"Bearer {LICHESS_BOT_TOKEN}"} if LICHESS_BOT_TOKEN else {}
    log(f"📤 GET {url}?fen=1&moves=1&pgn=1")

    r = requests.get(url, params=params, headers=headers, timeout=20)
    log(f"📥 HTTP {r.status_code}")
    if r.status_code != 200:
        log(f"Réponse: {r.text[:300]}", "❌")
        return None, None

    # Essayer JSON d'abord
    try:
        data = r.json()
        fen = data.get("fen")
        moves_str = data.get("moves") or ""
        if fen:
            log("✅ FEN reçue directement depuis JSON Lichess")
            return fen, moves_str
    except Exception:
        pass  # Pas du JSON → on passe au PGN brut

    # PGN brut → reconstruction
    pgn_text = r.text.strip()
    try:
        pgn_io = io.StringIO(pgn_text)
        game = chess.pgn.read_game(pgn_io)
        board = game.board()
        for move in game.mainline_moves():
            board.push(move)
        fen = board.fen()
        moves_str = " ".join(str(m) for m in game.mainline_moves())
        log("🔄 FEN reconstruite depuis le PGN brut")
        log(f"FEN: {fen}")
        log(f"Moves: {moves_str}")
        return fen, moves_str
    except Exception as e:
        log(f"❌ Erreur de lecture PGN brut: {e}", "❌")
        return None, None

def is_black_to_move(fen: str) -> bool:
    try:
        return fen.split()[1] == "b"
    except Exception:
        return False

# ---------- Dispatch GitHub (robuste) ----------
def _gh_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def _debug_token_scopes():
    try:
        rr = requests.get("https://api.github.com/rate_limit", headers=_gh_headers(), timeout=10)
        scopes = rr.headers.get("X-OAuth-Scopes", "")
        accepted = rr.headers.get("X-Accepted-OAuth-Scopes", "")
        log(f"Token scopes: {scopes or 'inconnu'} | Required: workflow (Actions: write).", "🔎")
        if rr.status_code == 401:
            log("Le token semble invalide (401).", "❌")
    except Exception as e:
        log(f"Impossible de lire les scopes du token: {e}", "⚠️")

def _dispatch_with_identifier(workflow_identifier: str, game_id: str, elo: str) -> requests.Response:
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{workflow_identifier}/dispatches"
    payload = {"ref": "main", "inputs": {"game_id": game_id, "elo": elo}}
    r = requests.post(url, headers=_gh_headers(), json=payload, timeout=20)
    return r

def _find_workflow_id_by_filename(filename: str) -> str | None:
    url = f"https://api.github.com/repos/{REPO}/actions/workflows"
    rr = requests.get(url, headers=_gh_headers(), timeout=20)
    if rr.status_code != 200:
        log(f"❌ Impossible de lister les workflows ({rr.status_code}): {rr.text[:300]}", "❌")
        return None
    data = rr.json()
    for wf in data.get("workflows", []):
        # On matche par nom de fichier (clé 'path' finit par /filename)
        if wf.get("path", "").endswith(f"/{filename}"):
            return str(wf.get("id"))
    return None

def trigger_bot_workflow(game_id: str, elo: str = "1500"):
    """Déclenche le workflow run_bot.yml par nom de fichier, sinon repli automatique par ID."""
    if not GITHUB_TOKEN:
        log("Pas de GH_WORKFLOW_TOKEN défini dans les secrets GitHub.", "❌")
        return False

    # 1) Tentative par NOM DE FICHIER (recommandé par GitHub)
    log(f"🚀 Dispatch workflow par nom: {WORKFLOW_FILENAME} (game_id={game_id}, elo={elo})")
    r = _dispatch_with_identifier(WORKFLOW_FILENAME, game_id, elo)
    if r.status_code == 204:
        log("Workflow bot déclenché (par nom).", "✅")
        return True

    log(f"❌ Dispatch par nom a échoué ({r.status_code}): {r.text}", "❌")

    # 2) En cas de 404 (ou 422 douteux), on cherche l'ID et on retente
    if r.status_code in (404, 422):
        wf_id = _find_workflow_id_by_filename(WORKFLOW_FILENAME)
        if not wf_id:
            _debug_token_scopes()
            log("Impossible de trouver l'ID de run_bot.yml via l'API. "
                "Vérifie que le fichier est sur 'main' et que le token a le scope 'workflow'.", "⚠️")
            return False

        log(f"🔁 Nouvel essai par ID: {wf_id}")
        r2 = _dispatch_with_identifier(wf_id, game_id, elo)
        if r2.status_code == 204:
            log("Workflow bot déclenché (par ID).", "✅")
            return True

        log(f"❌ Dispatch par ID a échoué ({r2.status_code}): {r2.text}", "❌")
        _debug_token_scopes()
        if r2.status_code == 422 and "workflow_dispatch" in (r2.text or "").lower():
            log("Le workflow cible n'a pas 'on: workflow_dispatch'. "
                "Assure-toi que le YAML contient bien ce trigger **sur la branche 'main'**.", "⚠️")
        return False

    # 3) Autre erreur → on affiche les scopes pour aider
    _debug_token_scopes()
    return False

# ---------- Mises à jour fichiers ----------
def update_files_after_black(move_san_or_uci: str, fen: str):
    FEN_FILE.write_text(fen or "", encoding="utf-8")
    LAST_MOVE_FILE.write_text(
        json.dumps({
            "dernier_coup": move_san_or_uci,
            "fen": fen,
            "horodatage": datetime.now(timezone.utc).isoformat()
        }, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    history = []
    if MOVE_HISTORY_FILE.exists():
        try:
            history = json.loads(MOVE_HISTORY_FILE.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []
    history.append({
        "couleur": "noir",
        "coup": move_san_or_uci,
        "fen_apres": fen,
        "horodatage": datetime.now(timezone.utc).isoformat()
    })
    MOVE_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    log("💾 position.fen, dernier_coup.json, move_history.json mis à jour", "✅")

def last_token(moves_str: str) -> str | None:
    toks = (moves_str or "").split()
    return toks[-1] if toks else None

# ----- Main -----
if __name__ == "__main__":
    if not LICHESS_BOT_TOKEN:
        log("LICHESS_BOT_TOKEN manquant.", "❌")
        raise SystemExit(1)

    gid = load_game_id()
    if not gid:
        raise SystemExit(1)

    fen_before, moves_before = fetch_game_state(gid)
    if not fen_before:
        raise SystemExit(1)

    log(f"Trait initial: {'noirs' if is_black_to_move(fen_before) else 'blancs'}")

    if not is_black_to_move(fen_before):
        log("Ce n'est pas aux Noirs de jouer — arrêt propre.", "ℹ️")
        raise SystemExit(0)

    if not trigger_bot_workflow(gid, elo="1500"):
        raise SystemExit(0)

    # Attente courte (3s) pour constater le coup noir
    for _ in range(3):  # 3 essais max
        time.sleep(1)
        fen_after, moves_after = fetch_game_state(gid)
        if not fen_after:
            continue
        if moves_after != moves_before:
            coup = last_token(moves_after) or "unknown"
            log(f"Nouveau coup détecté: {coup}")
            update_files_after_black(coup, fen_after)
            break
        else:
            log("Pas encore de nouveau coup… on réessaie.", "⏳")
    else:
        log("⚠️ Le bot n'a pas joué dans le délai imparti. Vérifie les logs du workflow 'run_bot.yml'.", "⚠️")
