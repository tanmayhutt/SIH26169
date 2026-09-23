# ARGUS web app: the same engine as the desktop application, served to a browser.
#   docker run -p 8095:8095 ghcr.io/tanmayhutt/argus-web:latest    then open http://127.0.0.1:8095/
# Built and pushed to GitHub Packages by .github/workflows/build.yml.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app

COPY pyproject.toml README.md ./
COPY fsoc_tracker ./fsoc_tracker
RUN pip install ".[web]"

# the server resolves scenarios, the model and its results folder relative to /app
COPY webapp ./webapp
COPY configs ./configs
COPY models ./models

RUN useradd --create-home --uid 1000 argus && mkdir -p results && chown argus results
USER argus

EXPOSE 8095
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8095/api/health', timeout=4)"
CMD ["uvicorn", "webapp.server:app", "--host", "0.0.0.0", "--port", "8095"]
