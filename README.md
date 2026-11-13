```
.__                                             .___      __    _____.__.__                 
|  |__ _____  ___.__._____  ______   ____     __| _/_____/  |__/ ____\__|  |   ____   ______
|  |  \\__  \<   |  |\__  \ \____ \ /  _ \   / __ |/  _ \   __\   __\|  |  | _/ __ \ /  ___/
|   Y  \/ __ \\___  | / __ \|  |_> >  <_> ) / /_/ (  <_> )  |  |  |  |  |  |_\  ___/ \___ \ 
|___|  (____  / ____|(____  /   __/ \____/  \____ |\____/|__|  |__|  |__|____/\___  >____  >
     \/     \/\/          \/|__|                 \/                               \/     \/ 
```

# hayapo's dotfile w/ chezmoi

Global Claude and Codex instructions share one source at
`.chezmoitemplates/agent-instructions/base.md.tmpl`. Chezmoi renders it to
`~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md`. Edit the shared source rather
than either generated file. APM owns skills and hooks; its global compile leaves
these hand-authored instruction files intact.
In a verified Herdr session, the shared instructions load the orchestration
skills (and the Herdr skill in herdr-tui). A manually started agent acts as
Chief before task enrollment; `agent-orchestration init` still requires a
concrete task before workers can launch.

## Setup

With reference to [ganyariya/dotfiles](https://github.com/ganyariya/dotfiles/blob/0c3a723325144cbd92b5573001c33e45b81306e1/README.md)

### mac

```bash
sh -c "$(curl -fsLS get.chezmoi.io)" -- -b $HOME/bin init --apply --verbose https://github.com/hayapo/dotfile_chezmoi.git
```

### linux or WSL

```bash
sudo apt update && \
sudo apt install -y build-essential curl file git procps zsh && \
chsh -s /usr/bin/zsh && \
sh -c "$(curl -fsLS get.chezmoi.io)" -- -b $HOME/bin init --apply --verbose https://github.com/hayapo/dotfile_chezmoi.git
```

### Homebrew packages

The first apply installs Homebrew if needed, then runs `brew bundle` after
`~/.Brewfile` has been deployed. Existing Homebrew installations are reused.
The bundle runs on the first apply and when the Brewfile changes. It installs
missing entries without upgrading installed packages and never runs cleanup.
On Ubuntu/WSL, install `build-essential`, `procps`, `curl`, `file`, and `git`
before applying if Homebrew is not already installed. Old glibc systems also
need Python 3.10+ with `venv` and `ensurepip` if APM is missing. On Ubuntu,
install it with `sudo apt install python3 python3-venv`. Homebrew may request
administrator authentication to install itself. On macOS, Homebrew may request the Xcode
Command Line Tools.

- macOS, Linux and WSL: install `herdr` and the shared CLI packages.
- Apple Silicon macOS: also install `herdr-app` via Homebrew Cask.
- Linux/WSL: install `xsel` for X11 clipboard support.
- Native Windows: Homebrew is not supported; use WSL for this setup.

The GUI app's Homebrew cask does not support Linux, Windows or Intel Macs.
See the [Herdr app installation guide](https://github.com/herdrdev/herdr-app#install)
for those platforms. Warp is not installed.

On WSL, `chezmoi apply` also copies the rendered WezTerm configuration to
`%USERPROFILE%\.wezterm.lua`. The Windows profile is discovered at runtime, and
the sync runs on first apply and whenever the rendered managed WezTerm config changes.

If a Homebrew run fails, fix the reported prerequisite or network issue and
reapply. Because the run-on-change command is recorded only after success,
chezmoi retries it on the next apply. To retry package setup explicitly, run:

```sh
chezmoi apply ~/.Brewfile
brew bundle --no-upgrade --file="$HOME/.Brewfile"
```

The apt update hook runs only on Debian or Ubuntu systems that provide `apt-get`.

Install Ponytail as a plugin in both Codex and Claude Code with the `/plugin`
commands printed during `chezmoi apply`. APM does not install Ponytail.

For machine-local shell credentials, place Zsh settings in
`~/.config/zsh/secrets.zsh`; the managed Zsh config sources it only when it is
readable. Its matching chezmoi source name is Git-ignored and excluded from
chezmoi management. Keep credentials out of tracked dotfiles. A `private_`
chezmoi source prefix sets restrictive file permissions; it does not encrypt
the file or protect it in version control.
