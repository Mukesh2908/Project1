You are reading a job description to work out what the role is really about.

JOB DESCRIPTION:
---
{jd_text}
---

First establish the intent of the role in one sentence: what would this person
actually do day to day? Read the skills in light of that intent, because long
skill lists often surround a single real focus.

Return:

- `job_title`, `role_intent`, `role_family` (frontend_dev, backend_dev,
  fullstack_dev, data_engineer, data_analyst, devops, qa, mobile_dev)
- `seniority`: junior, mid, senior or lead
- `domain`: the business domain if named, else null
- `domain_required`: true only if domain experience is explicitly required
- `responsibilities`: the responsibility bullets, as written
- `delivery_bullets`: how many responsibilities describe building or delivering
- `years_min`, `years_max`: the stated experience band, else null
- `certifications`: [{{"name": ..., "level": "required" | "preferred"}}]
- `education_requirements`: as stated, else an empty list
- `skill_signals`: for every skill named, tag ONLY what is observable:
    `in_title`, `in_opening`, `responsibility_bullets` (count),
    `extra_mentions` (count), `strong_language` (must, required, strong,
    expert, advanced, N+ years, extensive), `optional_language` (nice to have,
    plus, preferred, exposure, good to have), `required_years`, `depth_words`

Do not rank the skills, score them, or decide which is primary. Tag the signals
only; the scoring happens outside this call.
