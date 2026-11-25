# The guide: applying to jobs with Hermes

This kit is the setup I used for my new-grad search: an AI agent (Hermes) fills job applications in your own Chrome
from a profile you write once, reads every field back, drafts essays from your real background, and stops at the
Submit button. **You review each tab and click Submit yourself.** It's built for new-grad 2027 software roles in the
US, and the folder includes the open postings I found (`data/`).

What it is good at: Greenhouse, Ashby and Lever forms, which are most startup and mid-size tech postings. It reads
each form's questions from the company's public API before opening anything, so it knows which jobs it can finish
on its own and which need you. Workday and company-specific sites work too, but slower: the agent fills them field
by field with you watching.

What it never does: click Submit, type verification codes or passwords, make up an answer, or send anything.

---

## Contents
1. [Install Hermes](#1-install-hermes)
2. [Pick a model](#2-pick-a-model)
3. [Get the kit](#3-get-the-kit)
4. [Write your profile](#4-write-your-profile)
5. [The daily workflow](#5-the-daily-workflow)
6. [Essays and short answers](#6-essays-and-short-answers)
7. [The job list](#7-the-job-list)
8. [Gotchas by ATS](#8-gotchas-by-ats)
9. [Troubleshooting](#9-troubleshooting)
10. [Privacy and staying safe](#10-privacy-and-staying-safe)

---

## 1. Install Hermes

Hermes is an open-source AI agent from Nous Research that runs on your Mac. Docs: https://hermes-agent.nousresearch.com/docs/

Open **Terminal** (Cmd+Space, type Terminal) and paste:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source ~/.zshrc
hermes --version
```

The installer sets up its own Python and everything else it needs. If `hermes --version` says "command not found",
close Terminal, open a new one, and try again.

You can chat with Hermes in Terminal (`hermes`) or in the desktop app (`hermes desktop`, or download the app from the
Hermes website). Both use the same setup, so pick whichever you like. I use the desktop app.

**Keep Hermes's commands running on your Mac.** The kit drives your Chrome, so the agent's terminal has to run on
your Mac, not in a sandbox. That's the default. Check it:

```bash
hermes config get terminal.backend      # should say local (or nothing)
# if it says docker or anything else:
hermes config set terminal.backend local
```

## 2. Pick a model

Hermes needs an AI model to think with. Run:

```bash
hermes setup
```

It asks one question, "How do you want to power Hermes?". Two good answers for this:

| Option | What it is | Good if |
|---|---|---|
| **Anthropic API key** | Pay per use for Claude models. Make a key at https://console.anthropic.com (add a payment method and some credit first), then pick "Use my own API key" in `hermes setup` and choose Anthropic. | You want the strongest model and only pay for what you use. Filling forms and drafting essays is a lot of reading, so usage adds up over a long session; set a monthly spend limit in the Anthropic console. |
| **Nous Portal subscription** | One subscription with many models plus web search and other tools built in. Pick "Sign in to Nous Portal" (or run `hermes setup --portal`). | You want one flat bill and no API-key management. |

Use a strong model (a recent Claude Opus or Sonnet, or a comparable frontier model). Small or free models make more
mistakes reading forms, and mistakes on applications are what you're trying to avoid.

Test it: run `hermes`, say hi, make sure it answers. `hermes doctor` checks the install if something is off.

## 3. Get the kit

I'll invite you to the private GitHub repo. Accept the invite, then:

```bash
cd ~
git clone https://github.com/Saksham-Rustagi/job-apply-kit.git
cd ~/job-apply-kit
bash install.sh
```

(If `git` asks you to install developer tools, say yes, then run the clone again. If the clone asks for a password,
the easiest fix is installing the GitHub CLI and running `gh auth login`, or download the repo as a ZIP from GitHub
and unzip it to `~/job-apply-kit`.)

`install.sh` checks Python, creates your private profile files, runs the self-tests, links the skill into Hermes, and
checks that Chrome is installed. Re-run it any time; it's safe.

**One Chrome setting (required):** in Chrome's menu bar, **View > Developer > Allow JavaScript from Apple Events**,
and make sure it's ticked. The first time the agent touches Chrome, macOS asks whether Terminal (or Hermes) may
control Google Chrome: click **OK**. If you clicked "Don't Allow" by accident: System Settings > Privacy & Security >
Automation, and turn Google Chrome on for Terminal / Hermes.

Updating later: `cd ~/job-apply-kit && git pull`. Your profile and tracker are git-ignored, so pulling never touches
them.

## 4. Write your profile

Everything the bot types comes from two files that only live on your Mac:

- `profile/profile.jsonc`: facts and standing answers (name, school, work authorization, relocation, EEO, salary rule,
  consents, resume path). Template with comments: `profile/profile.example.jsonc`.
- `profile/reference.txt`: your background in your own words (jobs, projects, awards), used for essays. Template:
  `profile/reference.example.txt`.

Easiest way: start Hermes and say

> Load the job-apply-kit skill and help me set up my profile. My resume is at ~/Documents/resume.pdf

It reads your resume, fills what it can, then asks the rest **in one batch**: work authorization and sponsorship,
relocation and on-site, start date, salary fallback, EEO answers (each can be "decline"), consents. Answer honestly:
these answers decide whether applications get screened out, and the bot will never guess them.

Or edit the file yourself in any text editor, then check it:

```bash
cd ~/job-apply-kit
python3 applyq/candidate.py        # prints "profile OK" or exactly what's wrong
```

Things worth knowing about the profile:
- **Blank means "ask me."** Anything left `""` turns into a question for you instead of a guess.
- **Salary**: if a posting publishes a range, forms get that range. If not, and a form forces a number, it uses
  `salary_default` (or the lowest dropdown band containing it). Set `0` to be asked every time.
- **Relocation and on-site**: if the job is in your own city it picks "Yes, I live locally"; otherwise
  "Yes, I'd relocate" (when you said you would). It never picks "Yes, I live within commuting distance" for a city
  you don't live in.
- **Sponsorship** questions are answered from `needs_sponsorship_now` / `needs_sponsorship_future`, reading whether
  the question says "now", "currently" or "in the future".
- **EEO** answers are voluntary. "decline" picks the "I don't wish to answer" option.
- `esign_ok: true` lets it type your name into "type your name to sign" attestation boxes. Arbitration agreements are
  always left for you.

## 5. The daily workflow

This is how I ran it. You talk to Hermes in plain English; it runs the commands. The commands are listed so you know
what's happening (and can run them yourself).

### Step 1: build the queue
> Build my application queue.

```bash
python3 applyq/applyq.py build
python3 applyq/applyq.py summary --links
```

For every Greenhouse / Ashby / Lever job in `data/jobs.json` you haven't applied to, it downloads the form's
questions from the company's public API (no browser, about a second per job) and answers each from your profile.
Each job gets a label:

| Label | Meaning |
|---|---|
| `ready` | Every required question has an answer from your profile or your approved answers |
| `needs-ok` | Only "inferred" answers left: reasonable guesses that need your one-time OK |
| `essay` | Needs essay drafts |
| `needs-you` | A required question nothing answers yet |
| `dead` | The posting closed |

`python3 applyq/applyq.py plan <job id>` shows every answer for one job and where it came from
(`profile`, `bank`, `default`, `inferred`, `essay`, `you`).

### Step 2: answer the blockers once
> What questions are blocking the most jobs?

```bash
python3 applyq/applyq.py missing
```

This ranks unanswered questions by how many jobs each would unlock ("12 jobs ask about your high school"). Hermes
asks you the top ones together. Answers either go into your profile (facts) or into the answers bank
(`profile/answers_bank.json`) for one-off questions:

```bash
python3 applyq/applyq.py bank "have you previously applied to amazon or any amazon subsidiary?" "No"
```

Then it rebuilds, and more jobs turn `ready`. After a few rounds most new jobs come out `ready` on their own.

### Step 3: the rolling fill (the part that saves hours)
> Start filling my ready jobs in Chrome, one at a time. I'll submit each tab.

For each job, Hermes:
1. Re-checks the posting is still open (they close mid-day).
2. Opens it in a new tab in **your** Chrome (`chrome.py open`) and fills it from the plan (`chrome.py fill`),
   including the resume upload, phone country, location autocomplete, EEO and education.
3. Reads every field back (`chrome.py state`) and fixes anything wrong. On Greenhouse it also checks that the form's
   hidden store matches what's displayed (`chrome.py sync --check`), because Greenhouse dropdowns can look filled
   and still fail on Submit.
4. Scrolls to Submit and posts one line: **"Affirm - Software Engineer I is ready"**, plus anything non-obvious
   (the salary it typed, how it answered sponsorship).
5. Moves on to the next job without waiting for you.

You glance over the tab, fix anything you want, and click **Submit**. Hermes notices the confirmation page, logs the
application to `tracker/applications.csv`, and closes the tab. You never have to tell it "done".

Why your own Chrome: application sites run bot checks. A fresh automation browser gets flagged and Greenhouse
answers Submit with "we emailed you a security code". In your normal Chrome you're scored as a person. If a code
email still shows up ("Security code for your application to X"), type it in yourself; the bot never touches codes.
That happens more after many Greenhouse submits in one evening, so space those out a few minutes.

### Step 4: everything else
`data/jobs.json` also has Workday, iCIMS and company-site postings. For those:
> Fill the Capital One application in Chrome. I'll watch.

It fills field by field from your profile and stops at Submit, same rules. Workday needs an account per company;
you type the password. Log those with:

```bash
python3 applyq/log_applied.py --manual "Capital One" "Software Engineer" "<link>" "confirmation email"
```

### Useful things to say
- "What's ready?" / "What's next?" (`applyq.py next`)
- "Skip this one, it's MS-only." (`applyq.py hide <id> "MS/PhD only"`)
- "Show me the plan for the Stripe job before you fill it."
- "Did my last three submissions go through?" (it reads the tabs and your confirmation pages)
- "Show my tracker." (`log_applied.py --list`)

## 6. Essays and short answers

When a form has a free-response question ("Why us?", "Describe your most complex project"), Hermes:
1. Reads your `reference.txt` and resume, the job description, and your GitHub.
2. Drafts **one answer at a time** in chat: the question, the draft, and short notes on where each claim came from
   and anything it inferred that you should check.
3. Types it into the form only after you say OK.

House style (built in, because generic AI prose reads badly to recruiters): plain sentences, no em dashes, no
"delve" or "passionate about leveraging", about 150-220 words unless the form says otherwise, one concrete detail per
paragraph, and **only numbers you can prove** (test counts, users, contest ranks with their scope). It won't invent
a motivation or experience; if a question assumes something you haven't done, the draft says so and uses your closest
real work.

The better your `reference.txt`, the better the drafts. Paste old essays you liked into its last section and it will
reuse their phrasing.

## 7. The job list

`data/` holds the open postings I'd collected, re-checked as of the date at the top of `data/JOBS.md`:

| File | What |
|---|---|
| `data/JOBS.md` | Readable on GitHub: every posting, newest first, with pay, sponsorship and apply link |
| `data/jobs.xlsx` / `data/jobs.csv` | The same, for Excel / Google Sheets (filter and sort) |
| `data/jobs.json` | The same, in the format the queue reads |

Columns worth knowing:
- **Pay**: the employer's published range. Blank means they didn't publish one (most Workday postings don't); it is
  never an estimate.
- **Sponsorship**: read from each posting's own text: `Yes - posting says it sponsors`, `Not stated`, `Unclear`,
  `No - posting says no sponsorship`, `No - US citizen / green card / clearance only`. If you need sponsorship, skip
  or deprioritize the `No` rows.
- **Verified open**: when the link was last checked and how. Postings close every day, so the queue re-checks
  Greenhouse/Ashby/Lever jobs when it builds; for others, the page itself is the truth.

Want more jobs? Add rows to `data/jobs.json` in the same format (the `id` must be `greenhouse-<job id>`,
`ashby-<uuid>` or `lever-<uuid>` for the queue to fill it), or ask Hermes to add a posting you found.

## 8. Gotchas by ATS

- **Greenhouse**: dropdowns can display an answer the form won't submit (the sync check catches this). If Submit
  shows red "This field is required" after a fix, click Submit again: the old messages stick until the next try.
  Security-code emails are yours to type.
- **Ashby**: the location box needs a suggestion picked from its dropdown; if the bot couldn't (background tab), it
  tells you to pick it. Success shows on the same page ("Application Success"), sometimes with no email.
- **Lever**: may show an hCaptcha on Submit (you solve it). Its resume parser fills fields on its own; the bot
  re-checks them.
- **Workday**: one account per company. "Errors Found... Page Error" means your session expired: sign in again and
  restart the application; nothing typed after the expiry was saved. Never press Enter in Workday's multi-select
  boxes (it selects everything).
- **Job boards** (Handshake, LinkedIn): "Apply externally" buttons mark the job "applied" on the board when clicked.
  Apply on the company's own site instead.
- **Application caps**: some companies limit how many roles you can apply to (Google about 3 per 30 days, TikTok 2,
  Amazon about 10). Pick your favorites first.

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `ERR Chrome blocks AppleScript JS` | Chrome menu: View > Developer > Allow JavaScript from Apple Events |
| `Not authorized to send Apple events to Google Chrome` | System Settings > Privacy & Security > Automation: allow Chrome for Terminal / Hermes |
| Hermes says it can't find `osascript`, or commands run in Linux | `hermes config set terminal.backend local`, then restart Hermes |
| Hermes doesn't know the skill | `bash install.sh` again; or say "load the job-apply-kit skill"; check `hermes skills list` |
| `profile.jsonc is not valid JSON (line N)` | Usually a missing comma, a comma before `}`, or a `//` comment after a value on the same line |
| A job is `needs-you` for a question you think is obvious | `applyq.py plan <id>` shows the exact label; answer it once with `applyq.py bank` |
| The bot picked a wrong option | Fix it in the tab, then tell Hermes: it fixes the rule in `applyq.py` and adds a test (`python3 applyq/test_rules.py`) |
| `command not found: hermes` | New Terminal window, or `~/.local/bin/hermes` |

## 10. Privacy and staying safe

- Your profile, answers, essays and tracker are in `.gitignore`: they stay on your Mac. Don't `git add -f` them, and
  don't push changes back to the shared repo unless you mean to share code.
- Hermes can read your files and use your Chrome. Only point it at application sites and your own documents.
- Every answer on an application is a statement you're making. Review the tab before you click Submit, especially
  work authorization, sponsorship, and anything labelled "inferred".
- The bot never clicks Submit, never types codes or passwords, and never sends email. If it ever looks like it's
  about to, stop it (Ctrl+C in Terminal, or the stop button in the app).
