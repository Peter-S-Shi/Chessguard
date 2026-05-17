#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ChessGuard v3

A lightweight chess safety audit tool for humans and AI agents.

ChessGuard is not a chess engine.
It does not recommend best moves, search strategic plans, or evaluate positions.
It reports rule-based and tactical safety facts before a move is trusted.

Main features:
    - Rebuild a position from PGN-like SAN text.
    - Print a coordinate ASCII board.
    - Count material.
    - Check candidate move legality.
    - Compare multiple candidate moves.
    - Distinguish pseudo attacks from legal captures.
    - Report threatened important pieces.
    - Report legal recaptures after legal captures.
    - Report opponent one-move important-piece threat maps.
    - Report king safety and legal responses to check.
    - Add tactical tags, protection reports, pawn watch, and scan-all.
    - Filter ineffective defenders caused by absolute pins.
    - Report unique-defender loss risks after candidate moves.

Dependency:
    pip install chess
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import chess
    import chess.pgn
except ImportError:
    print(
        "ERROR: ChessGuard requires python-chess.\n"
        "Install it with:\n\n"
        "    pip install chess\n",
        file=sys.stderr,
    )
    sys.exit(1)


PROJECT_NAME = "ChessGuard"
VERSION = "3.0.0"
PROJECT_TAGLINE = "A lightweight chess safety audit tool for humans and AI agents."

PIECE_NAMES = {
    chess.PAWN: "P",
    chess.KNIGHT: "N",
    chess.BISHOP: "B",
    chess.ROOK: "R",
    chess.QUEEN: "Q",
    chess.KING: "K",
}

COLOR_NAMES = {
    chess.WHITE: "White",
    chess.BLACK: "Black",
}

MATERIAL_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}

IMPORTANT_PIECES = {
    chess.KING,
    chess.QUEEN,
    chess.ROOK,
    chess.BISHOP,
    chess.KNIGHT,
}

NEXT_THREAT_MOVERS = {
    chess.QUEEN,
    chess.ROOK,
    chess.BISHOP,
    chess.KNIGHT,
}

MOVE_NUMBER_RE = re.compile(r"\b\d+\.(?:\.\.)?")
RESULT_TOKENS = {"1-0", "0-1", "1/2-1/2", "*"}


@dataclass
class MaterialSummary:
    white_score: int
    black_score: int
    white_counts: Dict[int, int]
    black_counts: Dict[int, int]


@dataclass
class SquareSafety:
    square: int
    attacker_color: bool
    pseudo_attackers: List[int] = field(default_factory=list)
    legal_captures: List[chess.Move] = field(default_factory=list)


@dataclass
class PieceThreat:
    square: int
    piece: chess.Piece
    pseudo_attackers: List[int] = field(default_factory=list)
    defenders: List[int] = field(default_factory=list)
    pinned_defenders: List[int] = field(default_factory=list)
    legal_captures: List[chess.Move] = field(default_factory=list)
    recaptures_by_capture_uci: Dict[str, List[chess.Move]] = field(default_factory=dict)


@dataclass
class DefenderLossRisk:
    square: int
    piece: chess.Piece
    attackers_before: List[int] = field(default_factory=list)
    attackers_after: List[int] = field(default_factory=list)
    defender_before: Optional[int] = None
    defenders_after: List[int] = field(default_factory=list)


@dataclass
class CandidateAnalysis:
    input_text: str
    legal: bool
    error: Optional[str] = None
    move: Optional[chess.Move] = None
    san: Optional[str] = None
    uci: Optional[str] = None
    moving_piece_symbol: Optional[str] = None
    from_square: Optional[int] = None
    to_square: Optional[int] = None
    capture: bool = False
    castling: bool = False
    en_passant: bool = False
    promotion: Optional[str] = None
    gives_check: bool = False
    gives_checkmate: bool = False
    stalemate: bool = False
    fen_after: Optional[str] = None
    destination_safety: Optional[SquareSafety] = None
    opponent_mate_in_one: List[chess.Move] = field(default_factory=list)
    opponent_direct_checks: List[chess.Move] = field(default_factory=list)
    friendly_important_threats_after: List[PieceThreat] = field(default_factory=list)
    unique_defender_loss_risks: List[DefenderLossRisk] = field(default_factory=list)
    material_after: Optional[MaterialSummary] = None
    board_after: Optional[chess.Board] = None


@dataclass
class KingSafety:
    color: bool
    king_square: int
    in_check: bool
    checkmate: bool
    adjacent: List[Tuple[int, Optional[chess.Piece], bool, bool]] = field(default_factory=list)
    legal_king_moves: List[chess.Move] = field(default_factory=list)
    legal_check_responses: List[chess.Move] = field(default_factory=list)


@dataclass
class NextThreatEntry:
    move: chess.Move
    san: str
    moving_piece: chess.Piece
    from_square: int
    to_square: int
    captures: Optional[Tuple[int, chess.Piece]] = None
    gives_check: bool = False
    attacked_important_targets: List[Tuple[int, chess.Piece]] = field(default_factory=list)


def color_from_text(text: str) -> bool:
    t = text.strip().lower()
    if t in {"w", "white"}:
        return chess.WHITE
    if t in {"b", "black"}:
        return chess.BLACK
    raise ValueError("Color must be white/black or w/b.")


def opposite(color: bool) -> bool:
    return not color


def square_name(square: int) -> str:
    return chess.square_name(square)


def piece_label(board: chess.Board, square: int) -> str:
    piece = board.piece_at(square)
    if piece is None:
        return f"empty {square_name(square)}"
    return f"{COLOR_NAMES[piece.color]} {PIECE_NAMES[piece.piece_type]}{square_name(square)}"


def piece_label_from_piece(piece: chess.Piece, square: int) -> str:
    return f"{COLOR_NAMES[piece.color]} {PIECE_NAMES[piece.piece_type]}{square_name(square)}"


def move_san(board: chess.Board, move: chess.Move) -> str:
    try:
        return board.san(move)
    except Exception:
        return move.uci()


def ascii_board(board: chess.Board) -> str:
    lines: List[str] = []
    for rank in range(7, -1, -1):
        row: List[str] = []
        for file in range(8):
            sq = chess.square(file, rank)
            piece = board.piece_at(sq)
            row.append(piece.symbol() if piece else ".")
        lines.append(f"{rank + 1}  " + " ".join(row))
    lines.append("   a b c d e f g h")
    return "\n".join(lines)


def important_piece_squares(board: chess.Board, color: Optional[bool] = None, include_pawns: bool = False) -> List[int]:
    squares: List[int] = []
    allowed = set(IMPORTANT_PIECES)
    if include_pawns:
        allowed.add(chess.PAWN)
    for sq, piece in board.piece_map().items():
        if color is not None and piece.color != color:
            continue
        if piece.piece_type in allowed:
            squares.append(sq)
    squares.sort()
    return squares


def print_position_summary(board: chess.Board, include_material: bool = True) -> None:
    print("=== CURRENT POSITION ===")
    print()
    print(ascii_board(board))
    print()
    print(f"Side to move: {COLOR_NAMES[board.turn]}")
    print(f"Check: {board.is_check()}")
    print(f"Checkmate: {board.is_checkmate()}")
    print(f"Stalemate: {board.is_stalemate()}")
    print(f"FEN: {board.fen()}")
    print()
    if include_material:
        print_material_summary(material_summary(board))


def strip_comments_and_variations(text: str) -> str:
    text = re.sub(r"^\s*\[[^\]]*\]\s*$", " ", text, flags=re.MULTILINE)
    text = re.sub(r"\{[^}]*\}", " ", text, flags=re.DOTALL)
    text = re.sub(r";[^\n\r]*", " ", text)
    text = re.sub(r"\$\d+", " ", text)
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\([^()]*\)", " ", text)
    return text


def tokenize_moves(move_text: str) -> List[str]:
    text = strip_comments_and_variations(move_text)
    text = text.replace(",", " ").replace("\n", " ").replace("\r", " ")
    text = MOVE_NUMBER_RE.sub(" ", text)
    tokens: List[str] = []
    for tok in text.split():
        tok = tok.strip()
        if not tok or tok in RESULT_TOKENS or tok in {"...", "..."}:
            continue
        if tok.endswith(".") and tok[:-1].isdigit():
            continue
        tok = tok.lstrip(".")
        if tok:
            tokens.append(tok)
    return tokens


def normalize_san_text(move_text: str) -> str:
    m = move_text.strip()
    m = m.replace("0-0-0", "O-O-O")
    m = m.replace("0-0", "O-O")
    return m


def parse_candidate_move(board: chess.Board, move_text: str) -> chess.Move:
    m = normalize_san_text(move_text)
    try:
        return board.parse_san(m)
    except Exception:
        pass
    try:
        move = chess.Move.from_uci(m.lower())
        if move in board.legal_moves:
            return move
        raise ValueError(f"UCI move '{m}' is syntactically valid but not legal in this position.")
    except Exception as exc:
        raise ValueError(f"Could not parse legal move '{move_text}' as SAN or UCI. {exc}") from exc


def load_board_from_text(move_text: str) -> chess.Board:
    clean = move_text.strip()
    if not clean:
        return chess.Board()
    try:
        game = chess.pgn.read_game(io.StringIO(clean))
        if game is not None:
            pgn_board = game.board()
            moves_found = False
            for move in game.mainline_moves():
                pgn_board.push(move)
                moves_found = True
            if moves_found:
                return pgn_board
    except Exception:
        pass
    board = chess.Board()
    for token in tokenize_moves(clean):
        try:
            move = parse_candidate_move(board, token)
            board.push(move)
        except Exception as exc:
            raise ValueError(
                f"Could not parse move token '{token}' while rebuilding the board.\n"
                f"Moves parsed before failure: fullmove {board.fullmove_number}, side to move {COLOR_NAMES[board.turn]}.\n"
                f"Original error: {exc}"
            ) from exc
    return board


def material_summary(board: chess.Board) -> MaterialSummary:
    white_score = 0
    black_score = 0
    white_counts = {pt: 0 for pt in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]}
    black_counts = {pt: 0 for pt in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]}
    for piece in board.piece_map().values():
        value = MATERIAL_VALUES[piece.piece_type]
        if piece.color == chess.WHITE:
            white_score += value
            if piece.piece_type in white_counts:
                white_counts[piece.piece_type] += 1
        else:
            black_score += value
            if piece.piece_type in black_counts:
                black_counts[piece.piece_type] += 1
    return MaterialSummary(white_score, black_score, white_counts, black_counts)


def material_balance_text(summary: MaterialSummary) -> str:
    diff = summary.white_score - summary.black_score
    if diff > 0:
        return f"White +{diff}"
    if diff < 0:
        return f"Black +{-diff}"
    return "Equal"


def counts_text(counts: Dict[int, int]) -> str:
    order = [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]
    return " ".join(f"{PIECE_NAMES[pt]}:{counts.get(pt, 0)}" for pt in order)


def print_material_summary(summary: MaterialSummary) -> None:
    print("=== MATERIAL COUNT ===")
    print(f"White material: {summary.white_score}")
    print(f"Black material: {summary.black_score}")
    print(f"Balance: {material_balance_text(summary)}")
    print(f"White pieces: {counts_text(summary.white_counts)}")
    print(f"Black pieces: {counts_text(summary.black_counts)}")
    print()


def pseudo_attackers(board: chess.Board, attacker_color: bool, square: int) -> List[int]:
    attackers = list(board.attackers(attacker_color, square))
    attackers.sort()
    return attackers


def absolute_pinned_defenders(board: chess.Board, defender_color: bool, target_square: int) -> List[int]:
    pinned: List[int] = []
    for sq in pseudo_attackers(board, defender_color, target_square):
        piece = board.piece_at(sq)
        if piece is None or piece.color != defender_color:
            continue
        if piece.piece_type == chess.KING:
            continue
        if board.is_pinned(defender_color, sq):
            pinned.append(sq)
    pinned.sort()
    return pinned


def effective_defenders(board: chess.Board, defender_color: bool, target_square: int) -> List[int]:
    pinned = set(absolute_pinned_defenders(board, defender_color, target_square))
    defenders = [sq for sq in pseudo_attackers(board, defender_color, target_square) if sq not in pinned]
    defenders.sort()
    return defenders


def legal_captures_on_square(board: chess.Board, target_square: int) -> List[chess.Move]:
    target_piece = board.piece_at(target_square)
    if target_piece is None:
        return []
    return [move for move in list(board.legal_moves) if move.to_square == target_square and board.is_capture(move)]


def analyze_square_safety(board: chess.Board, square: int, attacker_color: bool) -> SquareSafety:
    legal_captures = legal_captures_on_square(board, square) if board.turn == attacker_color else []
    return SquareSafety(square, attacker_color, pseudo_attackers(board, attacker_color, square), legal_captures)


def print_square_safety(board: chess.Board, safety: SquareSafety, legal_capture_label: str = "Legal captures on square") -> None:
    print("=== SQUARE SAFETY CHECK ===")
    print(f"Square: {square_name(safety.square)}")
    print(f"Geometrically attacked by {COLOR_NAMES[safety.attacker_color]}: {bool(safety.pseudo_attackers)}")
    if safety.pseudo_attackers:
        print("Pseudo attackers:")
        for sq in safety.pseudo_attackers:
            print(f"- {piece_label(board, sq)}")
    else:
        print("Pseudo attackers: none")
    if board.turn == safety.attacker_color:
        print(f"{legal_capture_label}:")
        if safety.legal_captures:
            for move in safety.legal_captures:
                print(f"- {move_san(board, move)} / {move.uci()}")
        else:
            print("- none")
    else:
        print(f"{legal_capture_label}: not side to move")
    print()


def legal_recaptures_after_capture(board: chess.Board, capture_move: chess.Move) -> List[chess.Move]:
    if capture_move not in board.legal_moves:
        return []
    capture_square = capture_move.to_square
    after = board.copy(stack=False)
    after.push(capture_move)
    return [reply for reply in list(after.legal_moves) if reply.to_square == capture_square and after.is_capture(reply)]


def analyze_piece_threat(board: chess.Board, square: int) -> Optional[PieceThreat]:
    piece = board.piece_at(square)
    if piece is None:
        return None
    opponent = opposite(piece.color)
    pseudo = pseudo_attackers(board, opponent, square)
    defenders = effective_defenders(board, piece.color, square)
    pinned = absolute_pinned_defenders(board, piece.color, square)
    legal_caps: List[chess.Move] = []
    recapture_map: Dict[str, List[chess.Move]] = {}
    if board.turn == opponent:
        legal_caps = legal_captures_on_square(board, square)
        for cap in legal_caps:
            recapture_map[cap.uci()] = legal_recaptures_after_capture(board, cap)
    return PieceThreat(square, piece, pseudo, defenders, pinned, legal_caps, recapture_map)


def print_piece_threat(board: chess.Board, threat: PieceThreat) -> None:
    print(f"- {piece_label_from_piece(threat.piece, threat.square)}")
    if threat.pseudo_attackers:
        print("  Pseudo attackers:")
        for sq in threat.pseudo_attackers:
            print(f"  - {piece_label(board, sq)}")
    else:
        print("  Pseudo attackers: none")
    if threat.defenders:
        print("  Effective defenders:")
        for sq in threat.defenders:
            print(f"  - {piece_label(board, sq)}")
    else:
        print("  Effective defenders: none")
    if threat.pinned_defenders:
        print("  Absolute-pinned pseudo defenders excluded:")
        for sq in threat.pinned_defenders:
            print(f"  - {piece_label(board, sq)}")
    attacker_color = opposite(threat.piece.color)
    if board.turn == attacker_color:
        print("  Legal immediate captures:")
        if threat.legal_captures:
            for cap in threat.legal_captures:
                print(f"  - {move_san(board, cap)} / {cap.uci()}")
                recaps = threat.recaptures_by_capture_uci.get(cap.uci(), [])
                if recaps:
                    after = board.copy(stack=False)
                    after.push(cap)
                    print("    Legal recaptures:")
                    for recapture in recaps:
                        print(f"    - {move_san(after, recapture)} / {recapture.uci()}")
                else:
                    print("    Legal recaptures: none")
        else:
            print("  - none")
    else:
        print("  Legal immediate captures: not side to move")


def threatened_pieces_report(board: chess.Board, side: Optional[bool] = None, include_pawns: bool = False) -> List[PieceThreat]:
    threats: List[PieceThreat] = []
    colors = [chess.WHITE, chess.BLACK] if side is None else [side]
    for color in colors:
        for sq in important_piece_squares(board, color=color, include_pawns=include_pawns):
            threat = analyze_piece_threat(board, sq)
            if threat and (threat.pseudo_attackers or threat.legal_captures):
                threats.append(threat)
    return threats


def opponent_mate_in_one_moves(board_after_candidate: chess.Board) -> List[chess.Move]:
    mating_moves: List[chess.Move] = []
    for move in list(board_after_candidate.legal_moves):
        temp = board_after_candidate.copy(stack=False)
        temp.push(move)
        if temp.is_checkmate():
            mating_moves.append(move)
    return mating_moves


def direct_check_moves(board_after_candidate: chess.Board) -> List[chess.Move]:
    checking_moves: List[chess.Move] = []
    for move in list(board_after_candidate.legal_moves):
        temp = board_after_candidate.copy(stack=False)
        temp.push(move)
        if temp.is_check():
            checking_moves.append(move)
    return checking_moves


def analyze_important_friendly_threats_after_move(board_after: chess.Board, friendly_color: bool) -> List[PieceThreat]:
    threats: List[PieceThreat] = []
    for sq in important_piece_squares(board_after, color=friendly_color, include_pawns=False):
        threat = analyze_piece_threat(board_after, sq)
        if threat and (threat.pseudo_attackers or threat.legal_captures):
            threats.append(threat)
    return threats


def unique_defender_loss_risks(before: chess.Board, after: chess.Board, friendly_color: bool) -> List[DefenderLossRisk]:
    opponent = opposite(friendly_color)
    risks: List[DefenderLossRisk] = []
    for sq in important_piece_squares(before, color=friendly_color, include_pawns=False):
        piece_before = before.piece_at(sq)
        if piece_before is None:
            continue
        attackers_before = pseudo_attackers(before, opponent, sq)
        if not attackers_before:
            continue
        defenders_before = effective_defenders(before, friendly_color, sq)
        if len(defenders_before) != 1:
            continue
        piece_after = after.piece_at(sq)
        if piece_after is None or piece_after.color != friendly_color or piece_after.piece_type != piece_before.piece_type:
            continue
        attackers_after = pseudo_attackers(after, opponent, sq)
        if not attackers_after:
            continue
        defenders_after = effective_defenders(after, friendly_color, sq)
        if len(defenders_after) == 0:
            risks.append(
                DefenderLossRisk(
                    square=sq,
                    piece=piece_after,
                    attackers_before=attackers_before,
                    attackers_after=attackers_after,
                    defender_before=defenders_before[0],
                    defenders_after=defenders_after,
                )
            )
    return risks


def unique_defender_loss_summary(risks: List[DefenderLossRisk]) -> str:
    if not risks:
        return "none"
    return ",".join(f"{PIECE_NAMES[r.piece.piece_type]}{square_name(r.square)}" for r in risks)


def print_unique_defender_loss_risks(before: chess.Board, after: chess.Board, risks: List[DefenderLossRisk]) -> None:
    print("=== UNIQUE DEFENDER LOSS RISK AFTER MOVE ===")
    if not risks:
        print("No attacked important piece lost its only effective defender.")
        print()
        return
    for risk in risks:
        print(f"- {piece_label_from_piece(risk.piece, risk.square)}")
        if risk.defender_before is not None:
            before_piece = before.piece_at(risk.defender_before)
            if before_piece is not None:
                print(f"  Only effective defender before move: {piece_label_from_piece(before_piece, risk.defender_before)}")
            else:
                print(f"  Only effective defender before move: {square_name(risk.defender_before)}")
        print("  Attackers before move:")
        for sq in risk.attackers_before:
            print(f"  - {piece_label(before, sq)}")
        print("  Attackers after move:")
        for sq in risk.attackers_after:
            print(f"  - {piece_label(after, sq)}")
        print("  Effective defenders after move: none")
    print()


def analyze_candidate_move(board: chess.Board, move_text: str) -> CandidateAnalysis:
    result = CandidateAnalysis(input_text=move_text, legal=False)
    try:
        move = parse_candidate_move(board, move_text)
    except Exception as exc:
        result.error = str(exc)
        return result
    moving_piece = board.piece_at(move.from_square)
    if moving_piece is None:
        result.error = "No moving piece found."
        return result
    result.legal = True
    result.move = move
    result.san = move_san(board, move)
    result.uci = move.uci()
    result.moving_piece_symbol = moving_piece.symbol()
    result.from_square = move.from_square
    result.to_square = move.to_square
    result.capture = board.is_capture(move)
    result.castling = board.is_castling(move)
    result.en_passant = board.is_en_passant(move)
    result.promotion = PIECE_NAMES.get(move.promotion, None)
    after = board.copy(stack=False)
    after.push(move)
    result.board_after = after
    result.gives_check = after.is_check()
    result.gives_checkmate = after.is_checkmate()
    result.stalemate = after.is_stalemate()
    result.fen_after = after.fen()
    result.material_after = material_summary(after)
    opponent = opposite(moving_piece.color)
    result.destination_safety = analyze_square_safety(after, move.to_square, opponent)
    if not result.gives_checkmate:
        result.opponent_mate_in_one = opponent_mate_in_one_moves(after)
        result.opponent_direct_checks = direct_check_moves(after)
        result.friendly_important_threats_after = analyze_important_friendly_threats_after_move(after, moving_piece.color)
        result.unique_defender_loss_risks = unique_defender_loss_risks(board, after, moving_piece.color)
    return result


def print_candidate_analysis(board: chess.Board, analysis: CandidateAnalysis) -> None:
    print("=== CANDIDATE MOVE CHECK ===")
    print(f"Input: {analysis.input_text}")
    if not analysis.legal:
        print("Legal: False")
        print(f"Reason: {analysis.error}")
        print()
        return
    assert analysis.move is not None and analysis.to_square is not None and analysis.from_square is not None
    assert analysis.destination_safety is not None and analysis.board_after is not None
    print("Legal: True")
    print(f"SAN: {analysis.san}")
    print(f"UCI: {analysis.uci}")
    print(f"Moving piece: {analysis.moving_piece_symbol} from {square_name(analysis.from_square)} to {square_name(analysis.to_square)}")
    print(f"Capture: {analysis.capture}")
    print(f"Castling: {analysis.castling}")
    print(f"En passant: {analysis.en_passant}")
    print(f"Promotion: {analysis.promotion if analysis.promotion else 'None'}")
    print()
    print("After move:")
    print(f"Side to move: {COLOR_NAMES[analysis.board_after.turn]}")
    print(f"Opponent in check: {analysis.gives_check}")
    print(f"Opponent checkmated: {analysis.gives_checkmate}")
    print(f"Stalemate: {analysis.stalemate}")
    print(f"FEN: {analysis.fen_after}")
    print()
    print("=== DESTINATION SQUARE SAFETY AFTER MOVE ===")
    safety = analysis.destination_safety
    print(f"Destination square: {square_name(safety.square)}")
    print(f"Geometrically attacked by opponent ({COLOR_NAMES[safety.attacker_color]}): {bool(safety.pseudo_attackers)}")
    if safety.pseudo_attackers:
        print("Pseudo attackers:")
        for sq in safety.pseudo_attackers:
            print(f"- {piece_label(analysis.board_after, sq)}")
    else:
        print("Pseudo attackers: none")
    print("Opponent legal captures on destination square:")
    if safety.legal_captures:
        for cap in safety.legal_captures:
            print(f"- {move_san(analysis.board_after, cap)} / {cap.uci()}")
    else:
        print("- none")
    print()
    print("=== OPPONENT IMMEDIATE THREAT CHECK AFTER MOVE ===")
    if analysis.gives_checkmate:
        print("Opponent mate-in-1: game over")
        print("Opponent direct checking moves: game over")
    else:
        if analysis.opponent_mate_in_one:
            print("WARNING: Opponent has mate-in-1:")
            for m in analysis.opponent_mate_in_one:
                print(f"- {move_san(analysis.board_after, m)} / {m.uci()}")
        else:
            print("Opponent mate-in-1: none")
        if analysis.opponent_direct_checks:
            print("Opponent direct checking moves:")
            for m in analysis.opponent_direct_checks:
                print(f"- {move_san(analysis.board_after, m)} / {m.uci()}")
        else:
            print("Opponent direct checking moves: none")
    print()
    print("=== FRIENDLY IMPORTANT PIECES AFTER MOVE ===")
    if analysis.gives_checkmate:
        print("Game over.")
    elif analysis.friendly_important_threats_after:
        for threat in analysis.friendly_important_threats_after:
            print_piece_threat(analysis.board_after, threat)
    else:
        print("No friendly important pieces are geometrically attacked.")
    print()
    print_unique_defender_loss_risks(board, analysis.board_after, analysis.unique_defender_loss_risks)
    if analysis.material_after:
        print_material_summary(analysis.material_after)


def legal_king_moves(board: chess.Board, color: bool) -> List[chess.Move]:
    moves: List[chess.Move] = []
    king_square = board.king(color)
    if king_square is None:
        return moves
    temp = board.copy(stack=False)
    temp.turn = color
    for move in list(temp.legal_moves):
        piece = temp.piece_at(move.from_square)
        if piece and piece.piece_type == chess.KING:
            moves.append(move)
    return moves


def analyze_king_safety(board: chess.Board, color: bool) -> KingSafety:
    king_square = board.king(color)
    if king_square is None:
        raise ValueError(f"No {COLOR_NAMES[color]} king found.")
    temp = board.copy(stack=False)
    temp.turn = color
    in_check = temp.is_check()
    checkmate = temp.is_checkmate()
    opponent = opposite(color)
    adjacent: List[Tuple[int, Optional[chess.Piece], bool, bool]] = []
    king_file = chess.square_file(king_square)
    king_rank = chess.square_rank(king_square)
    legal_king_move_targets = {m.to_square for m in legal_king_moves(board, color)}
    for df in [-1, 0, 1]:
        for dr in [-1, 0, 1]:
            if df == 0 and dr == 0:
                continue
            f = king_file + df
            r = king_rank + dr
            if 0 <= f <= 7 and 0 <= r <= 7:
                sq = chess.square(f, r)
                piece = board.piece_at(sq)
                attacked = bool(pseudo_attackers(board, opponent, sq))
                legal_move = sq in legal_king_move_targets
                adjacent.append((sq, piece, attacked, legal_move))
    legal_responses: List[chess.Move] = []
    if temp.is_check():
        legal_responses = list(temp.legal_moves)
    return KingSafety(color, king_square, in_check, checkmate, adjacent, legal_king_moves(board, color), legal_responses)


def print_king_safety(board: chess.Board, safety: KingSafety) -> None:
    color = safety.color
    opponent = opposite(color)
    print(f"=== KING SAFETY: {COLOR_NAMES[color].upper()} ===")
    print()
    print(f"{COLOR_NAMES[color]} king: {square_name(safety.king_square)}")
    print(f"In check: {safety.in_check}")
    print(f"Checkmate: {safety.checkmate}")
    print()
    print("Adjacent squares:")
    for sq, piece, attacked, legal_move in safety.adjacent:
        occupant = piece_label_from_piece(piece, sq) if piece else "empty"
        print(f"- {square_name(sq)}: {occupant}, attacked by {COLOR_NAMES[opponent]}: {attacked}, legal king move: {legal_move}")
    print()
    print("Legal king moves:")
    temp = board.copy(stack=False)
    temp.turn = color
    if safety.legal_king_moves:
        for move in safety.legal_king_moves:
            print(f"- {move_san(temp, move)} / {move.uci()}")
    else:
        print("- none")
    print()
    if safety.in_check:
        print("Legal responses to check:")
        if safety.legal_check_responses:
            for move in safety.legal_check_responses:
                print(f"- {move_san(temp, move)} / {move.uci()}")
        else:
            print("- none")
    else:
        print(f"{COLOR_NAMES[color]} is not currently in check.")
    print()


def analyze_next_threats(board: chess.Board, my_color: bool) -> Tuple[chess.Board, bool, List[NextThreatEntry]]:
    opponent = opposite(my_color)
    analysis_board = board.copy(stack=False)
    used_as_if_turn = False
    if analysis_board.turn != opponent:
        analysis_board.turn = opponent
        used_as_if_turn = True
    my_targets = {
        sq: piece
        for sq, piece in analysis_board.piece_map().items()
        if piece.color == my_color and piece.piece_type in IMPORTANT_PIECES
    }
    entries: List[NextThreatEntry] = []
    for move in list(analysis_board.legal_moves):
        moving_piece = analysis_board.piece_at(move.from_square)
        if moving_piece is None or moving_piece.color != opponent or moving_piece.piece_type not in NEXT_THREAT_MOVERS:
            continue
        san = move_san(analysis_board, move)
        captured_piece = analysis_board.piece_at(move.to_square)
        captured_info = None
        if captured_piece and captured_piece.color == my_color:
            captured_info = (move.to_square, captured_piece)
        after = analysis_board.copy(stack=False)
        after.push(move)
        attacked_targets: List[Tuple[int, chess.Piece]] = []
        for target_sq, target_piece in my_targets.items():
            if captured_info and captured_info[0] == target_sq:
                continue
            current_piece = after.piece_at(target_sq)
            if current_piece is None or current_piece.color != my_color:
                continue
            if pseudo_attackers(after, opponent, target_sq):
                attacked_targets.append((target_sq, current_piece))
        entry = NextThreatEntry(move, san, moving_piece, move.from_square, move.to_square, captured_info, after.is_check(), attacked_targets)
        if entry.captures or entry.gives_check or entry.attacked_important_targets:
            entries.append(entry)
    entries.sort(key=lambda e: (square_name(e.from_square), e.san))
    return analysis_board, used_as_if_turn, entries


def print_next_threats(board: chess.Board, my_color: bool) -> None:
    opponent = opposite(my_color)
    _, used_as_if_turn, entries = analyze_next_threats(board, my_color)
    print("=== OPPONENT ONE-MOVE IMPORTANT PIECE THREAT MAP ===")
    print(f"My side: {COLOR_NAMES[my_color]}")
    print(f"Opponent: {COLOR_NAMES[opponent]}")
    if used_as_if_turn:
        print("Turn note: analyzed as if opponent were to move next.")
    else:
        print("Turn note: opponent is the current side to move.")
    print()
    if not entries:
        print("No opponent Q/R/B/N one-move threats against important pieces found.")
        print()
        return
    for entry in entries:
        print(f"Opponent move: {entry.san} / {entry.move.uci()}")
        print(f"Moving piece: {piece_label_from_piece(entry.moving_piece, entry.from_square)} to {square_name(entry.to_square)}")
        if entry.captures:
            sq, piece = entry.captures
            print(f"Captures: {piece_label_from_piece(piece, sq)}")
        else:
            print("Captures: none")
        print(f"Gives check: {entry.gives_check}")
        if entry.attacked_important_targets:
            print("Attacks after move:")
            for sq, piece in entry.attacked_important_targets:
                print(f"- {piece_label_from_piece(piece, sq)}")
        else:
            print("Attacks after move: none")
        print()


def summarize_important_threats(threats: List[PieceThreat]) -> str:
    if not threats:
        return "none"
    return ",".join(f"{PIECE_NAMES[t.piece.piece_type]}{square_name(t.square)}" for t in threats)


def summarize_moves_for_table(board: Optional[chess.Board], moves: List[chess.Move]) -> str:
    if not moves:
        return "none"
    if board is None:
        return ",".join(m.uci() for m in moves)
    return ",".join(move_san(board, m) for m in moves)


def print_compare_table(board: chess.Board, analyses: List[CandidateAnalysis]) -> None:
    print("=== CANDIDATE MOVE COMPARISON ===")
    print()
    headers = ["Move", "Legal", "Check", "Mate", "Capture", "DestPseudo", "DestLegalCaptures", "OppMateIn1", "FriendlyImportantAttacked", "UniqueDefLost", "Material"]
    rows: List[List[str]] = []
    for a in analyses:
        if not a.legal:
            rows.append([a.input_text, "False", "-", "-", "-", "-", "-", "-", "-", "-", "-"])
            continue
        dest_pseudo = "False"
        dest_legal = "none"
        if a.destination_safety:
            dest_pseudo = str(bool(a.destination_safety.pseudo_attackers))
            dest_legal = summarize_moves_for_table(a.board_after, a.destination_safety.legal_captures)
        opp_mate = "game over" if a.gives_checkmate else summarize_moves_for_table(a.board_after, a.opponent_mate_in_one)
        friendly = "game over" if a.gives_checkmate else summarize_important_threats(a.friendly_important_threats_after)
        unique_loss = "game over" if a.gives_checkmate else unique_defender_loss_summary(a.unique_defender_loss_risks)
        material = material_balance_text(a.material_after) if a.material_after else "-"
        rows.append([a.input_text, "True", str(a.gives_check), str(a.gives_checkmate), str(a.capture), dest_pseudo, dest_legal, opp_mate, friendly, unique_loss, material])
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    print("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        print("  ".join(row[i].ljust(widths[i]) for i in range(len(headers))))
    print()
    illegal = [a for a in analyses if not a.legal]
    if illegal:
        print("Illegal move details:")
        for a in illegal:
            print(f"- {a.input_text}: {a.error}")
        print()



# ------------------------------------------------------------
# V3: Tactical tags, protection system, scan-all, and defender validity
# ------------------------------------------------------------

SLIDER_DIRECTIONS = {
    chess.ROOK: [(1, 0), (-1, 0), (0, 1), (0, -1)],
    chess.BISHOP: [(1, 1), (1, -1), (-1, 1), (-1, -1)],
    chess.QUEEN: [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)],
}

TACTICAL_TARGETS = {chess.KING, chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT}


@dataclass
class TacticalTag:
    tag: str
    detail: str


@dataclass
class PieceProtection:
    square: int
    piece: chess.Piece
    defenders: List[int] = field(default_factory=list)
    pseudo_attackers: List[int] = field(default_factory=list)
    pinned_defenders: List[int] = field(default_factory=list)

    @property
    def defender_count(self) -> int:
        return len(self.defenders)

    @property
    def undefended(self) -> bool:
        return len(self.defenders) == 0

    @property
    def attacked(self) -> bool:
        return bool(self.pseudo_attackers)

    @property
    def unattacked_but_undefended(self) -> bool:
        return self.undefended and not self.attacked


def piece_value(piece_type: int) -> int:
    return MATERIAL_VALUES.get(piece_type, 0)


def side_from_optional_text(text: Optional[str]) -> Optional[bool]:
    if text is None or text == "both":
        return None
    return color_from_text(text)


def selected_colors(side: Optional[bool]) -> List[bool]:
    return [chess.WHITE, chess.BLACK] if side is None else [side]


def analyze_piece_protection(board: chess.Board, square: int) -> Optional[PieceProtection]:
    piece = board.piece_at(square)
    if piece is None:
        return None
    defenders = effective_defenders(board, piece.color, square)
    pinned = absolute_pinned_defenders(board, piece.color, square)
    attackers = pseudo_attackers(board, opposite(piece.color), square)
    return PieceProtection(square=square, piece=piece, defenders=defenders, pseudo_attackers=attackers, pinned_defenders=pinned)


def protection_report(board: chess.Board, side: Optional[bool] = None, include_pawns: bool = False) -> List[PieceProtection]:
    items: List[PieceProtection] = []
    for color in selected_colors(side):
        for sq in important_piece_squares(board, color=color, include_pawns=include_pawns):
            item = analyze_piece_protection(board, sq)
            if item:
                items.append(item)
    return items


def print_piece_protection(board: chess.Board, item: PieceProtection) -> None:
    print(f"- {piece_label_from_piece(item.piece, item.square)}")
    print(f"  Defender count: {item.defender_count}")
    if item.defenders:
        print("  Effective defenders:")
        for sq in item.defenders:
            print(f"  - {piece_label(board, sq)}")
    else:
        print("  Effective defenders: none")
    if item.pinned_defenders:
        print("  Absolute-pinned pseudo defenders excluded:")
        for sq in item.pinned_defenders:
            print(f"  - {piece_label(board, sq)}")
    print(f"  Currently attacked by opponent: {item.attacked}")
    print(f"  Undefended: {item.undefended}")
    print(f"  Unattacked but undefended: {item.unattacked_but_undefended}")


def print_protection_report(board: chess.Board, items: List[PieceProtection], top: Optional[int], least: Optional[int]) -> None:
    print("=== PIECE PROTECTION REPORT ===")
    print()
    if not items:
        print("No matching pieces found.")
        print()
        return
    if top is not None:
        items = sorted(items, key=lambda x: (-x.defender_count, COLOR_NAMES[x.piece.color], square_name(x.square)))[:top]
        print(f"Sort: most protected, count: {top}")
    elif least is not None:
        items = sorted(items, key=lambda x: (x.defender_count, COLOR_NAMES[x.piece.color], square_name(x.square)))[:least]
        print(f"Sort: least protected, count: {least}")
    else:
        items = sorted(items, key=lambda x: (COLOR_NAMES[x.piece.color], square_name(x.square)))
        print("Sort: side and square")
    print()
    current_color: Optional[bool] = None
    for item in items:
        if item.piece.color != current_color:
            current_color = item.piece.color
            print(f"{COLOR_NAMES[current_color]} pieces:")
        print_piece_protection(board, item)
        print()


def undefended_report(board: chess.Board, side: Optional[bool] = None, include_pawns: bool = False, only_unattacked: bool = False) -> List[PieceProtection]:
    items = protection_report(board, side=side, include_pawns=include_pawns)
    filtered = [x for x in items if x.undefended]
    if only_unattacked:
        filtered = [x for x in filtered if x.unattacked_but_undefended]
    return filtered


def print_undefended_report(board: chess.Board, items: List[PieceProtection], only_unattacked: bool) -> None:
    title = "UNATTACKED BUT UNDEFENDED PIECES" if only_unattacked else "UNDEFENDED PIECES"
    print(f"=== {title} ===")
    print()
    if not items:
        print("No matching undefended pieces found.")
        print()
        return
    items = sorted(items, key=lambda x: (COLOR_NAMES[x.piece.color], square_name(x.square)))
    current_color: Optional[bool] = None
    for item in items:
        if item.piece.color != current_color:
            current_color = item.piece.color
            print(f"{COLOR_NAMES[current_color]}:")
        print_piece_protection(board, item)
        print()


def legal_moves_that_attack_square(board: chess.Board, mover_color: bool, target_square: int) -> List[chess.Move]:
    analysis_board = board.copy(stack=False)
    if analysis_board.turn != mover_color:
        analysis_board.turn = mover_color
    moves: List[chess.Move] = []
    for move in list(analysis_board.legal_moves):
        after = analysis_board.copy(stack=False)
        after.push(move)
        if target_square in pseudo_attackers(after, mover_color, target_square):
            # This branch is not used; kept for clarity.
            pass
        if pseudo_attackers(after, mover_color, target_square):
            moves.append(move)
    return moves


def legal_moves_that_attack_target(board: chess.Board, mover_color: bool, target_square: int) -> Tuple[chess.Board, bool, List[chess.Move]]:
    analysis_board = board.copy(stack=False)
    as_if = False
    if analysis_board.turn != mover_color:
        analysis_board.turn = mover_color
        as_if = True
    moves: List[chess.Move] = []
    for move in list(analysis_board.legal_moves):
        after = analysis_board.copy(stack=False)
        after.push(move)
        if after.piece_at(target_square) is None:
            # A legal capture of the target also counts as attacking it.
            if move.to_square == target_square:
                moves.append(move)
            continue
        if pseudo_attackers(after, mover_color, target_square):
            moves.append(move)
    return analysis_board, as_if, moves


def print_pawn_watch(board: chess.Board, my_color: bool) -> None:
    opponent = opposite(my_color)
    print("=== PAWN WATCH ===")
    print(f"My side: {COLOR_NAMES[my_color]}")
    print(f"Opponent: {COLOR_NAMES[opponent]}")
    print()

    for label, color, attacker in [
        ("Opponent undefended pawns", opponent, my_color),
        ("My undefended pawns", my_color, opponent),
    ]:
        print(f"{label}:")
        pawns = []
        for sq, piece in board.piece_map().items():
            if piece.color == color and piece.piece_type == chess.PAWN:
                item = analyze_piece_protection(board, sq)
                if item and item.undefended:
                    pawns.append(item)
        if not pawns:
            print("- none")
            print()
            continue
        for item in sorted(pawns, key=lambda x: square_name(x.square)):
            print(f"- {piece_label_from_piece(item.piece, item.square)}")
            print(f"  Currently attacked by {COLOR_NAMES[attacker]}: {bool(item.pseudo_attackers)}")
            attack_board, as_if, moves = legal_moves_that_attack_target(board, attacker, item.square)
            note = "as-if turn" if as_if else "current turn"
            print(f"  Legal moves by {COLOR_NAMES[attacker]} that would attack it ({note}):")
            if moves:
                for move in moves[:20]:
                    print(f"  - {move_san(attack_board, move)} / {move.uci()}")
                if len(moves) > 20:
                    print(f"  - ... {len(moves) - 20} more")
            else:
                print("  - none")
        print()


def ray_squares_from(square: int, df: int, dr: int) -> List[int]:
    result: List[int] = []
    f = chess.square_file(square) + df
    r = chess.square_rank(square) + dr
    while 0 <= f <= 7 and 0 <= r <= 7:
        result.append(chess.square(f, r))
        f += df
        r += dr
    return result


def line_piece_attacks(board: chess.Board, color: bool) -> Dict[Tuple[int, int], str]:
    attacks: Dict[Tuple[int, int], str] = {}
    for sq, piece in board.piece_map().items():
        if piece.color != color or piece.piece_type not in SLIDER_DIRECTIONS:
            continue
        for target in board.attacks(sq):
            target_piece = board.piece_at(target)
            if target_piece and target_piece.color != color and target_piece.piece_type in TACTICAL_TARGETS:
                attacks[(sq, target)] = f"{piece_label_from_piece(piece, sq)} attacks {piece_label_from_piece(target_piece, target)}"
    return attacks


def detect_fork_like(board: chess.Board, color: bool) -> List[TacticalTag]:
    tags: List[TacticalTag] = []
    opponent = opposite(color)
    for sq, piece in board.piece_map().items():
        if piece.color != color:
            continue
        targets: List[str] = []
        for target in board.attacks(sq):
            target_piece = board.piece_at(target)
            if target_piece and target_piece.color == opponent and target_piece.piece_type in TACTICAL_TARGETS:
                targets.append(piece_label_from_piece(target_piece, target))
        if len(targets) >= 2:
            tags.append(TacticalTag("fork-like", f"{piece_label_from_piece(piece, sq)} attacks {', '.join(targets)}."))
    return tags


def detect_line_patterns(board: chess.Board, color: bool) -> List[TacticalTag]:
    tags: List[TacticalTag] = []
    opponent = opposite(color)
    for sq, piece in board.piece_map().items():
        if piece.color != color or piece.piece_type not in SLIDER_DIRECTIONS:
            continue
        for df, dr in SLIDER_DIRECTIONS[piece.piece_type]:
            seen: List[Tuple[int, chess.Piece]] = []
            for ray_sq in ray_squares_from(sq, df, dr):
                ray_piece = board.piece_at(ray_sq)
                if ray_piece is None:
                    continue
                if ray_piece.color == color:
                    break
                if ray_piece.color == opponent:
                    seen.append((ray_sq, ray_piece))
                    if len(seen) >= 2:
                        break
            if len(seen) < 2:
                continue
            first_sq, first_piece = seen[0]
            second_sq, second_piece = seen[1]
            if second_piece.piece_type == chess.KING:
                tags.append(TacticalTag("pin", f"{piece_label_from_piece(piece, sq)} pins {piece_label_from_piece(first_piece, first_sq)} to {piece_label_from_piece(second_piece, second_sq)}."))
            elif second_piece.piece_type in {chess.QUEEN, chess.ROOK} and piece_value(second_piece.piece_type) > piece_value(first_piece.piece_type):
                tags.append(TacticalTag("relative-pin", f"{piece_label_from_piece(piece, sq)} attacks through {piece_label_from_piece(first_piece, first_sq)} toward {piece_label_from_piece(second_piece, second_sq)}."))
            if first_piece.piece_type in {chess.KING, chess.QUEEN, chess.ROOK} and second_piece.piece_type in TACTICAL_TARGETS:
                if piece_value(first_piece.piece_type) >= piece_value(second_piece.piece_type):
                    tags.append(TacticalTag("skewer-like", f"{piece_label_from_piece(piece, sq)} lines up {piece_label_from_piece(first_piece, first_sq)} and {piece_label_from_piece(second_piece, second_sq)}."))
    return tags


def detect_potential_overload(board: chess.Board, color: bool) -> List[TacticalTag]:
    defended_by: Dict[int, List[str]] = {}
    opponent = opposite(color)
    for target_sq, target_piece in board.piece_map().items():
        if target_piece.color != color or target_piece.piece_type not in {chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT}:
            continue
        defenders = pseudo_attackers(board, color, target_sq)
        attackers = pseudo_attackers(board, opponent, target_sq)
        # Keep this tag conservative: count a defensive task only if the target is currently attacked.
        if not attackers:
            continue
        for defender_sq in defenders:
            defender_piece = board.piece_at(defender_sq)
            if defender_piece and defender_piece.color == color:
                defended_by.setdefault(defender_sq, []).append(piece_label_from_piece(target_piece, target_sq))
    tags: List[TacticalTag] = []
    for defender_sq, targets in defended_by.items():
        if len(targets) >= 2:
            defender = board.piece_at(defender_sq)
            if defender:
                tags.append(TacticalTag("potential-overload", f"{piece_label_from_piece(defender, defender_sq)} has multiple defensive tasks: {', '.join(targets)}."))
    return tags


def detect_line_changes(before: chess.Board, after: chess.Board, color: bool, moved_from: Optional[int] = None, moved_to: Optional[int] = None) -> List[TacticalTag]:
    before_attacks = line_piece_attacks(before, color)
    after_attacks = line_piece_attacks(after, color)
    tags: List[TacticalTag] = []
    for key, detail in sorted(after_attacks.items(), key=lambda x: (square_name(x[0][0]), square_name(x[0][1]))):
        if key not in before_attacks:
            tags.append(TacticalTag("line-opened", detail + "."))
            # A discovered attack should come from a line piece that was already on its line,
            # not from the moved piece itself becoming the new attacker.
            if moved_from is not None and moved_to is not None and key[0] != moved_to:
                tags.append(TacticalTag("discovered-attack-like", detail + " after another piece moved off the line."))
    for key, detail in sorted(before_attacks.items(), key=lambda x: (square_name(x[0][0]), square_name(x[0][1]))):
        if key not in after_attacks:
            tags.append(TacticalTag("line-blocked", detail + " no longer applies."))
    return tags


def analyze_tactical_tags(board: chess.Board, color: Optional[bool] = None, before_board: Optional[chess.Board] = None, moved_from: Optional[int] = None, moved_to: Optional[int] = None) -> List[TacticalTag]:
    colors = selected_colors(color)
    tags: List[TacticalTag] = []
    for c in colors:
        tags.extend(detect_fork_like(board, c))
        tags.extend(detect_line_patterns(board, c))
        tags.extend(detect_potential_overload(board, c))
        if before_board is not None:
            tags.extend(detect_line_changes(before_board, board, c, moved_from=moved_from, moved_to=moved_to))
    # Deduplicate while preserving order.
    seen = set()
    unique: List[TacticalTag] = []
    for tag in tags:
        key = (tag.tag, tag.detail)
        if key not in seen:
            seen.add(key)
            unique.append(tag)
    return unique


def tactical_tag_summary(tags: List[TacticalTag], max_items: int = 4) -> str:
    if not tags:
        return "none"
    names = []
    for tag in tags:
        if tag.tag not in names:
            names.append(tag.tag)
    text = ",".join(names[:max_items])
    if len(names) > max_items:
        text += ",..."
    return text


def print_tactical_tags(tags: List[TacticalTag], title: str = "TACTICAL TAGS") -> None:
    print(f"=== {title} ===")
    print("These tags are mechanical annotations, not move recommendations.")
    print()
    if not tags:
        print("No tactical tags detected.")
        print()
        return
    for tag in tags:
        print(f"- {tag.tag}: {tag.detail}")
    print()


def friendly_undefended_count_after(board_after: chess.Board, color: bool, include_pawns: bool = False) -> int:
    return len(undefended_report(board_after, side=color, include_pawns=include_pawns, only_unattacked=False))


def scan_all_legal_moves(board: chess.Board) -> List[CandidateAnalysis]:
    analyses: List[CandidateAnalysis] = []
    for move in list(board.legal_moves):
        san = move_san(board, move)
        analyses.append(analyze_candidate_move(board, san))
    return analyses


def move_piece_type_symbol(board: chess.Board, analysis: CandidateAnalysis) -> str:
    if analysis.from_square is None:
        return "-"
    piece = board.piece_at(analysis.from_square)
    if piece is None:
        return "-"
    return PIECE_NAMES[piece.piece_type]


def print_scan_all_table(board: chess.Board, analyses: List[CandidateAnalysis], args: argparse.Namespace) -> None:
    side = board.turn
    filtered: List[Tuple[CandidateAnalysis, List[TacticalTag], int]] = []
    for a in analyses:
        if not a.legal or a.move is None or a.board_after is None:
            continue
        if args.checks and not a.gives_check:
            continue
        if args.captures and not a.capture:
            continue
        if args.safe_destination and a.destination_safety and a.destination_safety.legal_captures:
            continue
        if args.from_square and square_name(a.move.from_square) != args.from_square.lower():
            continue
        if args.piece:
            p = board.piece_at(a.move.from_square)
            if not p or PIECE_NAMES[p.piece_type].upper() != args.piece.upper():
                continue
        tags = analyze_tactical_tags(a.board_after, color=side, before_board=board, moved_from=a.move.from_square, moved_to=a.move.to_square)
        if args.with_tags and not tags:
            continue
        undef_count = friendly_undefended_count_after(a.board_after, side, include_pawns=False)
        filtered.append((a, tags, undef_count))

    filtered.sort(key=lambda item: (not item[0].gives_check, not item[0].capture, tactical_tag_summary(item[1]) == "none", item[0].san or item[0].input_text))
    if args.limit is not None:
        filtered = filtered[:args.limit]

    print("=== EXHAUSTIVE LEGAL MOVE SCAN ===")
    print("Sort order is mechanical, not a recommendation.")
    print(f"Side to move: {COLOR_NAMES[side]}")
    print(f"Legal moves scanned: {len(analyses)}")
    print(f"Rows shown: {len(filtered)}")
    print()

    headers = ["Move", "Piece", "Capture", "Check", "Mate", "DestLegalCaptures", "OppMateIn1", "FriendlyImportant", "UniqueDefLost", "UndefAfter", "TacticalTags"]
    rows: List[List[str]] = []
    for a, tags, undef_count in filtered:
        dest_caps = summarize_moves_for_table(a.board_after, a.destination_safety.legal_captures if a.destination_safety else [])
        opp_mate = "game over" if a.gives_checkmate else summarize_moves_for_table(a.board_after, a.opponent_mate_in_one)
        friendly = "game over" if a.gives_checkmate else summarize_important_threats(a.friendly_important_threats_after)
        unique_loss = "game over" if a.gives_checkmate else unique_defender_loss_summary(a.unique_defender_loss_risks)
        rows.append([
            a.san or a.input_text,
            move_piece_type_symbol(board, a),
            str(a.capture),
            str(a.gives_check),
            str(a.gives_checkmate),
            dest_caps,
            opp_mate,
            friendly,
            unique_loss,
            str(undef_count),
            tactical_tag_summary(tags),
        ])
    if not rows:
        print("No moves matched the selected filters.")
        print()
        return
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], min(len(cell), 40))
    def clip(s: str, width: int) -> str:
        return s if len(s) <= width else s[: max(0, width - 3)] + "..."
    print("  ".join(headers[i].ljust(widths[i]) for i in range(len(headers))))
    print("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        print("  ".join(clip(row[i], widths[i]).ljust(widths[i]) for i in range(len(headers))))
    print()


# ------------------------------------------------------------
# ChessGuard command handlers
# ------------------------------------------------------------

def command_board(args: argparse.Namespace) -> None:
    board = load_board_from_text(args.moves)
    print_position_summary(board, include_material=True)


def command_material(args: argparse.Namespace) -> None:
    board = load_board_from_text(args.moves)
    print_material_summary(material_summary(board))


def command_move(args: argparse.Namespace) -> None:
    board = load_board_from_text(args.moves)
    print_position_summary(board, include_material=True)
    analysis = analyze_candidate_move(board, args.move)
    print_candidate_analysis(board, analysis)
    if analysis.legal and analysis.board_after is not None and analysis.move is not None:
        moving_piece = board.piece_at(analysis.move.from_square)
        color = moving_piece.color if moving_piece else board.turn
        tags = analyze_tactical_tags(analysis.board_after, color=color, before_board=board, moved_from=analysis.move.from_square, moved_to=analysis.move.to_square)
        print_tactical_tags(tags, title="TACTICAL TAGS AFTER MOVE")


def command_compare(args: argparse.Namespace) -> None:
    board = load_board_from_text(args.moves)
    print_position_summary(board, include_material=True)
    analyses = [analyze_candidate_move(board, mv) for mv in args.candidates]
    print_compare_table(board, analyses)
    print("Tactical tag summaries:")
    for analysis in analyses:
        if analysis.legal and analysis.board_after is not None and analysis.move is not None:
            moving_piece = board.piece_at(analysis.move.from_square)
            color = moving_piece.color if moving_piece else board.turn
            tags = analyze_tactical_tags(analysis.board_after, color=color, before_board=board, moved_from=analysis.move.from_square, moved_to=analysis.move.to_square)
            print(f"- {analysis.input_text}: {tactical_tag_summary(tags)}")
        else:
            print(f"- {analysis.input_text}: illegal")
    print()
    if args.verbose:
        for analysis in analyses:
            print_candidate_analysis(board, analysis)


def command_attack(args: argparse.Namespace) -> None:
    board = load_board_from_text(args.moves)
    print_position_summary(board, include_material=True)
    attacker_color = color_from_text(args.color)
    sq = chess.parse_square(args.square.lower())
    print_square_safety(board, analyze_square_safety(board, sq, attacker_color))


def command_attack_after(args: argparse.Namespace) -> None:
    board = load_board_from_text(args.moves)
    print_position_summary(board, include_material=True)
    analysis = analyze_candidate_move(board, args.move)
    if not analysis.legal:
        print_candidate_analysis(board, analysis)
        return
    assert analysis.board_after is not None
    attacker_color = color_from_text(args.color)
    sq = chess.parse_square(args.square.lower())
    safety = analyze_square_safety(analysis.board_after, sq, attacker_color)
    print("=== ATTACK CHECK AFTER CANDIDATE MOVE ===")
    print(f"Candidate move: {analysis.san} / {analysis.uci}")
    print("Board after move:")
    print(ascii_board(analysis.board_after))
    print()
    print_square_safety(analysis.board_after, safety)


def command_threatened_pieces(args: argparse.Namespace) -> None:
    board = load_board_from_text(args.moves)
    print_position_summary(board, include_material=True)
    side = color_from_text(args.side) if args.side else None
    threats = threatened_pieces_report(board, side=side, include_pawns=args.include_pawns)
    print("=== THREATENED IMPORTANT PIECES ===")
    print()
    if not threats:
        print("No important pieces are geometrically attacked.")
        print()
        return
    current_color: Optional[bool] = None
    for threat in threats:
        if threat.piece.color != current_color:
            current_color = threat.piece.color
            print(f"{COLOR_NAMES[current_color]} important pieces:")
        print_piece_threat(board, threat)
        print()


def command_next_threats(args: argparse.Namespace) -> None:
    board = load_board_from_text(args.moves)
    print_position_summary(board, include_material=True)
    print_next_threats(board, color_from_text(args.me))


def command_king_safety(args: argparse.Namespace) -> None:
    board = load_board_from_text(args.moves)
    print_position_summary(board, include_material=True)
    print_king_safety(board, analyze_king_safety(board, color_from_text(args.color)))


def command_tactical_tags(args: argparse.Namespace) -> None:
    board = load_board_from_text(args.moves)
    print_position_summary(board, include_material=True)
    side = side_from_optional_text(args.side)
    tags = analyze_tactical_tags(board, color=side)
    print_tactical_tags(tags)


def command_tactical_tags_after(args: argparse.Namespace) -> None:
    board = load_board_from_text(args.moves)
    print_position_summary(board, include_material=True)
    analysis = analyze_candidate_move(board, args.move)
    if not analysis.legal:
        print_candidate_analysis(board, analysis)
        return
    assert analysis.board_after is not None and analysis.move is not None
    moving_piece = board.piece_at(analysis.move.from_square)
    color = moving_piece.color if moving_piece else board.turn
    print(f"Candidate move: {analysis.san} / {analysis.uci}")
    tags = analyze_tactical_tags(analysis.board_after, color=color, before_board=board, moved_from=analysis.move.from_square, moved_to=analysis.move.to_square)
    print_tactical_tags(tags, title="TACTICAL TAGS AFTER MOVE")


def command_protection(args: argparse.Namespace) -> None:
    board = load_board_from_text(args.moves)
    print_position_summary(board, include_material=True)
    side = side_from_optional_text(args.side)
    items = protection_report(board, side=side, include_pawns=args.include_pawns)
    print_protection_report(board, items, top=args.top, least=args.least)


def command_undefended(args: argparse.Namespace) -> None:
    board = load_board_from_text(args.moves)
    print_position_summary(board, include_material=True)
    side = side_from_optional_text(args.side)
    items = undefended_report(board, side=side, include_pawns=args.include_pawns, only_unattacked=args.only_unattacked)
    print_undefended_report(board, items, only_unattacked=args.only_unattacked)


def command_pawn_watch(args: argparse.Namespace) -> None:
    board = load_board_from_text(args.moves)
    print_position_summary(board, include_material=True)
    print_pawn_watch(board, color_from_text(args.me))


def command_scan_all(args: argparse.Namespace) -> None:
    board = load_board_from_text(args.moves)
    print_position_summary(board, include_material=True)
    analyses = scan_all_legal_moves(board)
    print_scan_all_table(board, analyses, args)


# ------------------------------------------------------------
# ChessGuard CLI parser
# ------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ChessGuard: a lightweight chess safety audit tool for humans and AI agents.")
    parser.add_argument("--version", action="version", version=f"{PROJECT_NAME} {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_board = sub.add_parser("board", help="Rebuild position and print ASCII board.")
    p_board.add_argument("moves", help="PGN-like SAN move text.")
    p_board.set_defaults(func=command_board)

    p_material = sub.add_parser("material", help="Print material count.")
    p_material.add_argument("moves", help="PGN-like SAN move text.")
    p_material.set_defaults(func=command_material)

    p_move = sub.add_parser("move", help="Check candidate move legality and safety.")
    p_move.add_argument("moves", help="PGN-like SAN move text.")
    p_move.add_argument("move", help="Candidate move in SAN or UCI.")
    p_move.set_defaults(func=command_move)

    p_compare = sub.add_parser("compare", help="Compare multiple candidate moves.")
    p_compare.add_argument("moves", help="PGN-like SAN move text.")
    p_compare.add_argument("candidates", nargs="+", help="Candidate moves in SAN or UCI.")
    p_compare.add_argument("--me", choices=["white", "black", "w", "b"], help="Optional user side label.")
    p_compare.add_argument("--verbose", action="store_true", help="Print full reports after the summary table.")
    p_compare.set_defaults(func=command_compare)

    p_attack = sub.add_parser("attack", help="Check whether a square is attacked in current position.")
    p_attack.add_argument("moves", help="PGN-like SAN move text.")
    p_attack.add_argument("square", help="Square to check, e.g. g7.")
    p_attack.add_argument("color", help="Attacking color: white/black or w/b.")
    p_attack.set_defaults(func=command_attack)

    p_attack_after = sub.add_parser("attack-after", help="Simulate candidate move, then check square safety.")
    p_attack_after.add_argument("moves", help="PGN-like SAN move text.")
    p_attack_after.add_argument("move", help="Candidate move in SAN or UCI.")
    p_attack_after.add_argument("square", help="Square to check after move, e.g. g7.")
    p_attack_after.add_argument("color", help="Attacking color after move: white/black or w/b.")
    p_attack_after.set_defaults(func=command_attack_after)

    p_threat = sub.add_parser("threatened-pieces", help="Report threatened important pieces.")
    p_threat.add_argument("moves", help="PGN-like SAN move text.")
    p_threat.add_argument("--side", choices=["white", "black", "w", "b"], help="Only report one side.")
    p_threat.add_argument("--include-pawns", action="store_true", help="Include pawns in the report.")
    p_threat.set_defaults(func=command_threatened_pieces)

    p_next = sub.add_parser("next-threats", help="Report opponent one-move important-piece threats.")
    p_next.add_argument("moves", help="PGN-like SAN move text.")
    p_next.add_argument("--me", required=True, choices=["white", "black", "w", "b"], help="User side.")
    p_next.set_defaults(func=command_next_threats)

    p_king = sub.add_parser("king-safety", help="Report king safety for a selected side.")
    p_king.add_argument("moves", help="PGN-like SAN move text.")
    p_king.add_argument("color", choices=["white", "black", "w", "b"], help="King color to inspect.")
    p_king.set_defaults(func=command_king_safety)

    p_tags = sub.add_parser("tactical-tags", help="Report tactical tags in the current position.")
    p_tags.add_argument("moves", help="PGN-like SAN move text.")
    p_tags.add_argument("--side", default="both", choices=["white", "black", "w", "b", "both"], help="Side to inspect.")
    p_tags.set_defaults(func=command_tactical_tags)

    p_tags_after = sub.add_parser("tactical-tags-after", help="Report tactical tags after a candidate move.")
    p_tags_after.add_argument("moves", help="PGN-like SAN move text.")
    p_tags_after.add_argument("move", help="Candidate move in SAN or UCI.")
    p_tags_after.set_defaults(func=command_tactical_tags_after)

    p_protection = sub.add_parser("protection", help="Report piece protection and defender counts.")
    p_protection.add_argument("moves", help="PGN-like SAN move text.")
    p_protection.add_argument("--side", default="both", choices=["white", "black", "w", "b", "both"], help="Side to inspect.")
    p_protection.add_argument("--top", type=int, help="Show the most protected N pieces.")
    p_protection.add_argument("--least", type=int, help="Show the least protected N pieces.")
    p_protection.add_argument("--include-pawns", action="store_true", help="Include pawns.")
    p_protection.set_defaults(func=command_protection)

    p_undef = sub.add_parser("undefended", help="Report undefended pieces.")
    p_undef.add_argument("moves", help="PGN-like SAN move text.")
    p_undef.add_argument("--side", default="both", choices=["white", "black", "w", "b", "both"], help="Side to inspect.")
    p_undef.add_argument("--include-pawns", action="store_true", help="Include pawns.")
    p_undef.add_argument("--only-unattacked", action="store_true", help="Only show pieces that are both unattacked and undefended.")
    p_undef.set_defaults(func=command_undefended)

    p_pawn = sub.add_parser("pawn-watch", help="Report undefended pawns and legal moves that would attack them.")
    p_pawn.add_argument("moves", help="PGN-like SAN move text.")
    p_pawn.add_argument("--me", required=True, choices=["white", "black", "w", "b"], help="User side.")
    p_pawn.set_defaults(func=command_pawn_watch)

    p_scan = sub.add_parser("scan-all", help="Scan all legal moves for the side to move.")
    p_scan.add_argument("moves", help="PGN-like SAN move text.")
    p_scan.add_argument("--checks", action="store_true", help="Only show checking moves.")
    p_scan.add_argument("--captures", action="store_true", help="Only show captures.")
    p_scan.add_argument("--safe-destination", action="store_true", help="Only show moves whose destination has no legal capture by opponent.")
    p_scan.add_argument("--with-tags", action="store_true", help="Only show moves that create tactical tags.")
    p_scan.add_argument("--from", dest="from_square", help="Only show moves from this square, e.g. e6.")
    p_scan.add_argument("--piece", choices=["K", "Q", "R", "B", "N", "P"], help="Only show moves by this piece type.")
    p_scan.add_argument("--limit", type=int, help="Limit the number of displayed rows.")
    p_scan.set_defaults(func=command_scan_all)

    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except chess.InvalidMoveError as exc:
        print(f"ERROR: Invalid move: {exc}", file=sys.stderr)
        return 2
    except chess.IllegalMoveError as exc:
        print(f"ERROR: Illegal move: {exc}", file=sys.stderr)
        return 2
    except chess.AmbiguousMoveError as exc:
        print(f"ERROR: Ambiguous move: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
