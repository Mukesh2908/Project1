You are tagging evidence in one project from a resume. Work only from the text
given. Do not infer anything the text does not support.

PROJECT TITLE: {title}

PROJECT TEXT:
---
{project_text}
---

For every skill actually used in this project, return an entry with:

- `skill`: the technology name as written
- `action`: what the person did with it, in a few words
- `depth`: 1-5 using this ladder
    L1 Mentioned  - named only, no use described
    L2 Used       - basic use, simple queries or small changes
    L3 Built      - built delivered functionality with it
    L4 Advanced   - tuned, optimised or designed with it
    L5 Led        - owned the design, reviewed or mentored others on it
- `ownership`: "self" if the text uses direct action verbs for this person,
  "team" if it says we/the team, "vague" if unclear
- `production`: "yes" if it reached production or real users, "no" if the text
  says otherwise, "unknown" if not stated
- `usage_context`: dev, test, support, analysis or other
- `evidence_quality`:
    weak        - a bare mention
    weak_plus   - appears only in a tech-stack line
    medium      - described in a project responsibility
    strong      - an employment responsibility with a direct action verb
    very_strong - production ownership or measurable impact
- `quote`: the exact line from the text above that supports this entry, copied
  verbatim. If you cannot copy an exact line, omit the skill entirely.
- `stack_line_only`: true if the skill appears only in a tech-stack line
- `implied`: true if the skill is demonstrated but not named

Also return `role`, `domain` and `role_family` for the project when stated.
Use one of: frontend_dev, backend_dev, fullstack_dev, data_engineer,
data_analyst, devops, qa, mobile_dev.

Rules:
- Quote exactly. An entry whose quote is not in the text will be discarded.
- Return null rather than guessing.
- Do not judge the person. Tag only what the text shows.
