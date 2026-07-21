"""Per-ATS apply playbooks injected into the browser agent prompt.

These are the "custom ATS styles" people build: each platform has different
upload widgets, multi-step flows, and gotchas. Claude/generic agents still
drive the browser — strategies make them platform-aware.
"""

from __future__ import annotations

from applypilot.ats.detect import AtsInfo, detect_ats


_STRATEGIES: dict[str, str] = {
    "greenhouse": """
== ATS PLAYBOOK: Greenhouse ==
1. Landing is often boards.greenhouse.io or embedded iframe — stay in the job iframe if present.
2. Click "Apply" / "Submit application" to reveal the form.
3. Upload resume FIRST (file input). Wait for parse to finish before editing fields.
4. Greenhouse often auto-fills from resume — VERIFY every field; parsers mangle titles.
5. Required custom questions appear mid-form — answer from APPLICANT PROFILE only.
6. EEO/voluntary sections: use Decline / profile EEO defaults.
7. Final "Submit application" — wait for confirmation ("Thank you" / application id).
8. CAPTCHA rare on Greenhouse boards; if present, try CapSolver path or mark failed:captcha.
""",
    "lever": """
== ATS PLAYBOOK: Lever ==
1. jobs.lever.co/{company}/{id} — click Apply.
2. Resume upload is early; then full form.
3. Lever has "additional information" free-text — 2-3 sentence pitch from profile + role.
4. LinkedIn URL field common — use profile LinkedIn or leave blank if empty.
5. Submit → confirmation page. Do not double-submit.
""",
    "ashby": """
== ATS PLAYBOOK: Ashby ==
1. jobs.ashbyhq.com/{board}/... — multi-section form with Next buttons.
2. Complete each section fully before Next (Ashby blocks Next if required empty).
3. File upload for resume; sometimes cover letter optional — upload if available.
4. Work auth / sponsorship questions are strict — use exact profile answers.
5. Submit on last step only.
""",
    "workday": """
== ATS PLAYBOOK: Workday ==
1. myworkdayjobs.com — may require Create Account / Sign In. Use profile email + job site password.
2. If "Autofill with Resume" appears: upload PDF, WAIT for parsing spinner to finish.
3. Workday is multi-page: My Information → Experience → Application Questions → Review.
4. Click Next/Continue after each page; never skip required * fields.
5. Country/phone country code must match profile.
6. Experience section often needs manual row add if parser fails — use TAILORED RESUME facts only.
7. Review page: scroll entire page, fix errors (red text), then Submit.
8. Account already exists → Sign In, not Create.
9. If SSO (Okta/Microsoft) blocks → mark failed:sso and stop.
""",
    "indeed": """
== ATS PLAYBOOK: Indeed ==
1. Prefer "Apply now" on company site if Indeed only redirects.
2. Indeed Easy Apply: multi-step modal — resume select, questions, send.
3. If "Apply on company site" → follow external ATS playbook after navigation.
4. Avoid Indeed account walls when possible; use guest/apply flow if shown.
5. Confirmation = "Application submitted" toast or similar.
""",
    "amazon": """
== ATS PLAYBOOK: Amazon jobs (HARD) ==
1. amazon.jobs is a custom stack with strong bot defenses.
2. Prefer manual apply if CAPTCHA/login loops appear twice.
3. Flow: job → Apply → Amazon account login → application wizard.
4. Do NOT invent Amazon work history. Use profile only.
5. If blocked by CAPTCHA/puzzle → failed:captcha (permanent for this run).
6. Success: application confirmation number on screen.
""",
    "google": """
== ATS PLAYBOOK: Google Careers (HARD) ==
1. careers.google.com often requires Google account + slow multi-step.
2. Auto-apply success rate is low; prefer tailored resume + manual submit.
3. If open: fill only fields you can verify; upload resume PDF.
4. Two CAPTCHA failures → failed:captcha and stop.
""",
    "meta": """
== ATS PLAYBOOK: Meta Careers (HARD) ==
1. metacareers.com frequently requires login / MFA.
2. Treat as manual-first if login wall appears.
3. Upload resume; answer work auth honestly from profile.
4. Do not loop on login failures — failed:sso.
""",
    "microsoft": """
== ATS PLAYBOOK: Microsoft Careers (HARD) ==
1. jobs.careers.microsoft.com — multi-step + Microsoft account.
2. Resume upload then questionnaire.
3. SSO issues → failed:sso.
""",
    "linkedin": """
== ATS PLAYBOOK: LinkedIn Easy Apply (HARD) ==
1. Requires persistent logged-in LinkedIn Chrome profile.
2. Easy Apply modal: next through steps, upload resume, submit.
3. External apply → switch to detected external ATS playbook.
4. Avoid connection spam / non-job actions.
""",
    "unknown": """
== ATS PLAYBOOK: Generic ==
1. Find Apply / Submit / Careers CTA.
2. Upload resume PDF early.
3. Fill visible required fields from APPLICANT PROFILE + TAILORED RESUME.
4. Never invent employers, degrees, or skills.
5. Submit once; capture confirmation text.
""",
}


def get_apply_strategy(url: str | None = None, ats: AtsInfo | None = None) -> str:
    """Return the playbook text for a job URL or AtsInfo."""
    info = ats or detect_ats(url)
    body = _STRATEGIES.get(info.name, _STRATEGIES["unknown"])
    header = (
        f"Detected ATS: {info.name} | difficulty={info.difficulty} | "
        f"auto_recommended={info.supports_auto}\n"
        f"{info.notes}\n"
    )
    return header + body
