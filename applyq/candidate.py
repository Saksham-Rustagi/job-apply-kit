"""Load and check the candidate profile (profile/profile.jsonc).

The profile is JSON with comment lines: any line whose first non-space characters are `//` is ignored.
(Comments at the end of a line are NOT supported, because URLs contain `//`.)

Every value the answer rules need comes from here. A value left as "" or null means "unknown": the rules
then mark that question `you`, and `applyq.py missing` lists it so you can fill it in once.

Works on Python 3.9+ with the standard library only.
"""
import json
import os
import re
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
PROFILE_DIR = KIT / "profile"
PROFILE = PROFILE_DIR / "profile.jsonc"
EXAMPLE = PROFILE_DIR / "profile.example.jsonc"


def _strip_comments(text):
    return "\n".join("" if line.lstrip().startswith("//") else line for line in text.splitlines())


def load(path=None):
    p = Path(path or os.environ.get("JOB_KIT_PROFILE") or PROFILE)
    if not p.exists():
        sys.exit("No profile at %s.\nCopy the template first:  cp %s %s" % (p, EXAMPLE, PROFILE))
    raw = _strip_comments(p.read_text(encoding="utf-8"))
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        line = raw.splitlines()[e.lineno - 1] if e.lineno - 1 < len(raw.splitlines()) else ""
        sys.exit("profile.jsonc is not valid JSON (line %d, col %d): %s\n    %s\n"
                 "Common causes: a missing comma between fields, a trailing comma before } or ], "
                 "or a comment after a value on the same line." % (e.lineno, e.colno, e.msg, line.strip()))


class Profile(object):
    """Dotted access with 'unknown' detection: P.get('eligibility.needs_sponsorship_now')."""

    def __init__(self, data):
        self.data = data

    def get(self, path, default=None):
        cur = self.data
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def known(self, path):
        v = self.get(path)
        return not (v is None or v == "" or v == [] or (isinstance(v, str) and v.strip().upper().startswith("TODO")))

    def path(self, key):
        """A file path from the `files` section, with ~ expanded."""
        v = self.get("files." + key)
        return os.path.expanduser(v) if v else ""

    # convenience
    @property
    def full_name(self):
        return ("%s %s" % (self.get("name.first", ""), self.get("name.last", ""))).strip()


REQUIRED = [
    "name.first", "name.last", "contact.email", "contact.phone",
    "location.city", "location.state",
    "education.school", "education.degree", "education.major_text", "education.end",
    "eligibility.us_work_authorized", "eligibility.needs_sponsorship_now", "eligibility.needs_sponsorship_future",
    "preferences.start_text", "files.resume",
]
RECOMMENDED = [
    "contact.linkedin", "contact.github", "name.pronouns", "education.gpa", "education.grad_text",
    "education.school_search", "education.school_match", "location.autocomplete_query", "location.autocomplete_match",
    "work.last_employer", "work.last_title", "eligibility.visa_status", "eligibility.us_citizen",
    "preferences.willing_to_relocate", "preferences.onsite_ok", "preferences.how_heard", "preferences.salary_default",
    "eeo.gender", "eeo.race", "eeo.hispanic", "eeo.veteran", "eeo.disability",
]


def check(P):
    """Return (errors, warnings) as lists of strings."""
    errs = ["missing required: " + k for k in REQUIRED if not P.known(k)]
    warns = ["not set (questions about it will be asked): " + k for k in RECOMMENDED if not P.known(k)]
    resume = P.path("resume")
    if resume and not os.path.exists(resume):
        errs.append("files.resume does not exist on disk: " + resume)
    if resume and not resume.lower().endswith(".pdf"):
        warns.append("files.resume is not a PDF; most ATS forms want a PDF")
    ref = P.path("reference")
    if ref and not os.path.exists(ref):
        warns.append("files.reference does not exist yet (essays need it): " + ref)
    for k in ("education.start", "education.end"):
        v = P.get(k)
        if v and not re.match(r"^\d{4}-\d{2}$", str(v)):
            errs.append("%s must look like 2027-05 (got %r)" % (k, v))
    email = P.get("contact.email") or ""
    if email and "@" not in email:
        errs.append("contact.email does not look like an email address")
    for k, v in (P.get("eeo") or {}).items():
        if v and not isinstance(v, str):
            errs.append("eeo.%s must be a string (an answer like \"No\" or \"decline\")" % k)
    return errs, warns


if __name__ == "__main__":
    P = Profile(load(sys.argv[1] if len(sys.argv) > 1 else None))
    e, w = check(P)
    for x in e:
        print("ERROR  " + x)
    for x in w:
        print("note   " + x)
    print("profile OK" if not e else "\n%d error(s): fix them before running applyq.py build" % len(e))
    sys.exit(1 if e else 0)
