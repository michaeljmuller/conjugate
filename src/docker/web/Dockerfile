# Build context = the repository root, so that .git is reachable (see below).

# Stage one exists only to read git. It is discarded: nothing but the two lines
# it writes reaches the final image, so the app never carries a git binary or the
# object database.
#
# Copying .git alone is enough — rev-parse and log read the object database and
# never look at a worktree. That keeps .dockerignore purely a size optimisation
# rather than something correctness depends on.
FROM alpine/git AS version
COPY .git /src/.git
RUN git -C /src rev-parse --short HEAD > /version.txt \
 && git -C /src log -1 --format=%cI >> /version.txt

FROM python:3.12-slim

WORKDIR /app

# Install the component. Copy the manifest first for layer caching, then source.
COPY src/python/web/pyproject.toml ./
COPY src/python/web/web ./web
RUN pip install --no-cache-dir .

# Last, so that a new commit does not invalidate the pip layer above it.
COPY --from=version /version.txt /app/VERSION

EXPOSE 8000

# Plain HTTP; Caddy terminates TLS in front of this on the host. --proxy-headers
# makes uvicorn trust Caddy's X-Forwarded-Proto/Host so request.url_for() rebuilds
# https:// URLs (needed for the OAuth redirect_uri to match what's in Google).
# Only Caddy can reach this host port, so trusting all forwarded-for peers is safe.
CMD ["uvicorn", "web.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
