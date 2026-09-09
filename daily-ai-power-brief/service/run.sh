#!/usr/bin/env bash
set -euo pipefail
exec 9>/tmp/daily-ai-power-brief.lock
flock -n 9 || exit 0
REPO=/opt/daily-ai-power-brief/site
cd "$REPO"
git pull --ff-only origin main
python3 daily-ai-power-brief/service/publisher.py
git add daily-ai-power-brief/audio daily-ai-power-brief/data daily-ai-power-brief/posts daily-ai-power-brief/feed.xml 2>/dev/null || true
if ! git diff --cached --quiet; then
  git -c user.name='Daily Brief Publisher' -c user.email='publisher@localhost' commit -m "Publish daily AI and power brief"
  git push origin main
fi
