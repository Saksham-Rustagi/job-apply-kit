#!/bin/bash
# One-time setup for job-apply-kit on a Mac. Safe to re-run.
#   cd ~/job-apply-kit && bash install.sh
set -u
KIT="$(cd "$(dirname "$0")" && pwd)"
cd "$KIT"
ok()   { printf "  \033[32mOK\033[0m   %s\n" "$1"; }
warn() { printf "  \033[33mTODO\033[0m %s\n" "$1"; }
bad()  { printf "  \033[31mFAIL\033[0m %s\n" "$1"; }

echo "job-apply-kit setup ($KIT)"

# 1. Python 3.9+ (the Mac's built-in python3 is fine; nothing to pip install)
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  bad "python3 not found. Run: xcode-select --install   (then re-run this script)"; exit 1
fi
if "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  ok "python3 $("$PY" -c 'import platform; print(platform.python_version())') at $PY"
else
  bad "python3 is older than 3.9: install a newer one (https://www.python.org/downloads/)"; exit 1
fi

# 2. Folders + your private profile files (all git-ignored)
mkdir -p state tracker profile
if [ ! -f profile/profile.jsonc ]; then
  cp profile/profile.example.jsonc profile/profile.jsonc
  warn "created profile/profile.jsonc from the template: fill it in (or ask Hermes to, see GUIDE.md step 4)"
else
  ok "profile/profile.jsonc exists"
fi
[ -f profile/reference.txt ] || { cp profile/reference.example.txt profile/reference.txt; warn "created profile/reference.txt: fill it in for essays"; }

# 3. Rule tests (fictional people, no network)
if "$PY" applyq/test_rules.py >/tmp/jak_tests.txt 2>&1; then ok "answer-rule tests: $(tail -1 /tmp/jak_tests.txt)"; else bad "rule tests failed:"; cat /tmp/jak_tests.txt; fi

# 4. Hermes: load the skill from this folder, and make sure commands run on this Mac (not in a sandbox)
HERMES="$(command -v hermes || ls ~/.local/bin/hermes 2>/dev/null || true)"
if [ -n "$HERMES" ]; then
  ok "hermes found at $HERMES"
  CUR="$("$HERMES" config get skills.external_dirs 2>/dev/null || true)"
  if echo "$CUR" | grep -q "job-apply-kit/skills"; then
    ok "skill already linked (skills.external_dirs)"
  else
    # keep any skill folders already listed, add ours
    LIST="$(printf '%s\n' "$CUR" | sed -n 's/^[ -]*-[ ]*//p' | KIT="$KIT" "$PY" -c 'import json,os,sys; d=[l.strip() for l in sys.stdin if l.strip()]; d.append(os.environ["KIT"]+"/skills"); print(json.dumps(d))')"
    if "$HERMES" config set skills.external_dirs "$LIST" >/dev/null 2>&1; then
      ok "skill linked: skills.external_dirs = $KIT/skills (git pull updates it)"
    else
      warn "could not set skills.external_dirs; copy the skill instead: mkdir -p ~/.hermes/skills && cp -R \"$KIT/skills/job-apply-kit\" ~/.hermes/skills/"
    fi
  fi
  BACKEND="$("$HERMES" config get terminal.backend 2>/dev/null | tail -1 | tr -d '[:space:]' || true)"
  case "$BACKEND" in
    ""|local|*local*) ok "terminal backend is local (the agent can drive Chrome)";;
    *) warn "terminal backend is '$BACKEND': the Chrome filler needs commands to run on this Mac. Run: hermes config set terminal.backend local";;
  esac
else
  warn "Hermes not installed yet (GUIDE.md step 1). Re-run this script afterwards."
fi

# 5. Chrome
if [ -d "/Applications/Google Chrome.app" ]; then
  ok "Google Chrome installed"
  warn "in Chrome, tick: View > Developer > Allow JavaScript from Apple Events (one time)"
else
  bad "Google Chrome not found in /Applications (the filler drives Chrome)"
fi

# 6. Profile check
echo
"$PY" applyq/candidate.py || true
echo
echo "Next: open GUIDE.md (step 4 onward)."
