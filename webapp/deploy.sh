#!/usr/bin/env bash
# Deploy everything to the server: the repository into ~/SIH169, a Python venv, the web app as a
# systemd service on 127.0.0.1:8095, the progress site, downloads, and one Caddy site block.
#
#   bash webapp/deploy.sh                       # full deploy
#   HOST=ubuntu@1.2.3.4 DOMAIN=x.example.com bash webapp/deploy.sh
#
# Site map on $DOMAIN (everything behind one basic-auth login):
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
STAGE=$(mktemp -d)
mkdir -p "$STAGE/about/content/docs" "$STAGE/downloads"
cp "$HERE/site/index.html" "$HERE/site/progress.json" "$STAGE/about/"
cp "$HERE/site/plan.html" "$STAGE/about/plan.html"
cp "$HERE/docs/PROGRESS.md" "$HERE/docs/COMPLIANCE.md" "$HERE/docs/ARCHITECTURE.md" "$HERE/README.md" "$STAGE/about/content/"
cp "$HERE/docs/USER_MANUAL.md" "$HERE/docs/TECHNICAL_REPORT.md" "$STAGE/about/content/docs/"
cp "$HERE/docs/USER_MANUAL.pdf" "$HERE/docs/TECHNICAL_REPORT.pdf" "$STAGE/downloads/" 2>/dev/null || true
cp "$HERE/docs/submission/ARGUS_SIH2026_26169.pdf" "$STAGE/downloads/" 2>/dev/null || true
# the same deck under its earlier name, for links already shared
[ -f "$STAGE/downloads/ARGUS_SIH2026_26169.pdf" ] && cp "$STAGE/downloads/ARGUS_SIH2026_26169.pdf" "$STAGE/downloads/LAKSHYA_SIH2026_26169.pdf"
cp "$HERE/docs/demo/ARGUS-demo.mp4" "$STAGE/downloads/" 2>/dev/null || true
# the same video under its earlier name, which the submitted deck links to
[ -f "$STAGE/downloads/ARGUS-demo.mp4" ] && cp "$STAGE/downloads/ARGUS-demo.mp4" "$STAGE/downloads/FSOC-Tracker-demo.mp4"
cp "$HERE/docs/DEMO_SCRIPT.md" "$HERE/docs/TESTING_GUIDE.md" "$HERE/docs/HANDOVER.md" "$HERE/docs/KNOWLEDGE_TRANSFER.md" "$STAGE/about/content/docs/" 2>/dev/null || true
for z in "$HERE"/dist/*.zip "$HERE"/dist/*.tar.gz; do [ -f "$z" ] && cp "$z" "$STAGE/downloads/"; done
cat > "$STAGE/downloads/index.html" <<'EOF'
<!doctype html><html lang="en"><head><meta charset="utf-8"><title>SIH26169 downloads</title><link rel="icon" type="image/svg+xml" href="/static/favicon.svg"><link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32.png">
<style>body{margin:0;background:#0A1117;color:#E3ECF1;font-family:"IBM Plex Sans",-apple-system,sans-serif;padding:40px 22px;max-width:760px;margin:0 auto}h1,h2{font-family:"IBM Plex Sans Condensed",sans-serif}h2{margin-top:28px;font-size:20px}a{color:#52C4DE}li{margin:8px 0}small{color:#8DA1AD}</style></head>
<body><h1>Downloads and documents</h1>
<h2>Desktop application</h2><p><small>Download the archive for your platform, extract it to a folder you can write to, run the executable. No installation and no Python needed. Results are written to a <code>results</code> folder next to it.</small></p><ul>
<li><a href="ARGUS-windows-x64.zip">ARGUS-windows-x64.zip</a> <small>Windows 10 or 11, 64-bit. Run <code>ARGUS.exe</code>; <code>ARGUS-cli.exe</code> is the same program for the command line. SmartScreen: More info, Run anyway (the build is not code-signed).</small></li>
<li><a href="ARGUS-linux-x64.tar.gz">ARGUS-linux-x64.tar.gz</a> <small>Linux 64-bit: Ubuntu 22.04 or newer, Debian 12, BOSS, RHEL 9, Fedora. <code>tar xzf</code>, then <code>./ARGUS/ARGUS</code>.</small></li>
<li><a href="ARGUS-macos-intel.zip">ARGUS-macos-intel.zip</a> <small>macOS 13 or newer on Intel. If Gatekeeper objects: System Settings, Privacy and Security, Open Anyway.</small></li>
<li><a href="ARGUS-macos-arm64.zip">ARGUS-macos-arm64.zip</a> <small>macOS 13 or newer on Apple silicon (M1 and later).</small></li>
</ul>
<h2>Documents</h2><ul>
<li><a href="USER_MANUAL.pdf">USER_MANUAL.pdf</a> <small>installation on each platform, operation, every parameter, Benchmark 2, metric definitions</small></li>
<li><a href="TECHNICAL_REPORT.pdf">TECHNICAL_REPORT.pdf</a> <small>problem understanding, architecture, methods, tests, measured performance, appendices</small></li>
<li><a href="ARGUS_SIH2026_26169.pdf">ARGUS_SIH2026_26169.pdf</a> <small>SIH idea-submission presentation, 8 slides</small></li>
<li><a href="ARGUS-demo.mp4">ARGUS-demo.mp4</a> <small>demonstration video, about four minutes: eight scenarios and Benchmark 2, composed from the engine's own frames with live specification tiles</small></li>
</ul>
<p><small>Windows and Linux come from the GitHub build workflow, the two macOS archives from the team's Mac (tools/build_macos.sh); each passed the test suite and a smoke test of the packaged executable on its own platform. Source builds: clone the repository, <code>pip install -e ".[dev]"</code>, <code>pyinstaller fsoc_tracker.spec</code>.</small></p>
</ul><p><a href="/">Web app</a> &middot; <a href="/about/">Progress and documents</a></p></body></html>
EOF
ssh "$HOST" "sudo mkdir -p $SITE && sudo chown -R ubuntu:ubuntu $SITE"
# keep the archives already on the server when dist/ holds none locally (a docs-only deploy)
KEEP=()
ls "$HERE"/dist/*.zip "$HERE"/dist/*.tar.gz >/dev/null 2>&1 || KEEP=(--exclude '*.zip' --exclude '*.tar.gz')
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
# caddy: one site block, imported by the main Caddyfile; basic auth hash is created once and kept
HASHFILE=/etc/caddy/sih26169.progress.hash
if ! sudo test -s "$HASHFILE"; then echo "progress basic auth hash missing: create it with  sudo bash -c 'caddy hash-password --plaintext <password> > $HASHFILE'"; exit 2; fi
HASH=$(sudo cat "$HASHFILE")
USERFILE=/etc/caddy/sih26169.progress.user
if ! sudo test -s "$USERFILE"; then echo "site login user missing: create it with  echo <username> | sudo tee $USERFILE"; exit 2; fi
USERNAME=$(sudo cat "$USERFILE")
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
    basic_auth {
        $USERNAME $HASH
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
