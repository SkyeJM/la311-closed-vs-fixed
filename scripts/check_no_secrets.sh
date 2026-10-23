#!/bin/sh
# Pre-commit guard for a public repo: block staged files that look like they contain API keys.
# Usage (by pre-commit): check_no_secrets.sh FILE...
status=0
for file in "$@"; do
  if grep -nE 'sk-ant-[A-Za-z0-9_-]{16,}|(ANTHROPIC_API_KEY|SOCRATA_APP_TOKEN)=[^[:space:]#]+' "$file"; then
    echo "error: possible secret in $file (keys belong in .env, which is gitignored)" >&2
    status=1
  fi
done
exit $status
