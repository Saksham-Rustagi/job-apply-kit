#!/usr/bin/env python3
"""Fill Greenhouse / Ashby / Lever application forms in YOUR real Google Chrome, over AppleScript (macOS only).

Why your real Chrome: ATS bot checks (Greenhouse reCAPTCHA) flag fresh automation browsers and answer Submit with an
email "security code". In your own signed-in Chrome you are scored as a person, and YOU click Submit.

One-time setup: Chrome menu View > Developer > Allow JavaScript from Apple Events (tick it). The first command will
make macOS ask "Terminal/Hermes wants to control Google Chrome": click OK.

CLI (prints JSON):
  python3 applyq/chrome.py open <key> <url>          open a new tab in the front Chrome window, remember it as <key>
  python3 applyq/chrome.py find <key> <url-substring> adopt a tab you opened yourself
  python3 applyq/chrome.py fill <key> <job id> [--over answers.json] [--no-resume]
                                                     fill the tab from plans/<job id>.json (ATS picked from the plan)
  python3 applyq/chrome.py education <key> <job id>  fill the education block (Greenhouse / Ashby) when the read-back shows it empty
  python3 applyq/chrome.py state <key> <job id>      read back every displayed value (do this after every fill)
  python3 applyq/chrome.py sync <key> [--check]      Greenhouse only: push displayed values into the form store (--check = n must be 0)
  python3 applyq/chrome.py attach <key> <css selector> <pdf path>   attach any PDF (transcript, cover letter)
  python3 applyq/chrome.py combo <key> <ashby field path> "<text>" "<regex>"  Ashby searchable dropdown (e.g. "Linked" "^LinkedIn$")
  python3 applyq/chrome.py status <key>              SUBMITTED / CODE (security-code step) / open
  python3 applyq/chrome.py scroll <key>              scroll the Submit button into view (never clicks it)
  python3 applyq/chrome.py js <key> "<js expression>"  run JS in the tab (isolated world, DOM only) and print the result
  python3 applyq/chrome.py close <key>
  python3 applyq/chrome.py tabs

NOTHING here clicks Submit. Python 3.9+, standard library only.
"""
import base64 as _b64
import json as _json
import os as _os
import re as _re
import subprocess as _sp
import sys as _sys
import tempfile as _tf
import time as _time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KIT = ROOT.parent
_sys.path.insert(0, str(ROOT))
if __name__ == '__main__' and (len(_sys.argv) < 2 or _sys.argv[1] in ('-h', '--help', 'help')):
    print(__doc__)
    raise SystemExit(0)
import candidate  # noqa: E402
import applyq  # noqa: E402

_TABS = str(KIT / "state" / "chrome_tabs.json")
PLANS = str(ROOT / "plans")
P = candidate.Profile(candidate.load())
applyq.P = P
RESUME = P.path("resume")


def _pg(path, default=""):
    v = P.get(path)
    return default if v in (None, "") else v


# ---------- tab control ----------
def chrome_osa(script, timeout=45):
    try:
        r = _sp.run(['osascript', '-e', script], capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip()
    except _sp.TimeoutExpired:
        return '', 'TIMEOUT'


def _tabs():
    return _json.load(open(_TABS)) if _os.path.exists(_TABS) else {}


def _save_tabs(t):
    _os.makedirs(_os.path.dirname(_TABS), exist_ok=True)
    _json.dump(t, open(_TABS, 'w'), indent=1)


def chrome_open(key, url):
    out, err = chrome_osa('tell application "Google Chrome"\n if (count of windows) = 0 then make new window\n'
                          ' set w to front window\n set t to make new tab at end of tabs of w '
                          'with properties {URL:"%s"}\n return (id of w as text) & "," & (id of t as text)\nend tell' % url)
    if out:
        t = _tabs()
        t[key] = out
        _save_tabs(t)
    return out or err


def chrome_find(key, needle):
    """Adopt a tab you opened yourself: first tab whose URL contains `needle`."""
    out, err = chrome_osa('tell application "Google Chrome"\n repeat with w in windows\n  repeat with t in tabs of w\n'
                          '   if URL of t contains "%s" then return (id of w as text) & "," & (id of t as text)\n'
                          '  end repeat\n end repeat\n return ""\nend tell' % needle.replace('"', ''))
    if out:
        t = _tabs()
        t[key] = out
        _save_tabs(t)
    return out or err or 'not found'


def _tab(key):
    t = _tabs()
    if key not in t:
        raise SystemExit("unknown tab key %r: use `open` or `find` first (known: %s)" % (key, ", ".join(t) or "none"))
    return t[key].split(',')


def close_tab(key):
    """Close a tab and forget it. A tab you already closed errors with "Can't get tab id": the key is dropped."""
    w, t = _tab(key)
    out, err = chrome_osa('tell application "Google Chrome" to close (tab id %s of window id %s)' % (t, w))
    tabs = _tabs()
    tabs.pop(key, None)
    _save_tabs(tabs)
    return err or 'closed'


def cjs(key, code, timeout=45):
    """JS in the tab's ISOLATED world (DOM only; no page globals, no React internals). Returns stdout."""
    w, t = _tab(key)
    fd, path = _tf.mkstemp(suffix='.js')
    _os.write(fd, code.encode('utf-8'))
    _os.close(fd)
    script = ('set js to read POSIX file "%s" as \u00abclass utf8\u00bb\n'
              'tell application "Google Chrome" to execute tab id %s of window id %s javascript js' % (path, t, w))
    try:
        r = _sp.run(['osascript', '-e', script], capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0 and 'Allow JavaScript from Apple Events' in r.stderr:
            return 'ERR Chrome blocks AppleScript JS: tick View > Developer > Allow JavaScript from Apple Events'
        return r.stdout.strip() if r.returncode == 0 else 'ERR ' + r.stderr.strip()
    except _sp.TimeoutExpired:
        return 'ERR TIMEOUT'
    finally:
        _os.remove(path)


def tab_status(key):
    """Greenhouse /confirmation, Ashby success panel, Lever /thanks. Confirm with the confirmation email too."""
    return cjs(key, "(() => { const t=document.body.innerText; const u=location.href; return (u.includes('/confirmation') || "
                    "/jobs\\.lever\\.co\\/.+\\/thanks/.test(u) || /Application Success|successfully submitted|Thank you for applying|"
                    "Application submitted|Thanks for applying/i.test(t)) ? 'SUBMITTED' : "
                    "(/security code|verification code/i.test(t) ? 'CODE' : 'open'); })()")


def scroll_submit(key):
    return cjs(key, "(() => { const b=[...document.querySelectorAll('button')].find(b=>/submit/i.test(b.textContent)); "
                    "if(!b) return 'no submit'; b.scrollIntoView({block:'center'}); return 'ok'; })()")


# ---------- main world (Greenhouse; its CSP allows an injected <script>) ----------
MAIN_PRELUDE = r"""
const $=(s)=>document.querySelector(s); const $$=(s)=>[...document.querySelectorAll(s)];
const setVal=(e,v)=>{ if(typeof e==='string') e=$(e); if(!e) throw new Error('missing field'); const proto=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype; e.focus(); Object.getOwnPropertyDescriptor(proto,'value').set.call(e,v); e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true})); e.dispatchEvent(new Event('blur',{bubbles:true})); return e.value; };
const rsel=(input, re)=>{ const fk=Object.keys(input).find(k=>k.startsWith('__reactFiber')); let f=input[fk],n=0; while(f&&n<80){ if(f.stateNode&&typeof f.stateNode.selectOption==='function') break; f=f.return; n++; } if(!f) throw new Error('no react-select'); const inst=f.stateNode; const flat=[]; (inst.props.options||[]).forEach(o=>o.options?o.options.forEach(x=>flat.push(x)):flat.push(o)); const lab=o=>String(o.label??o.name??o.value); const o=flat.find(o=>re.test(lab(o))); if(!o) throw new Error('no option '+re+' in '+flat.slice(0,8).map(lab).join('/')); inst.selectOption(o); return lab(o); };
const rselAny=(input, res)=>{ for(const re of res){ try{ return rsel(input, re); }catch(e){} } throw new Error('no option for '+res.join(' | ')); };
"""


def cmain(key, body, timeout=45):
    """Run `body` (JS statements ending in `return X;`) in the page MAIN world; returns {'ok':..,'r':X} via a DOM attribute."""
    wrapped = ("(()=>{try{" + MAIN_PRELUDE + "const __r=(()=>{" + body + "})(); document.documentElement.dataset.probe="
               "JSON.stringify({ok:true,r:__r===undefined?null:__r});}catch(e){document.documentElement.dataset.probe="
               "JSON.stringify({ok:false,err:String(e&&e.message||e)});}})();")
    out = cjs(key, "(() => { delete document.documentElement.dataset.probe; const s=document.createElement('script'); s.textContent="
                   + _json.dumps(wrapped) + "; document.documentElement.appendChild(s); s.remove(); "
                   "return document.documentElement.dataset.probe || 'NO_PROBE'; })()", timeout)
    try:
        return _json.loads(out)
    except Exception:
        return {'ok': False, 'raw': out}   # 'NO_PROBE' = CSP blocked the script (Ashby): use iso() instead


def _stage_pdf(key, path):
    b = _b64.b64encode(open(path, 'rb').read()).decode()
    cjs(key, "document.documentElement.dataset.rb=''; 1")
    for i in range(0, len(b), 60000):   # both worlds share the DOM, not window
        cjs(key, "document.documentElement.dataset.rb += " + _json.dumps(b[i:i + 60000]) + "; 1")


# The File is named after basename(path), so a transcript never shows up under the resume's name.
_ATTACH_JS = ("const s=document.documentElement.dataset.rb; const bin=atob(s); const u=new Uint8Array(bin.length); "
              "for(let i=0;i<bin.length;i++) u[i]=bin.charCodeAt(i); const f=new File([u],%s,"
              "{type:'application/pdf',lastModified:Date.now()}); const inp=document.querySelector(%s); if(!inp) throw new Error('no file input'); "
              "const dt=new DataTransfer(); dt.items.add(f); inp.files=dt.files; inp.dispatchEvent(new Event('input',{bubbles:true})); "
              "inp.dispatchEvent(new Event('change',{bubbles:true})); delete document.documentElement.dataset.rb; return inp.files.length+':'+f.size;")


def attach_resume(key, selector='#resume', path=None):
    path = path or RESUME
    if not path or not _os.path.exists(path):
        return {'ok': False, 'err': 'resume not found: %r (files.resume in your profile)' % path}
    _stage_pdf(key, path)
    return cmain(key, _ATTACH_JS % (_json.dumps(_os.path.basename(path)), _json.dumps(selector)))


# ---------- isolated world (Ashby; also fine for plain text inputs anywhere) ----------
ISO_PRE = r"""const $=(s)=>document.querySelector(s); const setVal=(sel,v)=>{const e=typeof sel==='string'?document.getElementById(sel)||$(sel):sel; if(!e) return 'missing:'+sel; const proto=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype; e.focus(); Object.getOwnPropertyDescriptor(proto,'value').set.call(e,v); e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true})); e.blur(); return e.value;};"""


def iso(key, body):
    out = cjs(key, "(() => { try { " + ISO_PRE + " const r=(()=>{" + body + "})(); return JSON.stringify({ok:true,r}); } "
                   "catch(e) { return JSON.stringify({ok:false,err:String(e.message||e)}); } })()")
    try:
        return _json.loads(out)
    except Exception:
        return {'ok': False, 'raw': out}


def attach_iso(key, selector='#_systemfield_resume', path=None):
    path = path or RESUME
    if not path or not _os.path.exists(path):
        return {'ok': False, 'err': 'file not found: %r' % path}
    _stage_pdf(key, path)
    return iso(key, _ATTACH_JS % (_json.dumps(_os.path.basename(path)), _json.dumps(selector)))


def load_plan(job_id):
    p = _os.path.join(PLANS, job_id + '.json')
    if not _os.path.exists(p):
        raise SystemExit("no plan for %s: run `python3 applyq/applyq.py build` first" % job_id)
    return _json.load(open(p))


def _blank(ans):
    return ans is None or ans == ''


def _eeo_js(key):
    """The profile's EEO answer for `key` as a list of JS regex sources, or None."""
    pats = applyq.eeo_patterns(key)
    return pats


# ---------- Greenhouse ----------
GH_JS = r"""
const norm=s=>String(s).replace(/\s+/g,' ').trim().toLowerCase();
const inst=(el)=>{ const fk=Object.keys(el).find(k=>k.startsWith('__reactFiber')); let f=el[fk]; while(f&&!(f.stateNode&&f.stateNode.selectOption)) f=f.return; return f?f.stateNode:null; };
const pick=(el,val)=>{ const i=inst(el); if(!i) return 'NO_SELECT'; const flat=[]; (i.props.options||[]).forEach(o=>o.options?o.options.forEach(x=>flat.push(x)):flat.push(o)); const lab=o=>String(o.label??o.value); let o=flat.find(o=>norm(lab(o))===norm(val)) || flat.find(o=>norm(lab(o)).startsWith(norm(val))) || flat.find(o=>norm(val).startsWith(norm(lab(o)))); if(!o) return 'NO_OPTION ['+flat.map(lab).slice(0,8).join(' / ')+']'; i.selectOption(o); return lab(o); };
const num=(s)=>(String(s).match(/\d{4,}/)||[''])[0];
const out=[];
for(const a of ACTS){ try{
  let el=document.getElementById(a.id);
  if(!el && a.kind==='multi'){ const n=num(a.id); el=[...document.querySelectorAll('input.select__input')].find(i=>n && i.id.includes(n)) || null;
    if(!el){ // checkbox group: inputs question_<n>[]_<option id>, matched by label text
      const boxes=[...document.querySelectorAll('input[type=checkbox]')].filter(b=>n && b.id.includes(n)); const got=[];
      for(const v of a.val){ const b=boxes.find(b=>{ const l=document.querySelector('label[for="'+b.id+'"]')||b.closest('label'); return l && norm(l.textContent)===norm(v); }); if(b){ if(!b.checked) b.click(); got.push(v+(b.checked?'':' (UNCHECKED)')); } else got.push('NO_OPTION '+v); }
      out.push([a.id, boxes.length? got : 'MISSING']); continue; } }
  if(!el){ out.push([a.id,'MISSING']); continue; }
  if(a.kind==='text') out.push([a.id, setVal(el,a.val)]);
  else if(a.kind==='select') out.push([a.id, pick(el,a.val)]);
  else if(a.kind==='multi'){ const got=[]; for(const v of a.val) got.push(pick(el,v)); out.push([a.id, got]); }
}catch(e){ out.push([a.id,'ERR '+e.message]); } }
return out;
"""

# Greenhouse keeps answers in ONE useState object, and each field's onChange writes {...staleStore, [name]: v}. Setting
# many fields in one synchronous run keeps only the LAST write: dropdowns look filled but Submit says "required".
# gh_sync pushes every displayed select value and text box into the store with ONE functional update.
_GH_SYNC_JS = r"""
const fiberOf=el=>{ const k=Object.keys(el).find(k=>k.startsWith('__reactFiber')); return k? el[k]:null; };
const findHook=g=>{ let h=g&&g.memoizedState, n=0; while(h && n<80 && typeof h==='object'){ const v=h.memoizedState; if(v && typeof v==='object' && !Array.isArray(v) && 'email' in v && 'first_name' in v && h.queue && h.queue.dispatch) return h; h=h.next; n++; } return null; };
let hook=null; for(const any of document.querySelectorAll('input[id^=question_], textarea[id^=question_], #first_name')){ let g=fiberOf(any); while(g){ const h=findHook(g); if(h){ const h2=g.alternate? findHook(g.alternate):null; hook=(h2 && Object.keys(h2.memoizedState).length>Object.keys(h.memoizedState).length)? h2 : h; break; } g=g.return; } if(hook) break; }
if(!hook) return 'no store';
const store=hook.memoizedState; const upd={};
document.querySelectorAll('input.select__input[id^=question_]').forEach(i=>{
  let f=fiberOf(i); let x=f; while(x && !(x.stateNode && x.stateNode.selectOption)) x=x.return;
  let y=f; while(y && !(y.memoizedProps && y.memoizedProps.name && y.memoizedProps.type)) y=y.return;
  if(!x||!y) return; const p=y.memoizedProps; const v=x.stateNode.props.value; const cur=Array.isArray(v)? v:(v?[v]:[]); if(!cur.length) return;
  const multi=p.type==='multi_value_multi_select'; const key=multi? (p.name.endsWith('[]')? p.name : p.name+'[]') : p.name;
  const want= multi? cur.map(o=>String(o.value)) : String(cur[0].value);
  if(JSON.stringify(store[key])!==JSON.stringify(want)) upd[key]=want;
});
document.querySelectorAll('input[type=text][id^=question_], textarea[id^=question_]').forEach(i=>{ if(i.classList.contains('select__input')) return; if(i.value.trim() && store[i.id]!==i.value) upd[i.id]=i.value; });
if(APPLY && Object.keys(upd).length) hook.queue.dispatch(prev=>Object.assign({}, prev, upd));
return {n:Object.keys(upd).length, keys:Object.keys(upd).map(k=>k.slice(-12))};
"""


def gh_sync(key, apply=True):
    return cmain(key, ("const APPLY=%s;" % ('true' if apply else 'false')) + _GH_SYNC_JS)


def _js_res(pats):
    return "[" + ",".join("new RegExp(%s,'i')" % _json.dumps(p) for p in pats) + "]"


def gh_fill(key, job_id, over=None, resume=True):
    """Fill a Greenhouse form from its plan. `over` maps field name -> answer (None = leave blank).
    The string 'None' is a real option on selects (clearance level) and is only skipped on text fields."""
    over = over or {}
    acts, flags = [], []
    for r in load_plan(job_id)['plan']:
        n = r['name']
        ans = over.get(n, r['answer'])
        t = r['type']
        if t in ('input_file', 'eeoc') or not n or n in (
                'gender', 'hispanic_ethnicity', 'race', 'veteran_status', 'disability_status',
                'resume_text', 'cover_letter_text', 'cover_letter'):
            continue
        if _blank(ans) or (ans == 'None' and t != 'multi_value_single_select'):
            if r['required']:
                flags.append('REQUIRED BLANK: ' + r['label'][:60])
            continue
        if t in ('input_text', 'textarea'):
            acts.append({'kind': 'text', 'id': n, 'val': str(ans)})
        elif t == 'multi_value_single_select':
            acts.append({'kind': 'select', 'id': n, 'val': str(ans)})
        elif t == 'multi_value_multi_select':   # react-select multi, or a checkbox group question_<n>[]_<option>
            acts.append({'kind': 'multi', 'id': n, 'val': ans if isinstance(ans, list) else [str(ans)]})
        else:
            flags.append('UNHANDLED %s %s %r -> %r' % (t, n, r['label'][:50], ans))
    res = cmain(key, 'const ACTS=' + _json.dumps(acts) + ';' + GH_JS)
    c = cmain(key, "return document.getElementById('country')? rsel($('#country'), /^United States\\s*\\+1/) : 'no country';")
    # standard EEO block, from the profile's eeo section
    eeo = []
    for fid, k in (('gender', 'gender'), ('hispanic_ethnicity', 'hispanic'), ('veteran_status', 'veteran'),
                   ('disability_status', 'disability')):
        pats = _eeo_js(k)
        if pats is None:
            continue
        eeo.append(cmain(key, "return $('#%s')? rselAny($('#%s'), %s) : 'no %s';" % (fid, fid, _js_res(pats), fid)))
    _time.sleep(0.8)   # #race renders only after the ethnicity answer
    pats = _eeo_js('race')
    if pats is not None:
        eeo.append(cmain(key, "return $('#race')? rselAny($('#race'), %s) : 'no race';" % _js_res(pats)))
    loc = None
    q, m = _pg('location.autocomplete_query'), _pg('location.autocomplete_match')
    if q and cmain(key, "return !!document.getElementById('candidate-location');").get('r'):
        cmain(key, "const i=$('#candidate-location'); const fk=Object.keys(i).find(k=>k.startsWith('__reactFiber')); let f=i[fk]; "
                   "while(f&&!(f.stateNode&&f.stateNode.selectOption)) f=f.return; "
                   "f.stateNode.onInputChange(%s,{action:'input-change',prevInputValue:''}); f.stateNode.openMenu('first'); return 1;"
              % _json.dumps(q))
        _time.sleep(3)
        loc = cmain(key, "return rsel($('#candidate-location'), new RegExp(%s,'i'));" % _json.dumps('^' + _re.escape(m or q)))
    rz = attach_resume(key, '#resume') if resume else None
    _time.sleep(1.0)
    sync = gh_sync(key)
    return {'fields': res, 'country': c, 'eeo': eeo, 'location': loc, 'resume': rz, 'sync': sync, 'flags': flags}


def gh_load_pick(key, fid, search, pattern):
    """Paginated async select (education School/Degree/Discipline, months): call props.loadOptions directly."""
    G = ("const inst=(el)=>{ const fk=Object.keys(el).find(k=>k.startsWith('__reactFiber')); let f=el[fk]; "
         "while(f&&!(f.stateNode&&f.stateNode.selectOption)) f=f.return; return f.stateNode; };")
    cmain(key, G + """const i=inst($('#%s')); document.documentElement.dataset.lp='pending';
      const done=(opts)=>{ const re=new RegExp(%s,'i'); const o=opts.find(o=>re.test(o.label)); if(o){ inst($('#%s')).selectOption(o); document.documentElement.dataset.lp='picked:'+o.label; } else document.documentElement.dataset.lp='none:'+opts.slice(0,15).map(o=>o.label).join(' / '); };
      if(i.props.loadOptions) Promise.resolve(i.props.loadOptions(%s, [], {page:1})).then(r=>done(r.options||[])).catch(e=>document.documentElement.dataset.lp='err:'+e.message);
      else { const flat=[]; (i.props.options||[]).forEach(o=>o.options?o.options.forEach(x=>flat.push(x)):flat.push(o)); done(flat); }
      return 1;""" % (fid, _json.dumps(pattern), fid, _json.dumps(search)))
    _time.sleep(2.5)   # the promise resolves after cmain returns; read the result from the DOM
    return cjs(key, "document.documentElement.dataset.lp")


def _edu():
    s, e = str(_pg('education.start', '')), str(_pg('education.end', ''))
    sm = applyq.MONTHS[int(s[5:7]) - 1].capitalize() if len(s) >= 7 else ''
    em = applyq.MONTHS[int(e[5:7]) - 1].capitalize() if len(e) >= 7 else ''
    return dict(school=_pg('education.school_search') or _pg('education.school'),
                school_match=_pg('education.school_match') or _pg('education.school'),
                level=_pg('education.degree_level', "Bachelor's"), degree=_pg('education.degree'),
                major=(_pg('education.majors', ['Computer Science']) or ['Computer Science'])[0],
                major_text=_pg('education.major_text'), sm=sm, sy=s[:4], em=em, ey=e[:4])


def gh_education(key):
    d = _edu()
    lvl = d['level'][:6]
    school = 'none'
    for q in [d['school'], d['school_match'], _re.sub(r'^the ', '', d['school'], flags=_re.I).split(' at ')[0]]:
        if not q:
            continue   # Greenhouse spells schools its own way ("University of Texas - Austin"): try shorter searches
        school = gh_load_pick(key, 'school--0', q, applyq.school_regex())
        if str(school).startswith('picked'):
            break
    out = {'school': school,
           'degree': gh_load_pick(key, 'degree--0', lvl, "^%s.*Degree$|^%s" % (_re.escape(lvl), _re.escape(lvl))),
           'discipline': gh_load_pick(key, 'discipline--0', d['major'], '^' + _re.escape(d['major']) + '$')}
    if not str(out['discipline']).startswith('picked'):   # some boards have no exact major: try the first word
        w = d['major'].split()[0]
        out['discipline'] = gh_load_pick(key, 'discipline--0', w, '^' + _re.escape(w))
    for fid, mon in (('start-month--0', d['sm']), ('end-month--0', d['em'])):   # either can exist alone
        if mon and cmain(key, "return !!document.getElementById('%s');" % fid).get('r'):
            out[fid] = gh_load_pick(key, fid, '', '^%s$' % mon)
    out['years'] = cmain(key, "return [$('#start-year--0')?setVal('#start-year--0',%s):'-', $('#end-year--0')?setVal('#end-year--0',%s):'-'];"
                         % (_json.dumps(d['sy']), _json.dumps(d['ey']))).get('r')
    out['sync'] = gh_sync(key)
    return out


GH_STATE = r"""const out={}; ['first_name','last_name','preferred_name','email','phone'].forEach(id=>{const e=document.getElementById(id); if(e) out[id]=e.value;});
 out.selects=[...document.querySelectorAll('.select__control')].map(c=>{ const w=c.closest('.field-wrapper, .select, fieldset'); const lab=w?(w.querySelector('label,legend,.label')||{}).textContent:''; return (lab||'').trim().replace(/\s+/g,' ').slice(0,70)+' = '+[...c.querySelectorAll('.select__single-value, .select__multi-value__label')].map(v=>v.textContent).join(', '); });
 out.texts=[...document.querySelectorAll('input[id^=question_]:not(.select__input), textarea[id^=question_]')].map(i=>{ const l=document.querySelector('label[for="'+i.id+'"]'); return (l?l.textContent.trim().slice(0,50):i.id)+' = '+i.value.slice(0,80); });
 out.resume=[...document.querySelectorAll('.file-upload__filename')].map(e=>e.textContent.trim());
 if(!out.resume.length) out.resume=[...document.querySelectorAll('[class*=upload]')].map(e=>(e.innerText.match(/\S+\.pdf/)||[''])[0]).filter(Boolean).slice(0,1);
 out.file_inputs_left=[...document.querySelectorAll('input[type=file]')].map(i=>{ const w=i.closest('.field-wrapper, fieldset, div'); return (w? (w.querySelector('label,legend')||{}).textContent||i.id : i.id).trim().slice(0,60); });
 out.checks=[...document.querySelectorAll('input[type=checkbox]:checked')].map(i=>((document.querySelector('label[for="'+i.id+'"]')||i.closest('label')||{}).textContent||i.id).trim().slice(0,50));
 out.required_empty=[...document.querySelectorAll('[aria-required=true], [required]')].filter(i=>!i.value && i.type!=='file' && !i.classList.contains('select__input')).map(i=>i.id||i.name);
 out.hidden_with_value=[...document.querySelectorAll('input[type=hidden]')].filter(i=>i.value && !/token|csrf|utf8|authenticity|gh_src|recaptcha/i.test(i.name||i.id)).map(i=>(i.name||i.id)+'='+i.value.slice(0,40));
 return out;"""


def gh_state(key):
    """Read back displayed values. A react-select's own input.value is always empty: judge selects by `selects`."""
    return cmain(key, GH_STATE).get('r')


# ---------- Ashby ----------
ASH_JS = r"""
const norm=s=>String(s).replace(/\s+/g,' ').trim().toLowerCase();
const entry=(p)=>document.querySelector('[data-field-path="'+p+'"]');
const out=[];
for(const a of ACTS){ try{
  const en=entry(a.id); if(!en){ out.push([a.id.slice(0,8),'MISSING']); continue; }
  if(a.kind==='text'){ const el=document.getElementById(a.id) || en.querySelector('input:not([type=checkbox]):not([type=radio]):not([type=file]), textarea'); out.push([a.id.slice(0,8), setVal(el,a.val)]); }
  else if(a.kind==='bool'){ const v=norm(a.val); const opt=/^yes\b/.test(v)?'yes':(/^no\b/.test(v)?'no':null);
     // a non yes/no plan answer (e.g. a city typed for "willing to relocate?") is a rule bug: report it, never click "no"
     if(!opt){ out.push([a.id.slice(0,8),'ERR non-boolean answer: '+a.val]); continue; }
     const b=en.querySelector('button[data-option="'+opt+'"]'); if(b.getAttribute('aria-pressed')!=='true') b.click(); out.push([a.id.slice(0,8), b.dataset.option]); }
  else if(a.kind==='choice'){ const vals=Array.isArray(a.val)?a.val:[a.val]; const res=[];
     for(const v of vals){ const labs=[...en.querySelectorAll('label')].filter(l=>l.querySelector('input')||l.htmlFor); let l=labs.find(l=>norm(l.textContent)===norm(v)) || labs.find(l=>norm(l.textContent).startsWith(norm(v)));
       if(l){ const inp=l.querySelector('input')||document.getElementById(l.htmlFor); if(!inp.checked) inp.click(); res.push(l.textContent.trim()); }
       else res.push('NO_OPTION '+v+' ['+labs.map(l=>l.textContent.trim()).slice(0,8).join(' / ')+']'+(en.querySelector('input[role=combobox]')?' combo=true':'')); }
     out.push([a.id.slice(0,8), res]); }
  else if(a.kind==='loc'){ const el=en.querySelector('input'); out.push([a.id.slice(0,8), setVal(el,a.val)]); }
}catch(e){ out.push([a.id.slice(0,8),'ERR '+e.message]); } }
return out;
"""


def ashby_fill(key, job_id, over=None, resume=True):
    """Fill an Ashby form from its plan in the isolated world (Ashby's CSP blocks main-world injection).
    `over` keys must be the FULL field path (uuid): read them from the plan first."""
    over = over or {}
    acts, flags, locs = [], [], []
    q, m = _pg('location.autocomplete_query'), _pg('location.autocomplete_match')
    for r in load_plan(job_id)['plan']:
        n = r['name']
        ans = over.get(n, r['answer'])
        t = r['type']
        if t == 'File' or n == '_systemfield_resume':
            continue
        if n == '_systemfield_name':
            ans = P.full_name
        if _blank(ans) or ans == 'None':
            if r['required']:
                flags.append('REQUIRED BLANK: %s (%s)' % (r['label'][:60], t))
            continue
        if t in ('String', 'Email', 'Phone', 'Url', 'Number', 'LongText'):
            acts.append({'kind': 'text', 'id': n, 'val': str(ans)})
        elif t == 'Boolean':
            acts.append({'kind': 'bool', 'id': n, 'val': str(ans)})
        elif t in ('ValueSelect', 'MultiValueSelect'):
            acts.append({'kind': 'choice', 'id': n, 'val': ans})
        elif t == 'Location':
            acts.append({'kind': 'loc', 'id': n, 'val': q or str(ans)})
            locs.append(n)
        else:   # EducationHistory / Date: see references/ashby.md
            flags.append('UNHANDLED %s %s %r' % (t, n, r['label'][:50]))
    res = iso(key, 'const ACTS=' + _json.dumps(acts) + ';' + ASH_JS)
    lp = []
    if locs:
        _time.sleep(3)
        for n in locs:
            lp.append(iso(key, "const re=new RegExp(%s,'i'); const o=[...document.querySelectorAll('div[class*=_result_], [role=option]')].find(o=>re.test(o.textContent)); "
                               "if(!o) return 'NO_SUGGESTION (pick it yourself before Submit)'; ['pointerdown','mousedown','pointerup','mouseup','click'].forEach(t=>o.dispatchEvent("
                               "new MouseEvent(t,{bubbles:true,cancelable:true,button:0,view:window}))); return o.textContent.trim();"
                          % _json.dumps(_re.escape(m or q))))
    eeo = ashby_eeo(key)
    rz = attach_iso(key, '#_systemfield_resume') if resume else None
    return {'fields': res, 'locations': lp, 'eeo': eeo, 'resume': rz, 'flags': flags}


ASH_STATE = r"""return [...document.querySelectorAll('[data-field-path]')].map(e=>{ const lab=(e.querySelector('label')||{}).textContent||''; const req=!!(e.querySelector('label')&&/_required_/.test(e.querySelector('label').className)); const inp=e.querySelector('input:not([type=checkbox]):not([type=radio]):not([type=file]),textarea'); const yn=[...e.querySelectorAll('button[data-option][aria-pressed=true]')].map(b=>b.dataset.option).join(','); const ch=[...e.querySelectorAll('input[type=checkbox]:checked, input[type=radio]:checked')].map(i=>(i.closest('label')||document.querySelector('label[for="'+i.id+'"]')||{}).textContent).join(', '); const file=e.querySelector('input[type=file]')? e.innerText.replace(/\s+/g,' ').replace(/Replace or drag and drop here|Upload File|or drag and drop here/g,'').slice(0,60):''; const v=yn||ch||(inp?inp.value:'')||file; return (req?'* ':'  ')+lab.trim().replace(/\s+/g,' ').slice(0,80)+' => '+(v? String(v).slice(0,90):'(blank)'); });"""


def ashby_state(key):
    return iso(key, ASH_STATE).get('r')


_CLICK = ("['pointerdown','mousedown','pointerup','mouseup','click'].forEach(t=>o.dispatchEvent("
          "new MouseEvent(t,{bubbles:true,cancelable:true,button:0,view:window})));")


def ashby_combo_pick(key, input_css, query, pattern, wait=15):
    """Searchable Ashby combobox ("How did you hear about us?", Education History school): type `query`, poll the
    `_result_` rows until they stop saying Loading..., then pointer-click the first row matching `pattern`."""
    iso(key, "const i=document.querySelector(%s); i.focus(); i.click(); setVal(i,''); setVal(i,%s); return 1;"
        % (_json.dumps(input_css), _json.dumps(query)))
    rows = []
    for _ in range(max(1, int(wait / 1.5))):
        _time.sleep(1.5)
        rows = iso(key, "return [...document.querySelectorAll('div[class*=_result_]')].map(o=>o.textContent.trim().slice(0,80));").get('r') or []
        if rows and not all('Loading' in r for r in rows):
            break
    r = iso(key, "const re=new RegExp(%s,'i'); const o=[...document.querySelectorAll('div[class*=_result_]')].find(o=>re.test(o.textContent.trim())); "
                 "if(!o) return null; " % _json.dumps(pattern) + _CLICK + " return o.textContent.trim();").get('r')
    return r or 'NO_RESULT: ' + ' / '.join(rows[:6])


def ashby_education(key):
    """Fill _systemfield_education_history. If the school search never returns rows, the typed name stays and you
    pick the school yourself when you review the tab."""
    d = _edu()
    base = '[data-field-path="_systemfield_education_history"]'
    out = {'school': ashby_combo_pick(key, base + ' input[role=combobox]', d['school'], applyq.school_regex())}
    _time.sleep(0.8)
    want = [[d['sm'][:3], d['sm'], str(int(_pg('education.start', '2000-01')[5:7]))], [d['sy']],
            [d['em'][:3], d['em'], str(int(_pg('education.end', '2000-01')[5:7]))], [d['ey']]]
    out['rest'] = iso(key, r"""const en=document.querySelector('%s'); const r=[];
     const d=document.getElementById('_systemfield_education_history-degree'); if(d) r.push(setVal(d,%s));
     const m=document.getElementById('_systemfield_education_history-major'); if(m) r.push(setVal(m,%s));
     const want=%s;
     [...en.querySelectorAll('select')].slice(0,4).forEach((s,k)=>{ const opt=[...s.options].find(o=>want[k].some(w=>o.text.trim()===w||o.value===w));
       if(opt){ Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(s,opt.value); s.dispatchEvent(new Event('change',{bubbles:true})); r.push(opt.text);} else r.push('NO '+want[k][0]); });
     r.push('school='+en.querySelector('input[role=combobox]').value); return r;"""
                      % (base, _json.dumps(d['degree']), _json.dumps(d['major_text'] or d['major']), _json.dumps(want))).get('r')
    return out


# Optional Ashby demographic blocks, from the profile's eeo section. Unmapped questions stay blank.
def _ash_eeo_rules():
    rules = []
    for lab_rx, k in ((r'current age|your age', 'age_band'), (r'gender identity|^Gender$', 'gender'),
                      (r'transgender', 'transgender'), (r'sexual orientation', 'orientation'),
                      (r'ethnicit|^Race$|racial', 'race'), (r'Hispanic|Latin', 'hispanic'),
                      (r'Veteran', 'veteran'), (r'disabilit', 'disability')):
        pats = _eeo_js(k)
        if pats:
            rules.append([lab_rx, pats])
    return rules


def ashby_eeo(key):
    rules = _ash_eeo_rules()
    if not rules:
        return []
    js = "const RULES=" + _json.dumps(rules) + r""";
    const out=[];
    for(const e of document.querySelectorAll('[data-field-path]')){
      const lab=((e.querySelector('label')||{}).textContent||'').trim();
      const rule=RULES.find(r=>new RegExp(r[0],'i').test(lab)); if(!rule) continue;
      const labs=[...e.querySelectorAll('label')].slice(1).filter(l=>l.querySelector('input')||l.htmlFor);
      if(!labs.length) continue;
      if(labs.some(l=>{const i=l.querySelector('input')||document.getElementById(l.htmlFor); return i&&i.checked;})) { out.push(lab.slice(0,30)+' (already set)'); continue; }
      let l=null; for(const p of rule[1]){ l=labs.find(l=>new RegExp(p,'i').test(l.textContent.trim())); if(l) break; }
      if(!l){ out.push(lab.slice(0,30)+' => NO MATCH'); continue; }
      const i=l.querySelector('input')||document.getElementById(l.htmlFor); i.click(); out.push(lab.slice(0,30)+' => '+l.textContent.trim());
    }
    return out;"""
    return iso(key, js).get('r')


# ---------- Lever (plain HTML + jQuery; isolated world is enough, no store to sync) ----------
LEVER_JS = r"""
const out=[]; const norm=s=>String(s||'').replace(/\s+/g,' ').trim().toLowerCase();
const form=document.querySelector('#application-form')||document;
const setv=(e,v)=>{ const proto=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype; e.focus(); Object.getOwnPropertyDescriptor(proto,'value').set.call(e,v); e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true})); e.dispatchEvent(new Event('blur',{bubbles:true})); return e.value; };
const optText=b=>{ const l=b.closest('label'); const s=l&&l.querySelector('.application-answer-alternative'); return ((s? s.textContent : b.value)||'').trim(); };
const match=(txt,want)=>{ const a=norm(txt), w=norm(want); const a2=a.replace(/\s/g,''), w2=w.replace(/\s/g,''); return a===w || a.startsWith(w) || (w.length>8 && w.startsWith(a)) || a2===w2 || a2.startsWith(w2) || (w2.length>8 && w2.startsWith(a2)); };
for(const a of ACTS){ try{
  const els=[...form.querySelectorAll('[name="'+CSS.escape(a.name)+'"]')].filter(e=>e.type!=='hidden');
  if(!els.length){ out.push([a.name,'MISSING']); continue; }
  if(a.kind==='text'||a.kind==='textarea'){ out.push([a.name, setv(els[0], a.val)]); }
  else if(a.kind==='select'){ const s=els[0]; const o=[...s.options].find(o=>o.value && match(o.textContent,a.val)); if(!o){ out.push([a.name,'NO_OPTION ['+[...s.options].map(o=>o.textContent.trim()).slice(0,8).join(' / ')+']']); continue; } s.value=o.value; s.dispatchEvent(new Event('input',{bubbles:true})); s.dispatchEvent(new Event('change',{bubbles:true})); out.push([a.name,o.textContent.trim()]); }
  else if(a.kind==='radio'||a.kind==='checkbox'){ const want=Array.isArray(a.val)?a.val:[a.val]; const got=[];
    if(a.kind==='checkbox') els.forEach(b=>{ if(b.checked && !want.some(w=>match(optText(b),w))) b.click(); });
    for(const w of want){ const b=els.find(b=>match(optText(b),w)); if(!b){ got.push('NO_OPTION '+w); continue; } if(!b.checked) b.click(); got.push(optText(b).slice(0,40)+(b.checked?'':' (UNCHECKED)')); }
    out.push([a.name, got.join(' | ')]); }
}catch(e){ out.push([a.name,'ERR '+e.message]); } }
return out;
"""

LEVER_STATE_JS = r"""
const form=document.querySelector('#application-form')||document;
const optText=b=>{ const l=b.closest('label'); const s=l&&l.querySelector('.application-answer-alternative'); return ((s? s.textContent : b.value)||'').trim(); };
return PLAN.map(r=>{ const els=[...form.querySelectorAll('[name="'+CSS.escape(r.name)+'"]')].filter(e=>e.type!=='hidden'); let v='';
  if(!els.length) v='(missing on page)';
  else if(r.kind==='select'){ const s=els[0]; v=s.value? s.options[s.selectedIndex].textContent.trim():''; }
  else if(r.kind==='radio'||r.kind==='checkbox') v=els.filter(b=>b.checked).map(optText).join(', ');
  else if(r.kind==='file'){ const f=els[0].files&&els[0].files[0];
     v = r.name==='resume' ? ((document.querySelector('input[name=resumeStorageId]')||{}).value ? 'uploaded '+((f&&f.name)||'') : (f? 'attached, not uploaded yet: '+f.name : '')) : (f? f.name:''); }
  else v=els[0].value;
  if(r.name==='location'){ const sl=(document.querySelector('input[name=selectedLocation]')||{}).value; v += sl? '  [picked from list]' : (v? '  [typed, not picked]' : ''); }
  return (r.required?'* ':'  ')+String(r.label).replace(/\s+/g,' ').slice(0,75)+' => '+(v? String(v).replace(/\s+/g,' ').slice(0,90):'(blank)'); });
"""

LEVER_INVALID = ("(() => { const f=document.querySelector('#application-form'); return JSON.stringify([...new Set([...f.querySelectorAll("
                 "'input,select,textarea')].filter(e=>e.type!=='hidden' && !e.checkValidity()).map(e=>e.name))]); })()")


def _lever_acts(plan, over):
    acts, flags = [], []
    for r in plan:
        n, k = r['name'], r.get('kind') or ''
        ans = over.get(n, r['answer'])
        if k == 'file' or n == 'location':
            continue
        if ans == '__TODAY__':
            ans = _time.strftime('%m/%d/%Y')
        if ans in (None, 'None', '', []):
            if r['required']:
                flags.append('REQUIRED BLANK: %s' % r['label'][:70])
            continue
        if k in ('text', 'textarea', 'select', 'radio', 'checkbox'):
            acts.append({'kind': k, 'name': n, 'val': ans if isinstance(ans, list) else str(ans)})
        else:
            flags.append('UNHANDLED %s %s' % (k, n))
    return acts, flags


def lever_location(key):
    """Type (input + keydown starts Lever's debounced search), then mousedown the matching .dropdown-location.
    Never fire blur while the list is open: Lever's blur handler clears the box."""
    query, want = _pg('location.autocomplete_query') or _pg('location.city'), _pg('location.autocomplete_match') or _pg('location.city')
    TYPE = ("const i=document.querySelector('input.location-input'); if(!i) return 'no location box'; i.focus(); "
            "Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(i,%s); i.dispatchEvent(new Event('input',{bubbles:true})); "
            "i.dispatchEvent(new KeyboardEvent('keydown',{bubbles:true,key:'d'})); i.dispatchEvent(new KeyboardEvent('keyup',{bubbles:true,key:'d'})); return 'typed';")
    t = iso(key, TYPE % _json.dumps(query)).get('r')
    if t != 'typed':
        return t
    for _ in range(15):
        _time.sleep(0.7)
        r = iso(key, "const os=[...document.querySelectorAll('.dropdown-location')]; const o=os.find(o=>new RegExp(%s,'i').test(o.textContent)); "
                     "if(!o) return 'wait:'+os.length; o.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true,view:window})); "
                     "return 'picked '+o.textContent.trim();" % _json.dumps(_re.escape(want))).get('r')
        if str(r).startswith('picked'):
            return r
    typed = "%s, %s" % (_pg('location.city'), _pg('location.state_abbr') or _pg('location.state'))
    iso(key, "const i=document.querySelector('input.location-input'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(i,%s); "
             "i.dispatchEvent(new Event('change',{bubbles:true})); const c=document.querySelector('.dropdown-container'); if(c) c.style.display='none'; return 1;"
        % _json.dumps(typed))
    return 'no suggestion; typed ' + typed


def lever_fill(key, job_id, over=None, resume=True):
    """Fill a Lever /apply tab from its plan; `over` = {field name: answer} (approved essays etc.).
    Use resume=False for later fix-ups so the resume isn't re-uploaded."""
    over = over or {}
    plan = load_plan(job_id)['plan']
    rz = None
    if resume and any(r['name'] == 'resume' for r in plan):
        rz = attach_iso(key, 'input[name=resume]')
        for _ in range(30):   # wait for Lever's upload + parse so its autofill can't overwrite our answers
            _time.sleep(1)
            if cjs(key, "(document.querySelector('input[name=resumeStorageId]')||{}).value ? 'up' : 'no'") == 'up':
                break
        _time.sleep(1.5)
    acts, flags = _lever_acts(plan, over)
    res = iso(key, 'const ACTS=' + _json.dumps(acts) + ';' + LEVER_JS)
    if not any(a['name'] == 'org' for a in acts):   # Lever's resume parser writes your last employer into Current company
        iso(key, "const o=document.querySelector('input[name=org]'); if(o&&o.value){ o.value=''; o.dispatchEvent(new Event('input',{bubbles:true})); "
                 "o.dispatchEvent(new Event('change',{bubbles:true})); } return 1;")
    loc = lever_location(key) if (resume and any(r['name'] == 'location' for r in plan)) else None
    return {'fields': res, 'resume': rz, 'location': loc, 'flags': flags, 'invalid': cjs(key, LEVER_INVALID)}


def lever_state(key, job_id):
    plan = [{'name': r['name'], 'kind': r.get('kind'), 'label': r['label'], 'required': r['required']}
            for r in load_plan(job_id)['plan']]
    r = iso(key, 'const PLAN=' + _json.dumps(plan) + ';' + LEVER_STATE_JS)
    return r.get('r') if isinstance(r, dict) and r.get('ok') else r


# ---------- dispatch ----------
def _ats(job_id):
    return load_plan(job_id)['job']['ats']


def fill(key, job_id, over=None, resume=True):
    a = _ats(job_id)
    if a == 'greenhouse':
        return gh_fill(key, job_id, over, resume)
    if a == 'ashby':
        return ashby_fill(key, job_id, over, resume)
    if a == 'lever':
        return lever_fill(key, job_id, over, resume)
    raise SystemExit('no filler for ATS %r' % a)


def state(key, job_id):
    a = _ats(job_id)
    if a == 'greenhouse':
        return gh_state(key)
    if a == 'ashby':
        return ashby_state(key)
    return lever_state(key, job_id)


def education(key, job_id):
    a = _ats(job_id)
    if a == 'greenhouse':
        return gh_education(key)
    if a == 'ashby':
        return ashby_education(key)
    return 'Lever forms have no education block'


def _main(argv):
    if len(argv) < 2 or argv[1] in ('-h', '--help', 'help'):
        print(__doc__)
        return
    cmd, a = argv[1], argv[2:]
    over = None
    if '--over' in a:
        over = _json.load(open(a[a.index('--over') + 1]))
    resume = '--no-resume' not in a
    if cmd == 'open':
        r = chrome_open(a[0], a[1])
    elif cmd == 'find':
        r = chrome_find(a[0], a[1])
    elif cmd == 'fill':
        r = fill(a[0], a[1], over, resume)
    elif cmd == 'education':
        r = education(a[0], a[1])
    elif cmd == 'state':
        r = state(a[0], a[1])
    elif cmd == 'sync':
        r = gh_sync(a[0], apply='--check' not in a)
    elif cmd == 'combo':   # Ashby searchable dropdown: combo <key> <field path> <text to type> <regex of row to pick>
        r = ashby_combo_pick(a[0], '[data-field-path="%s"] input' % a[1], a[2], a[3])
    elif cmd == 'attach':
        r = attach_iso(a[0], a[1], _os.path.expanduser(a[2]))
    elif cmd == 'status':
        r = tab_status(a[0])
    elif cmd == 'scroll':
        r = scroll_submit(a[0])
    elif cmd == 'js':
        r = cjs(a[0], a[1])
    elif cmd == 'close':
        r = close_tab(a[0])
    elif cmd == 'tabs':
        r = _tabs()
    else:
        raise SystemExit(__doc__)
    print(_json.dumps(r, indent=1, ensure_ascii=False) if not isinstance(r, str) else r)


if __name__ == '__main__':
    _main(_sys.argv)
