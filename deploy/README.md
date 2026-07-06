# Deploying QuantumLabs (Ubuntu 24.04)

The API runs as a systemd service on `127.0.0.1:8000`, with **Caddy** in front for
TLS + reverse proxy (`api.q-labs.dev`). SSE streaming works through Caddy via
`flush_interval -1`. The frontend (`web/`) is a separate static Next.js app you
host elsewhere (Vercel, or `npm run build && npm start`).

Assumes a fresh Ubuntu 24.04 host and a DNS **A record** `api.q-labs.dev → <server IP>`.

## 1. System packages
```bash
sudo apt update
sudo apt install -y python3 python3-venv git curl debian-keyring debian-archive-keyring apt-transport-https

# Caddy (official repo)
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

## 2. App user + code
```bash
sudo useradd --system --home /opt/quantumlabs --shell /usr/sbin/nologin quantumlabs
sudo mkdir -p /opt/quantumlabs
sudo chown quantumlabs:quantumlabs /opt/quantumlabs
sudo -u quantumlabs git clone https://github.com/takemewa-collab/QuantumLabs /opt/quantumlabs
```

## 3. Python venv + dependencies
```bash
cd /opt/quantumlabs
sudo -u quantumlabs python3 -m venv .venv
# the venv may ship without pip — bootstrap it:
sudo -u quantumlabs .venv/bin/python -m ensurepip --upgrade
# runtime deps (fastapi/uvicorn/openai + the RAG stack from pyproject.toml):
sudo -u quantumlabs .venv/bin/pip install fastapi uvicorn openai chromadb sentence-transformers
```
The app runs in-place from `WorkingDirectory=/opt/quantumlabs`, so the package
itself is not installed — only its dependencies.

## 4. Environment file (`/etc/quantumlabs/env`)
```bash
sudo mkdir -p /etc/quantumlabs
sudo tee /etc/quantumlabs/env >/dev/null <<'EOF'
ALLOWED_ORIGINS=https://q-labs.dev,https://www.q-labs.dev
API_KEY=change-me-to-a-long-random-secret
# LLM endpoint (OpenAI-compatible); defaults to local Ollama if unset:
QL_BASE_URL=http://127.0.0.1:11434/v1
QL_API_KEY=ollama
QL_MODEL=deepseek-coder-v2:16b
EOF
sudo chown root:quantumlabs /etc/quantumlabs/env
sudo chmod 640 /etc/quantumlabs/env
```
- Remove/blank `API_KEY` to run **without** auth.
- `ALLOWED_ORIGINS` is comma-separated; it must include the frontend's origin.

## 5. systemd service
```bash
sudo cp /opt/quantumlabs/deploy/quantumlabs-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now quantumlabs-api
sudo systemctl status quantumlabs-api
```

## 6. Caddy (TLS + SSE-safe proxy)
```bash
sudo cp /opt/quantumlabs/deploy/Caddyfile /etc/caddy/Caddyfile
# edit the domain in the Caddyfile if it differs
sudo systemctl reload caddy
```
Caddy fetches a Let's Encrypt certificate automatically. `flush_interval -1`
disables proxy buffering so SSE events stream in real time.

## 7. Verify
```bash
# no auth: returns [] or the session list
curl https://api.q-labs.dev/sessions
# with API_KEY set: 401 without a token, 200 with it
curl -H "Authorization: Bearer <API_KEY>" https://api.q-labs.dev/sessions
```

## Frontend config
Build the frontend pointing at the API (Next.js `NEXT_PUBLIC_*` are build-time):
```
NEXT_PUBLIC_API_URL=https://api.q-labs.dev
NEXT_PUBLIC_API_KEY=<same as API_KEY, or empty>
```

## Operations
- **Single worker** — the service runs `--workers 1`; task/approval state is
  in-memory, sessions persist as jsonl transcripts and rehydrate from disk.
- **Update:**
  ```bash
  sudo -u quantumlabs git -C /opt/quantumlabs pull
  sudo systemctl restart quantumlabs-api
  ```
- **Logs:** `journalctl -u quantumlabs-api -f`
