# Build context = src/python/web (the component directory).
FROM python:3.12-slim

WORKDIR /app

# Install the component. Copy the manifest first for layer caching, then source.
COPY pyproject.toml ./
COPY web ./web
RUN pip install --no-cache-dir .

EXPOSE 8000

# Plain HTTP; Caddy terminates TLS in front of this on the host.
CMD ["uvicorn", "web.main:app", "--host", "0.0.0.0", "--port", "8000"]
