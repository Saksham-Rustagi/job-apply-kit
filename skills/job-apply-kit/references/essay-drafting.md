# Drafting essays and short answers

Applies to every free-response box: "why us", "describe a project", "anything else", cover letters, hackathon and
fellowship applications, and referral / outreach emails.

## Before writing anything
1. **Read the sources in full**: `files.reference` (the long background file) and the resume PDF (`files.resume`).
   Ground every claim in them. A plausible paragraph that cites no real experience reads as fabricated to an
   employer, and the user has to catch it.
2. **Pin the exact posting** (title + level + city) and read its job description. Role, product and "why" answers all
   hinge on the team. Fetch the JD without a browser:
   - Greenhouse: `curl -s 'https://boards-api.greenhouse.io/v1/boards/<token>/jobs/<id>'` -> `content` (escaped HTML)
   - Ashby: `curl -s https://api.ashbyhq.com/posting-api/job-board/<org>` -> `jobs[].descriptionHtml`
   - Lever: `curl -s 'https://api.lever.co/v0/postings/<company>?mode=json'` -> `descriptionPlain`, `lists[]`
3. **Check the user's GitHub** (`contact.github`) for recent projects the resume omits: READMEs, `docs/`, commit
   messages. Pull concrete facts from there, and suggest adding them to the reference file.
4. If the employer writes "please don't use AI" on a question, draft nothing for it: leave that box to the user.

## Writing rules (apply to the first draft, don't wait to be asked)
- **Plain, direct sentences. No em dashes. No AI-sounding phrasing** ("delve", "I'd be happy to", "that being said",
  stacked qualifiers, triplets of adjectives, "passionate about leveraging").
- **Short by default**: about 150-220 words when the form sets no limit; one short paragraph per sub-question
  ("what did you build / hardest part / how did you know it worked"), one concrete technical detail each. Extra
  evidence goes in your notes to the user, not in the answer.
- **Character limits**: measure the draft with `len()` in code, report the count, and offer a shorter fallback.
- **Only metrics the user can prove** (countable facts: test counts, users, contest ranks with their scope). Cut
  latency / uptime / cost-savings claims unless the user confirms they measured them.
- **Never invent a motivation, a metric, a framework, or experience.** If a question assumes experience the user
  lacks ("a robotics simulation you built"), say so plainly and use the closest real work.
- **Name what you inferred.** After the draft, list any framing that is not in the reference file as a claim for
  the user to check.

## Picking what to write about
- Match the project to what this company visibly cares about (read their careers copy and the JD), not to what
  sounds most impressive in isolation. Shipped work at a company usually beats a side project for role-fit questions;
  side projects belong in "personal project" questions.
- "Solved a pain point in your own life" wants a project where the user was also the user.
- A question that requires a specific link anchors the answer to what that link shows.
- Category / "area of specialization" pickers: choose the option that honestly labels the work. Building on an LLM
  API is backend engineering, not "Machine Learning".
- "Share a link to work you're proud of": GitHub, plus one sentence if the best work is in private company repos.
- Before linking a live site the user built, check it still shows their work (companies redesign). Use a Wayback
  Machine snapshot from their time there if not, and say so.

## Company-fit ("why us") answers
- Mostly about **them**, with at most one line about the user. Name specific things: their published work, the
  role's concrete problems from the JD, how the user has used the product.
- **Don't explain the company's business back to it** ("billing is the part of healthcare providers hate most").
  Lead with what the user wants to build and real work, then one concrete draw (team, stage, stack, customers).
- Questions about what the user personally reads, thinks, or does by hand: ask the user; never propose an answer.
- "What else should we know?": the kind of person they are (a trait, with one project as evidence), tied to what
  this company needs. Not a project list. Recommend leaving "anything else" blank when nothing beats the required
  answers.
- Weakness questions: real, low-risk weaknesses the user can defend in an interview; ask them to confirm.

## Reviewing with the user
- **One draft per message**: "N of M", the exact question, the draft as a blockquote, 2-3 short source notes. Wait
  for "ok" or edits before the next.
- Revision requests add, they don't replace: fold the new item in next to what was there.
- Before showing the next draft, re-check it against every lesson from earlier edits in the same session.
- Save approved answers to `profile/essays.json` (key = `<company>_<question>`), and reuse their phrasing for
  similar questions instead of starting over.
- Type an approved answer into the form only after the OK: `chrome.py fill <key> <job id> --over over.json
  --no-resume` where `over.json` maps the field name (from `applyq.py plan`) to the text.

## Cover letters
Two gates: a request decides whether one gets written; an explicit yes decides whether it gets attached. "Optional"
is never a reason to write one unasked, and a written letter stays unattached until the user says so.

## Referral / outreach emails
Pin the posting (title + req number in the subject and first line), ground the intro in the reference file,
150-200 words, plain sentences, signature with phone + email. Draft only: the user sends it.
