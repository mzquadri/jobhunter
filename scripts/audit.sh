#!/usr/bin/env bash
#
# Privacy and secret audit. Run before every push.
#
#   ./scripts/audit.sh          audit what is staged and tracked
#   ./scripts/audit.sh --all    also scan the working tree
#
# Exits non-zero if anything that must not be published would be.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[0;33m'; OFF=$'\033[0m'
failures=0

fail() { echo "${RED}FAIL${OFF}  $1"; failures=$((failures + 1)); }
pass() { echo "${GREEN} ok ${OFF}  $1"; }
warn() { echo "${YELLOW}warn${OFF}  $1"; }

echo "=== files that must never be tracked ==="
# Paths holding personal data or credentials. Each must be absent from the
# index entirely -- .gitignore alone is not proof, since a file added before
# it was ignored stays tracked.
for path in ".env" "config/profile.yml" "config/letter.md"; do
  if git ls-files --error-unmatch "$path" >/dev/null 2>&1; then
    fail "$path is tracked by git"
  else
    pass "$path is not tracked"
  fi
done

for pattern in "data/" "exports/" "*.xlsx" "*.csv" "*.sqlite" "*.db" "*.pem" "*.key"; do
  matches=$(git ls-files -- "$pattern" 2>/dev/null | head -5)
  if [ -n "$matches" ]; then
    fail "$pattern is tracked: $(echo "$matches" | tr '\n' ' ')"
  else
    pass "$pattern is not tracked"
  fi
done

echo
echo "=== secret patterns in tracked content ==="
# Deliberately narrow: broad patterns produce noise, and an audit nobody
# believes is an audit nobody runs.
declare -a PATTERNS=(
  'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}:GitHub token'
  'sk-[A-Za-z0-9]{32,}|sk-ant-[A-Za-z0-9-]{20,}:API key'
  'AKIA[0-9A-Z]{16}:AWS access key'
  '-----BEGIN [A-Z ]*PRIVATE KEY-----:private key'
  'xox[baprs]-[A-Za-z0-9-]{10,}:Slack token'
  '(password|passwd|secret|api_key|apikey|access_token)[[:space:]]*[=:][[:space:]]*["'"'"'][^"'"'"'{}$<> ]{8,}["'"'"']:hardcoded credential'
)

tracked=$(git ls-files)
for entry in "${PATTERNS[@]}"; do
  regex="${entry%%:*}"; label="${entry##*:}"
  hits=$(echo "$tracked" | xargs grep -InE "$regex" 2>/dev/null \
         | grep -vE '(example|sample|placeholder|change-me|your-|CHANGEME|audit\.sh)' \
         | head -5)
  if [ -n "$hits" ]; then
    fail "$label found:"
    echo "$hits" | sed 's/^/        /'
  else
    pass "no $label"
  fi
done

echo
echo "=== personal data in tracked content ==="
# Contact details belong in config/profile.yml, which is gitignored.
personal=$(echo "$tracked" | xargs grep -InE \
  '\+[0-9]{2}[0-9 ()-]{9,}|[A-Za-z0-9._%+-]+@(?!example\.com)[A-Za-z0-9.-]+\.(de|com|org|net)' \
  2>/dev/null | grep -vE '(example\.com|example\.org|noreply|your@|you@|audit\.sh|user_agent|github\.com)' | head -5)
if [ -n "$personal" ]; then
  warn "possible contact details in tracked files — check these are placeholders:"
  echo "$personal" | sed 's/^/        /'
else
  pass "no phone numbers or personal email addresses"
fi

echo
echo "=== example configs carry placeholders only ==="
for f in config/profile.example.yml config/letter.example.md .env.example; do
  [ -f "$f" ] || { fail "$f is missing"; continue; }
  if grep -qiE 'your name|you@example|\+49 000|change-me|Your Name' "$f"; then
    pass "$f uses placeholders"
  else
    warn "$f may contain real values — check it"
  fi
done

echo
echo "=== .gitignore covers the sensitive paths ==="
for entry in "config/profile.yml" "config/letter.md" ".env" "data/"; do
  if grep -qF "$entry" .gitignore 2>/dev/null; then
    pass ".gitignore covers $entry"
  else
    fail ".gitignore does not cover $entry"
  fi
done

echo
if [ "$failures" -eq 0 ]; then
  echo "${GREEN}Audit passed.${OFF} Safe to push."
  exit 0
fi
echo "${RED}Audit failed with $failures problem(s). Do not push.${OFF}"
exit 1
