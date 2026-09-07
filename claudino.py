#!/usr/bin/env python3
"""claudino - a one-key runner to play while Claude Code is thinking.

Press space. That is the whole game.

Pure Python 3.9+ standard library. Pure ASCII, so it renders the same in
Terminal.app, iTerm2 and Warp.
"""

import argparse
import curses
import glob
import json
import math
import os
import random
import sys
import threading
import time

VERSION = "1.2.0"

def sprite_w(rows):
    return max(len(r) for r in rows)


def mask(rows):
    """Solid cells of a sprite, as (dx, dy) offsets."""
    return {(x, y) for y, r in enumerate(rows) for x, ch in enumerate(r) if ch != " "}


# ------------------------------------------------------------------ sprites
#
# Sprites are pixel art, two pixel rows per character cell. A terminal cell is
# about twice as tall as it is wide, so a pair of stacked half-blocks is
# square. That doubles the vertical resolution and is the only reason a sprite
# this small can look like anything.
#
# The three half-block characters are East Asian "Ambiguous" width. Every
# terminal in scope defaults them to one cell, but a user who has switched
# ambiguous characters to double width would see the layout tear, so --ascii
# swaps in a pure-ASCII approximation with exactly the same dimensions. Same
# cell count means the physics are identical either way.

BLOCKS = ("\u2588", "\u2580", "\u2584")   # full, upper half, lower half
ASCII_BLOCKS = ("#", '"', ".")

DINO_BODY = [
    " ####### ",
    "#########",
    "#########",
    "## ### ##",
    "## ### ##",
    "#########",
    "#########",
    " ####### ",
]
# Four pixel rows of leg, so BOTH legs move: each frame extends one and
# lifts the other. Two rows only ever animated the left one.
DINO_LEGS = {
    "a": [" ##   ## ", " ##   ## ", " ##   ## ", " ##      "],
    "b": [" ##   ## ", " ##   ## ", " ##   ## ", "      ## "],
    "jump": [" ##   ## ", " ##   ## ", "  #   #  ", "         "],
}
DINO_DEAD_PIXELS = [
    " ####### ", "#########", "#########", "# ##### #",
    "# ##### #", "#########", "#########", " ####### ",
    "##     ##", "##     ##", "#       #", "#       #",
]
OBSTACLE_PIXELS = [
    ["# #", "# #", "###", " # ", " # ", " # "],
    ["# #", "###", " # ", " # ", " # ", " # "],
    ["#  #", "#  #", "####", " ## ", " ## ", " ## "],
    [" ## ", " ## ", "####", "####", " ## ", " ## "],
]


def to_cells(pixels, ascii_mode=False):
    """Fold pairs of pixel rows into one row of character cells."""
    full, upper, lower = ASCII_BLOCKS if ascii_mode else BLOCKS
    rows = list(pixels)
    if len(rows) % 2:
        rows.append(" " * len(rows[0]))
    out = []
    for y in range(0, len(rows), 2):
        top, bottom = rows[y], rows[y + 1]
        out.append("".join(
            full if t != " " and b != " " else
            upper if t != " " else
            lower if b != " " else " "
            for t, b in zip(top, bottom)))
    return out


def set_style(ascii_mode):
    """Choose half-block or ASCII sprites. Dimensions are the same either way."""
    global DINO_RUN, DINO_JUMP, DINO_DEAD, OBSTACLES, DINO_W, WIDEST_OBSTACLE
    DINO_RUN = [to_cells(DINO_BODY + DINO_LEGS[k], ascii_mode) for k in ("a", "b")]
    DINO_JUMP = to_cells(DINO_BODY + DINO_LEGS["jump"], ascii_mode)
    DINO_DEAD = to_cells(DINO_DEAD_PIXELS, ascii_mode)
    OBSTACLES = [to_cells(o, ascii_mode) for o in OBSTACLE_PIXELS]
    DINO_W = sprite_w(DINO_RUN[0])
    WIDEST_OBSTACLE = max(sprite_w(o) for o in OBSTACLES)


CLOUDS = [[" .--.", "(    )"], ["  .-.", " (   )"]]
STAR_CHARS = ".`'."

(C_DEF, C_DINO, C_OBS, C_GROUND, C_CLOUD,
 C_HUD, C_ACCENT, C_STAR, C_FRAME, C_SESSION) = range(10)

PANEL_ROWS = 4            # sessions listed under the summary

# ------------------------------------------------------------------ quips
# Things Claude says. Kept to ASCII so they render the same everywhere.

CLEARED_QUIPS = [
    "Sauteed!", "Brewed!", "Braised!", "Whisked!", "Deglazed!", "Julienned!",
    "Simmered.", "Plated.", "Folded in.", "Reduced nicely.",
    "Nailed it.", "Exit code 0", "LGTM", "Shipped.", "Merged.", "All green.",
    "Tests passing.", "Clean diff.", "No notes.", "Atomic commit.",
    "Zero regressions.", "Passed linting.", "Type-safe.", "No side effects.",
    "Idempotent.", "Deterministic.", "Cache hit.", "One-shot, no retries.",
    "Good catch.", "Noted.", "Handled.", "Verified.", "Acknowledged.",
    "That checks out.", "Within tolerance.", "Confidence: high.",
    "You're absolutely right.", "Reviewed and approved.",
    "Honest caveat: easy jump.", "Worth noting: cleared.",
    "I'd call that load-bearing.", "Small, reviewable jump.",
    "Refactored mid-air.", "Well-scoped.", "Minimal diff.",
    "To be fair, low cactus.", "No hallucination there.",
    "Ground truth: cleared.", "Token efficient.", "Let me be direct: clean.",
]

DEATH_QUIPS = [
    "It's a wash.", "Overcooked.", "The sauce broke.", "Curdled.",
    "Burnt the reduction.", "Underproofed.", "Left it in too long.",
    "Let me reconsider.", "Let me take a different approach.",
    "Let me step back and rethink.", "Hmm, that didn't work.",
    "Honest caveat: that was a cactus.", "I'll be direct: skill issue.",
    "You're absolutely right, I hit it.", "I want to be upfront: I crashed.",
    "Great question. No answer.", "Worth noting: I am dead.",
    "I appreciate you flagging that cactus.", "That's on me.",
    "Segmentation fault.", "Exit code 1.", "Tests failing.", "Reverted.",
    "Rolling back.", "Merge conflict.", "Off by one.", "Race condition.",
    "Panic: index out of range.", "Null pointer on approach.",
    "Unexpected token: cactus.", "Stale cache.", "Timed out.",
    "Rate limited.", "Context window exceeded.", "Retry limit reached.",
    "Blocked on cactus.", "That's a P0.", "Well, that regressed.",
    "I hallucinated the gap.", "Not idempotent after all.",
    "Confidence was misplaced.", "That was load-bearing.",
    "Insufficient test coverage.", "Deprecated maneuver.",
    "Should have read the docs.", "Needs more context.",
    "Escalating to a human.", "Let me be honest: cactus.",
]


# ------------------------------------------------------------------ physics
#
# The one rule that makes this game fair. To clear an obstacle you must stay
# above it for longer than it takes to pass through it:
#
#     time_above(h) = 2 * sqrt(JUMP_V^2 - 2*GRAVITY*(h-1)) / GRAVITY
#     overlap_time  = (dino_width + obstacle_width) / speed
#
# The first version failed this. An 8-wide dino took 0.55s to pass a cactus
# but stayed above it for only 0.49s, so some obstacles could not be cleared
# at any timing at all. Narrow sprites are what make the game winnable.
#
# A short jump is also what lets obstacles sit close together, because the gap
# between them has to cover a whole jump. That is why gravity is high: the
# 0.69s hop keeps the track busy where a floaty one would leave it empty.
#
# Note this gets EASIER as speed rises, because the overlap shrinks.
# Difficulty here is a reaction-time problem, which is the fun kind.

GRAVITY = 64.0
JUMP_V = 29.0
BASE_SPEED = 26.0
SPEED_CAP = 58.0
MIN_CROSSING_TIME = 1.55  # an obstacle must take this long to cross the pane.
                          # You have to be at the top of the jump when it
                          # arrives, so the last saving jump is half an air
                          # time before impact: this must exceed the reaction
                          # budget by that much.
REACTION_GAP = 0.42       # seconds on the ground between two obstacles
FRAME = 0.05

DINO_X = 5
HUD_H = 1
GROUND_PAD = 2
MIN_W, MIN_H = 60, 14     # a 9-wide dino needs room; below this the
                          # speed cap would fall under BASE_SPEED
MAX_PLAY_W, MAX_PLAY_H = 110, 20   # the track is centred, not stretched: a
                                   # full-screen window otherwise becomes a
                                   # very long strip of empty desert


def time_above(height):
    """Seconds the dino spends with its feet above `height` rows."""
    d = JUMP_V * JUMP_V - 2.0 * GRAVITY * height
    return 2.0 * math.sqrt(d) / GRAVITY if d > 0 else 0.0


AIR_TIME = 2.0 * JUMP_V / GRAVITY
set_style(False)


# ------------------------------------------------------------------ model

class Obstacle:
    __slots__ = ("rows", "x", "scored")

    def __init__(self, rows, x):
        self.rows = rows
        self.x = float(x)
        self.scored = False

    @property
    def w(self):
        return sprite_w(self.rows)

    @property
    def h(self):
        return len(self.rows)


class Game:
    """The whole simulation. No curses in here, so it can be tested headless."""

    def __init__(self, w=80, h=20, seed=None):
        self.rng = random.Random(seed)
        self.resize(w, h)
        self.reset()

    def resize(self, w, h):
        self.w = min(max(w, MIN_W), MAX_PLAY_W)
        self.h = min(max(h, MIN_H), MAX_PLAY_H)
        self.ground_y = self.h - GROUND_PAD - 1

    def reset(self):
        self.t = 0.0
        self.dist = 0.0          # real distance, so the ground never drifts
        self.score = 0.0
        self.dead = False
        self.started = False     # False until the first jump: shows the hint
        self.dy = 0.0
        self.vy = 0.0
        self.obstacles = []
        self.next_gap = self.w * 0.55
        self.flash = 0.0
        self.banner = []
        self.cleared = 0
        self.quip = ""
        self.quip_t = 0.0
        sky = max(HUD_H + 1, self.ground_y - 6)
        step = max(16, self.w // 3)
        self.clouds = [[float(i * step + self.rng.randrange(0, 10)),
                        self.rng.randrange(HUD_H, sky),
                        self.rng.randrange(len(CLOUDS))] for i in range(4)]
        self.stars = [[float(self.rng.randrange(self.w)),
                       self.rng.randrange(HUD_H, max(HUD_H + 1, self.ground_y - 7)),
                       self.rng.choice(STAR_CHARS)]
                      for _ in range(max(3, self.w // 14))]

    def say(self, pool, seconds):
        """Pick a line, never the same one twice running."""
        choice = self.rng.choice(pool)
        if choice == self.quip and len(pool) > 1:
            choice = self.rng.choice([q for q in pool if q != self.quip])
        self.quip, self.quip_t = choice, seconds

    @property
    def max_speed(self):
        """Never let an obstacle cross the pane faster than a person can react."""
        return min(SPEED_CAP, (self.w - DINO_X) / MIN_CROSSING_TIME)

    @property
    def speed(self):
        return min(self.max_speed, BASE_SPEED + self.score / 70.0)

    @property
    def airborne(self):
        return self.dy > 0.01

    def jump(self):
        if self.dead:
            return
        self.started = True
        if not self.airborne:
            self.vy = JUMP_V

    def dino_rows(self):
        if self.dead:
            return DINO_DEAD
        if self.airborne:
            return DINO_JUMP
        return DINO_RUN[int(self.t * 13) % 2]

    def spawn(self):
        self.obstacles.append(Obstacle(self.rng.choice(OBSTACLES), self.w + 1))
        # A gap has to cover a whole jump plus time on the ground to react.
        floor = self.speed * (AIR_TIME + REACTION_GAP) + WIDEST_OBSTACLE
        self.next_gap = max(floor, self.rng.uniform(floor, floor + 18))

    def step(self, dt):
        self.t += dt
        self.flash = max(0.0, self.flash - dt)
        self.quip_t = max(0.0, self.quip_t - dt)
        if self.dead or not self.started:
            return

        self.score += self.speed * dt * 0.8
        move = self.speed * dt
        self.dist += move

        self.vy -= GRAVITY * dt
        self.dy = max(0.0, self.dy + self.vy * dt)
        if self.dy == 0.0:
            self.vy = 0.0

        for ob in self.obstacles:
            ob.x -= move
            if not ob.scored and ob.x + ob.w < DINO_X:
                ob.scored = True
                self.cleared += 1
                if self.rng.random() < 0.55:
                    self.say(CLEARED_QUIPS, 1.3)
        self.obstacles = [o for o in self.obstacles if o.x + o.w > 0]

        self.next_gap -= move
        if self.next_gap <= 0:
            self.spawn()

        self._drift(self.clouds, move * 0.16, 8, len(CLOUDS))
        self._drift(self.stars, move * 0.04, 2, None)

        if self.collides():
            self.dead = True
            self.say(DEATH_QUIPS, 0.0)

    def _drift(self, layer, move, pad, variants):
        sky = max(HUD_H + 1, self.ground_y - (6 if variants else 7))
        for item in layer:
            item[0] -= move
            if item[0] < -pad:
                # Clouds respawn behind the last one, never at a random spot,
                # or two of them overlap and render as mush.
                item[0] = (max(o[0] for o in layer) + self.rng.randrange(18, 40)
                           if variants else self.w + self.rng.randrange(2, 26))
                item[1] = self.rng.randrange(HUD_H, sky)
                item[2] = (self.rng.randrange(variants) if variants
                           else self.rng.choice(STAR_CHARS))

    def dino_top(self):
        return self.ground_y - len(self.dino_rows()) + 1 - int(round(self.dy))

    def obstacle_top(self, ob):
        return self.ground_y - ob.h + 1

    def collides(self):
        top = self.dino_top()
        dino = {(DINO_X + dx, top + dy) for dx, dy in mask(self.dino_rows())}
        for ob in self.obstacles:
            ox = int(round(ob.x))
            if ox > DINO_X + DINO_W or ox + ob.w < DINO_X:
                continue
            oy = self.obstacle_top(ob)
            if dino & {(ox + dx, oy + dy) for dx, dy in mask(ob.rows)}:
                return True
        return False


# ------------------------------------------------------------------ render

def blit(grid, rows, x, y, color):
    h, w = len(grid), len(grid[0])
    for dy, line in enumerate(rows):
        gy = y + dy
        if 0 <= gy < h:
            for dx, ch in enumerate(line):
                gx = x + dx
                if ch != " " and 0 <= gx < w:
                    grid[gy][gx] = ((" ", C_DEF) if ch == "\0" else (ch, color))


def centred(grid, lines, color, dy=0):
    """Draw centred text on cleared ground, so scenery cannot show through."""
    w = len(grid[0])
    y0 = max(0, len(grid) // 2 - len(lines) // 2 + dy)
    pad = max(len(line) for line in lines) + 4
    x0 = max(0, (w - pad) // 2)
    for i in range(len(lines)):
        blit(grid, ["\0" * min(pad, w - x0)], x0, y0 + i, C_DEF)
    for i, line in enumerate(lines):
        blit(grid, [line], max(0, (w - len(line)) // 2), y0 + i, color)


def banner_for(names, width):
    """Two lines naming what just finished, so you know where to go back to."""
    if not names:
        return []
    if len(names) == 1:
        return [names[0][:width - 4], "is done"]
    joined = ", ".join(names)
    if len(joined) > width - 4:
        joined = joined[:width - 7] + "..."
    return ["%d sessions done" % len(names), joined]


STATE_MARK = {"working": ">", "ready": "-", "idle": ".", "unreadable": "?"}


def hud(grid, g, status):
    """Score on the left, token burn in the middle, sessions on the right."""
    width = len(grid[0])

    left = "%05d" % int(g.score)
    if status.get("best"):
        left += "  best %05d" % status["best"]
    wasted = status.get("wasted")
    if wasted is not None and width >= 74:
        left += "   %s wasted" % human(wasted)
    blit(grid, [left[:width - 2]], 1, 0, C_HUD)

    label = status.get("claude")
    if label:
        if len(left) + len(label) + 4 > width:
            label = label.replace("claude: ", "")
        blit(grid, [label[:width - 2]], max(1, width - len(label) - 1), 0, C_ACCENT)

    # One line per live session: marker, folder, and the tool it last called.
    rows = status.get("sessions") or []
    if not rows or width < 52:
        return
    shown = rows[:PANEL_ROWS]
    name_w = min(16, max(len(r["short"]) for r in shown))
    lines = ["%s %-*s %s" % (STATE_MARK.get(r["state"], "?"), name_w,
                             r["short"][:name_w], r["tool"])
             for r in shown]
    panel_w = max(len(l) for l in lines)
    x = max(1, width - panel_w - 1)
    for i, line in enumerate(lines):
        blit(grid, ["\0" * (panel_w + 1)], x - 1, 1 + i, C_DEF)
        blit(grid, [line], x, 1 + i,
             C_SESSION if shown[i]["state"] == "working" else C_HUD)


def say(grid, text, x, y):
    """A line of Claude, on cleared ground so the scenery cannot show through."""
    width = len(grid[0])
    text = text[:max(0, width - 4)]
    x = min(x, max(0, width - len(text) - 2))
    blit(grid, ["\0" * (len(text) + 2)], x - 1, y, C_DEF)
    blit(grid, [text], x, y, C_HUD)


def render(g, status):
    grid = [[(" ", C_DEF) for _ in range(g.w)] for _ in range(g.h)]

    for sx, sy, ch in g.stars:
        blit(grid, [ch], int(sx), sy, C_STAR)
    for cx, cy, variant in g.clouds:
        blit(grid, CLOUDS[variant], int(cx), cy, C_CLOUD)

    shift = int(g.dist)
    blit(grid, ["".join("." if (x + shift) % 11 == 0 else "_" for x in range(g.w))],
         0, g.ground_y + 1, C_GROUND)
    blit(grid, ["".join("." if (x * 7 + shift) % 23 == 0 else " " for x in range(g.w))],
         0, g.ground_y + 2, C_GROUND)

    for ob in g.obstacles:
        blit(grid, ob.rows, int(round(ob.x)), g.obstacle_top(ob), C_OBS)
    blit(grid, g.dino_rows(), DINO_X, g.dino_top(), C_DINO)

    hud(grid, g, status)

    if g.quip_t > 0 and not g.dead:
        say(grid, g.quip, DINO_X + 2, max(HUD_H + 1, g.dino_top() - 2))

    if g.dead:
        centred(grid, ["G A M E   O V E R", "", g.quip or "", "", "space to retry"],
                C_ACCENT, -1)
    elif not g.started:
        centred(grid, ["press space"], C_HUD, -3)
    elif g.flash > 0 and g.banner:
        centred(grid, g.banner, C_ACCENT, -4)
    return grid


# ------------------------------------------------------------------ sessions

class Sessions:
    """Status of every recent Claude Code session, not just the newest one.

    Privacy: this reads the `type` of the last few records and the working
    directory each session was started in. It never reads message text, and it
    never writes. Use --no-watch to switch it off.
    """

    ROOT = os.path.expanduser("~/.claude/projects")
    RECENT = 6 * 3600
    IDLE_AFTER = 900

    def __init__(self):
        self.rows = []
        self.checked = 0.0
        self.ready = set()
        self.finished = []
        self.primed = False   # the first scan only learns the current state

    @classmethod
    def available(cls):
        return os.path.isdir(cls.ROOT)

    @staticmethod
    def _classify(records, age):
        """State from what the records say, not from how fresh the file is.

        The log is written in bursts: during a long tool call nothing is
        appended for many seconds, so file freshness alone reports "idle"
        while Claude is busy. Only a long silence really means idle.
        """
        if age > Sessions.IDLE_AFTER:
            return "idle"
        for record in reversed(records):
            kind = record.get("type")
            if kind not in ("user", "assistant"):
                continue          # skip system, attachment and summary noise
            content = (record.get("message") or {}).get("content")
            blocks = [b.get("type") for b in content
                      if isinstance(b, dict)] if isinstance(content, list) else []
            if kind == "assistant":
                # A tool call means Claude is still going; text alone means it
                # has handed the turn back.
                return "working" if "tool_use" in blocks else "ready"
            return "working"      # a prompt or a tool result: Claude is busy
        return "idle"

    def scan(self):
        rows = []
        now = time.time()
        for path in glob.glob(os.path.join(self.ROOT, "*", "*.jsonl")):
            try:
                age = now - os.path.getmtime(path)
                if age > self.RECENT:
                    continue
                size = os.path.getsize(path)
                with open(path, "rb") as fh:
                    fh.seek(max(0, size - 32768))
                    text = fh.read().decode("utf-8", "replace")
                records = [json.loads(ln) for ln in text.splitlines()
                           if ln.strip().startswith("{")]
            except (OSError, ValueError):
                continue
            if not records:
                continue
            cwd = next((r.get("cwd") for r in reversed(records) if r.get("cwd")), "")
            rows.append({
                "state": self._classify(records, age),
                "age": age,
                "name": self._folder(cwd),
                "cwd": cwd,
                "id": os.path.basename(path)[:8],
                "tool": self._last_tool(records),
            })
        order = {"working": 0, "ready": 1, "idle": 2}
        rows.sort(key=lambda r: (order.get(r["state"], 3), r["age"]))

        # Several sessions often run in one folder, so the folder alone cannot
        # say which terminal to go back to. Add the session id where it is
        # genuinely ambiguous, and leave it off where it is not.
        counts = {}
        for row in rows:
            counts[row["name"]] = counts.get(row["name"], 0) + 1
        for row in rows:
            duplicated = counts[row["name"]] > 1
            row["label"] = (row["name"] if not duplicated
                            else "%s (%s)" % (row["name"], row["id"]))
            # The panel is narrow, so it gets a shorter form of the same idea.
            row["short"] = (row["name"] if not duplicated
                            else "%s~%s" % (row["name"][:10], row["id"][:4]))
        return rows

    @staticmethod
    def _last_tool(records):
        """Which tool the session called last: its step, roughly.

        Only the tool's name is taken. Its input holds shell commands and file
        paths, and none of that belongs on a screen someone might screenshot.
        """
        for record in reversed(records[-40:]):
            content = (record.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for block in reversed(content):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    return str(block.get("name") or "")[:12]
        return ""

    @staticmethod
    def _folder(cwd):
        """Folder name for a session. Never the username: ~ is called ~."""
        path = (cwd or "").rstrip("/")
        home = os.path.expanduser("~").rstrip("/")
        if not path or path == home:
            return "~"
        return os.path.basename(path) or "~"

    def poll(self, now):
        self.finished = []
        if now - self.checked < 1.5:
            return
        self.checked = now
        self.rows = self.scan()

        ready = {r["id"] for r in self.rows if r["state"] == "ready"}
        if self.primed:
            new = ready - self.ready
            self.finished = [r["label"] for r in self.rows if r["id"] in new]
        self.primed = True    # anything already waiting when the game started
                              # finished before you opened it: do not announce
        self.ready = ready

    def label(self):
        working = sum(1 for r in self.rows if r["state"] == "working")
        ready = len(self.ready)
        if not self.rows:
            return "no claude sessions"
        if working + ready == 0:
            return "claude: idle"
        parts = []
        if working:
            parts.append("%d working" % working)
        if ready:
            parts.append("%d ready" % ready)
        return "claude: " + ", ".join(parts)



class TokenMeter:
    """Adds up every token Claude has ever spent, across all sessions.

    The logs are hundreds of megabytes, and a full pass takes about a second,
    so this runs on a background thread and remembers how far into each file
    it got. Later sweeps only read what was appended since.

    It reads one field, `message.usage`, and nothing else.
    """

    FIELDS = ("input_tokens", "output_tokens",
              "cache_creation_input_tokens", "cache_read_input_tokens")
    SWEEP = 4.0

    def __init__(self):
        self.total = 0
        self.baseline = None        # total when the game started
        self.ready = False
        self._offsets = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while True:
            try:
                self._sweep()
            except Exception:       # a counter must never take the game down
                pass
            if self._stop.wait(self.SWEEP):
                return

    def _sweep(self):
        added = 0
        for path in glob.glob(os.path.join(Sessions.ROOT, "*", "*.jsonl")):
            try:
                size = os.path.getsize(path)
                start = self._offsets.get(path, 0)
                if size <= start:
                    continue
                with open(path, "rb") as fh:
                    fh.seek(start)
                    consumed = start
                    for raw in fh:          # by line, so a 50 MB file is fine
                        if not raw.endswith(b"\n"):
                            break           # a half-written line: read it next time
                        consumed += len(raw)
                        if b'"usage"' not in raw:
                            continue
                        try:
                            record = json.loads(raw.decode("utf-8", "replace"))
                        except ValueError:
                            continue
                        usage = (record.get("message") or {}).get("usage") or {}
                        added += sum(usage.get(k) or 0 for k in self.FIELDS)
                self._offsets[path] = consumed
            except OSError:
                continue
        with self._lock:
            self.total += added
            if self.baseline is None:
                self.baseline = self.total   # first sweep is all of history
                self.ready = True

    def burned(self):
        """Tokens spent since the game started."""
        with self._lock:
            return 0 if self.baseline is None else self.total - self.baseline


def human(value):
    for suffix, size in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("k", 1e3)):
        if value >= size:
            return "%.1f%s" % (value / size, suffix)
    return str(int(value))


# ------------------------------------------------------------------ scores

def score_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "claudino", "highscore.json")


def load_best():
    try:
        with open(score_path()) as fh:
            return int(json.load(fh).get("best", 0))
    except (OSError, ValueError, TypeError):
        return 0


def save_best(best):
    try:
        path = score_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump({"best": int(best)}, fh)
    except OSError:
        pass


# ------------------------------------------------------------------ colours
# 256 colours where available, which covers Terminal.app, iTerm2 and Warp.
# The 8-colour fallback keeps it legible on anything older.

PALETTE_256 = {
    C_DINO: (173, 0), C_OBS: (78, 0), C_GROUND: (137, 0),
    C_CLOUD: (67, 0), C_HUD: (145, 0), C_ACCENT: (212, curses.A_BOLD),
    C_STAR: (240, 0), C_FRAME: (238, 0), C_SESSION: (108, 0),
}
PALETTE_8 = {
    C_DINO: (curses.COLOR_YELLOW, curses.A_BOLD),
    C_OBS: (curses.COLOR_GREEN, 0),
    C_GROUND: (curses.COLOR_YELLOW, 0),
    C_CLOUD: (curses.COLOR_BLUE, curses.A_BOLD),
    C_HUD: (curses.COLOR_WHITE, 0),
    C_ACCENT: (curses.COLOR_MAGENTA, curses.A_BOLD),
    C_STAR: (curses.COLOR_WHITE, curses.A_DIM),
    C_FRAME: (curses.COLOR_WHITE, curses.A_DIM),
    C_SESSION: (curses.COLOR_GREEN, 0),
}
JUMP_KEYS = (ord(" "), curses.KEY_UP, ord("w"), ord("k"), ord("\n"))
QUIT_KEYS = (ord("q"), 27)


def build_attrs():
    attrs = {C_DEF: 0}
    if not curses.has_colors():
        return dict(attrs, **{cid: extra for cid, (_, extra) in PALETTE_8.items()})
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:
        bg = curses.COLOR_BLACK
    palette = PALETTE_256 if curses.COLORS >= 256 else PALETTE_8
    for i, (cid, (fg, extra)) in enumerate(palette.items(), start=1):
        try:
            curses.init_pair(i, fg, bg)
            attrs[cid] = curses.color_pair(i) | extra
        except curses.error:
            attrs[cid] = extra
    return attrs


def draw(stdscr, grid, attrs, h, w):
    """Centre the track in the window and frame it, instead of stretching it."""
    ph, pw = len(grid), len(grid[0])
    top = max(1, (h - ph) // 2)
    left = max(1, (w - pw) // 2)
    frame = attrs.get(C_FRAME, 0)

    stdscr.erase()
    put = stdscr.addstr
    try:
        if top >= 1 and left >= 1 and top + ph < h and left + pw + 1 < w:
            put(top - 1, left - 1, "+" + "-" * pw + "+", frame)
            put(top + ph, left - 1, "+" + "-" * pw + "+", frame)
            for y in range(ph):
                put(top + y, left - 1, "|", frame)
                put(top + y, left + pw, "|", frame)
    except curses.error:
        pass

    for y, row in enumerate(grid):
        gy = top + y
        if gy >= h:
            break
        for x, (ch, cid) in enumerate(row):
            if ch == " ":
                continue
            gx = left + x
            if gx >= w - 1:
                break
            try:
                stdscr.addch(gy, gx, ch, attrs.get(cid, 0))
            except curses.error:
                pass
    stdscr.refresh()


def run(stdscr, args):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)
    attrs = build_attrs()

    h, w = stdscr.getmaxyx()
    game = Game(w - 4, h - 4)
    watch = Sessions() if (not args.no_watch and Sessions.available()) else None
    meter = None
    if watch:
        meter = TokenMeter()
        meter.start()
    best = load_best()
    last = time.monotonic()

    while True:
        now = time.monotonic()
        dt = min(0.1, now - last)
        last = now

        while True:
            key = stdscr.getch()
            if key == -1:
                break
            if key in QUIT_KEYS:
                save_best(max(best, int(game.score)))
                if meter:
                    meter.stop()
                return
            if key in JUMP_KEYS:
                if game.dead:
                    best = max(best, int(game.score))
                    save_best(best)
                    game.reset()
                    game.started = True
                else:
                    game.jump()
            elif key == curses.KEY_RESIZE:
                h, w = stdscr.getmaxyx()
                game.resize(w - 4, h - 4)

        if watch:
            watch.poll(now)
            if watch.finished:
                game.banner = banner_for(watch.finished, game.w)
                game.flash = 3.5
                curses.flash()

        game.step(dt)
        if game.dead:
            best = max(best, int(game.score))

        nh, nw = stdscr.getmaxyx()
        if (nh, nw) != (h, w):
            h, w = nh, nw
            game.resize(w - 4, h - 4)

        if w < MIN_W + 4 or h < MIN_H + 4:
            stdscr.erase()
            try:
                stdscr.addstr(0, 0, "pane too small: need %dx%d" % (MIN_W + 4, MIN_H + 4))
            except curses.error:
                pass
            stdscr.refresh()
        else:
            status = {"best": best,
                      "claude": watch.label() if watch else None,
                      "sessions": watch.rows if watch else [],
                      "wasted": meter.total if meter and meter.ready else None}
            draw(stdscr, render(game, status), attrs, h, w)

        time.sleep(max(0.0, FRAME - (time.monotonic() - now)))


# ------------------------------------------------------------------ cli

def demo(args):
    """Render one frame as plain text. Needs no terminal, used by the tests."""
    game = Game(args.width, args.height, seed=args.seed)
    game.started = True
    for i in range(args.frames):
        if i == args.jump_at:
            game.jump()
        game.step(FRAME)
    grid = render(game, {"best": 1337, "claude": "claude: 2 working, 1 ready"})
    print("+" + "-" * game.w + "+")
    for row in grid:
        print("|" + "".join(ch for ch, _ in row) + "|")
    print("+" + "-" * game.w + "+")
    print("score=%d speed=%.1f max=%.1f obstacles=%d dead=%s"
          % (game.score, game.speed, game.max_speed, len(game.obstacles), game.dead))


def print_sessions():
    if not Sessions.available():
        print("no ~/.claude/projects, nothing to report")
        return
    rows = Sessions().scan()
    if not rows:
        print("no Claude sessions in the last 6 hours")
        return
    home = os.path.expanduser("~")
    print("%-9s %-11s %-12s %-30s %s"
          % ("STATE", "LAST SEEN", "LAST TOOL", "DIRECTORY", "SESSION"))
    for r in rows:
        age = r["age"]
        seen = "%.0fs ago" % age if age < 90 else "%.0fm ago" % (age / 60)
        print("%-9s %-11s %-12s %-30s %s"
              % (r["state"], seen, r["tool"] or "-",
                 (r["cwd"] or "?").replace(home, "~")[:30], r["id"]))
    working = sum(1 for r in rows if r["state"] == "working")
    ready = sum(1 for r in rows if r["state"] == "ready")
    print("\n%d session(s): %d working, %d waiting for you"
          % (len(rows), working, ready))


def doctor():
    print("claudino %s" % VERSION)
    print("python          %s" % sys.version.split()[0])
    print("TERM            %s" % os.environ.get("TERM", "(unset)"))
    print("TERM_PROGRAM    %s" % os.environ.get("TERM_PROGRAM", "(unset)"))
    try:
        size = os.get_terminal_size()
        need = "" if size.columns >= MIN_W + 4 and size.lines >= MIN_H + 4 \
            else "  TOO SMALL, need %dx%d" % (MIN_W + 4, MIN_H + 4)
        play = Game(size.columns - 4, size.lines - 4)
        print("pane            %dx%d%s" % (size.columns, size.lines, need))
        print("track           %dx%d, top speed %.0f cells/s"
              % (play.w, play.h, play.max_speed))
    except OSError:
        print("pane            unknown (not a terminal)")
    print("high score      %s (%d)" % (score_path(), load_best()))
    print("jump            peak %.1f rows, %.2fs airborne"
          % (JUMP_V ** 2 / (2 * GRAVITY), AIR_TIME))
    if Sessions.available():
        meter = TokenMeter()
        started = time.time()
        meter._sweep()
        print("tokens          %s spent across every session (%.1fs to add up)"
              % (human(meter.total), time.time() - started))
    print()
    print_sessions()


def main():
    p = argparse.ArgumentParser(prog="claudino", description=__doc__.splitlines()[0])
    p.add_argument("--sessions", action="store_true",
                   help="list every recent Claude session and exit")
    p.add_argument("--doctor", action="store_true", help="check this terminal and exit")
    p.add_argument("--ascii", action="store_true",
                   help="pure ASCII sprites, for terminals set to treat\n                         ambiguous-width characters as double width")
    p.add_argument("--no-watch", action="store_true", help="do not read Claude's status")
    p.add_argument("--demo", action="store_true", help="print one frame as text and exit")
    p.add_argument("--frames", type=int, default=60)
    p.add_argument("--jump-at", type=int, default=-1)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--width", type=int, default=100)
    p.add_argument("--height", type=int, default=18)
    p.add_argument("--version", action="version", version="claudino " + VERSION)
    args = p.parse_args()
    set_style(args.ascii)

    if args.sessions:
        print_sessions()
    elif args.doctor:
        doctor()
    elif args.demo:
        demo(args)
    else:
        curses.wrapper(run, args)


if __name__ == "__main__":
    main()
