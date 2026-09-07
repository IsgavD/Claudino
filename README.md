# claudino

A one-key terminal game to play while Claude Code is thinking.
You play as Claude. The obstacles are cacti.

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/IsgavD/Claudino/main/install.sh | sh
```

Then run it:

```sh
claudino
```

That is the whole install. No GitHub account, no login, no `sudo`, no
dependencies - it is a single Python file, and every Mac already has the
Python it needs.

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

Press space. That is the whole game.

<details>
<summary>What the installer does, and how to skip it</summary>

It finds a folder that is already on your PATH, checks you have Python 3.9 or
newer, downloads one file, and checks that file parses before putting it in
place so a half-finished download cannot install a broken game. It only
creates `~/.local/bin` if it has to, and then tells you the one line to add to
your shell profile.

#### By hand instead

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

</details>

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
counts them and then lists them:

```
                                       claude: 2 working, 1 ready
                                       > claudino        Bash
                                       > ai21-aoa-p~bfe4 Edit
                                       - ai21-aoa-p~5898 Bash
                                       . other-thing
```

- `>` **working** - running tools or writing
- `-` **ready** - finished, waiting for you
- `.` **idle** - nothing there for 15 minutes

The last column is the tool that session called most recently, which is a
decent guess at what it is doing. Several terminals open in one repo is
normal, so where the folder name repeats it gets the start of the session id
appended.

When a session finishes, the game flashes and names it, so you know *which*
terminal to go back to:

```
              claudino
              is done
```

If two finish at the same moment, both are named. Sessions that were already
waiting when you started the game are not announced - they finished before you
opened it, so they are not news.

You can also check from the shell, without starting the game:

```sh
claudino --sessions
```

```
STATE     LAST SEEN   LAST TOOL    DIRECTORY                      SESSION
working   3s ago      Bash         ~/claudino                     a44a6540
ready     3m ago      Edit         ~/work/repos/thing             bfe4dc9e
idle      46m ago     -            ~/scratch                      b7f31693
```

## Wasted tokens

The middle of the HUD counts every token Claude has ever spent on this
machine, across every session:

```
 00162  best 00900   32.0B wasted
```

That number is mostly cache reads. Each turn re-reads the conversation so far,
so a long session bills the same context over and over. Actual generated
output is a tiny slice of it - on the machine this was built on, 78.6M of
output against 31.3B of cache reads.

Adding it up means reading a few hundred megabytes of logs, so it happens on a
background thread. The first pass takes about a second, and after that each
sweep reads only the bytes appended since the last one, which is under a
millisecond. The game never waits for it.

## What it reads

A game that reads your Claude logs should be specific about what it takes.
It opens the files in `~/.claude/projects/` and reads four things:

| Read | Used for |
| --- | --- |
| the `type` of records, and of their content blocks | working / ready / idle |
| the working directory of each session | the name in the list |
| the `name` of the last tool called | the last column |
| `message.usage` token counts | the wasted counter |

It does **not** read the text of any message, and it does **not** read tool
inputs - those hold shell commands and file paths, and none of that belongs on
a screen someone might screenshot. It never writes to those files.

To switch the whole thing off:

```sh
claudino --no-watch
```

It also turns itself off if you have no Claude sessions.

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
