#!/usr/bin/env bash
# Deploy everything to the server: the repository into ~/SIH169, a Python venv, the web app as a
# systemd service on 127.0.0.1:8095, the progress site, downloads, and one Caddy site block.
#
#   bash webapp/deploy.sh                       # full deploy
#   HOST=ubuntu@1.2.3.4 DOMAIN=x.example.com bash webapp/deploy.sh
#
# Caddy layout on $DOMAIN:
#   /            landing page (web app or desktop application)
#   /app/        the web app (reverse proxy to the service)
#   /progress/   progress record, basic auth (credential set once on the server, see below)
#   /downloads/  desktop builds and the PDF documents
set -euo pipefail
HOST=${HOST:-ubuntu@15.206.247.203}
DOMAIN=${DOMAIN:-sih26169.blankpoint.club}
REPO=/home/ubuntu/SIH169
SITE=/srv/sih26169
HERE=$(cd "$(dirname "$0")/.." && pwd)

echo "== 1. repository -> $HOST:$REPO"
ssh "$HOST" "mkdir -p $REPO"
rsync -az --delete \
  --exclude .venv --exclude results --exclude dist --exclude build --exclude .git --exclude '__pycache__' --exclude '*.pyc' \
  --exclude context.md --exclude '.pytest_cache' \
  "$HERE/" "$HOST:$REPO/"

echo "== 2. static site (landing, progress, downloads) -> $SITE"
STAGE=$(mktemp -d)
mkdir -p "$STAGE/progress/content/docs" "$STAGE/downloads"
cp "$HERE/web/landing.html" "$STAGE/index.html"
cp "$HERE/web/index.html" "$HERE/web/progress.json" "$HERE/web/plan.html" "$STAGE/progress/"
cp "$HERE/PROGRESS.md" "$HERE/COMPLIANCE.md" "$HERE/ARCHITECTURE.md" "$HERE/README.md" "$STAGE/progress/content/"
cp "$HERE/docs/USER_MANUAL.md" "$HERE/docs/TECHNICAL_REPORT.md" "$STAGE/progress/content/docs/"
cp "$HERE/docs/USER_MANUAL.pdf" "$HERE/docs/TECHNICAL_REPORT.pdf" "$STAGE/downloads/" 2>/dev/null || true
for z in "$HERE"/dist/*.zip; do [ -f "$z" ] && cp "$z" "$STAGE/downloads/"; done
cat > "$STAGE/downloads/index.html" <<'EOF'
<!doctype html><html lang="en"><head><meta charset="utf-8"><title>SIH26169 downloads</title>
<style>body{margin:0;background:#0A1117;color:#E3ECF1;font-family:"IBM Plex Sans",-apple-system,sans-serif;padding:40px 22px;max-width:760px;margin:0 auto}h1{font-family:"IBM Plex Sans Condensed",sans-serif}a{color:#52C4DE}li{margin:8px 0}small{color:#8DA1AD}</style></head>
<body><h1>Downloads and documents</h1><ul>
<li><a href="FSOC-Tracker-macos-arm64.zip">FSOC-Tracker-macos-arm64.zip</a> <small>desktop application, Apple silicon. Unzip and run FSOC-Tracker. macOS may ask you to allow it in System Settings, Privacy and Security.</small></li>
<li><a href="USER_MANUAL.pdf">USER_MANUAL.pdf</a> <small>installation, operation, every parameter, Benchmark 2, metric definitions</small></li>
<li><a href="TECHNICAL_REPORT.pdf">TECHNICAL_REPORT.pdf</a> <small>problem understanding, architecture, methods, tests, measured performance, appendices</small></li>
<li>Windows and Linux <small>build from source: clone the repository, then <code>pip install -e ".[dev]"</code> and <code>pyinstaller fsoc_tracker.spec</code>. Prebuilt archives will appear here when built.</small></li>
</ul><p><a href="/">Back</a></p></body></html>
EOF
ssh "$HOST" "sudo mkdir -p $SITE && sudo chown -R ubuntu:ubuntu $SITE"
rsync -az --delete --chmod=D755,F644 "$STAGE/" "$HOST:$SITE/site/"
rm -rf "$STAGE"

echo "== 3. venv, service, caddy"
ssh "$HOST" bash -s "$REPO" "$DOMAIN" "$SITE" <<'REMOTE'
set -euo pipefail
REPO=$1; DOMAIN=$2; SITE=$3
cd "$REPO"
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e ".[web]"
mkdir -p results/web results/uploads
# systemd service
sudo tee /etc/systemd/system/sih26169-web.service >/dev/null <<EOF
[Unit]
Description=SIH26169 FSOC Tracker web app
After=network.target
[Service]
User=ubuntu
WorkingDirectory=$REPO
Environment=OMP_NUM_THREADS=2
ExecStart=$REPO/.venv/bin/uvicorn webapp.server:app --host 127.0.0.1 --port 8095 --root-path /app
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now sih26169-web >/dev/null
sudo systemctl restart sih26169-web
# caddy: one site block, imported by the main Caddyfile; basic auth hash is created once and kept
HASHFILE=/etc/caddy/sih26169.progress.hash
if ! sudo test -s "$HASHFILE"; then echo "progress basic auth hash missing: create it with  sudo bash -c 'caddy hash-password --plaintext <password> > $HASHFILE'"; exit 2; fi
HASH=$(sudo cat "$HASHFILE")
USERNAME=$(sudo cat /etc/caddy/sih26169.progress.user 2>/dev/null || echo REDACTED)
sudo tee /etc/caddy/sih26169.caddy >/dev/null <<EOF
# SIH26169: landing, web app, progress record, downloads. Managed by webapp/deploy.sh.
$DOMAIN {
    encode zstd gzip
    header {
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "no-referrer"
        X-Robots-Tag "noindex, nofollow"
    }
    redir /app /app/ 308
    redir /progress /progress/ 308
    redir /downloads /downloads/ 308
    handle_path /app/* {
        reverse_proxy 127.0.0.1:8095 {
            transport http {
                read_timeout 600s
            }
        }
    }
    handle /progress/* {
        basic_auth {
            $USERNAME $HASH
        }
        root * $SITE/site
        file_server
    }
    handle /downloads/* {
        root * $SITE/site
        file_server browse
    }
    handle {
        root * $SITE/site
        file_server
    }
}
EOF
grep -q "import /etc/caddy/sih26169.caddy" /etc/caddy/Caddyfile || echo "import /etc/caddy/sih26169.caddy" | sudo tee -a /etc/caddy/Caddyfile >/dev/null
sudo caddy validate --config /etc/caddy/Caddyfile >/dev/null && sudo systemctl reload caddy
sleep 2
echo "service: $(systemctl is-active sih26169-web)   caddy: $(systemctl is-active caddy)"
curl -s http://127.0.0.1:8095/api/health
echo
REMOTE
echo "== done: https://$DOMAIN/"
