# How I Thought About This Project

## Understanding the assignment

I read the instructions several times before coding. I wanted to understand
the problem, constraints, and expected deliverables before deciding what to build.

## Thinking about stakeholders: my six design rules

I considered three perspectives, asking what each wants most and dreads most:

- **Customer — GitHub maintainer:** wants clear, actionable priorities with
  minimal noise. Dreads hallucinated urgency and long, unhelpful summaries.
- **Product builder — engineering/platform team:** wants predictable costs,
  bounded execution, and flexible LLM providers. Dreads runaway agent loops,
  unnecessary complexity, and provider lock-in.
- **Regulator — security/governance:** wants read-only behavior, secret hygiene,
  and transparent recommendations. Dreads credential leaks, unintended actions,
  and unverified automated decisions.

These principles shaped the architecture: bounded GitHub retrieval, a small
LLM triage step, validation, and deterministic ranking in Python. Provider choice
is configurable. Reports include source links and sampling limits, and leave
the final decision with the maintainer. These are design choices, not guarantees
that the AI will always get the priorities right.

## Scoping under time constraints

I prioritized a working, useful assistant while leaving time for debugging,
testing, a live demo, and improvements. I deliberately avoided complex agent
frameworks, dashboards, and automatic GitHub writes. Time-window reporting and
date-stamped exports made the reports easier to interpret and keep track of.

## Reflection and future improvement

With more time, I would evaluate prioritization against real maintainer feedback:
are the suggested priorities useful, and do the next actions help? Passing tests
and changing the order of issues do not answer those questions.

I am also interested in how similar decision-support workflows could apply to
TechBio and pharmaceutical R&D, with domain-specific evaluation and human review.
