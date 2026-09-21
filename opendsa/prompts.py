"""Prompt assembly. Contract: providers get a single ``system`` string plus a
history of {role, content} dicts; the controller appends the per-call schema
block to the system string, never to business logic."""

from __future__ import annotations


def system_prompt() -> str:
    return (
        "You are open-dsa, a conversational DSA study guide in the terminal. "
        "You ask conceptual DSA questions and evaluate the user's approach conversationally. "
        "You are NOT a judge: you never execute or grade code. "
        "Never output copyrighted problem statements — base questions on your own knowledge of well-known "
        "free LeetCode problems and paraphrase them as fresh invented stories. "
        "On a wrong answer you must explain the correct approach clearly before moving on. "
        "Be concrete but concise."
    )


def generation_user_message(
    pattern: str,
    difficulty: str,
    company: str | None,
    seen_numbers: list[int],
) -> str:
    seen = ", ".join(str(n) for n in seen_numbers) or "none yet"
    company_line = (
        f" Frame the scenario at {company} (invented but professional)." if company else ""
    )
    return (
        f'Generate a DSA question for pattern "{pattern}" at difficulty "{difficulty}".{company_line}\n'
        "Base it on a well-known FREE (non-subscription) LeetCode problem that fits this pattern. "
        "Never quote or paste the original problem statement — invent a fresh scenario in your own words.\n"
        f"Avoid reusing these already-covered problem numbers for this pattern: {seen}.\n"
        "Write the story in Markdown. Put any example data/code inside fenced ``` blocks "
        "(e.g. ```python\\nprices = [1, 2, 3, 4, 6, 8, 9, 12]\\n```).\n"
        'Reply with ONLY JSON: {"title": "<short memorable title>", "story": "<full story-wrapped question in Markdown>", '
        '"problem_number": <int>}'
    )


def evaluation_block(force: bool = False) -> str:
    if force:
        allowed = 'MUST NOT be "partial" — only "correct" or "wrong".'
    else:
        allowed = 'one of "correct", "partial", "wrong".'
    return (
        "\nYou are now evaluating the latest user answer. Judge the conceptual approach, not wording. "
        "If the answer is on track but incomplete, return \"partial\" and reply conversationally to steer them. "
        f"The verdict {allowed}\n"
        'Respond with a JSON object only: '
        '{"verdict": "...", "explanation": "<your conversational message to the user>", '
        '"mistake_note": "<what to fix, or null if nothing>"}'
    )


def progress_track_text(patterns: list, summary: list[dict]) -> str:
    """Structured, small, never summarized (guidelines 2.1/2.5)."""
    lines = ["[progress_track]"]
    for p in patterns:
        lines.append(
            f"- {p.pattern} status={p.status} difficulty={p.difficulty.value} "
            f"attempts={p.attempts} correct_streak={p.correct_streak} wrong_streak={p.wrong_streak}"
            + (f" mastered_at={p.mastered_at}" if p.mastered_at else "")
        )
    if summary:
        lines.append("[resolved_summary]")
        for entry in summary:
            lines.append(
                f"- pattern={entry.get('pattern')} verdict={entry.get('verdict')} "
                f"mistake={entry.get('mistake') or '-'}"
            )
    return "\n".join(lines)