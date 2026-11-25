# Setting up a new user's profile

Goal: `profile/profile.jsonc` filled and passing `python3 applyq/candidate.py`, plus `profile/reference.txt` with
enough real detail for essays. Takes ~15 minutes with the user.

## 1. Start from their documents, not from questions
1. Ask for the resume PDF path (e.g. `~/Documents/resume.pdf`). Read it (`pdftotext` if installed, else open it as
   `file://` in Chrome and read the text). Fill name, contact, education, work, skills from it.
2. `cp profile/profile.example.jsonc profile/profile.jsonc` and write what the resume settles.
3. Copy `profile/reference.example.txt` to `profile/reference.txt` and paste the resume text into it as a start.

## 2. Ask the rest in ONE batch
Group the questions the resume can't answer and ask them together (a form with choices if the interface has one).
Never guess these; they decide whether applications get screened out.

- Work authorization: authorized to work in the US? need sponsorship now? in the future? visa status in their words?
  US citizen / permanent resident? any other countries they can work in?
- Clearance: ever held one? willing to get one?
- Relocation, on-site 5 days, travel: yes/no each. Office preferences in order (or "any").
- Earliest start date. Salary number to use when a posting publishes no range and the form forces one (0 = always
  ask).
- "How did you hear about us" default (LinkedIn is common).
- Location autocomplete: their city as it should be typed, and the suggestion text to click
  (e.g. "Durham" / "Durham, North Carolina").
- School as typed into search boxes, and the GPA they want reported (or blank).
- Consents: SMS updates, privacy acknowledgements, future roles, resume sharing with partners, interview recording,
  and whether you may type their name into e-signature attestations.
- EEO (voluntary): for each of gender, Hispanic/Latino, race, veteran, disability, transgender, orientation, age band:
  their answer or "decline". Make "decline" an easy choice; never push.
- Past employers (all of them, including internships) and total years of experience by resume dates.
- High school and graduation year, ACT/SAT (or blank), languages spoken.

## 3. Write, check, test
1. Write every answer into `profile.jsonc` exactly as given. Unknown stays `""`.
2. `python3 applyq/candidate.py` until it prints `profile OK`. Common JSON errors: a missing comma, a trailing comma
   before `}` or `]`, a comment after a value on the same line.
3. `python3 applyq/test_rules.py` (should pass regardless of profile; it uses fictional people).
4. `python3 applyq/applyq.py build`, then `summary` and `missing`. Walk the user through the top of `missing` in one
   batch, save answers (profile edits or `applyq.py bank`), rebuild.
5. Show them `plan <id>` for one `ready` job so they see exactly what will be typed, and get their OK on the
   approach before the first fill.

## 4. The reference file (for essays)
Ask for, in their words: each job/internship (what they built, their part, stack, team size, anything countable),
2-4 projects with links, awards with year and scope (site vs region vs national), activities and leadership, and
what kind of work they want. Countable facts only; if they aren't sure a number is right, leave it out.
