# open-dsa — Development Guidelines

## 1. Stack
- **Language:** Python
- **TUI:** Textual (mature, stable; OpenTUI is explicitly not production-ready as of now — do not use it)
- **Storage:** SQLite (single local file)
- **Model (v1):** Gemini API, behind an adapter interface

## 2. Architecture Rules

### 2.1 Data-layer separation (do not blend these)
1. **Progress track** — structured, small, always fully loaded into context. Source of truth for pattern sequencing, difficulty, and dedup. Never summarized or truncated.
2. **Transcript log** — append-only full history in SQLite. Used for review/analytics, not necessarily loaded into model context.
3. **Conversation context** — what's actually sent to the model: `system_prompt + progress_track + compacted_summary (if any) + last_N_raw_turns`.

### 2.2 Model adapter
Define one interface; every provider implements it. No caller should ever import a provider SDK directly.
```python
class ModelAdapter(Protocol):
    def generate(self, system: str, history: list[dict]) -> str: ...
    def stream(self, system: str, history: list[dict]) -> Iterator[str]: ...
```
`GeminiAdapter` is the only implementation in v1. Adding Claude/OpenAI later = new adapter class, zero changes to state machine or progress logic.

### 2.3 State machine
Implement the per-question flow as an explicit state machine (not ad-hoc if/else chains in the main loop):
`ASK → EVALUATE → {correct, partial, wrong, skip} → LOG → next state`
The verdict comes from the model self-classifying its own evaluation — the generation prompt must demand a structured `{verdict, explanation}` (optionally `{mistake_note}`) response so the state machine never has to guess.
Doubt/follow-up loop must have a hard turn cap — never allow unbounded looping.

### 2.4 Question generation
- Only ever send `{pattern, difficulty}` (and optionally a company name for flavor) to the model as generation seed.
- Never store, embed, or transmit actual LeetCode problem statements. The model's own training data supplies problem knowledge — the app supplies structure and tracking, not content.
- The model must return the target LeetCode **problem number** in its generation (free, non-subscription problems only); the app hands off and logs the number as-is. Building a real URL from the number is explicitly out of scope for v1. The bank's `question_id` is the dedup key and stays model-free.

### 2.5 Compaction
- Trigger on a token-count threshold (percentage of the active model's context window), not a vague "seems full" check.
- Compaction targets only the raw transcript portion of context — progress track is exempt.
- Compaction output: short structured summary per resolved question (`pattern, verdict, mistake`), not free-text prose recap.

### 2.6 Progress/mastery logic
- Difficulty is Easy/Medium/Hard only. Patterns start at **Medium**; two consecutive wrongs on a pattern drop **one tier** before the next question in that pattern, **floored at Easy**. No auto tier-up within a pattern in v1.
- `wrong_streak` resets on any `correct` verdict.
- Mastery requires both a minimum attempt count and a minimum correct streak (both configurable) — a single lucky correct answer should not mark a pattern mastered.
- Manual skip (`/skip`, `/next`) never counts toward mastery; flag it distinctly in the log (`advanced_manually: true`).

## 3. Coding Conventions
- All thresholds (doubt-loop cap, compaction %, mastery attempt/streak counts, last-N-turn window, difficulty start/floor, curriculum order) live in **one `config.toml`** at the repo root, loaded into typed dataclasses. No magic numbers scattered in logic. v1 defaults: doubt-loop cap 3, compaction threshold 70%, `last_n_turns` 8, mastery min attempts 5 / correct-streak 3.
- SQLite schema versioned from the start (migration path for future fields).
- Sessions resume the last session by default; a `--new` flag starts a fresh one.
- Keep TUI rendering code separate from state-machine/logic code — logic should be testable without spinning up Textual.

## 4. Non-negotiables
- No copyrighted problem text stored or sent, ever.
- No code-execution/judging in v1 — this is a conceptual guide tool, not a judge.
- Progress track must survive every compaction event untouched.
