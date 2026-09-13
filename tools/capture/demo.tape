# An intent typed into the surface, and what 495 does with it until there is a branch to merge.
#
# Every screen is held long enough to be read, and every question is walked answer by answer
# before one is taken: what a control does is on the screen beside it, and a recording that
# takes the first answer offered never shows the other three.
#
# Frames only: the GIF and the video are assembled by record.sh, which also stages the store
# this opens on and puts the `495` typed below on PATH. Nothing here is a mock-up — every
# command is the real one, and the run it opens is walked by the real engine.
Output frames/

Set Shell "bash"
Set FontFamily "SF Mono"
Set FontSize 16
Set Width 1400
Set Height 800
Set Padding 12
Set Framerate 20
Set TypingSpeed 25ms
Set WaitTimeout 240s

# Terminal.app's Basic profile in dark mode: its ground and its text straight from Terminal, and
# the ANSI palette it leaves at the system's own — the colours 495 is read in, not a new set.
Set Theme { "background": "#171717", "foreground": "#FFFFFF", "black": "#000000", "red": "#990000", "green": "#00A600", "yellow": "#999900", "blue": "#0000B2", "magenta": "#B200B2", "cyan": "#00A6B2", "white": "#BFBFBF", "brightBlack": "#666666", "brightRed": "#E50000", "brightGreen": "#00D900", "brightYellow": "#E5E500", "brightBlue": "#0000FF", "brightMagenta": "#E500E5", "brightCyan": "#00E5E5", "brightWhite": "#E5E5E5", "cursor": "#FFFFFF", "selection": "#3F638B" }

# The store is walked before the camera runs. This only steps into the project it was built in.
Hide
Type "cd $DEMO_PROJECT && clear"
Enter
Sleep 500ms
Show
Sleep 2s

# ---------------------------------------------------------------- what is usable here
Type "495 doctor"
Enter
Sleep 11s

# ---------------------------------------------------------------- what makes a change correct
Type "495 init"
Enter
Sleep 11s

# ---------------------------------------------------------------- the surface, and the store
Type "495 watch"
Enter
Sleep 11s

# An intent, in prose, typed where the run will open.
Type "c"
Sleep 3s
Type "Add a --shout option to the greeter: it prints the greeting in uppercase. Extend the check script to cover the option, both on its own and with a name."
Sleep 5s
Enter

# Who writes it — both answers, and what each one means, before one is taken.
Sleep 5s
Down
Sleep 5s
Down
Sleep 4s
Enter

# It profiles the project, then the specifier writes what must hold and what checks it.
Wait+Screen /waiting on you/
Sleep 3s
Type "n"
Sleep 11s

# The gate: three answers, each with what it does. Nothing is produced until one is taken.
Type "d"
Sleep 6s
Down
Sleep 5s
Down
Sleep 5s
Down
Sleep 4s
Enter

# ---------------------------------------------------------------- a producer, in its own worktree
Sleep 3s
Type "3"
Sleep 12s

# ---------------------------------------------------------------- the project's own commands
Type "4"
Sleep 6s
Down
Sleep 5s
Down
Sleep 6s

# ---------------------------------------------------------------- three independent readings
Type "5"
Sleep 7s
Down
Sleep 5s
Down
Sleep 5s

# ---------------------------------------------------------------- where each requirement stands
Wait+Screen /nothing has been merged/
Type "6"
Sleep 7s
Down
Sleep 5s
Down
Sleep 6s

# ---------------------------------------------------------------- the only command that writes
Type "m"
Sleep 7s
Down
Sleep 4s
Down
Sleep 4s
Down
Sleep 4s
Down
Sleep 4s
Enter
Sleep 5s
Down
Sleep 5s
Enter

# The eighth stop: what the branch you merged into holds, measured rather than assumed.
Sleep 3s
Type "8"
Wait+Screen /carries the verified change/
Sleep 12s

# ---------------------------------------------------------------- every run in the store
Type "l"
Sleep 8s
Down
Sleep 6s
Down
Sleep 6s
Down
Sleep 6s

Type "q"
Sleep 2s
