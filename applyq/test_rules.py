#!/usr/bin/env python3
"""Offline tests for the answer rules (no network, no browser).  Run:  python3 applyq/test_rules.py

Two fictional candidates: a US citizen who will relocate, and an F-1 student who needs sponsorship later.
After ANY edit to applyq.py RULES, run this file; add a case for every bug you fix.
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import applyq  # noqa: E402
import candidate  # noqa: E402

BASE = {
    "name": {"first": "Jordan", "last": "Lee", "preferred": "Jordan", "pronouns": "they/them", "pronunciation": ""},
    "contact": {"email": "jordan@example.com", "school_email": "jlee@school.edu", "phone": "(555) 010-1234",
                "linkedin": "https://linkedin.com/in/jlee", "github": "https://github.com/jlee", "website": ""},
    "location": {"city": "Durham", "state": "North Carolina", "state_abbr": "NC", "country": "United States",
                 "street": "", "zip": "27701", "autocomplete_query": "Durham", "autocomplete_match": "Durham, North Carolina"},
    "education": {"school": "University of North Carolina at Chapel Hill", "school_search": "", "school_match": "Chapel Hill",
                  "school_short": "UNC-Chapel Hill", "degree": "Bachelor of Science", "degree_level": "Bachelor's",
                  "majors": ["Computer Science"], "minors": [], "major_text": "Computer Science", "gpa": "3.8",
                  "start": "2023-08", "end": "2027-05", "grad_text": "May 2027",
                  "in_progress_degree_counts_as_completed": True, "high_school": "", "high_school_year": "", "act": "",
                  "sat": ""},
    "work": {"currently_employed": False, "current_employer": "", "current_title": "", "last_employer": "Acme",
             "last_title": "Software Engineering Intern", "past_employers": ["Acme"], "full_time_years": 0,
             "total_experience_years": 1.5, "non_compete": False, "ever_terminated": False},
    "eligibility": {"us_work_authorized": True, "needs_sponsorship_now": False, "needs_sponsorship_future": False,
                    "visa_status": "US citizen", "us_citizen": True, "permanent_resident": False,
                    "other_countries_authorized": [], "clearance_held": "none", "willing_to_get_clearance": True,
                    "over_18": True},
    "preferences": {"start_date": "2027-06-01", "start_text": "June 2027", "employment_type": "Full-Time",
                    "willing_to_relocate": True, "onsite_ok": True, "travel_ok": True, "office_preference": ["New York"],
                    "how_heard": "LinkedIn", "salary_default": 100000, "languages_spoken": ["English", "Korean"],
                    "strongest_language": "Python", "top_languages": "Python, Java, Go"},
    "consents": {"sms_updates_ok": True, "privacy_and_data_processing_ack": True, "consider_for_future_roles": True,
                 "share_resume_with_partners": True, "interview_recording_or_ai_notetaker_ok": True, "esign_ok": True,
                 "arbitration": ""},
    "eeo": {"gender": "decline", "hispanic": "No", "race": "Asian", "veteran": "No", "disability": "No",
            "transgender": "decline", "orientation": "decline", "age_band": "decline"},
    "files": {"resume": "/tmp/resume.pdf", "transcript": "", "reference": ""},
}
F1 = copy.deepcopy(BASE)
F1["eligibility"].update(us_citizen=False, needs_sponsorship_future=True, visa_status="F-1 student (OPT)",
                         willing_to_get_clearance=False)

YN = ["Yes", "No"]
CASES = [
    # (profile, label, options, type, required, job, expected answer, expected source)
    (BASE, "Will you now or in the future require sponsorship?", YN, "multi_value_single_select", True, {}, "No", "profile"),
    (F1, "Will you now or in the future require sponsorship?", YN, "multi_value_single_select", True, {}, "Yes", "profile"),
    (F1, "Do you currently require visa sponsorship?", YN, "multi_value_single_select", True, {}, "No", "profile"),
    (BASE, "Are you legally authorized to work in the United States without sponsorship?", YN, "multi_value_single_select",
     True, {}, "Yes", "profile"),
    (F1, "Are you legally authorized to work in the US without sponsorship now or in the future?", YN, "Boolean", True, {},
     "No", "profile"),
    (BASE, "What is your current visa status?", [], "input_text", True, {}, "US citizen", "profile"),
    (BASE, "Are you authorized to work lawfully in Poland?", YN, "multi_value_single_select", True, {}, "No", "profile"),
    (BASE, "Are you a U.S. person (export control)?", ["Yes, I am a U.S. person", "No"], "multi_value_single_select", True,
     {}, "Yes, I am a U.S. person", "profile"),
    (BASE, "Are you willing to relocate?", ["Yes, I currently live within commuting distance", "Yes, I will relocate", "No"],
     "multi_value_single_select", True, {"location": "New York, NY"}, "Yes, I will relocate", "profile"),
    (BASE, "This role is in-office 5 days a week. Are you able to work onsite?",
     ["Yes, I live locally", "Yes, but I will need to relocate", "No"], "multi_value_single_select", True,
     {"location": "Seattle, WA"}, "Yes, but I will need to relocate", "profile"),
    (BASE, "This role is in-office 5 days a week. Are you able to work onsite?",
     ["Yes, I live locally", "Yes, but I will need to relocate", "No"], "multi_value_single_select", True,
     {"location": "Durham, NC"}, "Yes, I live locally", "profile"),
    (BASE, "What is your GPA?", ["2.5 - 2.7 (out of 4.0)", "3.6 - 4.0", "Prefer not to say"], "multi_value_single_select",
     True, {}, "3.6 - 4.0", "profile"),
    (BASE, "GPA (undergraduate)", ["4.0 out of 4.0", "3.9 out of 4.0", "3.8 out of 4.0"], "multi_value_single_select", True,
     {}, "3.8 out of 4.0", "profile"),
    (BASE, "Is your graduation date between November 2026 and June 2027?", [], "Boolean", True, {}, "Yes", "profile"),
    (BASE, "Is your graduation date between December 2027 and June 2028?", [], "Boolean", True, {}, "No", "profile"),
    (BASE, "When do you graduate?", ["Dec 2026", "May - Aug 2027", "2028"], "multi_value_single_select", True, {},
     "May - Aug 2027", "profile"),
    (BASE, "Expected salary?", [], "input_text", True, {"pay": "$120,000 - $150,000", "location": "Austin, TX"},
     "$120,000 - $150,000", "profile"),
    (BASE, "Expected salary?", [], "input_text", True, {"pay": ""}, "$100,000", "profile"),
    (BASE, "What is your target salary range?", ["$80,000 - $89,999", "$90,000 - $99,999", "$100,000+"],
     "multi_value_single_select", True, {}, "$100,000+", "profile"),
    (BASE, "Race", ["East Asian", "South Asian", "White", "Decline to self-identify"], "multi_value_single_select", False, {},
     None, "skip"),   # "Asian" is ambiguous here: never guess East vs South
    (BASE, "Race", ["Asian", "White", "Decline to self-identify"], "multi_value_single_select", False, {}, "Asian", "profile"),
    (BASE, "Gender", ["Male", "Female", "Decline To Self Identify"], "multi_value_single_select", False, {},
     "Decline To Self Identify", "profile"),
    (BASE, "Disability Status", ["Yes, I have a disability", "No, I don't have a disability", "I don't wish to answer"],
     "multi_value_single_select", False, {}, "No, I don't have a disability", "profile"),
    (BASE, "Other than time off for reasons related to religion or a disability, can you work weekends?", YN,
     "multi_value_single_select", True, {}, None, "you"),   # must NOT be answered by the disability EEO rule
    (BASE, "How did you hear about us?", ["Indeed", "LinkedIn (Job Post)", "LinkedIn (Video)", "Other"],
     "multi_value_single_select", True, {}, "LinkedIn (Job Post)", "profile"),
    (BASE, "Have you ever worked for Acme?", YN, "multi_value_single_select", True, {"company": "Acme"}, "Yes", "profile"),
    (BASE, "Have you previously been employed at Initech?", YN, "multi_value_single_select", True, {"company": "Initech"},
     "No", "profile"),
    (BASE, "If located in the US, in what city and state do you reside?", [], "input_text", True, {}, "Durham, NC", "profile"),
    (BASE, "If yes, what type of sponsorship?", [], "input_text", False, {}, None, "skip"),
    (F1, "If yes, what type of sponsorship?", [], "input_text", True, {}, "F-1 student (OPT)", "inferred"),
    (BASE, "Please specify", [], "input_text", True, {}, "N/A", "default"),
    (BASE, "Please specify", [], "input_text", False, {}, None, "skip"),
    (BASE, "Which university are you currently attending?",
     ["University of North Carolina at Charlotte", "University of North Carolina - Chapel Hill", "Duke University"],
     "multi_value_single_select", True, {}, "University of North Carolina - Chapel Hill", "profile"),
    (BASE, "Do you possess any type of government clearance?", [], "input_text", True, {},
     "No, I have never held a government clearance.", "profile"),
    (BASE, "Why do you want to work here?", [], "textarea", True, {}, None, "essay"),
    (BASE, "Please review and acknowledge our arbitration agreement", ["I acknowledge"], "multi_value_single_select", True,
     {}, None, "you"),
    (BASE, "Would you like to receive communications via SMS to the phone number provided?", YN,
     "multi_value_single_select", True, {}, "Yes", "profile"),
    (BASE, "Resume/CV", [], "textarea", True, {}, None, "skip"),
    (BASE, "Which location are you applying for?", ["New York, NY", "Seattle, WA"], "multi_value_single_select", True,
     {"location": "Seattle, WA"}, "Seattle, WA", "default"),
    (BASE, "Are you open to relocation?", ["No", "No, but I'm open to remote", "New York, NY", "Seattle, WA"],
     "multi_value_single_select", True, {}, "New York, NY", "profile"),
    (BASE, "How many years of professional experience do you have?", ["0", "1-2", "3-5", "5+"], "multi_value_single_select",
     True, {}, "0", "profile"),
    (BASE, "For the sole purpose of determining export licensing requirements, please provide your country of citizenship",
     ["Canada", "United States of America (USA)", "India"], "multi_value_multi_select", True, {},
     "United States of America (USA)", "profile"),
    (F1, "Please provide your country of citizenship", ["Canada", "United States"], "multi_value_single_select", True, {},
     None, "you"),
    (BASE, "If offered employment by Amazon, would you be legally eligible to begin employment immediately?", YN,
     "multi_value_single_select", True, {}, "Yes", "profile"),
    (BASE, "Combined engineering or technical experience (including internships)",
     ["Less than 1 year", "1-2 years", "More than 3 years"], "multi_value_single_select", True, {}, "1-2 years", "profile"),
]


def main():
    applyq.BANK = Path("/nonexistent/bank.json")
    bad = 0
    for prof, label, opts, ftype, req, job, want, want_src in CASES:
        applyq.P = candidate.Profile(prof)
        applyq.CUR_JOB.clear()
        applyq.CUR_JOB.update(dict(dict(company="TestCo", title="Software Engineer", location="New York, NY", pay=""), **job))
        a, src, note = applyq.answer(label, opts, ftype, req, applyq.CUR_JOB["company"])
        ok = a == want and src == want_src
        if not ok:
            bad += 1
            print("FAIL  %-70s got %r [%s] (%s), want %r [%s]" % (label[:70], a, src, note, want, want_src))
    print("%d/%d passed" % (len(CASES) - bad, len(CASES)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
