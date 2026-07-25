# Deploy ApplyPilot as a 24/7 service

## Option A — tmux (simplest on any laptop)

```bash
cd /path/to/ApplyPilot
source .venv/bin/activate
tmux new -s applypilot './scripts/run-daemon.sh'
# detach: Ctrl-b d
# reattach: tmux attach -t applypilot
```

## Option B — systemd (Ubuntu/Debian laptop)

```bash
# 1. Install to /opt/applypilot (or edit paths in the unit)
sudo mkdir -p /opt/applypilot
sudo rsync -a --exclude .venv ./ /opt/applypilot/
cd /opt/applypilot
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install --no-deps python-jobspy
pip install pydantic tls-client requests markdownify regex

# 2. Install Grok Build CLI + Chrome + Node 18+

# 3. Configure
applypilot init
# edit ~/.applypilot/.env  (GEMINI_API_KEY, XAI_API_KEY optional, APPLY_BACKEND=grok)

# 4. Unit file (edit User/WorkingDirectory if needed)
sudo cp deploy/applypilot-daemon.service /etc/systemd/system/applypilot-daemon.service
# replace User=%i with your username, or use a template unit
sudo systemctl daemon-reload
sudo systemctl enable --now applypilot-daemon.service
sudo journalctl -u applypilot-daemon -f
```

## Option C — screen

```bash
screen -S applypilot ./scripts/run-daemon.sh
# detach: Ctrl-a d
# reattach: screen -r applypilot
```

## Dry-run first

```bash
./scripts/run-daemon.sh --dry-run
# or
applypilot daemon --dry-run
```
