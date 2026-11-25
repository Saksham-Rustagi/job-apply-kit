#!/usr/bin/env python3
"""applyq: the application queue for Greenhouse / Ashby / Lever postings (no browser needed).

  python3 applyq/applyq.py build [--ids a,b] [--company X] [--limit N]
                          fetch every un-applied Greenhouse/Ashby/Lever job's form questions from the ATS's public
                          API, answer each one from your profile, label the job, write queue.json + plans/<id>.json
  python3 applyq/applyq.py summary [--links]   the queue grouped by label (newest first)
  python3 applyq/applyq.py next                the next job that is ready to fill
  python3 applyq/applyq.py missing             unanswered questions across the queue, most common first
  python3 applyq/applyq.py plan <job id>       one job's full answer plan
  python3 applyq/applyq.py bank "<question label>" "<answer>"   save an answer you approved (unlocks more jobs)
  python3 applyq/applyq.py bank --list
  python3 applyq/applyq.py hide <job id> "<reason>"              skip a job for good (e.g. MS/PhD-only)

Every answer carries a source:
  profile    straight from profile/profile.jsonc
  bank       an answer you approved earlier (profile/answers_bank.json, grows over time)
  default    a safe universal answer (e.g. "able to perform the essential functions": Yes)
  inferred   reasonable but not confirmed by you -> needs your one-time OK
  essay      free response: the agent drafts it, you approve it
  you        nothing to go on -> you must answer
  skip       optional and intentionally left blank
Labels: ready (every required answer is profile/bank/default), needs-ok (only inferred items left),
essay (needs essay drafts), needs-you, dead (posting closed).

Python 3.9+, standard library only.
"""
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import candidate  # noqa: E402

ROOT = Path(__file__).resolve().parent
KIT = ROOT.parent
DATA = KIT / "data" / "jobs.json"
STATE = KIT / "state" / "jobs_state.json"
FORMS = ROOT / "forms"
PLANS = ROOT / "plans"
BANK = KIT / "profile" / "answers_bank.json"
QUEUE = ROOT / "queue.json"
UA = {"User-Agent": "Mozilla/5.0 (applyq; personal use)"}
AQ = ("query ApiJobPosting($organizationHostedJobsPageName: String!, $jobPostingId: String!) { "
      "jobPosting(organizationHostedJobsPageName: $organizationHostedJobsPageName, jobPostingId: $jobPostingId) { "
      "id title applicationForm { id sections { title fieldEntries { ... on FormFieldEntry { id field isRequired "
      "descriptionHtml } } } } } }")

P = None          # candidate.Profile, loaded in main() (tests may set it directly)
CUR_JOB = {}      # the job being planned: salary / onsite / role rules read it
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]


# ---------------------------------------------------------------- option helpers
def opt(options, *pats, avoid=None):
    """First option matching any pattern (patterns tried in order)."""
    for p in pats:
        if not p:
            continue
        for o in options:
            if re.search(p, str(o), re.I) and not (avoid and re.search(avoid, str(o), re.I)):
                return o
    return None


def not_no(options):
    """Drop options that start with No: 'able to relocate' would otherwise match 'No - not able to relocate'."""
    return [x for x in options if not re.match(r"\s*no\b", str(x), re.I)]


def yn_answer(val, o, src, note):
    """Turn a boolean into the form's Yes / No option (or literal Yes / No)."""
    if val is None:
        return None, "you", note
    if o:
        a = opt(o, r"^yes\b") if val else opt(o, r"^no\b")
        return (a, src, note) if a else (None, "you", note + " (no Yes/No option: " + "; ".join(map(str, o[:5])) + ")")
    return ("Yes" if val else "No"), src, note


def known(path):
    return P.known(path)


def g(path, default=None):
    return P.get(path, default)


# ---------------------------------------------------------------- rule builders
# A rule handler is f(label, options, ftype) -> (answer | None, source, note)
def F(path, note=""):
    """A profile value, or 'you' when it is not set."""
    def h(l, o, t):
        if not known(path):
            return None, "you", "set %s in your profile" % path
        v = g(path)
        if o:
            a = opt(o, r"^" + re.escape(str(v)) + r"$", r"^" + re.escape(str(v)), re.escape(str(v)))
            return (a, "profile", note) if a else (None, "you", "profile %s=%r matches no option" % (path, v))
        return v, "profile", note
    return h


def YN(path, invert=False, note=""):
    def h(l, o, t):
        if not known(path) and g(path) is not False:
            return None, "you", "set %s in your profile" % path
        v = bool(g(path))
        return yn_answer((not v) if invert else v, o, "profile", note or path)
    return h


def const(ans, src="default", note=""):
    return lambda l, o, t: (ans, src, note)


def yes(src="default", note=""):
    return lambda l, o, t: yn_answer(True, o, src, note)


def no(src="default", note=""):
    return lambda l, o, t: yn_answer(False, o, src, note)


def pick(*pats, src="default", note="", avoid=None):
    def h(l, o, t):
        if not o:
            return None, "you", "expected options"
        a = opt(o, *pats, avoid=avoid)
        return (a, src, note) if a else (None, "you", "no matching option: " + "; ".join(map(str, o[:6])))
    return h


# ---------------------------------------------------------------- EEO
DECLINE = (r"decline|don.?t wish|do not wish|prefer not|not to (say|answer|disclose|self)|choose not|rather not|"
           r"i don.?t want|not wish to")
EEO_SYNONYMS = {
    "gender": {"male": [r"^male$", r"^man$", r"^male\b", r"^man\b", r"^cis(gender)? (male|man)"],
               "female": [r"^female$", r"^woman$", r"^female\b", r"^woman\b", r"^cis(gender)? (female|woman)"],
               "non-binary": [r"non-?binary", r"gender ?queer", r"gender non"]},
    "veteran": {"no": [r"not a protected veteran", r"^no\b", r"^i am not", r"not a veteran"],
                "yes": [r"identify as one or more", r"^i am a protected veteran", r"^yes\b", r"^i am a veteran"]},
    "disability": {"no": [r"^no, i don", r"do not have a disability", r"^no\b"],
                   "yes": [r"^yes, i have", r"have a disability", r"^yes\b"]},
    "orientation": {"heterosexual": [r"heterosexual", r"straight"]},
}


def eeo_patterns(key):
    """Regex list for a profile EEO answer, or None when unset."""
    v = (g("eeo." + key) or "").strip()
    if not v:
        return None
    if v.lower() in ("decline", "prefer not to say", "prefer not to answer"):
        return [DECLINE]
    syn = EEO_SYNONYMS.get(key, {}).get(v.lower())
    if syn:
        return syn
    if v.lower() in ("yes", "no"):
        return [r"^" + v.lower() + r"\b"]
    return [r"^" + re.escape(v) + r"$", r"^" + re.escape(v) + r"\b"]


def eeo(key):
    def h(l, o, t):
        pats = eeo_patterns(key)
        if pats is None:
            return None, "you", "set eeo.%s in your profile (or \"decline\")" % key
        if not o:
            v = g("eeo." + key)
            return (None, "skip", "free-text EEO box: left blank") if v.lower() == "decline" else (v, "profile", "")
        a = opt(o, *pats)
        if a is None and key == "race" and pats != [DECLINE]:
            # "Asian (Not Hispanic or Latino)" style labels: accept a word match only when exactly one option has it
            # (never pick "East Asian" for "Asian" when "South Asian" is also listed)
            hits = [x for x in o if re.search(r"\b" + re.escape(g("eeo.race")) + r"\b", str(x), re.I)]
            a = hits[0] if len(hits) == 1 else None
        return (a, "profile", "eeo." + key) if a else (None, "you", "eeo.%s=%r matches no option: %s" % (
            key, g("eeo." + key), "; ".join(map(str, o[:6]))))
    return h


# ---------------------------------------------------------------- composite handlers
def _money(s):
    return [int(n.replace(",", "")) * (1000 if k.lower() == "k" else 1)
            for n, k in re.findall(r"\$?\s*([\d,]{2,})\s*([kK]?)", str(s)) if n.replace(",", "").isdigit()]


def salary(l, o, t):
    """The posting's own published range; otherwise salary_default (or the lowest band containing it)."""
    pay = str(CUR_JOB.get("pay") or "").strip()
    dflt = int(g("preferences.salary_default") or 0)
    if o:
        if not dflt:
            return None, "you", "salary dropdown: set preferences.salary_default to auto-pick a band"
        bands = [(x, _money(x)) for x in o]
        hit = [x for x, v in bands if (len(v) >= 2 and v[0] <= dflt <= v[1]) or
               (len(v) == 1 and re.search(r"\+|or more|and above|above", str(x)) and v[0] <= dflt)]
        return (hit[0] if hit else None), ("profile" if hit else "you"), "lowest band containing %s" % format(dflt, ",")
    if pay and len(_money(pay)) >= 2:
        loc = str(CUR_JOB.get("location") or "")
        parts = [p.strip() for p in re.split(r"[;(]", pay) if _money(p)]
        city0 = loc.split(",")[0].strip().lower()
        alias = {"san francisco": ["san francisco", "sf"], "new york": ["new york", "nyc", "ny"],
                 "los angeles": ["los angeles", "la"]}.get(city0, [city0])
        city = next((p for p in parts if city0 and any(re.search(r"\b" + re.escape(a) + r"\b", p, re.I) for a in alias)),
                    parts[0] if parts else pay)
        rng = re.search(r"\$[\d,]+(?:\.\d+)?[kK]?\s*[-–]\s*\$[\d,]+(?:\.\d+)?[kK]?", city)
        out = re.sub(r"\$(\d{4,})(?![\d,.])", lambda mm: "$" + format(int(mm.group(1)), ","), rng.group(0) if rng else city)
        return out, "profile", "the posting's own published range"
    if dflt:
        return "$" + format(dflt, ","), "profile", "no published range: preferences.salary_default"
    return None, "you", "no published range and preferences.salary_default is 0"


def _iso_month(iso):
    """'2027-05' -> ('may', '2027')"""
    m = re.match(r"(\d{4})-(\d{2})", str(iso or ""))
    return (MONTHS[int(m.group(2)) - 1], m.group(1)) if m else (None, None)


def grad_patterns():
    mon, yr = _iso_month(g("education.end"))
    if not mon:
        return []
    season = "spring" if mon in ("january", "february", "march", "april", "may", "june") else "fall"
    m3 = mon[:3]
    return [r"\b%s\b.*\b%s\b" % (m3, yr), r"\b%s\w*\s*%s" % (m3, yr), r"%s ?/ ?\w+ %s" % (m3, yr), r"\w+ ?/ ?%s %s" % (m3, yr),
            r"\b%s %s\b" % (season, yr), r"(january|jan) ?- ?(june|jun) %s" % yr if season == "spring" else
            r"(july|jul) ?- ?(december|dec) %s" % yr, r"\b%s\b" % yr]


def _month_years(s):
    """All 'month year' mentions in a label as (year, month) tuples."""
    out = []
    for m, y in re.findall(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,? (20\d\d)\b", s):
        out.append((int(y), [x[:3] for x in MONTHS].index(m) + 1))
    return out


def graduation(l, o, t):
    if not known("education.end"):
        return None, "you", "set education.end"
    end = re.match(r"(\d{4})-(\d{2})", str(g("education.end")))
    grad = (int(end.group(1)), int(end.group(2))) if end else None
    window = _month_years(l)
    if len(window) == 2 and grad and re.search(r"between|from .* (to|through|and)", l):
        inside = window[0] <= grad <= window[1]
        return yn_answer(inside, o, "profile", "graduation %s vs window %s-%s" % (g("education.grad_text"), window[0], window[1]))
    if o:
        a = opt(o, *grad_patterns())
        return (a, "profile", "graduates " + str(g("education.grad_text"))) if a else (
            None, "you", "no option matches your graduation date")
    if re.search(r"between|^is your|^will you|^are you", l):
        return None, "you", "yes/no question about a graduation window: check the dates"
    return g("education.grad_text") or g("education.end"), "profile", ""


def start_date(l, o, t):
    if not known("preferences.start_date"):
        return None, "you", "set preferences.start_date"
    if o:
        mon, yr = _iso_month(g("preferences.start_date"))
        a = opt(o, r"\b%s\w* %s" % (mon[:3], yr) if mon else None, r"summer %s" % yr if mon in ("may", "june", "july", "august") else None,
                r"\b%s\b" % yr)
        return (a, "profile", "") if a else (None, "you", "no option matches your start date")
    if t == "Date":
        return g("preferences.start_date"), "profile", ""
    return g("preferences.start_text") or g("preferences.start_date"), "profile", ""


def years_bucket(years):
    def h(l, o, t):
        y = float(g(years) or 0)
        if not o:
            return (str(int(y)) if y == int(y) else str(y)), "profile", years
        for x in o:
            s = str(x).lower()
            nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", s)]
            if not nums:
                if y == 0 and re.search(r"none|no experience|less than", s):
                    return x, "profile", years
                continue
            if re.search(r"less than|under|<", s) and y < nums[0]:
                return x, "profile", years
            if re.search(r"more than|over|\+|or more|>", s) and y >= nums[0] and (len(nums) == 1):
                return x, "profile", years
            if len(nums) >= 2 and nums[0] <= y < nums[1] + (1 if re.search(r"\d\s*-\s*\d", s) else 0):
                return x, "profile", years
            if len(nums) == 1 and y == nums[0] and not re.search(r"less|more|over|under|\+", s):
                return x, "profile", years
        return None, "you", "%s=%s matches no option: %s" % (years, y, "; ".join(map(str, o[:6])))
    return h


def needs_sponsorship(label):
    now, fut = g("eligibility.needs_sponsorship_now"), g("eligibility.needs_sponsorship_future")
    if now is None or fut is None or now == "" or fut == "":
        return None
    if re.search(r"\bfuture\b", label):
        return bool(now or fut)
    if re.search(r"\b(currently|current|now|at this time|today)\b", label):
        return bool(now)
    return bool(now or fut)


def sponsorship(l, o, t):
    need = needs_sponsorship(l)
    if need is None:
        return None, "you", "set eligibility.needs_sponsorship_now / _future"
    if o:
        a = (opt(o, r"^yes\b", r"will require", r"^i will", r"require") if need else
             opt(o, r"^no\b", r"do not require", r"^no,", r"will not require"))
        return (a, "profile", "sponsorship") if a else (None, "you", "no matching option")
    if t in ("Boolean", "ValueSelect") or "?" in l:
        return ("Yes" if need else "No"), "profile", "sponsorship"
    status = g("eligibility.visa_status") or ""
    return ((status + ", " if status else "") + ("will require sponsorship" if need else "no sponsorship needed"),
            "profile", "sponsorship (free text)")


def authorized_without_sponsorship(l, o, t):
    auth = g("eligibility.us_work_authorized")
    need = needs_sponsorship(l)
    if auth is None or need is None:
        return None, "you", "set eligibility.us_work_authorized and needs_sponsorship_*"
    return yn_answer(bool(auth) and not need, o, "profile", "authorized and no sponsorship needed")


def require_authorization(l, o, t):
    auth = g("eligibility.us_work_authorized")
    need = needs_sponsorship(l)
    if auth is None or need is None:
        return None, "you", "set eligibility fields"
    return yn_answer((not auth) or need, o, "profile", "work authorization")


def authorized(l, o, t):
    auth = g("eligibility.us_work_authorized")
    if auth is None or auth == "":
        return None, "you", "set eligibility.us_work_authorized"
    if o and auth:
        a = opt(o, r"any employer", r"^yes\b", r"currently eligible", r"authorized")
        return (a, "profile", "US work authorization") if a else (None, "you", "no matching option")
    return yn_answer(bool(auth), o, "profile", "US work authorization")


def citizenship(l, o, t):
    cit, pr = g("eligibility.us_citizen"), g("eligibility.permanent_resident")
    us_person = bool(cit or pr)   # export-control "U.S. person" includes green-card holders
    if re.search(r"u\.?s\.? person|export|\bitar\b|protected individual|lawful permanent", l):
        if cit is None and pr is None:
            return None, "you", "set eligibility.us_citizen / permanent_resident"
        if o:
            if us_person:
                a = opt(o, r"^yes\b", r"i am a u\.?s\.? person",
                        r"u\.?s\.? citizen|united states citizen|citizen or national" if cit else
                        r"permanent resident|green ?card", avoid=r"not a u\.?s|not currently|^no\b")
            else:
                a = opt(o, r"^no\b", r"not a u\.?s", r"neither")
            return (a, "profile", "export-control status") if a else (None, "you", "no matching option")
        return yn_answer(us_person, o, "profile", "export-control status")
    # plain citizenship question
    if cit:
        if o:
            a = opt(o, r"u\.?s\.? citizen", r"united states citizen", r"citizen or national", r"^yes\b",
                    avoid=r"not a u\.?s|not currently|non-?citizen")
            return (a, "profile", "US citizen") if a else (None, "you", "no matching option")
        return "Yes" if "?" in l else "US citizen", "profile", "US citizen"
    if pr:
        if o:
            a = opt(o, r"permanent resident|green card|lawful permanent", r"^no\b")
            return (a, "profile", "permanent resident") if a else (None, "you", "no matching option")
        return ("No" if "?" in l else "Permanent resident"), "profile", "permanent resident"
    return None, "you", "citizenship question: answer it yourself once (bank it)"


def clearance_held(l, o, t):
    v = (g("eligibility.clearance_held") or "").strip().lower()
    if not v:
        return None, "you", "set eligibility.clearance_held"
    if v in ("none", "no", "never"):
        if o:
            return opt(o, r"never held", r"^none", r"^no\b"), "profile", "never held one"
        return ("No" if t in ("Boolean", "ValueSelect") else "No, I have never held a government clearance."), "profile", ""
    return None, "you", "you hold a clearance: answer clearance questions yourself"


def can_obtain_clearance(l, o, t):
    w = g("eligibility.willing_to_get_clearance")
    if w is None or w == "" or g("eligibility.us_citizen") is None:
        return None, "you", "set eligibility.willing_to_get_clearance"
    ok = bool(w) and bool(g("eligibility.us_citizen"))   # most US clearances require citizenship
    if o:
        a = opt(o, r"eligible to obtain", r"^yes\b") if ok else opt(o, r"^no\b", r"not eligible")
        return (a, "profile", "clearance eligibility") if a else (None, "you", "no matching option")
    return yn_answer(ok, o, "profile", "clearance eligibility")


def foreign_auth(l, o, t):
    m = re.search(r"in (poland|canada|the uk|united kingdom|india|germany|ireland|mexico|brazil|the eu|europe|"
                  r"australia|singapore|israel|japan|france|netherlands|spain)\b", l)
    country = m.group(1) if m else ""
    allowed = [c.lower() for c in (g("eligibility.other_countries_authorized") or [])]
    ok = any(c in country or country in c for c in allowed) if country else False
    return yn_answer(ok, o, "profile", "authorized to work in %s" % country)


def worked_here_before(l, o, t):
    past = [e for e in (g("work.past_employers") or []) if e]
    company = str(CUR_JOB.get("company") or "").lower()
    hit = any(e.lower() in l or (company and (e.lower() in company or company in e.lower())) for e in past)
    if hit:
        return (opt(o, r"formerly", r"former", r"^yes\b") if o else "Yes"), "profile", "in work.past_employers"
    if o:
        return opt(o, r"^no\b", r"never", r"have not", r"not previously"), "profile", "not in work.past_employers"
    return "No", "profile", ""


def current_company(l, o, t):
    if "previous" in l:
        return F("work.last_employer")(l, o, t)
    if g("work.currently_employed"):
        return F("work.current_employer")(l, o, t)
    return None, "skip", "not currently employed: blank"


def current_title(l, o, t):
    if "previous" in l:
        return F("work.last_title")(l, o, t)
    if g("work.currently_employed"):
        return F("work.current_title")(l, o, t)
    return "Student (%s, %s)" % (g("education.major_text", ""), g("education.school_short") or g("education.school", "")), \
        "inferred", "full-time student"


def lives_near_job():
    """Is the posting in the candidate's own city/state? (decides 'Yes, I live locally' vs 'Yes, I'll relocate')"""
    loc = str(CUR_JOB.get("location") or "").lower()
    city = str(g("location.city") or "").lower()
    return bool(city) and city in loc


def onsite(l, o, t):
    ok = g("preferences.onsite_ok")
    if ok is None or ok == "":
        return None, "you", "set preferences.onsite_ok"
    if not ok:
        return yn_answer(False, o, "profile", "preferences.onsite_ok=false")
    if o:
        if lives_near_job():
            a = opt(o, r"^yes\b.*(live locally|currently live|commut|reside)", r"^yes$", r"^yes\b")
        else:
            a = opt(o, r"^yes\b.*relocat", r"willing to relocate", r"planning to relocate", r"able to relocate",
                    r"^yes$", r"^yes(?!.*(live locally|currently live|reside|commuting distance|live within))")
        return (a, "profile", "on-site OK" + ("" if lives_near_job() else "; you'd relocate")) if a else (
            None, "you", "no matching option")
    return "Yes", "profile", "on-site OK"


def relocate(l, o, t):
    r = g("preferences.willing_to_relocate")
    if r is None or r == "":
        return None, "you", "set preferences.willing_to_relocate"
    if o:
        if r:
            a = opt(not_no(o), r"^yes\b.*relocat", r"willing to relocate", r"able to relocate", r"planning to relocate",
                    r"relocat", r"^yes(?!.*(currently live|live within|live locally|reside|commuting distance))",
                    r"^yes\b")
        else:
            a = opt(o, r"^no\b", r"not willing")
        if a is None and r and not any(re.match(r"\s*yes\b", str(x), re.I) for x in o):
            # the options are office cities ("New York, NY", "Seattle, WA"): use the office rule
            return office_pref(0)(l + " relocate", o, t)
        return (a, "profile", "relocation") if a else (None, "you", "no matching option")
    return ("Yes" if r else "No"), "profile", "relocation"


def office_pref(idx=0):
    def h(l, o, t):
        prefs = g("preferences.office_preference") or []
        if o:
            if t in ("multi_value_multi_select", "MultiValueSelect") and g("preferences.willing_to_relocate") and \
                    re.search(r"relocat|open to|select all|mark (each|all)", l):
                picks = [x for x in o if looks_us(x)]
                return (picks or None), ("profile" if picks else "you"), "willing to relocate: every US office listed"
            a = opt(o, *([re.escape(p) for p in prefs[idx:]] + [r"any office", r"open to", r"no preference", r"flexible"]))
            return (a, "profile", "preferences.office_preference") if a else (None, "you", "set preferences.office_preference")
        if len(prefs) > idx:
            return prefs[idx], "profile", ""
        return None, "you", "set preferences.office_preference"
    return h


US_STATES = ("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK "
             "OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC").split()
US_CITIES = ["new york", "nyc", "san francisco", "bay area", "seattle", "boston", "chicago", "austin", "los angeles",
             "washington", "denver", "atlanta", "dallas", "houston", "miami", "philadelphia", "pittsburgh", "san diego",
             "san jose", "palo alto", "mountain view", "menlo park", "sunnyvale", "redmond", "bellevue", "raleigh",
             "durham", "phoenix", "salt lake", "portland", "minneapolis", "detroit", "nashville", "charlotte",
             "columbus", "baltimore", "jersey city", "princeton", "cambridge, ma", "united states", "usa", "u.s."]


def looks_us(option):
    s = str(option)
    if re.search(r"international|remote|none|not willing|outside the u|no preference|^no\b", s, re.I):
        return False
    if re.search(r",\s*(%s)\b" % "|".join(US_STATES), s):
        return True
    return any(c in s.lower() for c in US_CITIES)


def lives_in_bay_area(l, o, t):
    bay = {"san francisco", "oakland", "berkeley", "san jose", "palo alto", "mountain view", "sunnyvale",
           "santa clara", "menlo park", "redwood city", "cupertino", "fremont", "san mateo"}
    if "willing to relocate" in l:
        return relocate(l, o, t)
    city = str(g("location.city") or "").lower()
    if not city:
        return None, "you", "set location.city"
    inside = city in bay
    if o:
        a = opt(o, r"^yes\b") if inside else opt(o, r"relocat", r"^no\b")
        return (a, "profile", "location.city") if a else (None, "you", "no matching option")
    return ("Yes" if inside else "No"), "profile", "location.city"


def current_city(l, o, t):
    if not known("location.city"):
        return None, "you", "set location.city"
    city, st = g("location.city"), g("location.state", "")
    if o:
        a = opt(o, r"^" + re.escape(city), re.escape(st) if st else None,
                r"outside .* willing" if g("preferences.willing_to_relocate") else r"outside .* not willing", r"^other",
                avoid=r"not willing" if g("preferences.willing_to_relocate") else None)
        return (a, "profile", "location") if a else (None, "you", "no matching option")
    return "%s, %s" % (city, g("location.state_abbr") or st), "profile", ""


def languages_spoken(l, o, t):
    langs = g("preferences.languages_spoken") or []
    if not langs:
        return None, "you", "set preferences.languages_spoken"
    if o:
        picks = [x for x in o if any(re.match(re.escape(x0) + r"\b", str(x), re.I) for x0 in langs)]
        return (picks or None), "profile", ""
    return ", ".join(langs), "profile", ""


SCHOOL_STOP = {"the", "of", "at", "in", "and", "university", "college", "institute", "school", "-", "&"}


def school_regex(name=None):
    """Lookahead regex requiring every distinctive word of the school name, so 'The University of Texas at Austin'
    matches 'University of Texas - Austin' but never 'Austin College'."""
    name = name or g("education.school") or ""
    words = [w for w in re.findall(r"[a-z]+", name.lower()) if w not in SCHOOL_STOP]
    return "".join(r"(?=.*\b%s\b)" % re.escape(w) for w in words) or re.escape(name)


def school(l, o, t):
    if not known("education.school"):
        return None, "you", "set education.school"
    if o:
        a = opt(o, r"^" + re.escape(g("education.school")) + r"$", school_regex(),
                r"^" + re.escape(g("education.school_short") or "@@") + r"$")
        return (a, "profile", "") if a else (None, "you", "your school is not in the list")
    return g("education.school"), "profile", ""


def background(l, o, t):
    majors = g("education.majors") or []
    if not majors:
        return None, "you", "set education.majors"
    if o:
        if t == "multi_value_multi_select":
            picks = [x for x in o if any(re.match(re.escape(m) + r"$", str(x), re.I) for m in majors + (g("education.minors") or []))]
            return (picks or None), "profile", ""
        return opt(o, *[re.escape(m) for m in majors]), "profile", ""
    return majors[0], "profile", ""


def bachelor_done(l, o, t):
    v = g("education.in_progress_degree_counts_as_completed")
    if v is None:
        return None, "you", "set education.in_progress_degree_counts_as_completed"
    return yn_answer(bool(v), o, "profile", "in-progress degree counts (graduating %s)" % g("education.grad_text", ""))


def highest_education(l, o, t):
    if not g("education.in_progress_degree_counts_as_completed"):
        return None, "you", "highest completed education: your call"
    lvl = g("education.degree_level") or "Bachelor's"
    if o:
        a = opt(o, r"^" + re.escape(lvl[:6]), re.escape(lvl[:6]))
        return (a, "profile", "in-progress degree counts") if a else (None, "you", "no matching option")
    return lvl + " degree", "profile", "in-progress degree counts"


def test_score(kind):
    def h(l, o, t):
        v = g("education." + kind)
        if not v:
            return None, "you", "set education.%s (or answer \"did not take\" once)" % kind
        if o:
            a = opt(o, r"^" + re.escape(str(v)), re.escape(str(v)))
            return (a, "profile", "") if a else (None, "you", "no matching option")
        return "%s %s" % (kind.upper(), v), "profile", ""
    return h


def test_scores(l, o, t):
    for k in ("act", "sat"):
        if k in l:
            return test_score(k)(l, o, t)
    return None, "you", "test scores"


def gpa(l, o, t):
    if re.search(r"\((graduate|doctorate)\)|graduate gpa|masters? gpa", l):
        return None, "skip", "graduate GPA: not applicable"
    v = g("education.gpa")
    if not v:
        return None, "you", "set education.gpa"
    if o:
        a = opt(o, r"^" + re.escape(str(v)) + r"\b(?!\s*-)")
        if a is None:
            try:   # bands like "3.5 - 3.69", "3.7+"; ignore "(out of 4.0)" scale text
                f = float(v)
                for x in o:
                    n = [float(z) for z in re.findall(r"\d\.\d+", re.sub(r"\(?out of [\d.]+\)?", "", str(x)))]
                    if (len(n) == 2 and n[0] <= f <= n[1]) or (len(n) == 1 and "+" in str(x) and f >= n[0]):
                        a = x
                        break
            except ValueError:
                pass
        return (a, "profile", "") if a else (None, "you", "no option matches your GPA")
    return str(v), "profile", ""


def email(l, o, t):
    if re.search(r"school|university|\.edu|student email|college email", l) and known("contact.school_email"):
        return g("contact.school_email"), "profile", "school email (the question asks for one)"
    return F("contact.email")(l, o, t)


def github_or_link(l, o, t):
    if l.startswith("linkedin profile, github"):
        return F("contact.linkedin")(l, o, t)
    return F("contact.github")(l, o, t)


def website(l, o, t):
    if known("contact.website"):
        return g("contact.website"), "profile", ""
    return None, "skip", "no website (GitHub is filled here later when the form has no GitHub box)"


def esign(l, o, t):
    if not g("consents.esign_ok"):
        return None, "you", "e-signature: consents.esign_ok is false"
    return P.full_name, "profile", "attestation signed with your name (consents.esign_ok)"


def resume_file(l, o, t):
    if t in ("textarea", "input_text", "LongText", "String"):
        return None, "skip", "paste-your-resume box: the PDF upload covers it"
    p = P.path("resume")
    return ((p.rsplit("/", 1)[-1], "profile", p) if p else (None, "you", "set files.resume"))


def transcript_file(l, o, t):
    p = P.path("transcript")
    return ((p.rsplit("/", 1)[-1], "profile", p) if p else (None, "you", "needs a transcript PDF: set files.transcript"))


def immigration_case(l, o, t):
    if g("eligibility.us_citizen"):
        return yn_answer(False, o, "profile", "US citizen")
    return None, "you", "immigration case: answer yourself"


def f1_status(l, o, t):
    vs = str(g("eligibility.visa_status") or "")
    if re.search(r"f-?1", vs, re.I):
        return yn_answer(True, o, "profile", "visa_status mentions F-1")
    if g("eligibility.us_citizen") or g("eligibility.permanent_resident"):
        return yn_answer(False, o, "profile", "citizen / permanent resident")
    return None, "you", "set eligibility.visa_status"


def state_of_residence(l, o, t):
    st = g("location.state")
    if not st:
        return None, "you", "set location.state"
    if o:
        a = opt(o, r"^" + re.escape(st))
        return (a, "profile", "") if a else (None, "you", "no matching option")
    return st, "profile", ""


def california_resident(l, o, t):
    st = g("location.state")
    if not st:
        return None, "you", "set location.state"
    return yn_answer(st.lower() in ("california", "ca"), o, "profile", "location.state")


def us_based(l, o, t):
    c = g("location.country") or ""
    if not c:
        return None, "you", "set location.country"
    return yn_answer(c.lower() in ("united states", "usa", "us", "united states of america"), o, "profile", "")


def country(l, o, t):
    c = g("location.country") or ""
    if not c:
        return None, "you", "set location.country"
    if o:
        a = opt(o, r"^united states$", r"^united states", r"^usa$", r"^us$") if "united states" in c.lower() else opt(o, re.escape(c))
        return (a, "profile", "") if a else (None, "you", "no matching option")
    return c, "profile", ""


def degree_text(l, o, t):
    if not known("education.degree"):
        return None, "you", "set education.degree"
    return "%s, %s" % (g("education.degree"), g("education.major_text") or ""), "profile", ""


def education_history(l, o, t):
    if not known("education.school"):
        return None, "you", "set education.school"
    return ({"school": g("education.school"), "degree": g("education.degree_level"), "field": (g("education.majors") or [""])[0],
             "start": g("education.start"), "end": g("education.end")}, "profile", "")


def full_time_swe(l, o, t):
    return yn_answer(float(g("work.full_time_years") or 0) > 0, o, "profile", "work.full_time_years")


def how_heard(l, o, t):
    v = g("preferences.how_heard") or ""
    if not v:
        return None, "you", "set preferences.how_heard"
    if o:
        a = opt(o, r"^" + re.escape(v) + r"$", r"^" + re.escape(v) + r".*job", r"^" + re.escape(v) + r"(?! post)",
                re.escape(v))
        return (a, "profile", "") if a else (None, "you", "%r not in the list" % v)
    return v, "profile", ""


def referral(l, o, t):
    if o:
        return opt(o, r"^no\b"), "default", "no referral"
    return None, "skip", "no referral"


def consent(path, note):
    def h(l, o, t):
        v = g(path)
        if v is None or v == "":
            return None, "you", "set " + path
        if o:
            a = (opt(o, r"acknowledge", r"^yes\b", r"opt-?in", r"consent", r"agree", r"^i ") if v else
                 opt(o, r"^no\b", r"opt-?out", r"do not", r"decline"))
            return (a, "profile", note) if a else (None, "you", "no matching option")
        return ("Yes" if v else "No"), "profile", note
    return h


def disqualifier_reason(l, o, t):
    return yn_answer(False, o, "inferred", "no reason you couldn't support the role / mission (confirm once)")


# ---------------------------------------------------------------- rules (order matters: narrow before broad)
RULES = [
    (r"^disability form signature", esign),
    (r"^disability form date", const("__TODAY__", "default", "date of filling (MM/DD/YYYY)")),
    (r"authori[sz]\w* to work\w*.* in (poland|canada|the uk|united kingdom|india|germany|ireland|mexico|brazil|the eu|"
     r"europe|australia|singapore|israel|japan|france|netherlands|spain)\b", foreign_auth),
    (r"full legal name|^(what is your )?legal name\??$", lambda l, o, t: (P.full_name, "profile", "")),
    (r"citizen or resident of any of the following countries: cuba|sanctioned countr", lambda l, o, t: (
        yn_answer(False, o, "profile", "US citizen") if g("eligibility.us_citizen") else (None, "you", "sanctions question"))),
    (r"by entering your name below|type your (full )?name (below )?to sign|electronic signature", esign),
    (r"transitioning service member|military spouse|served in the (u\.s\. )?(military|armed forces)",
     lambda l, o, t: yn_answer(False, o, "profile", "eeo.veteran = No") if str(g("eeo.veteran", "")).lower() == "no"
     else (None, "you", "military service question")),
    (r"resident of california", california_resident),
    (r"local to the .* office|\(within \d+ miles\)", lambda l, o, t: (
        yn_answer(True, o, "profile", "the posting is in your city") if lives_near_job()
        else (None, "you", "are you local to that office?"))),
    (r"currently in f-1|f-1 status", f1_status),
    (r"language skill|languages? (do you )?speak|languages spoken|languages are you fluent", languages_spoken),
    (r"which university|university are you (currently )?attending", school),
    (r"what full[- ]time job\(?s?\)? are you applying|which (role|position|job)\(?s?\)? are you applying for",
     lambda l, o, t: (CUR_JOB.get("title"), "default", "this posting's title")),
    (r"start your fellowship", const(None, "skip", "not a fellowship")),
    (r"available for full[- ]time work", start_date),
    (r"did you see a linkedin post", no("inferred", "found it on a job list, not a LinkedIn post")),
    (r"combined (engineering|technical|software)( or technical)? experience", years_bucket("work.total_experience_years")),
    (r"status of your bachelor", graduation),
    (r"educational or technical background", background),
    (r"travel to client sites|travel requirement|willing to travel|\d+ ?% (of )?(the time )?travel|level of travel|"
     r"ok with .*travel", lambda l, o, t: (
        (opt(o, r"^i can meet", r"^yes", r"can meet", r"willing", r"100"), "profile", "preferences.travel_ok")
        if o and g("preferences.travel_ok") else YN("preferences.travel_ok")(l, o, t))),
    (r"ever been terminated|asked to resign", YN("work.ever_terminated")),
    (r"(possess|have|hold) any (type of )?(government |security )?clearance|do you (currently )?(have|hold|possess) an? "
     r"(active )?(government |security )?clearance", clearance_held),
    (r"^year of high school graduation|high school graduation (year|date)", F("education.high_school_year")),
    (r"^high school name|name of (your )?high school|what high school", F("education.high_school")),
    (r"any reasons? why you (would|could) not|reasons? (that )?you would not be able", disqualifier_reason),
    (r"eligib\w* to obtain|eligible to obtain", can_obtain_clearance),
    (r"office\(?s?\)? would you be willing to relocate to|offices? (are you|would you be) (willing|open) to relocate",
     office_pref(0)),
    (r"share my resume .* partners|share (your|my) (resume|information) with (external )?(partners|third)",
     consent("consents.share_resume_with_partners", "consents.share_resume_with_partners")),
    # EEO
    (r"transgender", eeo("transgender")),
    (r"sexual orientation", eeo("orientation")),
    (r"gender|^are you (a )?man|identify with", eeo("gender")),
    (r"hispanic|latino", eeo("hispanic")),
    (r"\brac(e|ial)\b|ethnicity", eeo("race")),
    (r"veteran", eeo("veteran")),
    (r"^disability|disability status|have (a|any) disabilit|disabilit(y|ies) self|identify as .*disab|"
     r"self-identification of disability|^do you have a disability", eeo("disability")),
    (r"current age|your age|age range", eeo("age_band")),
    (r"text me|\bsms\b|text message|consent to receiv\w* text", consent("consents.sms_updates_ok", "SMS updates")),
    (r"\bi (hereby )?(affirm|certify|attest)\b|^by submitting this application", lambda l, o, t: (
        consent("consents.privacy_and_data_processing_ack", "attestation")(l, o, t) if o or t in ("Boolean",) else esign(l, o, t))),
    # identity / contact
    (r"^(legal )?first name$|^legal first name", F("name.first")),
    (r"^(legal )?last name$|^legal last name", F("name.last")),
    (r"^(full name|name|legal name|legal name \(first name last name\)|preferred first & last name|first and last name)$",
     lambda l, o, t: (P.full_name, "profile", "")),
    (r"preferred (first )?name|nickname", lambda l, o, t: ((g("name.preferred") or g("name.first")), "profile", "")),
    (r"^email|email address", email),
    (r"phone|mobile number", F("contact.phone")),
    (r"^(your )?linkedin|linkedin (profile|url)", F("contact.linkedin")),
    (r"^(your )?github( url)?$|^github or (personal )?website|github, portfolio|links? to relevant work|"
     r"a link we should look at|linkedin profile, github|optional github|github, project", github_or_link),
    (r"^(website|portfolio|website ?/ ?portfolio|your personal website|personal website|twitter|social media|"
     r"other links|your urls)", website),
    (r"name pronunciation|name pronounciation", lambda l, o, t: (
        (g("name.pronunciation"), "profile", "") if known("name.pronunciation") else (None, "you", "set name.pronunciation"))),
    (r"pronouns", F("name.pronouns")),
    # work authorization / sponsorship / citizenship (narrow phrasings first)
    (r"part 810|subject to a specific authorization", no("inferred", "never had DOE Part 810 access (confirm once)")),
    (r"how does (this|that) excite you|please keep your answer to|in \d ?- ?\d sentences|in a few sentences",
     lambda l, o, t: (None, "essay", "free-text prompt") if not o else (None, "you", "free-text prompt with options")),
    (r"^if other, please (provide|explain|specify)|^if \(?[a-z]\)? ?other, please|^please specify$|answer n/?a if not applicable",
     lambda l, o, t: ((None, "skip", "conditional follow-up with options") if o else ("N/A", "default", "conditional follow-up: N/A"))),
    (r"^if you answered ['\"]?no['\"]? to the previous", const(None, "skip", "conditional follow-up")),
    (r"require (work |employment )?authorization to (legally )?work", require_authorization),
    (r"(willing|able)( and able| and willing)? to relocate", relocate),
    (r"authoriz\w* to work.*without (requiring )?(an )?(employer[- ]sponsored )?(visa |work )?"
     r"(sponsorship|authorization)", authorized_without_sponsorship),
    (r"what is your current visa status|current (immigration|visa|work authorization) status",
     lambda l, o, t: ((g("eligibility.visa_status"), "profile", "") if known("eligibility.visa_status")
                      else (None, "you", "set eligibility.visa_status"))),
    (r"(authoriz|eligible|able) to work.*without (visa )?sponsorship", authorized_without_sponsorship),
    (r"sponsor|visa|immigration (assistance|support)|h-1b|work permit", sponsorship),
    (r"authoriz|eligible to work|legally (able|entitled)|proof that you are authorized|"
     r"legally eligible to begin employment", authorized),
    (r"countr(y|ies) of citizenship|provide your countr(y|ies)|which countr(y|ies) .*citizen", lambda l, o, t: (
        (opt(o, r"^united states$", r"^united states", r"^usa\b", r"^us$"), "profile", "US citizen") if o and g("eligibility.us_citizen")
        else ("United States", "profile", "US citizen") if g("eligibility.us_citizen")
        else (None, "you", "country of citizenship: answer once (bank it)"))),
    (r"citizenship status|u\.s\. citizen|us citizen|u\.s\. person|export|\bitar\b|lawful permanent|"
     r"protected individual|united states citizen", citizenship),
    (r"q security clearance|active (united states )?security clearance|clearance\(s\)|highest level of security clearance",
     clearance_held),
    (r"clearance eligibility|meet the citizenship requirements to obtain|able to obtain", can_obtain_clearance),
    (r"18 years|18\+|over 18", YN("eligibility.over_18")),
    (r"active immigration case", immigration_case),
    # location
    (r"which location are you applying|location are you applying for|which office are you applying",
     lambda l, o, t: ((opt(o, re.escape((CUR_JOB.get("location") or "").split(",")[0].strip() or "@@")), "default",
                       "the posting's own location") if o else (CUR_JOB.get("location"), "default", "the posting's own location"))),
    (r"city and state|city, state|city/state", current_city),
    (r"which u\.s\. state|state .* reside", state_of_residence),
    (r"(city|location|where).*(live|reside|located|based)|^location$|current location|what city do you live", current_city),
    (r"^street address$|current address|^address( line 1)?$", lambda l, o, t: (
        (g("location.street"), "profile", "") if known("location.street") else (None, "you", "set location.street"))),
    (r"^(home )?(zip|postal) ?code$|^what is your (home )?(zip|postal) code", F("location.zip")),
    (r"^city$", F("location.city")),
    (r"^state$", F("location.state")),
    (r"country where you currently reside|country/region do you have citizenship|country of citizenship|^country$", country),
    # education
    (r"gpa|grade point", gpa),
    (r"graduat|year of graduation", graduation),
    (r"what university|where did you attend|undergad|undergraduate studies|^school$|^university$", school),
    (r"undergrad(uate)? (degree|major)|what did you get your undergrad", degree_text),
    (r"enrolled in a degree program .*computer science", lambda l, o, t: yn_answer(
        any("computer" in m.lower() for m in (g("education.majors") or [])), o, "profile", "education.majors")),
    (r"which degree are you currently pursuing", lambda l, o, t: (
        opt(o, re.escape((g("education.degree_level") or "bachelor")[:6])) if o else g("education.degree_level"), "profile", "")),
    (r"did you attend graduate school|graduate major", const(None, "skip", "no grad school")),
    (r"sat score|act score|gre score|sat or act", test_scores),
    (r"transcript|academic record", transcript_file),
    # start / employment
    (r"start date|available to start|when can you start|earliest date|soonest available|when will you be available|"
     r"earliest you could start|earliest (possible )?start",
     start_date),
    (r"desired employment|employment type", F("preferences.employment_type")),
    (r"previously (been )?employed|ever worked for|worked at|currently a .* employee|current employee|"
     r"employment history|ever been employed|are your currently a .* contractor|current or former|"
     r"have you previously been employed", worked_here_before),
    (r"previously applied to", const(None, "you", "have you applied to this employer before?")),
    (r"current (or previous )?employer|current company|what is your current company", current_company),
    (r"current (or previous )?job title|current position|current job title", current_title),
    (r"non-?compet|restrictive covenant|post-employment agreement|contractual restrictions", YN("work.non_compete")),
    (r"essential functions", yes("default", "able to perform the essential functions")),
    (r"years of (industry |ml infrastructure |compiler |professional )?experience|how many years of",
     years_bucket("work.full_time_years")),
    (r"worked as a full-time software engineer", full_time_swe),
    # source / referral
    (r"how did you (first )?(hear|learn)|where did you hear|how did you learn|how you heard about|how you found", how_heard),
    (r"\brefer(red|ral)?\b|who referred", referral),
    (r"please specify|if other|if you selected|if yes|if you answered|if \(f\) other|anything else to add",
     const(None, "skip", "conditional follow-up")),
    # relocation / onsite
    (r"relocat", relocate),
    (r"on-?site|in-?office|in office|in person|in-person|days (per|a) week|office .* week|commut|hybrid", onsite),
    (r"which .*office|preferred office|office location|location preference|first location preference", office_pref(0)),
    (r"second location preference", office_pref(1)),
    (r"third location preference", office_pref(2)),
    (r"live in the san francisco|bay area", lives_in_bay_area),
    # acknowledgements / consents
    (r"arbitration", const(None, "you", "arbitration agreement: your decision")),
    (r"text me|sms|text message|consent to receiv\w* text", consent("consents.sms_updates_ok", "SMS updates")),
    (r"privacy|data protection|acknowledge|consent", consent("consents.privacy_and_data_processing_ack",
                                                             "privacy / data-processing acknowledgement")),
    (r"considered for (other|future)|future opportunities", consent("consents.consider_for_future_roles", "future roles")),
    (r"metaview|notetak|record(ing)? (the |your |our )?(interview|conversation|call)|transcribe",
     consent("consents.interview_recording_or_ai_notetaker_ok", "interview recording / AI notetaker")),
    (r"education history", education_history),
    (r"currently (based|located|living|residing) in the (united states|u\.?s\.?)\b", us_based),
    (r"what country are you applying from|country (of|where you) (currently )?(reside|live)", country),
    (r"prepared to work at a startup", yes("inferred", "startup willingness assumed")),
    (r"^job location$", lambda l, o, t: (opt(o, r"able to relocate", r"able to work at") if o else None,
                                         "profile" if g("preferences.willing_to_relocate") else "you", "")),
    (r"completed at least a bachelor|(have|hold|obtained|possess) (at least )?a bachelor", bachelor_done),
    (r"highest (level of )?education (you have )?completed|highest degree (completed|obtained|earned)", highest_education),
    (r"salary|compensation|base pay|pay expectations", salary),
    (r"strongest coding language|preferred coding language|strongest (programming )?language", lambda l, o, t: (
        (opt(o, r"^" + re.escape(g("preferences.strongest_language")) + r" ?\d?$", re.escape(g("preferences.strongest_language")))
         if o else g("preferences.strongest_language")), "profile", "")
        if known("preferences.strongest_language") else (None, "you", "set preferences.strongest_language")),
    (r"top 3 programming languages", F("preferences.top_languages")),
    (r"cover letter|portfolio or cover letter", const(None, "skip", "optional; cover letters only on request")),
    (r"^(resume|cv)\b|^upload (your )?(resume|cv)|^attach (your )?(resume|cv)", resume_file),
    (r"complete the takehome|take-?home", const(None, "you", "take-home assignment")),
    (r"offer deadline|other processes|timelines|recruiting-process deadline", const(None, "you",
                                                                                   "active offers/deadlines: your call")),
    (r"employment obligations", lambda l, o, t: (("None", "profile", "no agreements") if g("work.non_compete") is False
                                                 else (None, "you", "employment obligations"))),
]
ESSAY_TYPES = {"textarea", "LongText"}
READY_SOURCES = {"profile", "bank", "default"}


# ---------------------------------------------------------------- answering
def bank():
    try:
        return json.loads(BANK.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def norm(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", s).strip().lower().rstrip("*").strip()


def answer(label, options, ftype, required, company=""):
    l = norm(label)
    b = bank().get(l)
    if b is not None:
        return b, "bank", "approved earlier"
    # SMS consent hidden under a generic label ("Phone number" with "Yes - I consent to receiving text messages")
    if options and any(re.search(r"consent to receiv\w* text|text messag", str(x), re.I) for x in options):
        return consent("consents.sms_updates_ok", "SMS updates")(l, options, ftype)
    if re.search(r"^if (yes|so|you (require|need|answered ['\"]?yes))\b", l) and re.search(r"sponsor|visa", l):
        # follow-up to a sponsorship question: only meaningful when you need sponsorship
        need = needs_sponsorship(l + " future")
        if need and options:
            return None, "you", "sponsorship follow-up with options: pick yours once (then bank it)"
        if need:
            return ((g("eligibility.visa_status"), "inferred", "you need sponsorship: your visa status (check wording)")
                    if known("eligibility.visa_status") else (None, "you", "set eligibility.visa_status"))
        if need is False:
            return ("N/A", "default", "you don't need sponsorship") if required else (None, "skip", "not applicable")
    if re.search(r"^if (yes|so|other|applicable|not|you (selected|answered|require|checked|chose|need))\b|^if [\"'“]|"
                 r"^please specify|^if \(f\)", l):
        # required conditional follow-ups get N/A; optional ones stay blank
        return ("N/A", "default", "required conditional follow-up: N/A") if required and not options else (
            None, "skip" if not required else "you", "conditional follow-up")
    for rx, h in RULES:
        if re.search(rx, l, re.I):
            a, src, note = h(l, options, ftype)
            if a == "N/A" and not required:
                return None, "skip", "optional conditional follow-up: leave blank"
            if a is None and required and re.search(r"current company|current (or previous )?employer", l):
                if known("education.school_short") or known("education.school"):
                    return "%s (student)" % (g("education.school_short") or g("education.school")), "inferred", \
                        "required; you are a full-time student"
            if a is None and src in READY_SOURCES and required:
                src, note = "you", note or "rule had no answer"
            if a is None and src == "you" and not required:
                src = "skip"   # optional and unknown: leave blank rather than ask
            return a, src, note
    if ftype in ESSAY_TYPES or (ftype in ("String", "input_text") and len(l) > 60 and "?" in l):
        return None, "essay", "free response"
    return None, ("you" if required else "skip"), "no rule"


# ---------------------------------------------------------------- fetching forms
def http_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=dict(UA, **(headers or {})))
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def http_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


LEVER_SKIP = {"selectedLocation", "accountId", "linkedInData", "origin", "referer", "timezone", "socialReferralKey",
              "socialSource", "resumeStorageId", "h-captcha-response", "source"}
LEVER_LABELS = {"name": "Full name", "email": "Email", "phone": "Phone", "location": "Current location",
                "org": "Current company", "comments": "Additional information", "resume": "Resume/CV",
                "eeo[gender]": "Gender", "eeo[race]": "Race", "eeo[veteran]": "Veteran status",
                "eeo[disability]": "Disability status",
                "eeo[disabilitySignature]": "Disability form signature (your name)",
                "eeo[disabilitySignatureDate]": "Disability form date",
                "consent[marketing]": "Consent to be contacted about future job opportunities",
                "opportunityLocationId": "Which location are you applying for?"}
LEVER_FTYPE = {"text": "input_text", "textarea": "textarea", "select": "multi_value_single_select",
               "radio": "multi_value_single_select", "checkbox": "multi_value_multi_select", "file": "input_file"}


def _attr(attrs, k):
    m = re.search(r'\b%s="([^"]*)"' % re.escape(k), attrs)
    return html.unescape(m.group(1)) if m else None


def _txt(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<svg.*?</svg>", "", s, flags=re.S)))).strip()


def fetch_lever(x):
    m = re.search(r"jobs\.lever\.co/([^/]+)/([0-9a-f-]{36})", x["apply_url"] + " " + x.get("posting_url", ""))
    co, jid = m.group(1), m.group(2)
    try:
        api = http_json("https://api.lever.co/v0/postings/%s/%s" % (co, jid))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None  # posting closed
        raise
    t = http_text(api.get("applyUrl") or "https://jobs.lever.co/%s/%s/apply" % (co, jid))
    i = t.find('id="application-form"')
    if i < 0:
        return None
    form = t[i:]
    cards = {}
    for tag in re.findall(r"<input\b[^>]*baseTemplate[^>]*>", form):
        cid = re.search(r'name="cards\[([^\]]+)\]', tag).group(1)
        d = json.loads(html.unescape(re.search(r'value="([^"]*)"', tag).group(1)))
        for n, f in enumerate(d.get("fields") or []):
            cards["cards[%s][field%d]" % (cid, n)] = dict(label=f.get("text", ""), required=bool(f.get("required")),
                                                          options=[o.get("text", "") for o in f.get("options") or []],
                                                          section=d.get("text", ""))
    qs, seen = [], {}
    for mm in re.finditer(r"<(input|select|textarea)\b([^>]*)>", form):
        tag, attrs = mm.group(1), mm.group(2)
        nm = _attr(attrs, "name")
        typ = (_attr(attrs, "type") or tag).lower()
        if not nm or nm in LEVER_SKIP or nm.endswith("[baseTemplate]") or typ in ("hidden", "submit", "button"):
            continue
        kind = ("select" if tag == "select" else "textarea" if tag == "textarea" else
                typ if typ in ("radio", "checkbox", "file") else "text")
        val = ""
        if kind in ("radio", "checkbox"):
            val = _attr(attrs, "value") or ""
            if val in ("", "0", "1", "on"):  # option text lives in the label next to the box
                nxt = re.search(r'application-answer-alternative[^>]*>(.*?)</(?:span|p)>', form[mm.end():mm.end() + 800], re.S)
                val = _txt(nxt.group(1)) if nxt else val
        if nm in seen:
            if kind in ("radio", "checkbox") and val not in seen[nm]["options"]:
                seen[nm]["options"].append(val)
            continue
        before = form[max(0, mm.start() - 6000):mm.start()]
        k = before.rfind('class="application-label')
        # the label must belong to this question (same application-question block), not an earlier one
        if k >= 0 and (before.rfind("application-question") > k or "</li>" in before[k:]):
            k = -1
        lab_html = before[k:] if k >= 0 else ""
        lab_html = lab_html[lab_html.find(">") + 1:]
        lab = _txt(lab_html.split("</div>", 1)[0]) if k >= 0 else ""
        if not lab and k >= 0:  # card labels sit in a nested <div class="text">
            lab = _txt(lab_html[:lab_html.find("</div></div>")])
        req = "✱" in lab or bool(re.search(r"\brequired\b", attrs))
        lab = lab.replace("✱", "").strip()
        opts = []
        if kind == "select":
            body = form[mm.end():form.find("</select>", mm.end())]
            opts = [_txt(o) for o in re.findall(r"<option[^>]*>(.*?)</option>", body, re.S)]
            opts = [o for o in opts if o and not re.match(r"^select\s*\.*$", o, re.I)]
        elif kind in ("radio", "checkbox"):
            opts = [val]
        q = dict(label=LEVER_LABELS.get(nm, lab), name=nm, type=LEVER_FTYPE[kind], kind=kind, required=req,
                 options=opts, section="")
        if nm in cards:
            c = cards[nm]
            q.update(label=c["label"], required=c["required"], section=c["section"])
            if c["options"]:
                q["options"] = c["options"]
        if nm in ("eeo[disabilitySignature]", "eeo[disabilitySignatureDate]"):
            q["required"] = False
        seen[nm] = q
        qs.append(q)
    return dict(token=co, job_id=jid, title=api.get("text"), questions=qs,
                has_hcaptcha="h-captcha" in t, apply_url=api.get("applyUrl"))


def fetch_form(x):
    urls = x.get("apply_url", "") + " " + x.get("posting_url", "")
    if x["ats"] == "lever":
        return fetch_lever(x)
    if x["ats"] == "greenhouse":
        m = re.search(r"greenhouse\.io/(?:embed/job_app\?for=)?([A-Za-z0-9_-]+)", urls)
        tok, jid = m.group(1), x["id"].split("-", 1)[1]
        try:
            d = http_json("https://boards-api.greenhouse.io/v1/boards/%s/jobs/%s?questions=true" % (tok, jid))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise
        qs = []
        for q in d.get("questions", []):
            for f in q["fields"]:
                qs.append(dict(label=q["label"], name=f["name"], type=f["type"], required=bool(q.get("required")),
                               options=[v["label"] for v in f.get("values", [])]))
        for sec in ("compliance", "demographic_questions"):
            blk = d.get(sec) or []
            blk = blk if isinstance(blk, list) else blk.get("questions", [])
            for q in blk:
                for f in q.get("fields", [q]):
                    # custom demographic questions carry no field name: the DOM id is the question id
                    qs.append(dict(label=q.get("label") or q.get("description", ""),
                                   name=f.get("name") or (str(q["id"]) if sec == "demographic_questions" and q.get("id") else ""),
                                   type=f.get("type", "multi_value_single_select"), required=bool(q.get("required")),
                                   options=[v.get("label", "") for v in (f.get("values") or q.get("answer_options") or [])],
                                   section=sec))
        return dict(token=tok, job_id=jid, title=d.get("title"), questions=qs,
                    has_compliance=bool(d.get("compliance")), has_demographics=bool(d.get("demographic_questions")))
    m = re.search(r"jobs\.ashbyhq\.com/([^/]+)/([0-9a-f-]{36})", urls)
    tok, jid = m.group(1), m.group(2)
    r = http_json("https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting",
                  data=json.dumps({"operationName": "ApiJobPosting", "query": AQ,
                                   "variables": {"organizationHostedJobsPageName": tok, "jobPostingId": jid}}).encode(),
                  headers={"Content-Type": "application/json"})
    jp = (r.get("data") or {}).get("jobPosting")
    if not jp:
        return None
    qs = []
    for s in jp["applicationForm"]["sections"]:
        for e in s["fieldEntries"]:
            f = e.get("field") or {}
            qs.append(dict(label=f.get("title", ""), name=f.get("path", ""), type=f.get("type", ""),
                           required=bool(e.get("isRequired")),
                           options=[v.get("label", "") for v in (f.get("selectableValues") or [])]))
    return dict(token=tok, job_id=jid, title=jp.get("title"), questions=qs)


# ---------------------------------------------------------------- state
def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def save_state(state):
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")


def plan_job(x, form):
    """Answer every question of one form. Returns (row, plan)."""
    row = dict(id=x["id"], ats=x["ats"], company=x["company"], title=x["title"], location=x.get("location", ""),
               posted=x.get("posted", ""), pay=x.get("pay", ""), apply_url=x["apply_url"], notes=x.get("notes", ""))
    plan = []
    CUR_JOB.clear()
    CUR_JOB.update(x)
    for q in form["questions"]:
        a, src, note = answer(q["label"], q["options"], q["type"], q["required"], x["company"])
        plan.append(dict(label=q["label"], name=q["name"], type=q["type"], required=q["required"],
                         options=q["options"][:40], answer=a, source=src, note=note,
                         section=q.get("section", ""), kind=q.get("kind", "")))
    # Lever "Which location are you applying for?": the posting's own location
    for p in plan:
        if p["name"] == "opportunityLocationId" and p["options"]:
            city = (x.get("location") or "").split(",")[0].strip()
            o = opt(p["options"], re.escape(city)) if city else None
            if o:
                p.update(answer=o, source="default", note="the posting's own location")
    # Website/Portfolio gets the GitHub link unless the same form already asks for GitHub
    gh = g("contact.github")
    if gh and not known("contact.website") and not any(
            p["answer"] == gh or re.search(r"github", p["label"], re.I) for p in plan):
        for p in plan:
            if p["source"] == "skip" and re.match(r"\s*(website|portfolio|website ?/ ?portfolio|your personal website|"
                                                  r"personal website)", p["label"], re.I):
                p.update(answer=gh, source="profile", note="website/portfolio = GitHub (the form has no GitHub box)")
    req = [p for p in plan if p["required"]]
    essays = [p for p in req if p["source"] == "essay"]
    you = [p for p in req if p["source"] == "you"]
    inferred = [p for p in req if p["source"] == "inferred"]
    label = "needs-you" if you else "essay" if essays else "needs-ok" if inferred else "ready"
    row.update(label=label, n_questions=len(plan), n_required=len(req),
               essays=[e["label"] for e in essays], needs_you=[(p["label"], p["note"]) for p in you],
               inferred=[(p["label"], p["answer"], p["note"]) for p in inferred],
               optional_essays=[p["label"] for p in plan if not p["required"] and p["source"] == "essay"])
    return row, plan


def build(ids=None, company=None, limit=None):
    FORMS.mkdir(exist_ok=True)
    PLANS.mkdir(exist_ok=True)
    jobs = json.loads(DATA.read_text(encoding="utf-8"))["jobs"]
    state = load_state()
    back = [x for x in jobs if x["ats"] in ("greenhouse", "ashby", "lever") and x["id"] not in state]
    if ids:
        back = [x for x in back if x["id"] in ids]
    if company:
        back = [x for x in back if company.lower() in x["company"].lower()]
    back.sort(key=lambda r: r.get("posted", ""), reverse=True)
    if limit:
        back = back[:limit]
    old = {}
    if QUEUE.exists() and (ids or company or limit):
        old = {j["id"]: j for j in json.loads(QUEUE.read_text(encoding="utf-8"))["jobs"]}
    queue = []
    print("fetching %d forms..." % len(back), flush=True)
    for x in back:
        try:
            form = fetch_form(x)
            err = ""
        except Exception as e:  # noqa: BLE001
            form, err = None, str(e)[:80]
        if not form:
            row = dict(id=x["id"], ats=x["ats"], company=x["company"], title=x["title"], location=x.get("location", ""),
                       posted=x.get("posted", ""), pay=x.get("pay", ""), apply_url=x["apply_url"],
                       label="dead", reason=err or "form not found (posting closed?)")
            queue.append(row)
            continue
        (FORMS / ("%s.json" % x["id"])).write_text(json.dumps(form, indent=1), encoding="utf-8")
        row, plan = plan_job(x, form)
        (PLANS / ("%s.json" % x["id"])).write_text(json.dumps(dict(job=row, form_meta={k: v for k, v in form.items()
                                                                                         if k != "questions"},
                                                                    plan=plan), indent=1, ensure_ascii=False),
                                                   encoding="utf-8")
        queue.append(row)
        time.sleep(0.15)
    if old:
        new_ids = {j["id"] for j in queue}
        queue += [j for i, j in old.items() if i not in new_ids and i not in state]
    QUEUE.write_text(json.dumps(dict(built_at=datetime.now().isoformat(timespec="seconds"), jobs=queue), indent=1,
                                ensure_ascii=False), encoding="utf-8")
    summary()


def _queue():
    if not QUEUE.exists():
        sys.exit("No queue yet: run  python3 applyq/applyq.py build")
    state = load_state()
    return [j for j in json.loads(QUEUE.read_text(encoding="utf-8"))["jobs"] if j["id"] not in state]


def summary(links=False):
    q = _queue()
    c = Counter(j["label"] for j in q)
    print("%d jobs: " % len(q) + ", ".join("%s %d" % (k, v) for k, v in c.most_common()))
    for lab in ("ready", "needs-ok", "essay", "needs-you", "dead"):
        rows = [j for j in q if j["label"] == lab]
        if not rows:
            continue
        print("\n== %s (%d)" % (lab, len(rows)))
        for j in sorted(rows, key=lambda r: r.get("posted", ""), reverse=True):
            extra = ""
            if lab == "essay":
                extra = " | " + " / ".join(e[:50] for e in j["essays"])
            elif lab == "needs-you":
                extra = " | " + " / ".join("%s (%s)" % (a[:45], b[:35]) for a, b in j["needs_you"])
            elif lab == "needs-ok":
                extra = " | " + " / ".join(a[:40] for a, b, c_ in j["inferred"])
            print("  %s %s %-24s %-55s%s" % (j.get("posted", ""), j["ats"][:2], j["company"][:24], j["title"][:55], extra[:230]))
            if links:
                print("      id=%s  %s" % (j["id"], j["apply_url"]))


def next_job():
    q = [j for j in _queue() if j["label"] in ("ready", "needs-ok")]
    if not q:
        print("No ready jobs. Run `missing` and answer the top questions, or draft essays for `essay` jobs.")
        return
    j = sorted([x for x in q if x["label"] == "ready"], key=lambda r: r.get("posted", ""), reverse=True) or \
        sorted(q, key=lambda r: r.get("posted", ""), reverse=True)
    x = j[0]
    print(json.dumps({k: x[k] for k in ("id", "ats", "company", "title", "location", "posted", "pay", "apply_url", "label")
                      if k in x}, indent=1))
    if x.get("optional_essays"):
        print("optional essay boxes:", x["optional_essays"])


def missing():
    q = _queue()
    c, by = Counter(), defaultdict(list)
    for j in q:
        for lab, note in j.get("needs_you", []):
            k = norm(lab)[:90] + "  [" + note + "]"
            c[k] += 1
            by[k].append(j["company"])
        for lab, a, note in j.get("inferred", []):
            k = "(inferred: %s) " % (a,) + norm(lab)[:70] + "  [" + note + "]"
            c[k] += 1
            by[k].append(j["company"])
    if not c:
        print("Nothing missing.")
    for k, n in c.most_common():
        print("%3d  %s  <- %s" % (n, k, ", ".join(sorted(set(by[k])))[:120]))


def bank_cmd(args):
    b = bank()
    if not args or args[0] == "--list":
        for k, v in sorted(b.items()):
            print("%-90s -> %s" % (k[:90], v))
        return
    if len(args) != 2:
        sys.exit('usage: applyq.py bank "<question label>" "<answer>"   (answer may be JSON, e.g. \'["A","B"]\')')
    label, ans = norm(args[0]), args[1]
    try:
        ans = json.loads(ans) if ans.strip().startswith(("[", "{")) else ans
    except ValueError:
        pass
    b[label] = ans
    BANK.parent.mkdir(exist_ok=True)
    BANK.write_text(json.dumps(b, indent=1, ensure_ascii=False), encoding="utf-8")
    print("saved: %r -> %r  (re-run build to apply)" % (label, ans))


def hide(job_id, reason):
    s = load_state()
    s[job_id] = dict(status="hidden", reason=reason, at=datetime.now().isoformat(timespec="seconds"))
    save_state(s)
    print("hidden:", job_id, "-", reason)


def main(argv):
    global P
    cmd = argv[1] if len(argv) > 1 else "summary"
    if cmd in ("build", "plan", "next", "summary", "missing"):
        P = candidate.Profile(candidate.load())
    if cmd == "build":
        if P:
            errs, _ = candidate.check(P)
            if errs:
                sys.exit("Fix your profile first (python3 applyq/candidate.py):\n  " + "\n  ".join(errs))
        a = argv[2:]
        ids = a[a.index("--ids") + 1].split(",") if "--ids" in a else None
        co = a[a.index("--company") + 1] if "--company" in a else None
        lim = int(a[a.index("--limit") + 1]) if "--limit" in a else None
        build(ids, co, lim)
    elif cmd == "summary":
        summary(links="--links" in argv)
    elif cmd == "next":
        next_job()
    elif cmd == "missing":
        missing()
    elif cmd == "plan":
        p = json.loads((PLANS / ("%s.json" % argv[2])).read_text(encoding="utf-8"))
        print("%s - %s (%s)  %s" % (p["job"]["company"], p["job"]["title"], p["job"]["label"], p["job"]["apply_url"]))
        for r in p["plan"]:
            print("%s [%-8s] %-80s -> %s  %s" % ("*" if r["required"] else " ", r["source"], norm(r["label"])[:80],
                                                  r["answer"], ("(" + r["note"] + ")") if r["note"] else ""))
    elif cmd == "bank":
        bank_cmd(argv[2:])
    elif cmd == "hide":
        hide(argv[2], " ".join(argv[3:]) or "skipped")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
