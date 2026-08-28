#!/usr/bin/env bash
#
# Pull the seed files down from the running deployment and write them into the
# repo. Sentences fixed in the app are not overwritten by a redeploy any more, so
# the deployment's database runs ahead of what is committed; this is how the
# committed files catch up.
#
#   src/python/web/tools/pull_seed.sh
#
# Updates the files and stops. It never commits — read the diff, decide whether
# you want it, commit it yourself.
#
# Credentials come from src/docker/.env (gitignored), the same EXPORT_USER /
# EXPORT_PASSWORD the server is configured with. Point somewhere else with:
#
#   CONJUGATE_HOST=http://localhost:8081 src/python/web/tools/pull_seed.sh
#
# Needs curl and git — no language runtime, so it runs on a host that only keeps
# an editor, git and a container runtime.

set -euo pipefail

HOST="${CONJUGATE_HOST:-https://conjugate.themullers.org}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
ENV_FILE="$REPO/src/docker/.env"

die() { echo "pull_seed: $*" >&2; exit 1; }

# One key out of .env, without sourcing the file: a stray line in there should
# not be able to run as shell.
env_value() {
  local key="$1" line
  line="$(grep -E "^[[:space:]]*${key}=" "$ENV_FILE" | tail -1 || true)"
  line="${line#*=}"
  line="${line%\"}"; line="${line#\"}"      # strip surrounding quotes
  line="${line%\'}"; line="${line#\'}"
  printf '%s' "$line"
}

[ -f "$ENV_FILE" ] || die "no $ENV_FILE — copy .env.example and fill it in"
USER_NAME="$(env_value EXPORT_USER)"
PASSWORD="$(env_value EXPORT_PASSWORD)"
[ -n "$USER_NAME" ] && [ -n "$PASSWORD" ] ||
  die "EXPORT_USER / EXPORT_PASSWORD are not set in $ENV_FILE (the endpoint 404s without them)"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# fetch <remote name> <destination>
fetch() {
  local name="$1" dest="$2" tmp="$TMP/$1"

  # --fail turns an HTTP error into a non-zero exit rather than a saved error
  # page; downloading beside the target means a failure never truncates a file
  # that took a model an hour to write. curl reports the reason itself on stderr
  # (--show-error), so the message below only adds what curl cannot know.
  local code
  code="$(curl --fail --silent --show-error --location \
               --user "$USER_NAME:$PASSWORD" \
               --output "$tmp" \
               --write-out '%{http_code}' \
               "$HOST/export/$name")" || {
    case "$code" in
      401) die "$HOST rejected EXPORT_USER/EXPORT_PASSWORD from $ENV_FILE" ;;
      404) die "$HOST has no export endpoint — its EXPORT_USER/EXPORT_PASSWORD are unset, or it predates this feature" ;;
      000|"") die "could not reach $HOST" ;;
      *) die "GET $HOST/export/$name returned $code" ;;
    esac
  }

  [ -s "$tmp" ] || die "$name came back empty"
  case "$(head -c 1 "$tmp")" in
    '['|'{') ;;
    *) die "$name is not JSON — is $HOST really the app?" ;;
  esac

  if cmp -s "$tmp" "$dest"; then
    echo "  $name: unchanged"
  else
    mv "$tmp" "$dest"
    echo "  $name: updated"
  fi
}

echo "Pulling from $HOST as $USER_NAME"
fetch verbs_seed.json "$REPO/src/python/web/web/data/verbs_seed.json"
fetch examples.json   "$REPO/src/python/web/web/languages/pt/examples.json"

echo
git -C "$REPO" --no-pager diff --stat -- \
  src/python/web/web/data/verbs_seed.json \
  src/python/web/web/languages/pt/examples.json
git -C "$REPO" diff --quiet -- \
  src/python/web/web/data/verbs_seed.json \
  src/python/web/web/languages/pt/examples.json \
  && echo "Nothing changed; the committed files already match the deployment." \
  || echo "Not committed — review the diff, then commit if you want it."
