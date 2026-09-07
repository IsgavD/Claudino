#!/usr/bin/env python3
"""Fairness tests for claudino.

The prototype this replaced was mathematically unwinnable: some obstacles
could not be cleared at any jump timing, because the dino took longer to pass
through them than a jump kept it above them. These tests brute-force every
obstacle at every speed so that can never come back unnoticed.

Deterministic: fixed seeds, fixed time step, no wall-clock dependency.
Standard library only - run with `python3 test_claudino.py -v`.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import claudino as C

MIN_WINDOW_FRAMES = 5      # 250ms: a person must be able to hit it, not just a bot
MIN_REACTION_S = 1.0       # from an obstacle appearing to the last saving jump
WIDTHS = (60, 72, 90, 110)   # MIN_W .. MAX_PLAY_W


def speeds_for(width):
    """Every speed the game can actually reach in a pane this wide."""
    top = C.Game(width, 20).max_speed
    out, s = [], C.BASE_SPEED
    while s < top:
        out.append(round(s, 2))
        s += 2.0
    out.append(round(top, 2))
    return out


def fixed_speed_game(speed, width, height=20):
    """A Game pinned to one speed that never spawns, for isolated trials."""

    class Fixed(C.Game):
        @property
        def speed(self):
            return speed

        def spawn(self):
            pass

    g = Fixed(width, height, seed=0)
    g.started = True
    g.clouds = []
    return g


def trial(rows, speed, width, jump_frame):
    """Spawn one obstacle at the edge, jump at `jump_frame`. Did we survive?"""
    g = fixed_speed_game(speed, width)
    g.obstacles = [C.Obstacle(rows, width - 1)]
    limit = int(width / speed / C.FRAME) + 30
    for i in range(limit):
        if i == jump_frame:
            g.jump()
        g.step(C.FRAME)
        if g.dead:
            return False
        if not g.obstacles:
            return True
    return not g.dead


def jump_window(rows, speed, width):
    """Longest run of consecutive jump frames that clears the obstacle."""
    limit = int(width / speed / C.FRAME) + 5
    ok = [f for f in range(limit) if trial(rows, speed, width, f)]
    if not ok:
        return [], 0
    best = run = 1
    start = best_start = ok[0]
    for prev, cur in zip(ok, ok[1:]):
        if cur == prev + 1:
            run += 1
            if run > best:
                best, best_start = run, start
        else:
            run, start = 1, cur
    return list(range(best_start, best_start + best)), best


class Clearable(unittest.TestCase):
    def test_every_obstacle_is_clearable(self):
        """No obstacle may be impossible at any reachable speed."""
        for width in WIDTHS:
            for speed in speeds_for(width):
                for i, rows in enumerate(C.OBSTACLES):
                    _, size = jump_window(rows, speed, width)
                    self.assertGreater(
                        size, 0,
                        "obstacle %d (%d wide, %d tall) is unclearable at "
                        "speed %.1f in a %d-wide pane"
                        % (i, C.sprite_w(rows), len(rows), speed, width))

    def test_jump_window_is_humane(self):
        """A person needs a real window, not a single perfect frame."""
        for width in WIDTHS:
            for speed in speeds_for(width):
                for i, rows in enumerate(C.OBSTACLES):
                    _, size = jump_window(rows, speed, width)
                    self.assertGreaterEqual(
                        size, MIN_WINDOW_FRAMES,
                        "obstacle %d at speed %.1f in a %d-wide pane has only "
                        "%d good frames (%.0fms), need %d"
                        % (i, speed, width, size, size * C.FRAME * 1000,
                           MIN_WINDOW_FRAMES))

    def test_reaction_time_is_sufficient(self):
        """You must have time to see it before the last jump that saves you."""
        for width in WIDTHS:
            speed = C.Game(width, 20).max_speed
            for i, rows in enumerate(C.OBSTACLES):
                frames, _ = jump_window(rows, speed, width)
                latest = frames[-1] * C.FRAME
                self.assertGreaterEqual(
                    latest, MIN_REACTION_S,
                    "obstacle %d in a %d-wide pane at top speed %.1f gives only "
                    "%.2fs to react, need %.2fs"
                    % (i, width, speed, latest, MIN_REACTION_S))


class Playable(unittest.TestCase):
    def _bot_survives(self, seed, seconds, width=80):
        """Plays the way a person does: time the top of the jump to the cactus.

        A jump reaches its peak JUMP_V/GRAVITY seconds after take-off, so jump
        when the obstacle's centre is exactly that far from the dino's centre.
        This is a fixed rule, not a search: if it clears the game, so can a
        person who has learnt the timing. A search-based bot proves less,
        because a greedy search can strand itself and that says nothing about
        whether the game is fair.
        """
        apex = C.JUMP_V / C.GRAVITY
        g = C.Game(width, 20, seed=seed)
        g.started = True
        for _ in range(int(seconds / C.FRAME)):
            if not g.airborne and g.obstacles:
                near = min(g.obstacles, key=lambda o: o.x)
                centre = near.x + near.w / 2.0 - (C.DINO_X + C.DINO_W / 2.0)
                if 0 < centre / g.speed <= apex:
                    g.jump()
            g.step(C.FRAME)
            if g.dead:
                return False, g.score, "died at speed %.1f" % g.speed
        return True, g.score, "survived"

    def test_perfect_play_survives_ten_minutes(self):
        ok, score, why = self._bot_survives(seed=1, seconds=600)
        self.assertTrue(ok, "bot failed at score %d: %s" % (score, why))

    def test_perfect_play_survives_many_seeds(self):
        for seed in range(20):
            ok, score, why = self._bot_survives(seed=seed, seconds=45)
            self.assertTrue(ok, "seed %d failed at score %d: %s" % (seed, score, why))

    def test_perfect_play_survives_in_a_small_pane(self):
        for width in (C.MIN_W, 60):
            ok, score, why = self._bot_survives(seed=2, seconds=120, width=width)
            self.assertTrue(ok, "%d-wide pane failed at score %d: %s"
                            % (width, score, why))

    def test_no_input_dies(self):
        """A game you cannot lose is not a game."""
        g = C.Game(80, 20, seed=3)
        g.started = True
        for _ in range(int(30 / C.FRAME)):
            g.step(C.FRAME)
            if g.dead:
                return
        self.fail("standing still survived 30 seconds")


class Portability(unittest.TestCase):
    def _all_glyphs(self):
        seen = set()
        for width, height in ((C.MIN_W, C.MIN_H), (80, 24), (C.MAX_PLAY_W, C.MAX_PLAY_H)):
            g = C.Game(width, height, seed=5)
            g.started = True
            for i in range(200):
                if i % 37 == 0:
                    g.jump()
                g.step(C.FRAME)
                if g.dead:
                    g.reset()
                    g.started = True
            for row in render_all_states(g):
                seen.update(ch for ch, _ in row)
        return seen

    def test_default_glyphs_are_ascii_or_half_blocks(self):
        """Half-blocks are the only non-ASCII allowed, and only these three."""
        allowed = set(C.BLOCKS)
        for ch in self._all_glyphs():
            self.assertTrue(ord(ch) < 128 or ch in allowed,
                            "glyph %r is neither ASCII nor a half-block" % ch)

    def test_ascii_mode_is_pure_ascii(self):
        """--ascii must be safe where ambiguous-width characters go double."""
        C.set_style(True)
        try:
            for ch in self._all_glyphs():
                self.assertLess(ord(ch), 128,
                                "glyph %r is not ASCII in --ascii mode" % ch)
        finally:
            C.set_style(False)

    def test_both_styles_are_the_same_size(self):
        """--ascii must not change the physics, so it must not change widths."""
        C.set_style(False)
        blocks = (C.DINO_W, len(C.DINO_RUN[0]), [C.sprite_w(o) for o in C.OBSTACLES])
        C.set_style(True)
        try:
            plain = (C.DINO_W, len(C.DINO_RUN[0]), [C.sprite_w(o) for o in C.OBSTACLES])
        finally:
            C.set_style(False)
        self.assertEqual(blocks, plain)

    def test_renders_at_minimum_size(self):
        g = C.Game(C.MIN_W, C.MIN_H, seed=1)
        g.started = True
        for _ in range(120):
            g.step(C.FRAME)
        grid = C.render(g, {"best": 99999, "claude": "claude: working"})
        self.assertEqual(len(grid), C.MIN_H)
        self.assertTrue(all(len(r) == C.MIN_W for r in grid))

    def test_speed_cap_respects_pane_width(self):
        """Narrow panes must not outrun a human's reaction time."""
        for width in WIDTHS:
            g = C.Game(width, 20)
            crossing = (width - C.DINO_X) / g.max_speed
            self.assertGreaterEqual(
                crossing, C.MIN_CROSSING_TIME - 1e-9,
                "in a %d-wide pane an obstacle crosses in %.2fs"
                % (width, crossing))

    def test_track_is_capped_not_stretched(self):
        """A full-screen window must not become a very long empty strip."""
        g = C.Game(400, 120)
        self.assertEqual((g.w, g.h), (C.MAX_PLAY_W, C.MAX_PLAY_H))

    def test_quips_fit_the_smallest_track(self):
        """A quip wider than the track would be cut off mid-word."""
        longest = max(C.CLEARED_QUIPS + C.DEATH_QUIPS, key=len)
        self.assertLessEqual(len(longest), C.MIN_W - 8,
                             "%r is %d chars, too wide for a %d-cell track"
                             % (longest, len(longest), C.MIN_W))

    def test_quips_are_ascii_and_unique(self):
        for quip in C.CLEARED_QUIPS + C.DEATH_QUIPS:
            self.assertTrue(all(ord(c) < 128 for c in quip), repr(quip))
        for pool in (C.CLEARED_QUIPS, C.DEATH_QUIPS):
            self.assertEqual(len(pool), len(set(pool)), "duplicate quip")

    def test_clearing_a_cactus_is_counted_once(self):
        """The quip fires on the pass, not on every frame after it."""
        g = C.Game(80, 20, seed=1)
        g.started = True
        apex = C.JUMP_V / C.GRAVITY
        for _ in range(1200):
            if not g.airborne and g.obstacles:
                near = min(g.obstacles, key=lambda o: o.x)
                centre = near.x + near.w / 2.0 - (C.DINO_X + C.DINO_W / 2.0)
                if 0 < centre / g.speed <= apex:
                    g.jump()
            g.step(C.FRAME)
            if g.dead:
                break
        self.assertGreater(g.cleared, 5)
        self.assertLessEqual(g.cleared, 1200)

    def test_score_file_is_outside_the_install_dir(self):
        """A re-install must not wipe your high score."""
        self.assertNotIn(os.path.dirname(os.path.abspath(C.__file__)),
                         C.score_path())


def render_all_states(g):
    grid = C.render(g, {"best": 12345, "claude": "claude: working"})
    dead = C.Game(g.w, g.h, seed=1)
    dead.started = True
    dead.dead = True
    grid += C.render(dead, {"best": 0, "claude": None})
    start = C.Game(g.w, g.h, seed=1)
    grid += C.render(start, {"best": 0, "claude": "claude: your turn"})
    flashing = C.Game(g.w, g.h, seed=1)
    flashing.started = True
    flashing.flash = 2.0
    grid += C.render(flashing, {"best": 1, "claude": "claude: idle"})
    return grid


class SessionBanner(unittest.TestCase):
    """The banner has to say which terminal to go back to, and only when true."""

    HOME = os.path.expanduser("~")

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.real_root = C.Sessions.ROOT
        C.Sessions.ROOT = self.root
        self.watch = C.Sessions()
        self.clock = 100.0

    def tearDown(self):
        C.Sessions.ROOT = self.real_root
        shutil.rmtree(self.root, ignore_errors=True)

    def session(self, sid, cwd, state):
        folder = os.path.join(self.root, "proj-" + sid)
        os.makedirs(folder, exist_ok=True)
        block = {"type": "tool_use" if state == "working" else "text"}
        records = [{"type": "user", "cwd": cwd, "message": {"content": [{"type": "text"}]}},
                   {"type": "assistant", "cwd": cwd, "message": {"content": [block]}}]
        with open(os.path.join(folder, sid + ".jsonl"), "w") as fh:
            for record in records:
                fh.write(json.dumps(record) + "\n")

    def poll(self):
        self.clock += 2.0
        self.watch.poll(self.clock)
        return self.watch.finished

    def test_nothing_is_announced_on_the_first_scan(self):
        """A session that finished before you opened the game is not news."""
        self.session("aaaaaaaa", self.HOME + "/work/thing", "ready")
        self.assertEqual(self.poll(), [])

    def test_a_session_finishing_is_announced_by_folder(self):
        self.session("aaaaaaaa", self.HOME + "/work/thing", "working")
        self.poll()
        self.session("aaaaaaaa", self.HOME + "/work/thing", "ready")
        self.assertEqual(self.poll(), ["thing"])

    def test_same_folder_sessions_are_told_apart(self):
        """Several terminals in one repo is normal; the name alone is useless."""
        for sid in ("aaaaaaaa", "bbbbbbbb"):
            self.session(sid, self.HOME + "/work/thing", "working")
        self.poll()
        self.session("aaaaaaaa", self.HOME + "/work/thing", "ready")
        self.assertEqual(self.poll(), ["thing (aaaaaaaa)"])

    def test_two_finishing_at_once_are_both_named(self):
        self.session("aaaaaaaa", self.HOME + "/work/one", "working")
        self.session("bbbbbbbb", self.HOME + "/work/two", "working")
        self.poll()
        self.session("aaaaaaaa", self.HOME + "/work/one", "ready")
        self.session("bbbbbbbb", self.HOME + "/work/two", "ready")
        self.assertEqual(sorted(self.poll()), ["one", "two"])

    def test_home_directory_is_not_shown_as_your_username(self):
        self.session("aaaaaaaa", self.HOME, "working")
        self.poll()
        self.session("aaaaaaaa", self.HOME, "ready")
        self.assertEqual(self.poll(), ["~"])

    def test_banner_fits_the_track(self):
        for names, expect_lines in (([], 0), (["one"], 2), (["one", "two"], 2)):
            lines = C.banner_for(names, 44)
            self.assertEqual(len(lines), expect_lines)
            for line in lines:
                self.assertLessEqual(len(line), 44 - 4)
        long = C.banner_for(["a-very-long-project-name"] * 6, 44)
        self.assertEqual(long[0], "6 sessions done")
        self.assertLessEqual(len(long[1]), 40)


class Tokens(unittest.TestCase):
    """The counter reads live files, so partial lines are the real risk."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.real_root = C.Sessions.ROOT
        C.Sessions.ROOT = self.root
        os.makedirs(os.path.join(self.root, "proj"))
        self.log = os.path.join(self.root, "proj", "s.jsonl")

    def tearDown(self):
        C.Sessions.ROOT = self.real_root
        shutil.rmtree(self.root, ignore_errors=True)

    def append(self, *usages, **kw):
        with open(self.log, "a") as fh:
            for usage in usages:
                fh.write(json.dumps({"type": "assistant",
                                     "message": {"usage": usage}}) + "\n")
            if kw.get("partial"):
                fh.write('{"type": "assistant", "message": {"usage": {"output_')

    def test_sums_every_token_field(self):
        self.append({"input_tokens": 1, "output_tokens": 2,
                     "cache_creation_input_tokens": 4,
                     "cache_read_input_tokens": 8})
        meter = C.TokenMeter()
        meter._sweep()
        self.assertEqual(meter.total, 15)

    def test_later_sweeps_only_count_new_lines(self):
        self.append({"output_tokens": 100})
        meter = C.TokenMeter()
        meter._sweep()
        meter._sweep()
        meter._sweep()
        self.assertEqual(meter.total, 100, "a re-read double counted")
        self.append({"output_tokens": 5})
        meter._sweep()
        self.assertEqual(meter.total, 105)

    def test_a_half_written_line_is_not_counted_then_is(self):
        """Logs are appended to live, so a sweep can land mid-line."""
        self.append({"output_tokens": 7}, partial=True)
        meter = C.TokenMeter()
        meter._sweep()
        self.assertEqual(meter.total, 7, "counted a partial line")
        with open(self.log, "a") as fh:      # the writer finishes the line
            fh.write('tokens": 3}}}\n')
        meter._sweep()
        self.assertEqual(meter.total, 10, "did not re-read the finished line")

    def test_baseline_is_the_first_sweep(self):
        self.append({"output_tokens": 1000})
        meter = C.TokenMeter()
        meter._sweep()
        self.assertEqual(meter.burned(), 0, "history counted as burned just now")
        self.append({"output_tokens": 25})
        meter._sweep()
        self.assertEqual(meter.burned(), 25)

    def test_bad_json_does_not_stop_the_count(self):
        with open(self.log, "a") as fh:
            fh.write('not json at all\n')
        self.append({"output_tokens": 9})
        meter = C.TokenMeter()
        meter._sweep()
        self.assertEqual(meter.total, 9)

    def test_human_readable_sizes(self):
        for value, want in ((999, "999"), (1500, "1.5k"), (2_000_000, "2.0M"),
                            (32_000_000_000, "32.0B"), (1.5e12, "1.5T")):
            self.assertEqual(C.human(value), want)


class Panel(unittest.TestCase):
    def rows(self, names):
        return [{"state": "working", "age": 1.0, "name": n, "cwd": "/x/" + n,
                 "id": "%08d" % i, "tool": "Bash", "short": n, "label": n}
                for i, n in enumerate(names)]

    def test_panel_never_overflows_the_track(self):
        for width in (C.MIN_W, 80, C.MAX_PLAY_W):
            g = C.Game(width, 20, seed=1)
            g.started = True
            grid = C.render(g, {"best": 99999, "claude": "claude: 9 working, 9 ready",
                                "sessions": self.rows(["a-very-long-project-name"] * 6),
                                "wasted": 32_000_000_000})
            self.assertEqual(len(grid), min(20, C.MAX_PLAY_H))
            for row in grid:
                self.assertEqual(len(row), min(max(width, C.MIN_W), C.MAX_PLAY_W))

    def test_panel_lists_at_most_its_row_budget(self):
        g = C.Game(100, 20, seed=1)
        g.started = True
        grid = C.render(g, {"best": 0, "claude": "claude: 9 working",
                            "sessions": self.rows(["p%d" % i for i in range(9)]),
                            "wasted": None})
        text = ["".join(ch for ch, _ in row) for row in grid]
        listed = sum(1 for name in ["p%d" % i for i in range(9)]
                     if any(name in line for line in text))
        self.assertLessEqual(listed, C.PANEL_ROWS)

    def test_sessions_in_one_folder_are_distinguishable(self):
        watch = C.Sessions()
        rows = [{"name": "repo", "id": "aaaaaaaa", "state": "working", "age": 1,
                 "cwd": "/x/repo", "tool": ""},
                {"name": "repo", "id": "bbbbbbbb", "state": "idle", "age": 2,
                 "cwd": "/x/repo", "tool": ""}]
        counts = {}
        for r in rows:
            counts[r["name"]] = counts.get(r["name"], 0) + 1
        shorts = [r["name"] if counts[r["name"]] == 1
                  else "%s~%s" % (r["name"][:10], r["id"][:4]) for r in rows]
        self.assertEqual(len(set(shorts)), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
