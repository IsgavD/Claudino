#!/bin/sh
# claudino installer.
#
# No account, no login, no dependencies. Just downloads one Python file and
# puts it somewhere on your PATH.
#
#   curl -fsSL https://raw.githubusercontent.com/IsgavD/Claudino/main/install.sh | sh
#
# Prefer not to pipe a script into your shell? Fair. Read it first, or skip it
# entirely and follow the two-line install in the README.

set -eu

RAW="https://raw.githubusercontent.com/IsgavD/Claudino/main/claudino.py"

say()  { printf '%s\n' "$*"; }
fail() { printf 'claudino: %s\n' "$*" >&2; exit 1; }

# --- python 3.9 or newer ----------------------------------------------------
PY=""
for candidate in python3 /usr/bin/python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' \
       >/dev/null 2>&1; then
        PY="$candidate"
        break
    fi
done
[ -n "$PY" ] || fail "needs Python 3.9 or newer. On a Mac, run: xcode-select --install"

# --- somewhere on PATH to put it -------------------------------------------
on_path() {
    case ":${PATH}:" in *":$1:"*) return 0 ;; *) return 1 ;; esac
}

TARGET=""
for dir in "$HOME/.local/bin" "$HOME/bin" /usr/local/bin; do
    if on_path "$dir" && [ -w "$dir" ]; then TARGET="$dir"; break; fi
done
NEEDS_PATH=""
if [ -z "$TARGET" ]; then
    TARGET="$HOME/.local/bin"
    mkdir -p "$TARGET" || fail "cannot create $TARGET"
    on_path "$TARGET" || NEEDS_PATH="yes"
fi

# --- download ---------------------------------------------------------------
TMP="$(mktemp)" || fail "cannot create a temporary file"
trap 'rm -f "$TMP"' EXIT INT TERM

if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$RAW" -o "$TMP" || fail "download failed: $RAW"
elif command -v wget >/dev/null 2>&1; then
    wget -qO "$TMP" "$RAW" || fail "download failed: $RAW"
else
    fail "needs curl or wget"
fi

# A truncated download would install a broken game, so check before moving it.
"$PY" -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$TMP" \
    >/dev/null 2>&1 || fail "the download looks incomplete, try again"

# mktemp makes the file private (600); "chmod +x" alone would leave it 711,
# readable by nobody else. Set the mode outright.
chmod 755 "$TMP"
mv "$TMP" "$TARGET/claudino"
trap - EXIT INT TERM

say ""
say "  installed to $TARGET/claudino"
if [ -n "$NEEDS_PATH" ]; then
    case "${SHELL:-}" in
        *zsh)  RC="~/.zshrc"  ;;
        *bash) RC="~/.bashrc" ;;
        *)     RC="your shell profile" ;;
    esac
    say ""
    say "  $TARGET is not on your PATH. Add this to $RC:"
    say ""
    say "      export PATH=\"\$HOME/.local/bin:\$PATH\""
    say ""
    say "  or just run it directly:  $TARGET/claudino"
else
    say ""
    say "  run:  claudino"
fi
say ""
