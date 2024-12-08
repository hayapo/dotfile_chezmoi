```
.__                                             .___      __    _____.__.__                 
|  |__ _____  ___.__._____  ______   ____     __| _/_____/  |__/ ____\__|  |   ____   ______
|  |  \\__  \<   |  |\__  \ \____ \ /  _ \   / __ |/  _ \   __\   __\|  |  | _/ __ \ /  ___/
|   Y  \/ __ \\___  | / __ \|  |_> >  <_> ) / /_/ (  <_> )  |  |  |  |  |  |_\  ___/ \___ \ 
|___|  (____  / ____|(____  /   __/ \____/  \____ |\____/|__|  |__|  |__|____/\___  >____  >
     \/     \/\/          \/|__|                 \/                               \/     \/ 
```

# hayapo's dotfile w/ chezmoi

## Setup

With reference to [ganyariya/dotfiles](https://github.com/ganyariya/dotfiles/blob/0c3a723325144cbd92b5573001c33e45b81306e1/README.md)

### mac

```bash
sh -c "$(curl -fsLS get.chezmoi.io)" -- -b $HOME/bin init --apply --verbose https://github.com/hayapo/dotfile_chezmoi.git
```

### linux or WSL

```bash
sudo apt update && \
sudo apt install -y curl git zsh && \
chsh -s /usr/bin/zsh && \
sh -c "$(curl -fsLS get.chezmoi.io)" -- -b $HOME/bin init --apply --verbose https://github.com/hayapo/dotfile_chezmoi.git
```
