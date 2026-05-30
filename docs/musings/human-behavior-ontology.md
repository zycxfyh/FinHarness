# Human Behavior Ontology

This document defines a first-principles map for studying human behavior.
It is not a demographic stereotype table. It is a system for decomposing
observable behavior into context, incentives, constraints, choices, and feedback.

The goal is to build a behavior atlas that can support learning, research,
product design, finance, AI agents, and social analysis without becoming a
Wikipedia-style list of disconnected facts.

## Difference From Wikipedia

Wikipedia answers:

```text
What is this thing?
When did it happen?
Who is involved?
What are the named categories?
```

This ontology answers:

```text
What problem is the person solving?
What constraints shape the behavior?
What resources do they have?
What role are they acting in?
What choice do they make?
What feedback changes future behavior?
```

Wikipedia is mostly noun-centered.
This system is behavior-centered.

Wikipedia stores facts.
This system stores reusable causal structure.

## Core Principle

Human behavior is not determined by identity. It emerges from:

```text
Biology + environment + resources + institutions + relationships + incentives + memory
```

A safer behavior model says:

```text
Context changes probability.
It does not determine the person.
```

Use demographic variables as coordinates, not as destiny.

## Occam Layer

Before adding any category, ask:

1. Does it change constraints?
2. Does it change incentives?
3. Does it change available actions?
4. Does it change risk?
5. Does it change feedback?

If not, remove it.

## Top-Level Map

The whole system can be compressed into this loop:

```text
Need -> Context -> Options -> Action -> Outcome -> Feedback -> Updated behavior
```

Every behavior record should fit this schema:

```text
Actor context:
Need:
Available resources:
Institutional environment:
Social role:
Action:
Cost:
Reward:
Risk:
Feedback:
```

## Level 0: Universal Human Drivers

These are close to universal and should be studied before demographic splits.

```text
Survival: food, health, shelter, safety
Belonging: family, friends, tribe, status group
Status: respect, rank, recognition, autonomy
Reproduction/care: mating, parenting, kin support
Meaning: religion, identity, story, purpose
Control: predictability, agency, optionality
Learning: skill, curiosity, adaptation
Pleasure: comfort, entertainment, novelty
```

Use these as root causes, not moral judgments.

## Level 1: Life Stage

Age matters because it changes biology, dependency, time horizon, legal status,
energy, social expectation, and accumulated capital.

```text
Infancy: dependence, attachment, basic safety
Childhood: play, imitation, schooling, family norms
Adolescence: identity, peers, status, risk-taking
Early adulthood: mate choice, education, first work, mobility
Young adulthood: career formation, family formation, asset building
Middle adulthood: responsibility, specialization, status maintenance
Late adulthood: health, legacy, risk reduction, family transfer
End of life: care, dignity, inheritance, meaning
```

Do not use age alone. Pair it with role and resources.

Example:

```text
18-year-old student in a rich city
18-year-old factory worker in a poor region
18-year-old conscript in wartime
```

Same age, different behavior constraints.

## Level 2: Place And Institution

Country and region matter because institutions change available paths.

Use this split:

```text
Legal system
Political stability
Currency and inflation regime
Education system
Labor market
Healthcare access
Housing system
Family norms
Digital infrastructure
Public safety
```

Country is a shortcut label. The real causes are institutions.

Better:

```text
Weak job market + expensive housing + credential-heavy education
```

Worse:

```text
People from Country X behave like Y
```

## Level 3: Culture, Language, And Identity

Culture matters, but it is dangerous as a first split because it easily becomes
stereotype. Use it only when it changes norms, trust, obligations, or meaning.

Useful variables:

```text
Language
Religion
Family structure
Gender norms
Honor/shame norms
Individualism/collectivism
Migration history
Minority/majority status
Urban/rural identity
```

Rule:

```text
Never infer individual behavior from ethnicity alone.
Use culture as a hypothesis, then check institution, class, role, and context.
```

## Level 4: Resource Position

Resources define realistic options.

Core resource axes:

```text
Household assets
Income stability
Debt burden
Education
Health
Time flexibility
Social capital
Digital access
Legal status
Geographic mobility
```

This layer is often more predictive than identity.

Example:

```text
High education + low assets -> seeks credentials, mobility, high-upside career
Low education + stable assets -> protects local position, avoids credential games
High income + high debt -> status pressure, fragile liquidity
Low income + strong family network -> informal insurance, local dependence
```

## Level 5: Social Role

People behave differently by role.

One person can be:

```text
Child
Student
Worker
Founder
Parent
Investor
Patient
Citizen
Consumer
Friend
Partner
Caregiver
Community member
Online identity
```

Behavior should be tagged by role.

Example:

```text
As a student: seeks grades and credentials.
As a worker: seeks income and stability.
As a son/daughter: responds to family obligation.
As an investor: seeks return and risk control.
```

## Level 6: Behavior Domains

Use domains to organize observable behavior.

```text
Work: labor, career, entrepreneurship, coordination
Learning: school, self-study, apprenticeship, exploration
Family: care, marriage, parenting, inheritance, conflict
Consumption: shopping, housing, food, entertainment
Finance: saving, borrowing, investing, insurance, gambling
Health: sleep, diet, exercise, treatment, avoidance
Social: friendship, status, dating, community, reputation
Media: attention, belief, identity, persuasion
Politics: voting, protest, compliance, ideology
Religion/meaning: ritual, morality, belonging, transcendence
Migration: moving, adapting, remitting, identity negotiation
Crime/conflict: rule-breaking, defense, coercion, revenge
Creativity: art, writing, building, play, expression
```

Each domain can be decomposed into behavior units.

## Level 7: Atomic Behavior Unit

An atomic behavior is the smallest useful behavior we want to model.

Format:

```text
Behavior:
Trigger:
Goal:
Cost:
Reward:
Risk:
Required resources:
Institutional dependency:
Social meaning:
Feedback:
```

Example:

```text
Behavior: choose a college major
Trigger: entrance into higher education
Goal: future income, identity, family approval, intellectual interest
Cost: tuition, time, opportunity cost
Reward: credential, skill, network, status
Risk: poor job market, mismatch, debt
Required resources: grades, information, money, guidance
Institutional dependency: admissions, labor market, credential value
Social meaning: family pride, class mobility, peer identity
Feedback: grades, internships, job offers, family response
```

## Level 8: Decision Pattern

Many behaviors are repeated decision patterns.

Common patterns:

```text
Explore vs exploit
Short-term relief vs long-term gain
Risk seeking vs risk avoidance
Status seeking vs security seeking
Conformity vs differentiation
Exit vs voice vs loyalty
Trust vs verify
Save vs spend
Learn vs perform
Cooperate vs defect
```

This layer is useful because the same pattern appears across many domains.

Example:

```text
Finance: save vs spend
Career: stable job vs startup
Education: broad exploration vs exam optimization
Relationships: conformity vs self-expression
```

## Recommended Data Structure

Use axes instead of one giant tree.

A tree forces one category path:

```text
Age -> Country -> Ethnicity -> Income -> Behavior
```

That becomes brittle and often misleading.

Use a multi-axis graph:

```text
Person/context node
  -> life_stage
  -> institution
  -> resources
  -> role
  -> domain
  -> behavior_unit
  -> feedback_loop
```

Better mental model:

```text
Graph, not hierarchy.
Coordinates, not labels.
Probabilities, not destiny.
```

## Minimal Schema

For our knowledge base, every behavior entry should use this template:

```text
# Behavior: <name>

## Definition
One sentence.

## Core Need
What human driver does this serve?

## Context Axes
- Life stage:
- Place/institution:
- Resource position:
- Social role:
- Domain:

## Process
Trigger -> options -> action -> outcome -> feedback

## Key Variables
The 3-7 variables that actually change the behavior.

## Metrics / Signals
How the behavior becomes observable.

## Failure Modes
What causes bad decisions or harm?

## Examples
Concrete cases, not stereotypes.
```

## Example: Learning Behavior

```text
Behavior: self-directed learning
Core need: capability, status, control, curiosity
Life stage: adolescence to adulthood
Resources: time, internet, language ability, mentor access
Role: student, worker, founder, hobbyist
Domain: learning
Trigger: perceived gap between current ability and desired identity/outcome
Options: course, book, project, mentor, community, exam
Action: practice with feedback
Reward: skill, confidence, credential, opportunity
Risk: shallow consumption, no feedback, distraction, fake mastery
Feedback: project quality, test score, job offer, peer review
```

## Example: Investing Behavior

```text
Behavior: buying a risky asset
Core need: future security, optionality, status, excitement
Life stage: usually late adolescence onward
Resources: disposable capital, market access, financial literacy
Role: investor, speculator, saver
Domain: finance
Trigger: surplus cash, social proof, fear of missing out, planned allocation
Options: cash, bond, fund, stock, crypto, business, education
Action: allocate capital
Reward: return, identity, learning, optionality
Risk: loss, leverage, fraud, liquidity trap, overconfidence
Feedback: price movement, income change, emotional reaction, portfolio review
```

## Example: Career Choice

```text
Behavior: choosing a first career path
Core need: income, identity, status, autonomy, belonging
Life stage: adolescence or early adulthood
Resources: education, family assets, city access, network, health
Role: student, worker, child, future provider
Domain: work
Trigger: graduation, family pressure, economic need, aspiration
Options: job, higher education, exam, entrepreneurship, migration
Action: commit time to a path
Reward: income, skill, identity, network
Risk: lock-in, credential mismatch, low wage, burnout
Feedback: salary, promotion, learning curve, social approval, regret
```

## Build Order

Do not start by mapping every human group.
Start by mapping universal behavior loops.

Recommended order:

1. Define universal human drivers.
2. Define life stages.
3. Define resource axes.
4. Define social roles.
5. Define behavior domains.
6. Define atomic behavior templates.
7. Add examples from different countries/classes/cultures.
8. Only then add demographic comparisons.

This order prevents the system from becoming a stereotype database.

## What To Build First

Start with 20 high-value behavior units:

```text
Choose a school
Choose a major
Self-study a skill
Look for a job
Choose a career path
Start a business
Save money
Borrow money
Buy a risky asset
Buy insurance
Rent or buy housing
Choose a partner
Support parents
Raise a child
Move to another city
Join a community
Consume short-form media
Trust an authority
Avoid medical care
Change belief after evidence
```

Each one can later branch by age, institution, resources, and culture.

## Design Rule

The behavior atlas should help us ask better questions:

```text
What is this person trying to solve?
What options are visible to them?
What constraints are invisible to outsiders?
What feedback teaches or traps them?
What would change the next action?
```

That is the difference between an encyclopedia and a living behavior model.

