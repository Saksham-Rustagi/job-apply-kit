#!/usr/bin/env python3
"""Log a job you submitted, so the queue drops it and your tracker CSV grows.

  python3 applyq/log_applied.py <job id> "<proof>" ["<notes>"]
      proof = what you saw: "Greenhouse confirmation page", "confirmation email 11/24 3:05pm", ...
  python3 applyq/log_applied.py --manual "<Company>" "<Role>" "<apply link>" "<proof>"
      for an application outside the queue (Workday, iCIMS, a company site)
  python3 applyq/log_applied.py --list

Writes state/jobs_state.json (the queue skips these ids) and tracker/applications.csv
(Date applied, Company, Role, Location, Link, ATS, Proof, Status, Next step, Notes).
Python 3.9+, standard library only.
"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
STATE = KIT / "state" / "jobs_state.json"
TRACKER = KIT / "tracker" / "applications.csv"
DATA = KIT / "data" / "jobs.json"
COLS = ["Date applied", "Company", "Role", "Location", "Link", "ATS", "Proof", "Status", "Next step", "Notes", "Job id"]


def _load(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _append(row):
    TRACKER.parent.mkdir(exist_ok=True)
    new = not TRACKER.exists()
    with open(TRACKER, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        if new:
            w.writeheader()
        w.writerow(row)


def log(job_id, proof, notes=""):
    jobs = {j["id"]: j for j in _load(DATA, {"jobs": []})["jobs"]}
    j = jobs.get(job_id)
    if not j:
        plan = KIT / "applyq" / "plans" / ("%s.json" % job_id)
        j = _load(plan, {}).get("job")
    if not j:
        sys.exit("unknown job id %r (not in data/jobs.json or applyq/plans)" % job_id)
    state = _load(STATE, {})
    if job_id in state and state[job_id].get("status") == "applied":
        sys.exit("already logged: %s %s on %s" % (j["company"], j["title"], state[job_id].get("at")))
    now = datetime.now()
    state[job_id] = dict(status="applied", at=now.isoformat(timespec="seconds"), proof=proof)
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
    _append({"Date applied": now.strftime("%Y-%m-%d"), "Company": j["company"], "Role": j["title"],
             "Location": j.get("location", ""), "Link": j.get("apply_url", ""), "ATS": j.get("ats", ""),
             "Proof": proof, "Status": "Applied", "Next step": "Waiting on them", "Notes": notes, "Job id": job_id})
    print("logged: %s - %s" % (j["company"], j["title"]))


def manual(company, role, link, proof):
    _append({"Date applied": datetime.now().strftime("%Y-%m-%d"), "Company": company, "Role": role, "Location": "",
             "Link": link, "ATS": "", "Proof": proof, "Status": "Applied", "Next step": "Waiting on them", "Notes": "",
             "Job id": ""})
    # also hide any feed row with the same link so the queue never offers it again
    state = _load(STATE, {})
    for j in _load(DATA, {"jobs": []})["jobs"]:
        if link and link.rstrip("/") in (j.get("apply_url", "").rstrip("/"), j.get("posting_url", "").rstrip("/")):
            state[j["id"]] = dict(status="applied", at=datetime.now().isoformat(timespec="seconds"), proof=proof)
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
    print("logged: %s - %s" % (company, role))


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        sys.exit(__doc__)
    if a[0] == "--list":
        if TRACKER.exists():
            print(TRACKER.read_text(encoding="utf-8"))
        else:
            print("no applications logged yet")
    elif a[0] == "--manual":
        if len(a) < 5:
            sys.exit(__doc__)
        manual(*a[1:5])
    else:
        if len(a) < 2:
            sys.exit(__doc__)
        log(a[0], a[1], a[2] if len(a) > 2 else "")
