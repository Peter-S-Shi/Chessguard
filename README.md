# ChessGuard

**A lightweight chess safety audit tool for humans and AI agents.**

ChessGuard is a command-line tool that helps verify whether a chess move is legal, safe, and tactically trustworthy before it is played. It is designed for human chess advisors, chess learners, and AI agents that need a mechanical validation layer without relying on an external chess engine, opening book, or tablebase.

ChessGuard does **not** try to replace engines such as Stockfish. Instead, it focuses on a narrower and practical mission:

> Before trusting a candidate move, check whether it is legal, whether the destination square is safe, whether the move allows immediate tactical punishment, and whether important pieces lose critical protection.

---

## Why ChessGuard?

Large language models can discuss chess plans and generate candidate moves, but they can also make chess-specific mistakes:

- forgetting the current board state;
- suggesting illegal moves;
- missing blocked lines for bishops, rooks, or queens;
- overlooking that a destination square is attacked;
- assuming a piece is defended when its defender is absolutely pinned;
- ignoring whether a capture has a legal recapture;
- moving a defender away and leaving another important piece tactically exposed;
- missing immediate checks, mate-in-one threats, or forced tactical replies.

ChessGuard acts as a **mechanical safety layer** between strategic reasoning and move execution. A human or AI advisor can propose moves, and ChessGuard audits the concrete tactical facts.

---

## What ChessGuard Is Not

ChessGuard is **not a chess engine**.

It does not:

- choose the objectively best move;
- evaluate positions like Stockfish;
- search deep tactical trees by default;
- use opening books;
- use endgame tablebases;
- claim that a mechanically safe move is strategically best.

ChessGuard is best understood as a **rule-based and tactical audit tool**. It helps prevent obvious tactical and legality failures, especially in human + AI or AI-agent chess workflows.

---

## Core Features

ChessGuard can:

- rebuild a position from PGN-like SAN move text;
- print a coordinate ASCII board;
- count material;
- validate candidate moves in SAN or UCI format;
- compare multiple candidate moves;
- distinguish geometric attacks from legal captures;
- check destination-square safety after a move;
- report opponent mate-in-one threats after a candidate move;
- report opponent direct checking moves;
- report threatened important pieces;
- report legal recaptures after captures;
- inspect king safety and legal check responses;
- report opponent one-move important-piece threat maps;
- report tactical tags;
- report protection and defender counts;
- report undefended pieces;
- watch undefended pawns and possible attacks on them;
- scan all legal moves with filters;
- exclude ineffective defenders caused by absolute pins;
- report risks where a move removes the only effective defender of an attacked important piece.

---

## Installation

ChessGuard currently depends on `python-chess`.

```bash
pip install chess
```

Then run:

```bash
python chessguard.py --version
```

Expected output:

```text
ChessGuard 3.0.0
```

---

## Basic Usage

### Print the current board

```bash
python chessguard.py board "1. e4 e5 2. Nf3 Nc6 3. Bb5"
```

This rebuilds the position and prints a coordinate ASCII board.

---

### Check a candidate move

```bash
python chessguard.py move "1. e4 e5 2. Nf3 Nc6" "Bb5"
```

ChessGuard reports:

- whether the move is legal;
- SAN and UCI notation;
- whether it gives check or checkmate;
- whether the destination square is attacked;
- whether the opponent has mate-in-one;
- whether the opponent has direct checking moves;
- whether friendly important pieces become tactically exposed;
- whether an attacked important piece loses its only effective defender.

---

### Compare multiple candidate moves

```bash
python chessguard.py compare "1. e4 e5 2. Nf3 Nc6 3. c3 Nf6" "d4" "Bb5" "Bc4" --me white
```

Use `--verbose` for full reports:

```bash
python chessguard.py compare "1. e4 e5 2. Nf3 Nc6" "Bb5" "Bc4" "d4" --me white --verbose
```

---

### Check whether a square is attacked

```bash
python chessguard.py attack "1. e4 e5 2. Nf3 Nc6" e5 white
```

This checks whether White attacks `e5` in the current position.

---

### Check square safety after a move

```bash
python chessguard.py attack-after "1. e4 e5 2. Nf3 Nc6" "Bb5" c6 white
```

This simulates the candidate move first, then checks whether the selected square is attacked.

---

### Report threatened important pieces

```bash
python chessguard.py threatened-pieces "1. e4 e5 2. Nf3 Nc6 3. Bb5" --side black
```

Important pieces include:

- king;
- queen;
- rooks;
- bishops;
- knights.

Pawns can be included with:

```bash
python chessguard.py threatened-pieces "1. e4 e5" --side black --include-pawns
```

---

### Inspect king safety

```bash
python chessguard.py king-safety "1. e4 e5 2. Qh5" black
```

ChessGuard reports:

- king location;
- whether the king is in check;
- whether it is checkmate;
- adjacent king squares;
- whether adjacent squares are attacked;
- legal king moves;
- legal responses to check, if applicable.

---

### Scan all legal moves

```bash
python chessguard.py scan-all "1. e4 e5 2. Nf3 Nc6"
```

Useful filters:

```bash
python chessguard.py scan-all "1. e4 e5 2. Nf3 Nc6" --checks
python chessguard.py scan-all "1. e4 e5 2. Nf3 Nc6" --captures
python chessguard.py scan-all "1. e4 e5 2. Nf3 Nc6" --safe-destination
python chessguard.py scan-all "1. e4 e5 2. Nf3 Nc6" --piece N
python chessguard.py scan-all "1. e4 e5 2. Nf3 Nc6" --from f3
python chessguard.py scan-all "1. e4 e5 2. Nf3 Nc6" --limit 10
```

---

## Example Output Philosophy

ChessGuard is intentionally explicit. It reports tactical facts instead of giving vague advice.

For example, a candidate move report may include:

```text
Input: Nc6
Legal: True
SAN: Nc6
UCI: b8c6
Destination square: c6
Geometrically attacked by opponent: False
Opponent legal captures on destination square:
- none
Opponent mate-in-1: none
Opponent direct checking moves: none
```

The goal is to make every recommendation auditable.

---

## AI Agent Use Case

ChessGuard is especially useful as a tool layer for AI chess agents.

A possible agent workflow:

1. The AI model reads the current PGN or move history.
2. The AI proposes several candidate moves.
3. ChessGuard validates each candidate.
4. The AI filters out illegal or tactically dangerous moves.
5. The AI explains the remaining candidate moves in human language.
6. A human or agent chooses the final move.

In this workflow, ChessGuard does not replace the AI model. It gives the model a reliable tactical checkpoint.

---

## Recommended AI Advisor Workflow

ChessGuard is designed to be used as a mechanical checkpoint inside a human + AI or AI-agent chess workflow.

The AI advisor should not simply generate a move and trust its own explanation. Each turn should follow a repeatable audit sequence:

### 1. Update the move record

Record the latest move from the opponent and update the full move history.

The AI should treat the move list as the source of truth. Before evaluating a position, it should rebuild the board from the current PGN-like move text rather than relying on memory.

Example:

```bash
python chessguard.py board "1. e4 e5 2. Nf3 Nc6 3. c3 Nf6"
```

The purpose of this step is to confirm:

- the current board state;
- the side to move;
- whether either king is in check;
- material balance;
- FEN;
- the coordinate ASCII board.

---

### 2. Read the current position before recommending anything

After ChessGuard prints the current position, the AI should first explain the concrete position:

- whose turn it is;
- whether the side to move is in check;
- whether any important piece is currently attacked;
- whether the opponent has immediate threats;
- whether the position is tactically quiet or forcing.

The AI should not recommend a move until this board-state check is complete.

---

### 3. Identify candidate moves

The AI should generate a small set of candidate moves before choosing one.

Typical candidate groups:

- forcing moves: checks, captures, direct threats;
- defensive moves: escaping check, saving attacked pieces, defending key squares;
- development moves: improving inactive pieces;
- strategic moves: pawn breaks, central control, king safety, file control;
- tactical continuations: recaptures, pins, discovered attacks, promotion threats.

For uncertain positions, the AI should use `scan-all` or compare more candidates instead of relying on a single intuition.

Example:

```bash
python chessguard.py compare "1. e4 e5 2. Nf3 Nc6" "Bb5" "Bc4" "d4" --me white
```

---

### 4. Audit every serious candidate with ChessGuard

For each serious candidate, ChessGuard should be used to check mechanical safety:

```bash
python chessguard.py move "<move history>" "<candidate move>"
```

The AI should verify:

- whether the move is legal;
- whether the route is blocked for bishops, rooks, or queens;
- whether the move gives check or checkmate;
- whether the destination square is geometrically attacked;
- whether the opponent has a legal capture on the destination square;
- whether the opponent has mate-in-one after the move;
- whether the opponent has direct checking moves;
- whether friendly important pieces become attacked after the move;
- whether an attacked piece loses its only effective defender;
- whether defenders are real defenders or only pseudo-defenders blocked by absolute pins.

---

### 5. Distinguish danger from acceptable exchange

A destination square being attacked does not automatically mean a move is bad.

The AI must ask:

- If the piece is captured, do we have a legal recapture?
- Is the recapturing piece actually able to move, or is it pinned?
- Is the exchange materially favorable, equal, or losing?
- Does the exchange improve or damage king safety?
- Does the move remove the only defender of another important piece?

This is especially important for positions where a move is tactically allowed but strategically risky.

---

### 6. Simulate the opponent's best reply

After choosing a likely best candidate, the AI should imagine the opponent's most forcing replies:

- checks;
- captures;
- threats against queen, rooks, bishops, knights, or king;
- pawn breaks;
- promotion threats;
- recaptures;
- moves that attack the moved piece.

In tactical or endgame positions, the AI should perform at least a simple three-ply logic:

```text
our candidate move
        ↓
opponent's strongest reply
        ↓
our planned answer
```

This prevents the AI from recommending moves that are legal on move one but collapse after an obvious reply.

---

### 7. Validate checkmate claims separately

Any claimed checkmate must be verified square by square.

The AI should confirm:

- the checked king has no legal king move;
- the checking piece cannot be captured;
- the checking line cannot be blocked;
- all escape squares are controlled;
- the king is not allowed to capture the checking piece;
- the move is legal and the checking line is not blocked.

A move that gives check is not automatically safe, and a move written with `#` should not be trusted until escape squares are verified.

---

### 8. Produce the final recommendation

Only after the above checks should the AI make a final recommendation.

A good final answer should include:

- the recommended move;
- whether ChessGuard found it legal;
- the key safety result;
- the main opponent reply to watch;
- the planned response if the opponent chooses the forcing line;
- a short strategic reason.

The AI should be honest about uncertainty. If ChessGuard reports tactical danger, the AI should either reject the candidate or clearly explain why the danger is acceptable.

---

### 9. Post-move update

After the user plays the recommended move, the move must be added to the move record.

Then the next turn begins again from step 1.

The workflow is cyclical:

```text
update move history
        ↓
rebuild board with ChessGuard
        ↓
read current position
        ↓
generate candidates
        ↓
audit candidates
        ↓
simulate opponent reply
        ↓
recommend move
        ↓
record move
        ↓
repeat
```

---

### Practical Principle

ChessGuard should be used before the AI trusts a move, not after the move has already been justified.

The AI may provide strategic judgment, but legality, route safety, destination-square danger, recapture logic, immediate checks, mate threats, pinned defenders, and defender-loss risks should be mechanically verified whenever possible.

---

## Design Philosophy

ChessGuard follows a simple principle:

> Strategy can be discussed. Legality and immediate tactical safety should be mechanically verified.

This is especially important in chess conversations involving large language models. A model may produce convincing strategic language while missing a concrete tactical detail. ChessGuard makes those details visible.

The project intentionally separates two roles:

| Role | Responsibility |
|---|---|
| Human or AI advisor | strategy, plans, candidate generation, explanation |
| ChessGuard | legality, board reconstruction, tactical safety, defender logic, immediate threats |

---

## Current Limitations

ChessGuard is still a lightweight audit tool.

Known limitations:

- It does not perform full engine evaluation.
- It does not guarantee that a safe move is the best move.
- It does not perform deep forced-mate search by default.
- It does not use an opening database.
- It does not use endgame tablebases.
- Its tactical reports are only as good as the current implemented rule checks.

A move can pass ChessGuard and still be strategically poor. ChessGuard prevents many concrete mistakes, but it does not replace chess judgment.

---

## Roadmap

Possible future development:

### v4: Agent Mode

- structured JSON output;
- machine-readable risk reports;
- clearer integration with AI agent tool calls;
- stable output schema.

### v5: Risk Levels

Add simple tactical risk ratings:

- `LOW`
- `MEDIUM`
- `HIGH`
- `CRITICAL`

Example criteria:

- `CRITICAL`: candidate allows opponent mate-in-one;
- `HIGH`: candidate hangs queen or rook without recapture;
- `MEDIUM`: candidate removes the only effective defender of an attacked piece;
- `LOW`: no immediate tactical problem detected.

### v6: Blunder Filter

- scan all legal moves;
- filter out immediate blunders;
- identify mechanically safe candidate moves;
- preserve the project boundary: still not a full chess engine.

---

## Project Status

Current version:

```text
ChessGuard 3.0.0
```

This version is suitable for command-line tactical auditing and experimental human + AI chess guidance workflows.

---

## License

A permissive open-source license such as MIT is recommended for this project.

---

## Acknowledgments

ChessGuard is built on top of `python-chess`, which provides reliable chess rules, move validation, board representation, and PGN handling.

---

## Disclaimer

ChessGuard is an experimental chess safety audit tool. It should not be treated as a professional chess engine or a complete tactical oracle. Always verify important game decisions with appropriate judgment, especially in competitive settings.
