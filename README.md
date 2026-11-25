# job-apply-kit

An AI agent ([Hermes](https://hermes-agent.nousresearch.com/docs/)) fills your job applications in your own Chrome,
from a profile you write once, reads every field back, drafts essays from your real background, and **stops at
Submit. You click Submit.** Plus a list of open new-grad 2027 US software postings.

**Start here: [GUIDE.md](GUIDE.md)** (install, setup, the workflow, troubleshooting).
**The job list: [data/JOBS.md](data/JOBS.md)** (or `data/jobs.xlsx`).

## Quick start (Mac)
```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash   # install Hermes
source ~/.zshrc && hermes setup                                       # pick a model
git clone https://github.com/Saksham-Rustagi/job-apply-kit.git ~/job-apply-kit
cd ~/job-apply-kit && bash install.sh                                 # checks + links the skill
```
Then in Chrome tick **View > Developer > Allow JavaScript from Apple Events**, start `hermes`, and say:
> Load the job-apply-kit skill and help me set up my profile. My resume is at ~/Documents/resume.pdf

## What's in here
| Path | What |
|---|---|
| `GUIDE.md` | The full guide |
| `skills/job-apply-kit/` | The Hermes skill: rules, workflow, per-ATS notes, essay style |
| `applyq/applyq.py` | Builds the queue: fetches each form's questions from the ATS's public API and answers them from your profile |
| `applyq/chrome.py` | Fills Greenhouse / Ashby / Lever forms in your Chrome over AppleScript (never clicks Submit) |
| `applyq/log_applied.py` | Logs submissions to `tracker/applications.csv` |
| `applyq/candidate.py` | Checks your profile |
| `applyq/test_rules.py` | Offline tests for the answer rules |
| `profile/*.example.*` | Templates for your profile and background file |
| `data/` | Open postings: `JOBS.md`, `jobs.xlsx`, `jobs.csv`, `jobs.json` |

Python 3.9+ standard library only (the Mac's built-in `python3` works). macOS + Google Chrome required for filling;
the queue and job list work anywhere.

Your profile, answers, essays and tracker are git-ignored and never leave your Mac.
