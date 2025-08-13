import chess
import chess.pgn
import chess.svg
from pathlib import Path

PGN_FILE = Path("data/game.pgn")
SVG_FILE = Path("data/thumbnail_black.svg")

def format_history(moves_list):
    """Retourne l'historique formaté avec un saut de ligne tous les 4 demi-coups."""
    lines = []
    for i in range(0, len(moves_list), 4):
        lines.append(" ".join(moves_list[i:i+4]))
    return "\n".join(lines)

def generate_black_svg_from_pgn():
    if not PGN_FILE.exists():
        raise SystemExit(f"❌ Fichier {PGN_FILE} introuvable")

    # Lire et rejouer le PGN complet
    with open(PGN_FILE, "r", encoding="utf-8") as f:
        game = chess.pgn.read_game(f)

    if not game:
        raise SystemExit("❌ Impossible de parser le PGN")

    board = game.board()
    moves_list = []
    last_move = None

    for move in game.mainline_moves():
        san = board.san(move)
        moves_list.append(san)
        last_move = move
        board.push(move)

    formatted_history = format_history(moves_list)
    formatted_history_svg = formatted_history.replace(
        "\n",
        "</text><text x='20' y='" + str(720 - 55) + "' font-size='20' font-family='Arial' fill='black'>"
    )

    # Génération du SVG
    svg = chess.svg.board(
        board,
        orientation=chess.BLACK,
        size=720,
        lastmove=last_move,
        colors={"light": "#ebf0f7", "dark": "#6095df"},
        borders=False
    )

    # Zone historique en bas
    history_box = (
        f"<rect x='10' y='{720 - 110}' width='700' height='100' rx='15' ry='15' fill='white' fill-opacity='0.8'/>"
        f"<text x='20' y='{720 - 80}' font-size='20' font-family='Arial' fill='black'>{formatted_history_svg}</text>"
    )

    svg_with_history = svg.replace("</svg>", history_box + "\n</svg>")

    # Sauvegarde
    SVG_FILE.write_text(svg_with_history, encoding="utf-8")
    print(f"✅ SVG généré depuis PGN : {SVG_FILE}")

if __name__ == "__main__":
    generate_black_svg_from_pgn()
