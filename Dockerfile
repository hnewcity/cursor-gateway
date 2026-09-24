FROM python:3.14-slim AS source
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY pyproject.toml README.md LICENSE NOTICE CONTRIBUTING.md SECURITY.md CODE_OF_CONDUCT.md CHANGELOG.md ./
COPY src ./src

FROM source AS test
COPY scripts ./scripts
COPY tests ./tests
COPY docs ./docs
COPY deploy ./deploy
COPY .github ./.github
COPY .env.example .python-version .gitignore .gitleaks.toml .dockerignore Dockerfile docker-compose.yml ./
RUN python3.14 -m pip install --no-cache-dir ".[dev]"
RUN ruff check src scripts tests \
    && ruff format --check src scripts tests \
    && python3.14 -m pytest -q \
    && python3.14 -m pip check \
    && python3.14 -m build

FROM source AS runtime
ARG VCS_REF=unknown
ARG SOURCE_URL="https://github.com/hnewcity/cursor-gateway"
LABEL org.opencontainers.image.title="Cursor Gateway" \
    org.opencontainers.image.description="Python FastAPI gateway for Cursor with OpenAI-compatible APIs" \
    org.opencontainers.image.source="${SOURCE_URL}" \
    org.opencontainers.image.licenses="AGPL-3.0-only" \
    org.opencontainers.image.revision="${VCS_REF}"
ENV CURSOR_DIRECT_HOST=0.0.0.0 \
    CURSOR_DIRECT_PORT=8790 \
    CURSOR_DIRECT_AUTH_FILE=/data/accounts.json
RUN python3.14 -m pip install --no-cache-dir . && mkdir -p /data
VOLUME ["/data"]
EXPOSE 8790
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python3.14 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8790/health', timeout=4)"
ENTRYPOINT ["cursor-gateway"]
CMD ["serve"]
