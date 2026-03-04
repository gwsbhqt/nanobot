FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates git && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy the full source and install
COPY nanobot/ nanobot/
RUN uv sync --frozen --no-dev

# Create config directory
RUN mkdir -p /root/.nanobot

# Use project virtualenv binaries by default
ENV PATH="/app/.venv/bin:$PATH"

# Gateway default port
EXPOSE 18790

ENTRYPOINT ["nanobot"]
CMD ["status"]
