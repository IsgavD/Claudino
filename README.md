# claudino

A one-key terminal game to play while Claude Code is thinking.
You play as Claude. The obstacles are cacti.

Press space. That is the whole game.

```
| 00104  best 00862                                           claude: 1 working, 3 ready |
|                                      .--.                   .                          |
|                                     (    )                                             |
|                                                                                        |
|              .-.  .                                                                    |
|     ▄███████▄   )                       .                                              |
|     ██▀███▀██                                              .           .--.            |
|     ██▄███▄██     '                                           `       (    )           |
|     ▀███████▀                                                                          |
|      ▀█   █▀                                                                           |
|                                                                                        |
|                                                                                        |
|                                                                                        |
|       █  █                                      ██                                     |
|       ▀██▀                                     ████                                    |
|        ██                                       ██                                     |
|_.__________.__________.__________.__________.__________.__________.__________._________|
| .                      .                      .                      .                 |
```

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/IsgavD/Claudino/main/install.sh | sh
```

Then:

```sh
claudino
```

No account, no login, no sudo, no dependencies. It is one Python file. The
script finds a folder that is already on your PATH, puts the file there, and
only creates `~/.local/bin` if it has to - in which case it tells you the one
line to add to your shell profile.

Python 3.9 or newer, which every Mac already has.

### Or do it by hand

Rather not pipe a script into your shell? Reasonable. It is 70 lines, so read
it first, or skip it:

```sh
mkdir -p ~/.local/bin
curl -fsSL https://raw.githubusercontent.com/IsgavD/Claudino/main/claudino.py \
  -o ~/.local/bin/claudino && chmod 755 ~/.local/bin/claudino
```

The `mkdir` is needed because macOS does not ship `~/.local/bin`. If that
folder is not on your PATH, add this to `~/.zshrc`:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Do not pipe the game itself (`curl ... | python3 -`). Piping makes the script
arrive on standard input, so the game has no terminal to read keys from and
will not start. The installer is fine to pipe; the game is not.

## Play

Open a second terminal pane next to Claude Code and run `claudino`. It needs
a pane at least 64 columns wide. In iTerm2
that is `Cmd+D` for a split, or `Cmd+T` for a tab. The game never touches your
Claude session, so it cannot interrupt it.

| Key | Action |
| --- | --- |
| space, up, w, k | jump |
| q | quit |

Claude has opinions about how the jump went. Clear a cactus and you may get
`Sauteed!`, `Exit code 0`, `Honest caveat: easy jump.` Hit one and you get
`It's a wash.`, `The sauce broke.`, `I appreciate you flagging that cactus.`
There are 98 of them.

Your best score is kept in `~/.config/claudino/highscore.json`.

## The status line

Most people have more than one Claude running at once, so the top right corner
counts all of them:

```
claude: 2 working, 1 ready
```

- **working** - Claude is running tools or writing
- **ready** - Claude has finished and is waiting for you
- **idle** - nothing has happened there for 15 minutes

When a session finishes, the game flashes and names it, so you know *which*
terminal to go back to:

```
              claudino
              is done
```

If you have several terminals open in the same repo, which is normal, the
folder name alone is not enough, so the session id is added:

```
      ai21-aoa-poc (88a63718)
              is done
```

If two finish at the same moment, both are named:

```
          2 sessions done
   claudino, ai21-aoa-poc (bbbbbbbb)
```

Sessions that were already waiting when you started the game are not
announced. They finished before you opened it, so they are not news.

You can also check from the shell, without starting the game:

```sh
claudino --sessions
```

```
STATE     LAST SEEN   DIRECTORY                          SESSION
working   11s ago     ~/work/repos/thing                 a44a6540
ready     15s ago     ~/work/repos/other                 88a63718
idle      52m ago     ~/scratch                          b7f31693

3 session(s): 1 working, 1 waiting for you
```

**What it reads.** It opens the logs in `~/.claude/projects/` and looks at
exactly two things: the `type` of the last few records, and the folder each
session was started in. It never reads the text of any message, and it never
writes anything. Run `claudino --no-watch` to switch it off, and it turns
itself off if you have no Claude sessions.

## Terminals

Tested in iTerm2 and Apple Terminal.app. It should also work in Warp, but that
is not confirmed yet - please open an issue either way.

Sprites are pixel art. Each character cell holds two pixels, drawn with the
half-block characters, because a terminal cell is about twice as tall as it is
wide - so a stacked pair is square. That doubles the vertical resolution, and
it is the only reason a nine-cell-wide sprite can look like anything.

Those three characters are the one compromise in the game. They are East Asian
"Ambiguous" width, which means they are a single cell only because all three
terminals default them that way. If you have switched ambiguous characters to
double width, the layout will tear. Run it like this instead:

```sh
claudino --ascii
```

That swaps in a pure-ASCII approximation with exactly the same dimensions, so
the game plays identically. Nothing else in the game leaves ASCII: no braille,
which renders with gaps in Warp, and no emoji, which vary by terminal.

The track is centred and framed rather than stretched to your whole window. A
full-screen terminal would otherwise turn it into a very long strip of empty
desert.

If something looks wrong:

```sh
claudino --doctor
```

It prints your Python version, `TERM`, pane size, the track size it chose, and
every session it can see.

## Why the game is fair

To clear an obstacle you must stay above it for longer than it takes to pass
through it:

```
time_above(h) = 2 * sqrt(JUMP_V^2 - 2 * GRAVITY * (h - 1)) / GRAVITY
overlap_time  = (dino_width + obstacle_width) / speed
```

The first version of this game failed that test. An 8-cell-wide dino took
0.55s to pass a cactus but stayed above it for only 0.49s, so some obstacles
could not be cleared at any timing at all. The game was unwinnable, and it did
not look it.

So `test_claudino.py` brute-forces every obstacle at every speed the game can
reach, in panes from 60 to 110 columns wide, and checks three things: that a
jump exists, that its window is at least 250ms so a person and not just a bot
can hit it, and that you get at least a full second to react. A bot using one
fixed timing rule then has to survive ten minutes.

Two consequences are worth knowing:

- Going faster makes obstacles **easier** to clear, because you spend less
  time inside them. Difficulty here is a reaction-time problem, not a physics
  one.
- A short jump is what lets cacti stand close together, because the gap
  between two of them has to cover a whole jump. Gravity is high so the hop
  lasts 0.78s; a floatier jump would leave the track half empty.

```sh
python3 test_claudino.py -v
```

## Licence

MIT.
