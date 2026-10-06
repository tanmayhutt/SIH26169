#!/usr/bin/env bash
# Deploy everything to the server: the repository into ~/SIH169, a Python venv, the web app as a
# systemd service on 127.0.0.1:8095, the progress site, downloads, and one Caddy site block.
#
#   bash webapp/deploy.sh                       # full deploy
#   HOST=ubuntu@1.2.3.4 DOMAIN=x.example.com bash webapp/deploy.sh
#
# Site map on $DOMAIN (public, no login):
#   /               the web app (FastAPI on 127.0.0.1:8095): /api/*, /ws/*, /runs/*, /static/*
#   /about/         progress record and documents (static)
#   /downloads/     desktop builds, PDFs, demo video (static, browsable)
#   /progress, /app old addresses, redirected to /about/ and / (temporary redirects, never cached)
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

echo "== 2. static site (about, downloads) -> $SITE"
# The progress site and the documents are not in this repository: they come from the team's records
# folder (a sibling named SIH169-records by default; override with RECORDS). Without it, only the
# web app and the downloads already on the server are deployed.
RECORDS=${RECORDS:-$HERE/../SIH169-records}
STAGE=$(mktemp -d)
mkdir -p "$STAGE/about/content" "$STAGE/downloads"
if [ -d "$RECORDS/site" ]; then
cp "$RECORDS/site/index.html" "$RECORDS/site/progress.json" "$STAGE/about/"
cp "$RECORDS/site/plan.html" "$STAGE/about/plan.html"
cp "$RECORDS"/record/{PROGRESS,COMPLIANCE,ARCHITECTURE,KNOWLEDGE_TRANSFER,HANDOVER,TESTING_GUIDE,DEMO_SCRIPT}.md "$RECORDS/sources/manual/USER_MANUAL.md" "$HERE/README.md" "$STAGE/about/content/"
cp "$RECORDS"/deliverables/*.pdf "$STAGE/downloads/" 2>/dev/null || true
else
echo "   records folder $RECORDS not found: the progress site and documents are left as they are on the server"
fi
# the same deck under its earlier name, for links already shared
[ -f "$STAGE/downloads/ARGUS_SIH2026_26169.pdf" ] && cp "$STAGE/downloads/ARGUS_SIH2026_26169.pdf" "$STAGE/downloads/LAKSHYA_SIH2026_26169.pdf"
cp "$RECORDS/deliverables/ARGUS-demo.mp4" "$STAGE/downloads/" 2>/dev/null || true
# the same video under its earlier name, which the submitted deck links to
[ -f "$STAGE/downloads/ARGUS-demo.mp4" ] && cp "$STAGE/downloads/ARGUS-demo.mp4" "$STAGE/downloads/FSOC-Tracker-demo.mp4"
for z in "$HERE"/dist/*.zip "$HERE"/dist/*.tar.gz; do [ -f "$z" ] && cp "$z" "$STAGE/downloads/"; done
cat > "$STAGE/downloads/index.html" <<'EOF'
<!doctype html><html lang="en"><head><meta charset="utf-8"><title>SIH26169 downloads</title><link rel="icon" type="image/svg+xml" href="/static/favicon.svg"><link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32.png">
<style>body{margin:0;background:#0A1117;color:#E3ECF1;font-family:"IBM Plex Sans",-apple-system,sans-serif;padding:40px 22px;max-width:760px;margin:0 auto}h1,h2{font-family:"IBM Plex Sans Condensed",sans-serif}h2{margin-top:28px;font-size:20px}a{color:#52C4DE}li{margin:8px 0}small{color:#8DA1AD}</style></head>
<body><h1>Downloads</h1>
<h2>Desktop application</h2><p><small>Runs offline. Unzip and open ARGUS.</small></p><ul>
<li><a href="ARGUS-windows-x64.zip">Windows</a> <small>64-bit, Windows 10 or 11</small></li>
<li><a href="ARGUS-linux-x64.tar.gz">Linux</a> <small>64-bit, Ubuntu 22.04 or newer</small></li>
<li><a href="ARGUS-macos-arm64.zip">macOS, Apple silicon</a> <small>macOS 13 or newer</small></li>
<li><a href="ARGUS-macos-intel.zip">macOS, Intel</a> <small>macOS 13 or newer</small></li>
</ul>
<h2>Documents</h2><ul>
<li><a href="USER_MANUAL.pdf">User manual</a> <small>installation, operation, parameters</small></li>
<li><a href="TECHNICAL_REPORT.pdf">Technical report</a></li>
<li><a href="ARGUS_SIH2026_26169.pdf">Presentation</a></li>
<li><a href="ARGUS-demo.mp4">Demo video</a> <small>about four minutes</small></li>
</ul><p><a href="/">Web app</a> &middot; <a href="/about/">Progress and documents</a></p></body></html>
EOF
ssh "$HOST" "sudo mkdir -p $SITE && sudo chown -R ubuntu:ubuntu $SITE"
# keep the archives already on the server when dist/ holds none locally (a docs-only deploy)
KEEP=()
ls "$HERE"/dist/*.zip "$HERE"/dist/*.tar.gz >/dev/null 2>&1 || KEEP=(--exclude '*.zip' --exclude '*.tar.gz')
[ -d "$RECORDS/site" ] || KEEP+=(--exclude 'about/' --exclude '*.pdf' --exclude '*.mp4')
rsync -az --delete ${KEEP[@]+"${KEEP[@]}"} --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r "$STAGE/" "$HOST:$SITE/site/"
ssh "$HOST" "chmod -R u=rwX,go=rX $SITE"   # caddy runs as its own user and must read the site
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
Description=SIH26169 ARGUS web app
After=network.target
[Service]
User=ubuntu
WorkingDirectory=$REPO
Environment=OMP_NUM_THREADS=2
ExecStart=$REPO/.venv/bin/uvicorn webapp.server:app --host 127.0.0.1 --port 8095 --proxy-headers --forwarded-allow-ips 127.0.0.1 --timeout-graceful-shutdown 5
Restart=always
RestartSec=3
TimeoutStopSec=15
LimitNOFILE=8192
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now sih26169-web >/dev/null
sudo systemctl restart sih26169-web
# caddy: one site block, imported by the main Caddyfile. The site is public (login removed on
# 2026-10-06 for the submission).
sudo tee /etc/caddy/sih26169.caddy >/dev/null <<EOF
# SIH26169 site. Managed by webapp/deploy.sh; edit there, not here.
#   /            web app (reverse proxy)      /about/      progress record (static)
#   /downloads/  builds and documents (static) /progress,/app  old addresses -> redirects
$DOMAIN {
    encode zstd gzip
    header {
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "no-referrer"
        X-Robots-Tag "noindex, nofollow"
    }
    # canonical addresses end with a slash
    redir /about /about/ 302
    redir /downloads /downloads/ 302

    # old addresses (temporary redirects so browsers never cache them)
    redir /progress /about/ 302
    redir /progress/* /about/ 302
    redir /app /  302
    redir /app/* / 302

    # static: progress record and documents
    handle_path /about/* {
        root * $SITE/site/about
        file_server
    }

    # static: desktop builds, PDFs, demo video
    handle_path /downloads/* {
        root * $SITE/site/downloads
        file_server browse
    }

    # everything else is the web app: /, /api/*, /ws/*, /runs/*, /static/*
    handle {
        reverse_proxy 127.0.0.1:8095 {
            transport http {
                read_timeout 600s
            }
        }
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
