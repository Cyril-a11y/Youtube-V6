if board.turn != chess.BLACK:
    print("❌ Ce n'est pas aux Noirs de jouer.")
    exit(0)

engine = chess.engine.SimpleEngine.popen_uci("/usr/bin/stockfish")
engine.configure({"UCI_LimitStrength": True, "UCI_Elo": elo})
result = engine.play(board, chess.engine.Limit(time=1.0))
move = result.move
engine.quit()

print(f"🤖 Coup choisi: {move.uci()}")

# Mettre à jour le plateau avec le coup noir
board.push(move)

# Envoyer le coup à Lichess
url = f"https://lichess.org/api/board/game/{game_id}/move/{move.uci()}"
headers = {"Authorization": f"Bearer {token}"}
r = requests.post(url, headers=headers)
print(f"📤 POST {url} -> {r.status_code} {r.text}")
if r.status_code != 200:
    exit(1)

# Sauvegarder la position mise à jour
fen_after = board.fen()
position_file = "data/position.fen"
last_move_file = "data/dernier_coup.json"
move_history_file = "data/move_history.json"

Path(position_file).write_text(fen_after, encoding="utf-8")
Path(last_move_file).write_text(
    json.dumps({
        "dernier_coup": move.uci(),
        "fen": fen_after,
        "horodatage": datetime.now(timezone.utc).isoformat()
    }, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

history = []
if Path(move_history_file).exists():
    try:
        history = json.loads(Path(move_history_file).read_text(encoding="utf-8"))
        if not isinstance(history, list):
            history = []
    except Exception:
        history = []
history.append({
    "couleur": "noir",
    "coup": move.uci(),
    "fen_apres": fen_after,
    "horodatage": datetime.now(timezone.utc).isoformat()
})
Path(move_history_file).write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

print("✅ position.fen, dernier_coup.json, move_history.json mis à jour")
