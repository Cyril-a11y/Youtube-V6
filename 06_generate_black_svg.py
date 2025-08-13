import json
import chess
import chess.svg
from pathlib import Path
from config import FEN_FILE, LAST_MOVE_FILE, MOVE_HISTORY_FILE

SVG_FILE = Path("data/thumbnail_black.svg")

def format_history(moves_list):
    """Retourne l'historique formaté avec un saut de ligne tous les 4 demi-coups."""
    lines = []
    for i in range(0, len(moves_list), 4):
        lines.append(" ".join(moves_list[i:i+4]))
    return "\n".join(lines)

def generate_black_svg():
    # Charger la position actuelle
    fen = Path(FEN_FILE).read_text(encoding="utf-8").strip()
    board = chess.Board(fen)

    # Récupérer le dernier coup joué (UCI ou ancien format)
    last_move = None
    if Path(LAST_MOVE_FILE).exists():
        try:
            with open(LAST_MOVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            last_move = data.get("dernier_coup_uci") or data.get("dernier_coup")
        except Exception as e:
            print(f"⚠️ Impossible de lire {LAST_MOVE_FILE}: {e}")

    # Récupérer l'historique des coups
    moves_list = []
    if Path(MOVE_HISTORY_FILE).exists():
        try:
            with open(MOVE_HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
            for entry in history:
                moves_list.append(entry.get("coup", ""))
        except Exception as e:
            print(f"⚠️ Impossible de lire {MOVE_HISTORY_FILE}: {e}")

    formatted_history = format_history(moves_list)

    # Générer le SVG principal
    svg = chess.svg.board(
        board,
        orientation=chess.BLACK,
        size=720,
        lastmove=chess.Move.from_uci(last_move) if last_move else None,
        colors={"light": "#ebf0f7", "dark": "#6095df"},
        borders=False
    )

    # Ajouter l'historique en overlay avec fond semi-transparent
    history_box = f'''
    <rect x="10" y="{720 - 110}" width="700" height="100" rx="15" ry="15" fill="white" fill-opacity="0.8"/>
    <text x="20" y="{720 - 80}" font-size="20" font-family="Arial" fill="black">
        {formatted_history.replace("\n", "</text><text x='20' y='" + str(720 - 55) + "' font-size='20' font-family='Arial' fill='black'>")}
    </text>
    '''

    svg_with_history = svg.replace("</svg>", history_box + "\n</svg>")

    # Sauvegarder
    SVG_FILE.write_text(svg_with_history, encoding="utf-8")
    print(f"✅ SVG généré avec historique : {SVG_FILE}")

if __name__ == "__main__":
    generate_black_svg()
