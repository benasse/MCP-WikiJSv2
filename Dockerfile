FROM python:3.12-slim

# Create non-root user
RUN useradd -m -u 1000 mcp

WORKDIR /app

# Copy source then install (hatchling editable install requires source present)
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .

# Switch to non-root user
USER mcp

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python", "-m", "wikijs_mcp.server"]
