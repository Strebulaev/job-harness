# jobharness Telegram bot image (plan step 6.2). x86_64 Typst build; adjust TYPST_ARCH for arm64.
FROM python:3.12-slim

ARG TYPST_VERSION=0.13.1
ARG TYPST_ARCH=x86_64-unknown-linux-musl

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl xz-utils ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL "https://github.com/typst/typst/releases/download/v${TYPST_VERSION}/typst-${TYPST_ARCH}.tar.xz" \
       | tar -xJ --strip-components=1 -C /usr/local/bin --wildcards '*/typst' \
    && typst --version

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY config ./config
RUN uv sync --no-dev

ENV PATH="/app/.venv/bin:${PATH}" \
    JH_DATA_DIR=/data \
    JH_CONFIG=/app/config/config.yaml \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]

CMD ["jh", "bot", "run"]
