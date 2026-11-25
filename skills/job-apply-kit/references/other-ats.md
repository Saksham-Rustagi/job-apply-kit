# Other ATSs: Workday, iCIMS, Workable, SmartRecruiters, company sites, job boards

There is no API plan for these. Open the page in the user's Chrome (`chrome.py open`), read the form
(`chrome.py js <key> "<expression>"`), fill field by field from the profile, read every value back, stop at Submit.
The standing rules in SKILL.md apply unchanged.

## Workday (`<company>.wd<N>.myworkdayjobs.com`)
- Needs an account per company. Account creation is a committing action: ask first, and let the user type the
  password (never invent or store one). Use the email from the profile.
- "Autofill with Resume" or "Use My Last Application" is the fastest start; then audit every pre-filled value.
- **Prompt fields** (Company, Location, School, Degree, Field of Study, Skills) store a hidden ID only when a
  suggestion is *picked*. Setting the text alone leaves the ID blank. Type with real keystrokes, wait for the list,
  click the row.
- **Never press Enter in a multi-select prompt** (Skills, How did you hear): Enter selects every match. Remove extra
  chips one at a time via the x on each chip.
- **"Errors Found" with only `Error - Page Error - Error Code: VPS|<uuid>`** = the application session died (often
  signed out mid-flow while the page still renders). Re-typing fields won't help; sign in again and restart from
  `/apply`. Nothing typed into the dead session was saved. "Something went wrong" mid-fill usually recovers on reload.
- `How Did You Hear About Us?` is required and first; if its list spins forever, reload the apply page.
- Liveness check without a browser: `https://<host>/wday/cxs/<tenant>/<site>/job/<jobPath>` returns the posting JSON
  while it exists.

## Workable / iCIMS / SmartRecruiters
- These often ask for data the profile may not hold: supervisor name and title, clearance history, high school,
  signature attestations. Fill what the profile supports, then ask for the missing items by name. Never invent a
  supervisor. Signature boxes get the user's name only if `consents.esign_ok` is true.
- iCIMS "The requested job could not be found" = closed.

## Job boards (Handshake, LinkedIn Easy Apply, Simplify, etc.)
- "Apply externally" buttons open a new window and record "applied" on the board when clicked. Don't retry the
  popup: search for the employer's own posting (company + role + "careers") and apply there. If you clicked only to
  see where it goes, click "Withdraw external apply" to undo the false applied state.
- Cloudflare "Just a moment" walls block automation browsers; the user's real Chrome usually passes.

## Autofill extensions (Simplify etc.), if the user has one
- Treat every value an extension writes as unverified: they mis-map custom questions (a surname into "country",
  a first name into "notice period") and use their own defaults for "how did you hear" and phone type.
- Extensions often leave the resume empty or attach a stale stored copy: attach the profile's PDF.
- Read displayed values, not `input.value`: react-select answers live in `.select__single-value`.
