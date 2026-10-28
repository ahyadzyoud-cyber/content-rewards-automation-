FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_CACHE_DIR=/tmp/uv-cache
RUN --mount=type=secret,id=platform-ca,mode=0444 \
    if [ -f /run/secrets/platform-ca ]; then \
      export SSL_CERT_FILE=/run/secrets/platform-ca PIP_CERT=/run/secrets/platform-ca; \
      printf '%s\n' 'Acquire::https::CaInfo "/run/secrets/platform-ca";' > /etc/apt/apt.conf.d/99-platform-ca; \
    fi; \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update -o APT::Update::Error-Mode=any && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.12.23 \
    && rm -f /etc/apt/apt.conf.d/99-platform-ca
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN --mount=type=secret,id=platform-ca,mode=0444 \
    if [ -f /run/secrets/platform-ca ]; then export SSL_CERT_FILE=/run/secrets/platform-ca; fi; \
    uv sync --frozen --no-dev --no-editable && chmod -R a+rX /app/.venv \
    && useradd --uid 10001 --create-home rewards \
    && mkdir -p /app/.data/media && chown -R rewards:rewards /app/.data
ENV PATH="/app/.venv/bin:$PATH"
USER rewards
CMD ["rewards", "worker"]
