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
| space, up, w, k | jump, and choose on the menu |
| up, down, 1 2 3 | pick a difficulty |
| d | back to the menu after a game |
| q | quit |

Claude has opinions about how the jump went. Clear a cactus and you may get
`Sauteed!`, `Exit code 0`, `Honest caveat: easy jump.` Hit one and you get
`It's a wash.`, `The sauce broke.`, `I appreciate you flagging that cactus.`
There are 98 of them.

Your best score is kept in `~/.config/claudino/highscore.json`.

## Difficulty

The game opens on a menu. Up and down to choose, space to run, or skip it with
`claudino --difficulty hard`. Best scores are kept per level, because
comparing a hard score with an easy one means nothing.

| | starts at | tops out at | gap between cacti | jump |
| --- | --- | --- | --- | --- |
| easy | 22 cells/s | 36 | widest | floatiest, 1.03s |
| normal | 26 cells/s | 58 | medium | 0.91s |
| hard | 32 cells/s | 76 | tightest | 0.91s |

Easy has a floatier jump, and that is not decoration. **A slower game is not
automatically an easier one.** At a lower speed you spend longer inside a
cactus, so the window to jump it gets *narrower*. Easy's starting speed with
the normal jump leaves a 3.3-frame window against normal's 5.1 - it would have
shipped as the hardest setting in the game. The fairness tests run on all
three levels, which is how that got caught.

## The competition

Five rivals drift overhead: OpenAI, Gemini, Grok, Meta AI and DeepSeek.

```
      █                    ▄█████ ██▄▄▄
     ███                  ████████▄███▀
  ▄▄█████▄▄               █   ▀██████
  ▀▀█████▀▀               ▀█▄ ▄ ████
     ███                   ▀██████▀█
      █
```

These are the official SVG marks, rendered at 512 pixels and area-downsampled
so the thin strokes survive, then checked by eye. Rasterising straight to a
small size destroys them.

They are in the sky for a reason. A mark needs about 13 cells across to be
recognisable, and an obstacle may not exceed 4 - a wider one takes longer to
pass, which eats the window to jump it. At four cells every one of these is
the same indistinguishable blob. So the cacti stay green, and the rivals get
the one part of the screen with room.

## The status line

Most people have more than one Claude running at once, so the top right corner
counts them and then lists them:

```
                                       claude: 2 working, 1 ready
                                       > claudino          Bash
                                       > ai21-aoa-poc bfe4 Edit
                                       - ai21-aoa-poc 5898 Bash
```

- `>` **working** - running tools or writing
- `-` **ready** - finished, waiting for you

Idle sessions are not listed and not counted, so the summary above always
matches the rows below it.

The session in the folder you started the game from is hidden, since that is
almost always the one sitting next to you and listing it back is just noise.
Use `--show-all` to keep it, or `--hide FOLDER` to drop others.

The last column is the tool that session called most recently, which is a
decent guess at what it is doing. Several terminals open in one repo is
normal, so where the folder name repeats the session id gets its own column
next to the whole folder name.

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

The middle of the HUD counts the tokens spent by the sessions that are
currently alive, in dimmer type than your score:

```
 00162  best 00900   Tokens Wasted (in your Live Sessions) 6.7B
```

On a narrow pane it shortens to `Tokens Wasted 6.7B` rather than disappearing.

Only live sessions count. Adding up every log ever written gives a bigger
number and a meaningless one, since most of it belongs to work finished days
ago. When a session goes quiet its total drops back out.

That number is mostly cache reads. Each turn re-reads the conversation so far,
so a long session bills the same context over and over. Actual generated
output is a tiny slice of it - on the machine this was built on, 78.6M of
output against 31.3B of cache reads across all history.

It is still ~185 MB of log, so it happens on a background thread. The first
pass takes about a quarter of a second, and after that each sweep reads only
the bytes appended since the last one, which is under a millisecond. Measured
effect on frame time: worst frame 1.1ms to 3.3ms, against a 50ms budget.

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
