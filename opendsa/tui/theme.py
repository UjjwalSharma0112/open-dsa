"""Single dark theme for the whole study UI (TUI-GUIDE.MD §2).

Follows the opencode terminal aesthetic: near-black zinc background, muted
grays, a single warm primary used only for focus/active states, and quiet
status colors. Tokens are substituted into the CSS via string.Template, and a
matching Textual ``Theme`` is exported so every built-in widget (buttons,
textarea cursor, links) inherits the same palette instead of the default blue.
"""

from __future__ import annotations

from string import Template

from textual.theme import Theme

SCHEME = {
    # base canvas (opencode zinc-black)
    "bg": "#111214",
    "surface": "#1a1c20",
    "surface2": "#17181b",
    "border": "#2a2d33",
    "border2": "#3a3e45",
    "text": "#d6d8dc",
    "bright": "#eef0f3",
    "muted": "#6f7480",
    # opencode accents (warm, reserved)
    "primary": "#d8945a",
    "success": "#7fd88f",
    "warning": "#dcae6b",
    "error": "#e06c75",
}

_CSS = """
Screen {
    background: $bg;
    color: $text;
    align-horizontal: center;
}

/* main content column is centered with a cap relative to the terminal */
#header, #body, #input-wrap, #status {
    width: 1fr;
    max-width: 128;
}

/* ---- header (TUI-GUIDE.MD §3) ---- */
#header {
    height: 1;
    padding: 0 1;
}
#brand {
    width: 10;
    content-align: left middle;
    color: $bright;
    text-style: bold;
}
#hint {
    width: 1fr;
    content-align: right middle;
    color: $muted;
}
#chip {
    width: 13;
    content-align: right middle;
    color: $muted;
    text-style: bold;
}
#chip.resolved { color: $success; }

/* ---- body: progress panel + question/conversation column ---- */
#body {
    height: 1fr;
    padding-top: 1;
}
#panel {
    width: 32;
    display: none;
    background: $surface2;
    border-right: solid $border;
    padding: 1 2;
}
#panel.visible {
    display: block;
}
#panel-title {
    color: $muted;
    text-style: bold;
    padding-bottom: 1;
}
#panel-body {
    color: $text;
}

/* ---- question blocks (TUI-GUIDE.MD §4, §17) - appended to the scroll ---- */
.convo-qtitle {
    width: 1fr;
    color: $bright;
    text-style: bold;
    padding: 0 0 1 0;
}
.convo-qbody {
    width: 1fr;
    margin: 0;
}
.turn.question { width: 1fr; margin: 1 0 1 0; }
Markdown { background: transparent; color: $text; margin: 0; }
MarkdownParagraph { color: $text; margin: 0 0 1 0; }
MarkdownH1, MarkdownH2, MarkdownH3 { color: $bright; text-style: bold; }
MarkdownLink { color: $bright; text-style: underline; }
MarkdownCodeBlock, MarkdownFence {
    background: $surface;
    border: solid $border;
    padding: 0 2;
    color: $bright;
    margin: 1 0;
}

/* ---- conversation (TUI-GUIDE.MD §8) ---- */
#convo {
    width: 1fr;
    height: 1fr;
    padding: 1 3 1 3;
}
.turn { height: auto; width: 1fr; }
.turn-rule { height: 1; background: $border; margin: 1 0; }
.turn-role { color: $muted; text-style: bold; padding-bottom: 1; }
.turn-content { color: $text; }
.turn-count { color: $muted; padding-top: 1; }
.turn-note { color: $muted; }
.turn-verdict-correct { color: $success; text-style: bold; }
.turn-verdict-partial { color: $warning; text-style: bold; }
.turn-verdict-wrong   { color: $error; text-style: bold; }
.turn-link { color: $bright; text-style: underline; }

/* ---- answer input (TUI-GUIDE.MD §5) ---- */
#input-wrap {
    height: auto;
    padding: 1 3;
}
TextArea {
    min-height: 5;
    max-height: 12;
    height: auto;
    background: $surface;
    border: solid $border;
    padding: 1 2;
    color: $text;
}
TextArea:focus { border: solid $primary; }

/* ---- status bar (TUI-GUIDE.MD §6) ---- */
#status {
    height: 1;
    padding: 0 3;
    color: $muted;
}
#status.busy { color: $primary; }

/* ---- modals / cards ---- */
StartScreen, ResumeScreen, ProgressScreen, HelpScreen, ErrorScreen {
    align: center middle;
}
#card {
    width: 55%;
    max-width: 90%;
    height: auto;
    max-height: 92%;
    overflow-y: auto;
    border: solid $border;
    background: $surface;
    padding: 2 3;
}
.card-title { color: $bright; text-style: bold; }
.card-sub   { color: $muted; }
.card-line  { color: $text; }
.card-rule  { height: 1; background: $border; margin: 1 0; }
.card-line.muted { color: $muted; }
.card-line.ok    { color: $success; }
.card-line.cur   { color: $bright; text-style: bold; }
.card-line.todo  { color: $muted; }
#card-scroll { height: auto; max-height: 55%; }
Button {
    width: 16;
    min-width: 14;
    margin: 2 1 0 0;
    background: $surface2;
    color: $text;
    border: solid $border;
}
Button.primary { color: $bright; text-style: bold; }
Button:focus { border: solid $primary; color: $bright; text-style: bold; }
#error-detail { color: $muted; }
"""

CSS = Template(_CSS).safe_substitute(SCHEME)


THEME = Theme(
    name="opendsa-dark",
    primary=SCHEME["primary"],
    secondary=SCHEME["primary"],
    accent=SCHEME["primary"],
    warning=SCHEME["warning"],
    error=SCHEME["error"],
    success=SCHEME["success"],
    foreground=SCHEME["text"],
    background=SCHEME["bg"],
    surface=SCHEME["surface"],
    panel=SCHEME["surface2"],
    boost=SCHEME["surface"],
    dark=True,
    luminosity_spread=0.1,
    variables={
        "input-cursor-background": SCHEME["primary"],
        "input-cursor-foreground": SCHEME["bg"],
        "input-cursor-text-style": "bold",
    },
)