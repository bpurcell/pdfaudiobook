#!/usr/bin/env bash
# Narrate every book in books/ (Markdown first, then PDFs), one at a time.
# Waits for any pdf2audiobook run already in progress to finish first.
# Already-finished chapters are skipped, so it's safe to rerun.
cd "$(dirname "$0")"
while pgrep -f "pdf2audiobook.py" >/dev/null; do sleep 60; done
for f in books/*.md books/*.pdf; do
  [ -e "$f" ] || continue
  echo "=== $f ==="
  python pdf2audiobook.py "$f" || echo "!!! failed: $f"
done
echo "All done."
