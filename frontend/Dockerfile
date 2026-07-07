FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Dependency layer — cached unless pyproject.toml changes
COPY pyproject.toml ./
RUN uv sync --no-dev

# Application code
COPY . .

EXPOSE 8501

ENTRYPOINT [ \
    "uv", "run", "streamlit", "run", "streamlit_app.py", \
    "--server.port", "8501", \
    "--server.address", "0.0.0.0", \
    "--server.headless", "true", \
    "--theme.base", "dark" \
]
