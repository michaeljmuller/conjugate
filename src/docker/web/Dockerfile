# Build context = src/python/web (the component directory).
FROM python:3.12-slim

WORKDIR /app

# Install the component. Copy the manifest first for layer caching, then source.
COPY pyproject.toml ./
COPY web ./web
RUN pip install --no-cache-dir .

EXPOSE 8000

# Plain HTTP; Caddy terminates TLS in front of this on the host. --proxy-headers
# makes uvicorn trust Caddy's X-Forwarded-Proto/Host so request.url_for() rebuilds
# https:// URLs (needed for the OAuth redirect_uri to match what's in Google).
# Only Caddy can reach this host port, so trusting all forwarded-for peers is safe.
CMD ["uvicorn", "web.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
