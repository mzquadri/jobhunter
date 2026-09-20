# Cover letter source

Copy to `config/letter.md` and make it yours. That file is gitignored, so your
career history stays out of the repository.

Two parts:

- **BULLET bank** — every paragraph you might want in a cover letter, each
  tagged. For a given posting the drafter scores each paragraph by how many of
  its tags the job actually asked for and keeps the best three, so an aerospace
  role and a medical-imaging role get genuinely different letters rather than
  the same letter with the company name swapped.
- **LETTER** — the frame. `{{...}}` markers are filled in automatically from
  `config/profile.yml` and the posting itself.

To add a paragraph, copy a BULLET line, give it a new id and tags, and write
the text underneath. Nothing else needs changing.

Available markers: `{{DATE}}` `{{ROLE}}` `{{COMPANY}}` `{{LOCATION_LINE}}`
`{{GRADUATION}}` `{{NAME}}` `{{EMAIL}}` `{{PHONE}}` `{{CITY}}` `{{BULLETS}}`
`{{SKILLS_LINE}}` `{{WHY_COMPANY}}`

---

<!-- BULLET: THESIS | tags: research, uncertainty, pytorch, graph neural, simulation, optimization -->
Describe your thesis or most substantial research project here. Lead with the
problem, then what you built, then a number that shows it worked — a percentage
improvement, a dataset size, a metric that moved.

<!-- BULLET: PRODUCTION-SYSTEM | tags: fastapi, docker, kafka, postgresql, production, backend, mlops -->
Describe a system you shipped rather than prototyped. Name the pieces that
actually ran in production and what each one was responsible for.

<!-- BULLET: DOMAIN-PROJECT | tags: computer vision, imaging, nlp, llm, rag, forecasting -->
Describe a project in the domain you most want to work in. Keep it concrete:
what the model did, how it was evaluated, what you would do differently.

<!-- BULLET: INDUSTRY-EXPERIENCE | tags: automotive, aerospace, manufacturing, enterprise, process-automation -->
Describe industry experience — an internship or placement. Say what you learned
about how that kind of organisation works, not only what you built.

<!-- BULLET: FOUNDATIONS | tags: mathematics, statistics, probability, numerical, algorithm, theory -->
Describe your academic foundation and how you use it: what you reach for when a
model misbehaves and hyperparameter tuning is not the answer.

---

<!-- LETTER -->
{{DATE}}

**Application for {{ROLE}}**
{{COMPANY}}{{LOCATION_LINE}}

Dear Hiring Team,

I am applying for the {{ROLE}} position at {{COMPANY}}.

{{BULLETS}}

{{SKILLS_LINE}}

{{WHY_COMPANY}}

I would welcome the chance to discuss how I can contribute to your team.

Yours sincerely,

**{{NAME}}**
{{EMAIL}} · {{PHONE}}
{{CITY}}
