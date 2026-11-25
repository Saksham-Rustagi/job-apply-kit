# Ashby forms (jobs.ashbyhq.com/<org>/<uuid>/application)

## How the kit reads them
GraphQL `https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting` returns the form's sections and field
entries (`path`, `type`, `isRequired`, options). No `jobPosting` in the answer = closed. An id missing from the
public board JSON does not mean closed: unlisted postings keep a live form.

## Page structure
- React app with **no `<form>` element**. Questions are `div[data-field-path="<path>"]`; the label carries class
  `_required_` when required. The input id is the field path.
- Ashby's CSP blocks injected scripts, so everything runs in Chrome's isolated world (DOM only). That's fine:
  native value setter + `input`/`change` events update React state.
- **Yes/No** = a pair of `button[data-option=yes|no]`; `aria-pressed="true"` confirms. These are toggles: clicking a
  pressed button clears it. The filler only clicks when not already pressed.
- **ValueSelect / MultiValueSelect** render as radio / checkbox labels inside the entry. Some are searchable
  comboboxes ("How did you hear about us?"): `fill` reports `NO_OPTION ... combo=true`; use
  `python3 applyq/chrome.py combo <key> <field path> "Linked" "^LinkedIn$"` (types, waits for rows, clicks the match).
- **Location**: type exactly `location.autocomplete_query` (adding ", NJ" style suffixes returns no rows), wait, click
  the row matching `autocomplete_match`. If no row appears in a background tab, the typed text stays and Submit fails
  with "Missing entry for required field: Location": tell the user to pick it from the dropdown.
- **Education History** (`_systemfield_education_history`): `chrome.py education`. The school search can sit on
  "Loading..." for seconds; if nothing appears, the user picks the school. Leave "Still student?" unchecked so the
  end date stays visible.
- **Date fields** ("earliest start date", placeholder "Pick date..."): `fill` flags them UNHANDLED. Set
  `MM/DD/YYYY` with the value setter (`chrome.py js`), then tell the user to re-pick from the calendar if Submit
  rejects it.
- Demographic blocks: filled from the profile's `eeo` section; unmapped questions stay blank. Option inputs are
  named after their own label text, so query by `[data-field-path]`, never `input[name]`.
- Lazy rendering: some sections appear only after scrolling or after answering the question above. Re-run `state`
  after any answer that changes the form.
- Ashby's own "Autofill from resume" drop zone is a separate feature: leave it alone.

## Submit behaviour
Same URL, the form is replaced by "Application Success" / "successfully submitted". Some companies send no email at
all, so the success panel is the proof. A programmatic click can leave a Yes/No looking pressed while the app's model
is empty, which fails server-side with "Your form needs corrections - Missing entry for required field": re-click
that option and re-check `aria-pressed`.
