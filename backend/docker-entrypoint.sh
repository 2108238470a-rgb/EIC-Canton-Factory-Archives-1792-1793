#!/bin/sh
set -eu
if [ -f /run/secrets/database_url ]; then export DATABASE_URL="$(cat /run/secrets/database_url)"; fi
if [ -f /run/secrets/gpt_api_key ]; then export GPT_API_KEY="$(cat /run/secrets/gpt_api_key)"; fi
exec "$@"
