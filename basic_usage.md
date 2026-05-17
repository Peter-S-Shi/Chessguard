# Basic Usage Examples

This document shows simple command-line examples for ChessGuard.

ChessGuard is a move-safety audit tool. It does not choose the best move like a chess engine. Instead, it verifies board state, legal moves, tactical risks, destination-square safety, recaptures, checks, and immediate threats.

---

## 1. Print the current board

```bash
python chessguard.py board "1. e4 e5 2. Nf3 Nc6"
```

Expected purpose:

- rebuild the position from SAN-like move text;
- print a coordinate ASCII board;
- show side to move;
- show check, checkmate, stalemate status;
- show FEN;
- show material count.

---

## 2. Check a candidate move

```bash
python chessguard.py move "1. e4 e5 2. Nf3 Nc6" "Bb5"
```

Expected purpose:

- verify whether `Bb5` is legal;
- print SAN and UCI forms;
- simulate the move;
- check whether the destination square is attacked;
- report opponent mate-in-1 threats;
- report opponent direct checking moves;
- report friendly important pieces under attack after the move;
- report unique-defender loss risks.

---

## 3. Compare multiple candidate moves

```bash
python chessguard.py compare "1. e4 e5 2. Nf3 Nc6" "Bb5" "Bc4" "d4" "Nc3"
```

Expected purpose:

- compare several legal or illegal candidate moves;
- highlight immediate tactical safety facts;
- help a human or AI advisor avoid obviously unsafe moves before strategic judgment.

---

## 4. Check whether a square is attacked

```bash
python chessguard.py attack "1. e4 e5 2. Nf3 Nc6" e5 white
```

Expected purpose:

- check whether `e5` is geometrically attacked by White;
- distinguish attack patterns from legal captures when appropriate.

---

## 5. Check attack status after a candidate move

```bash
python chessguard.py attack-after "1. e4 e5 2. Nf3 Nc6" "Bb5" c6 white
```

Expected purpose:

- simulate `Bb5`;
- then check whether `c6` is attacked by White;
- useful for testing pins, pressure, and tactical consequences.

---

## 6. Inspect king safety

```bash
python chessguard.py king "1. e4 e5 2. Nf3 Nc6" black
```

Expected purpose:

- locate the king;
- report whether the king is in check;
- list adjacent squares;
- show whether adjacent squares are attacked;
- show legal king moves;
- show legal responses if the king is currently in check.

---

## 7. Scan all legal moves

```bash
python chessguard.py scan-all "1. e4 e5 2. Nf3 Nc6"
```

Expected purpose:

- scan every legal move in the current position;
- provide a broad tactical safety overview;
- useful for humans or AI agents when candidate generation is uncertain.

---

## 8. AI Agent integration idea

A simple agent workflow can be:

1. The AI model generates several candidate moves.
2. ChessGuard checks each candidate mechanically.
3. The AI model discards illegal or tactically critical moves.
4. The AI model chooses among the remaining safe candidates using strategic reasoning.

Example conceptual flow:

```text
LLM candidate generation
        ↓
ChessGuard legality and safety audit
        ↓
Risk filtering
        ↓
LLM strategic explanation
        ↓
Final move recommendation
```

ChessGuard is designed to be a guardrail, not a replacement for chess understanding.
