# open-dsa

Terminal-based DSA learning guide. Asks story-wrapped DSA questions (company-flavored), evaluates your conceptual answer conversationally, tracks mastery, and hands off the real LeetCode problem number. **Not a judge** — it never executes or grades code.

## Requirements

- Python 3.11+
- A Gemini API key (`GOOGLE_API_KEY`)

## Install

```bash
pip install -e ".[gemini]"
```

This installs the app, the Textual TUI, and the `google-genai` SDK. For a plain code-only setup (no model calls) you can omit `[gemini]`.

## Environment

Copy the template and fill in your key:

```bash
cp .env.example .env
```

```bash
# .env
GOOGLE_API_KEY=your-key-here
GEMINI_MODEL=gemini-2.5-flash
```

The app **auto-loads** `.env` (searched from your working directory upward, then the project root) on every launch — no manual `export` needed. Values already set in your shell take precedence over the file.

| Variable         | Required | Meaning                                                        |
| ---------------- | -------- | -------------------------------------------------------------- |
| `GOOGLE_API_KEY` | yes      | Gemini API key.                                                |
| `GEMINI_MODEL`   | no       | Model to use. Precedence: `$GEMINI_MODEL` > `--model` > `config.toml` > `gemini-2.5-flash`. |

## Configure

All thresholds live in `config.toml` — no magic numbers in code:

- `[app]` — SQLite DB path, default model
- `[context]` — `last_n_turns` (raw turns kept in context) and compaction trigger % of the model's context window
- `[model]` — provider + context window size (used for the compaction threshold)
- `[doubts]` — follow-up/doubt loop cap
- `[mastery]` — attempts + correct-streak required to mark a pattern mastered
- `[difficulty]` — starting tier and drop floor (Easy/Medium/Hard)
- `[curriculum]` — the fixed ordered pattern progression
- `[flavor]` — companies used to flavor generated stories
- `[bank]` — local metadata seed file

## Run

```bash
opendsa                 # resume your last session (prompts Resume / New Session)
opendsa --new            # start a fresh session (skips the resume prompt)
opendsa --model gemini-2.5-flash   # override the model
opendsa --config path/to/config.toml
```

Equivalent: `python -m opendsa ...`

On launch you get a **Start screen** (brand-new profile) or a **Resume screen**
(previous session exists, showing your current pattern, difficulty, attempts
and correct streak). `--new` bypasses the resume prompt.

### Interface

- **Header** — `open-dsa` left, session context right (`Medium • Two Pointer • Amazon`).
- **Question area** — title, state chip (`[ ASK ]`, `[ EVALUATING ]`, `[ FOLLOW-UP ]`, `[ RESOLVED ]`), story rendered as Markdown with code blocks.
- **Conversation** — per-turn feedback from the model; streams live when the provider supports it; verdicts shown as `✓ CORRECT`, `~ PARTIAL`, `× WRONG`; the `LeetCode #N` handoff is always shown when a question resolves.
- **Answer box** — a multiline `TextArea`. Type a conceptual answer (algorithm, reasoning, complexity, intuition — **not code**) and press `Ctrl+Enter` to submit. `Enter` inserts a newline.
- **Status bar** — always-visible command help; shows a small inline spinner while the model is generating or evaluating (no blocking load screen).

### In-session commands

| Command     | Effect                                                            |
| ----------- | ----------------------------------------------------------------- |
| `/skip`     | Force-advance. Logged `advanced_manually`, counts toward nothing. |
| `/next`     | Same as `/skip`.                                                  |
| `/resolve`  | (during a doubt loop) force the final verdict immediately.        |
| `/panel`    | Toggle the collapsible progress sidebar (bars per pattern + current stats). |
| `/progress` | Open the detailed progress screen (`/history` does the same).     |
| `/help`     | Command/key reference overlay.                                   |
| `/quit`     | End the session.                                                  |

### Keys

`Ctrl+Enter` submit — `Tab` move focus — `Esc` close overlays — `PageUp`/`PageDown` scroll — `Ctrl+C` quit.

If the model call fails (e.g. Gemini outage), you get a retry dialog and the
session is preserved — the progress track is never lost to an API error.

## How it works

Three separate data layers (guideline and FR14):

1. **Progress track** — structured, small, always in the model context; never summarized or truncated. Source of truth for sequencing, difficulty, and dedup.
2. **Transcript log** — append-only full history in SQLite for review/analytics.
3. **Conversation context** — `system prompt + progress track + compacted summary + last N raw turns`, rebuilt per request.

The per-question flow is an explicit state machine: `ASK → EVALUATE → {correct, partial, wrong, skip} → LOG`. A `partial` answer opens a doubt loop capped at `[doubts].loop_cap` turns; two consecutive wrongs drop that pattern one difficulty tier (floored at Easy); a pattern masters only after both the attempt and correct-streak thresholds clear.

Model access goes through a single `ModelAdapter` interface (`opendsa/adapters/base.py`). Adding Claude/OpenAI means a new adapter class — zero changes to the state machine or progress logic.

## Non-negotiables

- No copyrighted problem text is stored or sent — only `{pattern, difficulty}` (+ company flavor) plus the problem number are passed to the model; it is told to paraphrase.
- The free/non-subscription claim relies on the generation prompt (v1 cannot scrape to verify); flag any bad number and it's logged for review.
- No code execution or judging anywhere in v1.

## Tests

```bash
python -m pytest
```

## Layout

```
config.toml          thresholds + curriculum (TOML)
opendsa/
  controller.py      state machine + session driver (no UI imports)
  progress.py        mastery / streak / difficulty logic
  transcript.py      append-only log
  compaction.py      token-triggered context compaction
  prompts.py         system/generation/evaluation prompts
  session.py         resume-by-default / --new
  db.py              versioned SQLite schema + migrations
  adapters/
    base.py          ModelAdapter Protocol
    gemini.py        Gemini implementation (only provider SDK import)
  tui/
    app.py         Textual study app (layout + flow)
    screens.py     Start / Resume / Progress / Help / Error modals
    widgets.py     header, status bar, conversation stream
    output.py      controller-thread -> UI bridge (structured events)
    theme.py       opencode-style dark theme (CSS + registered Theme)
```