# Lever forms (jobs.lever.co/<company>/<uuid>/apply)

One plain-HTML page with jQuery, no account, no React store. `api.lever.co/v0/postings/<company>/<id>` returns 404
when the posting is closed.

- `applyq.py build` parses the apply page: standard fields by `name` (`name`, `email`, `phone`, `location`, `org`,
  `urls[LinkedIn]`, `urls[GitHub]`, `pronouns`, `eeo[...]`, `opportunityLocationId`, `consent[marketing]`, `comments`)
  and custom cards from each hidden `cards[<id>][baseTemplate]` JSON, filled as `cards[<id>][fieldN]`.
- **Resume first.** `fill` attaches it and waits for `input[name=resumeStorageId]`: Lever uploads and parses it, and
  its parser autofills fields (it writes your last employer into Current company, which `fill` clears when you are
  not employed). Later fix-ups: `fill ... --no-resume`.
- **Location box** (`input.location-input`): the search runs on keydown (500 ms debounce) and a suggestion is picked
  on mousedown on `.dropdown-location`. Never fire `blur` while the list is open: Lever's blur handler wipes the box.
  If no suggestion appears, `fill` types "City, ST" and hides the list.
- Option labels can contain a `<br>` (consent text + "Privacy policy"), so option text is matched with whitespace
  removed.
- "Which location are you applying for?" (`opportunityLocationId`) gets the posting's own city.
- The EEO disability signature date is the placeholder `__TODAY__` in plans, filled as MM/DD/YYYY at fill time.
- After `fill`, its `invalid` list shows fields failing HTML validation: each one needs an answer before Submit.
- Submit can show an hCaptcha: the user handles it. Confirmation = `/thanks` or "Application submitted"; the email
  comes from `no-reply@hire.lever.co` within a minute.
