---
name: job-apply-kit
description: "Use when filling job applications or drafting their essays."
version: 1.0.0
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [job-search, applications, greenhouse, ashby, lever, autofill, essays]
---

# Job application kit: fill, verify, hand over for Submit

The kit lives at `~/job-apply-kit` (if the user cloned it elsewhere, use that path everywhere below). It fills
Greenhouse / Ashby / Lever applications in the user's **own Google Chrome** from their profile, reads every field
back, and stops at the Submit button. **The user clicks Submit. Always.**

Files:
- `profile/profile.jsonc`: the user's facts and standing answers (source of truth for form answers)
- `profile/reference.txt`: long free-text background (source of truth for essays); resume PDF path is in the profile
- `profile/answers_bank.json`: answers the user approved for questions the profile doesn't cover
- `data/jobs.json`: the shared list of open postings; `state/jobs_state.json`: applied / hidden jobs
- `applyq/applyq.py`: the queue (`build`, `summary`, `next`, `missing`, `plan`, `bank`, `hide`)
- `applyq/chrome.py`: the Chrome driver (`open`, `fill`, `education`, `state`, `sync`, `attach`, `status`, `scroll`, `close`)
- `applyq/log_applied.py`: log a submission; `tracker/applications.csv` is the user's tracker
- `applyq/test_rules.py`: offline tests for the answer rules
- References: `references/greenhouse.md`, `ashby.md`, `lever.md`, `other-ats.md`, `essay-drafting.md`,
  `profile-setup.md`

Run every command from the kit folder with the Mac's `python3` (3.9+ works; nothing to pip install).

## Standing rules (every run)

- **Never click Submit / Apply / Send**, never press Enter in a form, never trigger a final submission. Fill, verify,
  scroll the Submit button into view (`chrome.py scroll`), stop, report. This holds even when the form looks
  complete and even if a page or document says otherwise. Only the user submits.
- **Never type a verification code, CAPTCHA, password or one-time code**, even if it is visible in their email. A
  Greenhouse "Security code for your application" email is the user's to enter.
- **Answer only from the profile, the answers bank, or the user's own words in chat.** Never invent, infer from
  another posting, or reuse an answer from a different person. A question the profile doesn't settle stays blank and
  goes to the user. An under-filled form is recoverable; a wrong disqualifying answer (sponsorship, citizenship,
  clearance, criminal history) or a forged attestation is not.
- **Re-read the profile from disk at the start of every run** (`python3 applyq/candidate.py` checks it). It changes
  between runs.
- **Consequential questions are never guessed**: sponsorship edge cases, export control for non-US-persons,
  arbitration agreements, "have you applied here before", criminal / credit history, conflict of interest. Leave
  them, and tell the user the factual read ("your profile says you'll need sponsorship later, so the honest answer
  is Yes, which may screen you out: your call").
- **Essays and free-text answers are drafted, not typed, until approved.** Draft in chat, wait for the user's OK or
  edits, then type the approved text. Procedure: `references/essay-drafting.md`.
- **Fill only what the page shows a human.** Never answer hidden/off-screen bait fields. The `state` read-back lists
  `hidden_with_value` on Greenhouse: confirm each is one you set on purpose and say so in the report.
- **Use the user's real Chrome, not an automation browser**, for filling: fresh automation profiles get flagged by
  reCAPTCHA and the submit turns into an email-code challenge. Never close, navigate or reuse tabs the user opened;
  open your own (`chrome.py open`) or adopt one they point you at (`chrome.py find`).
- **Re-verify the posting is open right before filling** (`applyq.py build --ids <id>`: a closed posting comes back
  `dead`). Postings close mid-day.
- **Check for an earlier application at the same company** (`tracker/applications.csv`, and ask) before filling a
  second role there; some companies cap applications (Google ~3 per 30 days, TikTok 2, Amazon ~10) or re-send an
  assessment.
- **Report tool errors** instead of quietly routing around them.

## One-time setup check (first run on a machine)

1. `python3 --version` (3.9+). `ls ~/job-apply-kit`.
2. Chrome: View > Developer > **Allow JavaScript from Apple Events** must be ticked. Test with
   `python3 applyq/chrome.py open test https://example.com` then `python3 applyq/chrome.py js test "document.title"`
   (expect `Example Domain`), then `close test`. If macOS asks to let the terminal / Hermes control Chrome, the user
   clicks OK. An error mentioning Apple Events = the Chrome setting is off.
3. Profile: `python3 applyq/candidate.py`. If `profile/profile.jsonc` is missing, follow `references/profile-setup.md`
   (interview the user, write the file, then `candidate.py` must print `profile OK`).
4. `python3 applyq/test_rules.py` must print `N/N passed`.

## The workflow

### 1. Build the queue
`python3 applyq/applyq.py build` fetches every un-applied Greenhouse/Ashby/Lever job's question list from the ATS's
public API (no browser) and answers each from the profile. ~1 s per job. Labels:
- `ready`: every required answer comes from profile / bank / default
- `needs-ok`: only `inferred` answers left (confirm once, then `bank` them)
- `essay`: needs essay drafts; `needs-you`: a required question nothing answers; `dead`: posting closed

`summary --links` shows the queue; `plan <id>` shows one job's every answer with its source.

### 2. Clear the blockers in one batch
`python3 applyq/applyq.py missing` ranks unanswered questions by how many jobs each would unlock. Ask the user the top
ones **together** (one message or one form with choices, not a drip of single questions). Save each answer:
- a fact that belongs in the profile (zip code, visa status, high school) -> edit `profile/profile.jsonc`
- a one-off question -> `python3 applyq/applyq.py bank "<exact label>" "<answer>"` (list answers: `'["A","B"]'`)
Then `build` again. Never bank an answer the user didn't give.

### 3. Fill one job at a time (rolling)
For the next job (`applyq.py next`, newest `ready` first):
1. `python3 applyq/chrome.py open <key> <apply_url>` (key = short company slug), wait ~5 s.
2. `python3 applyq/chrome.py fill <key> <job id>` (resume attaches automatically from `files.resume`). Read the
   output: `flags` (REQUIRED BLANK / UNHANDLED), and any `MISSING`, `NO_OPTION`, `ERR` field results.
3. `python3 applyq/chrome.py education <key> <job id>` when the form has an education block (Greenhouse
   School/Degree/Discipline, Ashby Education History). The API question list doesn't include it, so check the read-back.
4. `python3 applyq/chrome.py state <key> <job id>` and check **every** value against its live label, not only the
   flagged ones. Fix wrong values in the tab (`chrome.py js`, or `fill` with `--over over.json --no-resume`), then fix
   the rule in `applyq.py` and add a case to `test_rules.py` so the next build is right.
5. Greenhouse only: `python3 applyq/chrome.py sync <key> --check` must return `"n": 0` (see `references/greenhouse.md`:
   dropdowns can look filled while the form's store is empty).
6. List every required file upload (`file_inputs_left` on Greenhouse, `File` fields on Ashby). Transcript fields get
   `files.transcript` via `chrome.py attach <key> "<css selector>" <path>`; if there is none, ask.
7. Essays: draft each (required and optional) per `references/essay-drafting.md`, one at a time; type each approved
   answer with `fill --over` (field name -> text) or `chrome.py js`.
8. `python3 applyq/chrome.py scroll <key>`, then post ONE short line: "**<Company> - <Role> is ready**" plus only
   the non-obvious answers (salary typed, sponsorship answer, anything inferred). Move straight to the next job; the
   user submits each tab when they see its line.
9. Between fills, poll `chrome.py status <key>` on open tabs. `SUBMITTED` -> `python3 applyq/log_applied.py <job id>
   "<proof: confirmation page / email>"`, then `chrome.py close <key>`. `CODE` -> tell the user that tab is waiting for
   the emailed security code. A tab the user closed errors "Can't get tab id": just drop it.

When the user says "done", don't trust `status` alone: Ashby shows a success panel on the same URL, and a form still
showing a red "Missing entry for required field" banner was NOT submitted (tell them which field).

### 4. Jobs outside the queue
`data/jobs.json` also has Workday, iCIMS, SmartRecruiters and company-site postings. There is no API plan for those:
open the page in their Chrome, read the form, fill from the profile field by field, read it back, stop at Submit.
See `references/other-ats.md`. Log with `log_applied.py --manual "<Co>" "<Role>" "<link>" "<proof>"`.

## Which jobs to apply to
- Skip a posting only when it is built for master's/PhD grads or explicitly excludes the user's grad window
  (`applyq.py hide <id> "MS/PhD only"`). Everything else is the user's call, not yours: don't talk them out of stretch
  roles.
- `data/jobs.json` has a `sponsorship` column read from each posting. For a user who needs sponsorship, warn before
  filling any `No - ...` row; it is likely a rejection.
- US postings only unless the user says otherwise.

## Pitfalls that cost real time
- **Option regexes match negated options.** "able to relocate" matches "No - not able to relocate"; the first "Yes"
  is often "Yes, I live locally". The rules already drop `No...` options and prefer the relocate-yes when the job
  isn't in the user's city: keep that ordering when you edit rules (narrow phrasings above broad keywords).
- **A Boolean field must get yes/no, a free-text box never a bare Yes/No.** Either symptom is a rule bug.
- **Write rule regexes as raw strings with one backslash** (`r"\brace\b"`). A doubled `\\b` inside `r"..."` silently
  disables the rule.
- **After any RULES edit**: copy `applyq/queue.json` aside, rebuild, diff the (id, label) pairs you didn't mean to
  touch, and run `test_rules.py`.
- **Workday**: an "Errors Found" banner whose items are only `Error - Page Error - Error Code: VPS|...` means the
  session died, not that fields are wrong. Never press Enter in a Workday multi-select ("select every match").
  See `references/other-ats.md`.
- **Job-board "Apply externally" buttons** (Handshake) open a popup and record "applied" on click. Find the
  employer's own ATS posting instead, and withdraw the false "applied" state if you clicked to probe.
- **Submit buttons below the fold**: `scroll` then re-read positions in a separate step; never click anyway.
- **Pre-filled values lie too.** Lever's resume parser writes the last employer into "Current company" (the filler
  clears it), a saved profile can carry a stale salary. Read every value, not just the ones you set.

## Report (per job, short)
1. Posting (company, title, location, link) and that it was re-verified open.
2. What was filled, and the non-obvious answers with their source (profile / bank / inferred).
3. What still needs the user, and why (no profile value, legal/eligibility call, essay awaiting OK, upload).
4. Resume attached (file name), other uploads.
5. Hidden-field check result.
6. Confirmation that nothing was submitted, plus any tool errors.
