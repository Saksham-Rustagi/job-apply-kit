# Greenhouse forms (job-boards.greenhouse.io/<board>/jobs/<id>, or embedded on a company site)

## How the kit reads them
`boards-api.greenhouse.io/v1/boards/<token>/jobs/<id>?questions=true` returns every question with its field `name`,
`type`, required flag and options. Those names are the DOM ids: `#first_name`, `#last_name`, `#email`, `#phone`,
`#resume`, `#question_<id>`. Custom demographic questions have no name; their DOM id is the question id (numeric).
A `404` = the posting is closed.

Not in the API list (check the read-back): the **education block** (`school--0`, `degree--0`, `discipline--0`,
`start-month--0`, `end-month--0`, `start-year--0`, `end-year--0`) and sometimes `#candidate-location`.

## The store-sync trap ("looks filled, but Submit says required")
The form keeps every answer in ONE React state object, and each field's onChange writes `{...staleStore, [name]: v}`.
Setting many dropdowns in one synchronous run keeps only the LAST write, so the page displays answers that the form
will not submit. `chrome.py fill` and `education` call `gh_sync`, which pushes every displayed value into the store
in one update. Gate before saying "ready": `python3 applyq/chrome.py sync <key> --check` returns `"n": 0`.
After a failed submit the red "This field is required." messages stay until the next Submit even once the store is
fixed: tell the user to click Submit again rather than refilling.

## Widgets
- Dropdowns are react-select. Synthetic clicks/keys don't open them; the filler calls the widget's own
  `selectOption` in the page's main world (Greenhouse's CSP allows an injected `<script>`).
- **Phone country** `#country`: `United States +1`. An intl-tel-input listbox `#iti-0__country-listbox` is a hidden
  decoy; ignore it.
- **Location (City)** `#candidate-location` loads options as you type; the filler types
  `location.autocomplete_query` and picks the option starting with `location.autocomplete_match`. In a batch of fresh
  tabs it sometimes runs before options load and stays empty: re-run `fill --no-resume` for that tab.
- **Education** is an async paginated select: `education` calls its `loadOptions(search)` directly and picks the row
  matching every distinctive word of your school name (so "University of Texas at Austin" never becomes
  "Austin College"). Greenhouse spells schools its own way ("University of North Carolina - Chapel Hill"). Some boards
  have no exact major: it falls back to the first word ("Computer ...").
- `multi_value_multi_select` is either a react-select multi (office preference) or a checkbox group
  `question_<n>[]_<option id>`; the filler handles both.
- Standard EEO selects: `#gender`, `#hispanic_ethnicity`, `#race` (renders only after the Hispanic answer),
  `#veteran_status`, `#disability_status`, filled from the profile's `eeo` section.
- The attached resume doesn't always show in `.file-upload__filename`; look in the upload block text before
  re-attaching. Greenhouse removes a file input from the page once a file is attached, so the inputs left are the
  unfilled ones (`file_inputs_left` in `state`).

## Submit behaviour (the user's click)
Success redirects to `.../jobs/<id>/confirmation` with "Thank you for your interest..." and a confirmation email
follows from `no-reply@us.greenhouse-mail.io` within minutes. If reCAPTCHA scores the session as automated, the page
instead says a verification code was sent to the email, with 8 one-character boxes. **The user types that code.**
After many Greenhouse submits in one evening the code step starts appearing even in a real Chrome: space the
remaining Greenhouse submits a few minutes apart.

## Dead-looking boards
`?error=true` "Page not found" or "The job board you were viewing is no longer active" can mean a wrong board slug,
not a closed job: employers embed the same form on their own site (`<company>.com/...?gh_jid=<id>`). Check the API
(404 = closed) before calling it dead.
