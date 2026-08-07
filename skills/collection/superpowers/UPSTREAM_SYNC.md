# Superpowers Upstream Sync Guide

This document defines how an LLM / coding agent should update the curated
Superpowers skills in this repository while preserving the intentionally small
set of local compatibility adjustments.

Upstream:

```text
https://github.com/obra/superpowers
```

Curated location:

```text
skills/collection/superpowers/
```

Currently curated skills:

```text
brainstorming
writing-plans
using-git-worktrees
```

The goal is:

> Keep the curated skills as close to upstream as possible while preserving
> only explicitly documented compatibility adjustments.

Do not treat this repository as an independent fork of Superpowers.

---

## Core rule

When updating from upstream:

1. Start from the new upstream version.
2. Preserve upstream changes wherever possible.
3. Re-apply only the local compatibility adjustments documented below.
4. Do not carry unrelated historical differences forward.
5. Do not rewrite upstream methodology merely to make the local diff smaller.
6. Do not blindly re-apply an old local override if upstream has changed the
   relevant behavior.

The desired result is:

```text
new upstream
+
small documented compatibility overrides
=
current curated copy
```

not:

```text
old local copy
+
selected upstream edits
```

---

# Files expected to remain upstream-identical

Unless a future documented compatibility adjustment explicitly says otherwise,
the following should remain identical to the selected upstream revision:

```text
skills/collection/superpowers/brainstorming/**
skills/collection/superpowers/using-git-worktrees/**
```

Supporting files inside those skill directories should also be copied from
upstream unchanged.

For `writing-plans`, files other than explicitly documented overrides should
also remain upstream-identical.

Do not opportunistically modify:

- TDD guidance
- RED → GREEN steps
- checkbox tracking
- task decomposition
- testing guidance
- Self-Review
- file/interface planning
- worktree lifecycle
- Git behavior
- reviewer behavior
- other upstream methodology

unless a separate local override is explicitly documented.

---

# Local override types

Local compatibility adjustments use one of two semantic modes:

```text
replace
insert
```

These modes are important.

They describe how the local change relates to upstream.

---

## `mode=replace`

A replace override means:

> The local block semantically replaces an upstream block.

The original upstream block and the local replacement MUST NOT both remain
active when they contain conflicting instructions.

Example:

```text
upstream:
REQUIRED SUB-SKILL

local:
optional execution helper
```

These instructions conflict.

Correct:

```diff
- REQUIRED SUB-SKILL ...
+ optional execution helper ...
```

Incorrect:

```text
REQUIRED SUB-SKILL ...

[NOTE]
Actually this skill is optional.
```

The second form leaves conflicting instructions in the same skill and can
confuse the LLM.

### Updating a replace override

When upstream changes:

1. Locate the corresponding semantic block in the new upstream version.
2. Read the new upstream behavior.
3. Determine whether the original reason for the local override still exists.
4. If the issue still exists, apply the local replacement against the NEW
   upstream structure.
5. If upstream already solves the compatibility issue, do not blindly restore
   the old replacement.
6. Report that the override may now be obsolete.

Never re-apply a replace override by line number alone.

Use semantic context.

---

## `mode=insert`

An insert override means:

> The upstream content remains valid and the local block only adds additional
> compatibility information or behavior.

For an insert override:

1. Preserve the new upstream block.
2. Reinsert the local addition at the appropriate semantic anchor.
3. Do not replace upstream text unless the override is explicitly changed to
   `mode=replace`.

Example:

```text
upstream paragraph

<!-- LOCAL OVERRIDE START: example; mode=insert -->
local compatibility note
<!-- LOCAL OVERRIDE END: example -->

next upstream paragraph
```

---

# Marker conventions

Normal local blocks should use:

```html
<!-- LOCAL OVERRIDE START: <id>; mode=<replace|insert> -->

...

<!-- LOCAL OVERRIDE END: <id> -->
```

If the existing marker omits `mode=...`, consult this document and the
surrounding semantics before changing it.

Do not rename existing override IDs unnecessarily.

Stable marker names help future automated updates.

---

# Special case: generated document templates

A local compatibility replacement may sometimes occur inside a fenced template
that is copied into generated output.

For example, `writing-plans` contains the template used to generate:

```text
docs/superpowers/plans/*.md
```

Repository-maintenance markers must NOT accidentally become part of every
generated plan.

Therefore, a local replacement inside a generated template may use a
single metadata annotation OUTSIDE the code fence:

```html
<!-- LOCAL OVERRIDE: optional execution handoff; target=plan-document-header-agentic-worker-note; mode=replace -->
```

followed by:

````text
```markdown
content that should actually appear in generated plans
```
`````

The maintenance marker stays outside the generated template.

The generated template itself should contain only content intended for the
generated document.

Do not move repository-maintenance comments inside the template merely to make
the marker style uniform.

---

# Current `writing-plans` compatibility adjustments

`writing-plans` currently contains compatibility adjustments for two purposes.

---

## 1. Optional/contextual execution handoff

### Upstream behavior

Upstream `writing-plans` may refer to:

```text
subagent-driven-development
executing-plans
```

as required execution sub-skills and may prescribe a fixed execution workflow.

This curated subset intentionally does not require those execution skills.

### Local behavior

Those execution helpers are optional capabilities.

They do not have automatic priority over:

* the current agent's native execution capabilities
* host-framework subagents
* host-framework routing/delegation
* direct execution
* other available execution mechanisms

The execution mechanism should be selected based on:

* the actual implementation plan
* user instructions
* available capabilities
* host-framework routing/delegation policy

Do not use subagents merely because they are available.

Do not automatically search for or install a missing execution skill.

### Subagent decision

When subagent delegation would materially help:

1. Derive a concrete delegation structure from the actual plan.
2. Do not blindly create one subagent per task.
3. Group work according to meaningful responsibilities, specialist needs,
   independent research, parallelizable work, or useful context isolation.
4. Offer:

   * subagent-assisted execution
   * direct execution

When subagent delegation would NOT materially help:

* do not invent a subagent structure
* ask whether to proceed with direct execution

An available matching `subagent-driven-development` skill is one possible
subagent execution mechanism, not a mandatory or preferred mechanism.

An available matching `executing-plans` skill is one possible direct/inline
execution helper, not a requirement.

---

## 2. Skill-name compatibility

Different installation mechanisms may expose a matching skill using either a
namespaced or bare identity.

When resolving a referenced Superpowers skill, use this lookup order:

```text
superpowers:<skill-name>
        ↓ unavailable
<skill-name>
        ↓ unavailable
unavailable
```

Example:

```text
superpowers:using-git-worktrees
        ↓
using-git-worktrees
```

and:

```text
superpowers:subagent-driven-development
        ↓
subagent-driven-development
```

Important:

> This is skill identity resolution order, NOT execution priority.

For example:

```text
superpowers:subagent-driven-development
```

being found first does NOT mean it should take precedence over the current host
framework's native delegation system.

The resolution rule only answers:

> Which identity refers to this matching skill in the current environment?

It does not answer:

> Which execution mechanism should be used?

Do not automatically search for or install a referenced skill merely because
neither identity is currently available.

---

# Current marker locations in `writing-plans`

The current compatibility adjustments should remain easy to locate.

Conceptually they include:

### Worktree skill reference compatibility

Near the `Context` section:

```text
superpowers:using-git-worktrees
→ using-git-worktrees
```

This is a local skill-reference compatibility replacement.

### Plan Document Header

The upstream required execution instruction is replaced by an optional,
framework-neutral NOTE.

Because this replacement is inside a generated-plan template, its maintenance
annotation is outside the template code fence.

Expected marker form:

```html
<!-- LOCAL OVERRIDE: optional execution handoff; target=plan-document-header-agentic-worker-note; mode=replace -->
```

Do not put that maintenance marker inside the generated plan template.

### Execution Handoff

The final execution handoff is a local replacement.

It should remain enclosed by clearly identifiable local override markers.

Do not restore the upstream required execution workflow alongside the local
replacement.

---

# Upstream changes that overlap an override

If the new upstream revision modifies a block touched by a local override, do
NOT mechanically copy the previous local block back.

Instead:

1. Compare the OLD upstream block.
2. Compare the NEW upstream block.
3. Read the local override purpose.
4. Determine whether the local compatibility problem still exists.

Possible outcomes:

### A. Upstream behavior is unchanged

Re-apply the local override.

### B. Upstream changed, but the compatibility problem still exists

Adapt the local override to the new upstream structure while preserving only
the intended compatibility behavior.

### C. Upstream has solved the compatibility problem

Do not duplicate the fix.

Report:

```text
The upstream behavior now appears to satisfy the purpose of local override
<id>. This override may be removable.
```

Do not remove it silently if doing so would materially change behavior.

### D. Upstream and local behavior now conflict in a new or ambiguous way

Stop automatic modification of that block and report the conflict for review.

Do not guess.

---

# Sync procedure

When asked to update this curated Superpowers collection:

## Step 1 — Inspect current state

Read:

```text
skills/collection/superpowers/UPSTREAM_SYNC.md
README.md
skills/collection/superpowers/**
```

Identify:

* current upstream revision
* currently documented local overrides
* current marker locations

---

## Step 2 — Determine upstream target

Determine the requested upstream revision.

If the user says "latest", resolve the latest upstream revision and record the
exact commit SHA.

Do not silently change revisions if a specific SHA was requested.

---

## Step 3 — Obtain clean upstream copies

For each curated skill:

```text
brainstorming
writing-plans
using-git-worktrees
```

obtain the complete corresponding upstream directory, including supporting
files.

Do not copy additional Superpowers skills merely because they are referenced.

The curated subset remains intentionally limited.

---

## Step 4 — Compare old upstream → new upstream

Before applying local overrides, inspect upstream changes.

Pay special attention to areas corresponding to local compatibility
adjustments.

Do not use the current modified local copy as the only basis for understanding
upstream changes.

---

## Step 5 — Build from the new upstream version

Conceptually:

```text
new upstream copy
        ↓
re-evaluate documented local overrides
        ↓
apply only still-needed overrides
```

Do NOT incrementally merge random upstream changes into the previous local
file.

---

## Step 6 — Re-apply local overrides

For every override:

### `mode=replace`

* find the new semantic target
* verify the incompatibility still exists
* replace the corresponding upstream block
* do not leave conflicting upstream instructions active

### `mode=insert`

* preserve new upstream text
* insert the local block at its semantic anchor

### template-internal replacement

* keep maintenance annotation outside generated template fences
* keep only generated content inside the template

---

## Step 7 — Preserve skill-name resolution semantics

References affected by local compatibility should continue to resolve:

```text
superpowers:<name>
→ <name>
→ unavailable
```

unless the current skill ecosystem provides a confirmed native alias mechanism
that makes the local compatibility rule unnecessary.

Do not invent unsupported YAML fields such as aliases.

If the current skill loader now officially supports aliases or namespace
fallback, report that before changing the local compatibility implementation.

---

## Step 8 — Validate unrelated upstream content

Check that local modifications did not accidentally alter unrelated upstream
content.

Common accidental changes to detect:

* `-` changed to `*`
* code fence length changed
* blank lines inserted throughout the file
* file permissions changed
* wording reformatted without semantic reason
* supporting files rewritten
* unrelated Markdown cleanup
* automatic formatter churn

These should normally be reverted.

A compatibility update should not become a formatting refactor.

---

# Validation

After updating, run appropriate checks.

At minimum inspect:

```bash
git diff --check
git diff --summary
git status --short
git diff -- skills/collection/superpowers/
```

Also inspect local markers, for example:

```bash
grep -RniF 'LOCAL OVERRIDE' skills/collection/superpowers/
```

Do not merely state that checks passed.

Base the report on actual command output.

---

## Validate upstream-identical skills

Confirm that:

```text
brainstorming
using-git-worktrees
```

remain identical to the selected upstream revision unless a documented local
override explicitly says otherwise.

Use recursive diff or checksums when practical.

---

## Validate `writing-plans`

Confirm:

* unrelated upstream methodology remains unchanged
* checkbox tracking remains present
* RED → GREEN planning remains present
* TDD guidance remains present
* task structure remains present
* no accidental code-fence changes exist
* no unrelated bullet-style changes exist
* no required execution dependency was accidentally restored
* skill identity resolution is still:
  `superpowers:<name>` → `<name>` → unavailable
* that resolution order is NOT presented as execution priority
* native/framework execution is not merely a fallback after Superpowers
* missing referenced skills do not trigger automatic installation
* subagent delegation is conditional on actual benefit
* direct execution remains available
* repository-maintenance markers do not leak into generated plan templates

---

# README updates

If the upstream revision changes, update the recorded upstream commit SHA.

If the local compatibility behavior changes, update the README NOTE.

README must accurately distinguish:

```text
upstream behavior
```

from:

```text
local curated-subset compatibility behavior
```

Do not claim a modified skill is an untouched upstream copy.

Do not claim a local compatibility behavior originated upstream.

If an override becomes unnecessary because upstream incorporated equivalent
behavior, update the README accordingly.

---

# License

Keep the upstream Superpowers license at:

```text
skills/collection/superpowers/LICENSE
```

Do not remove or rewrite the upstream license.

Do not create additional NOTICE files unless required by a future licensing
change or explicitly requested.

---

# What not to do during sync

Do not:

* import the complete Superpowers repository
* automatically add referenced Superpowers skills
* install missing skills
* redesign upstream methodology
* remove TDD merely for local preference
* remove testing guidance
* change worktree behavior for local project preferences
* add fixed subagent-per-task orchestration
* impose the local host framework on all users
* change Git policy for token optimization
* refactor unrelated README sections
* reformat unrelated Markdown
* change file permissions accidentally
* commit or push unless explicitly requested

Project/user-specific policy belongs outside the copied upstream skill whenever
possible.

---

# Expected final report

After an upstream sync, report:

1. Previous upstream SHA.
2. New upstream SHA.
3. Upstream changes relevant to the curated skills.
4. Which local overrides were re-applied.
5. Which overrides required adaptation.
6. Whether any override appears obsolete because upstream solved it.
7. Whether `brainstorming` remains upstream-identical.
8. Whether `using-git-worktrees` remains upstream-identical.
9. Whether unrelated `writing-plans` content remains upstream-identical.
10. Actual local override marker locations.
11. Validation results.
12. Any unresolved upstream/local semantic conflicts.

Do not commit or push unless explicitly requested.

---

# Quick decision table

| Situation                                                     | Action                                     |
| ------------------------------------------------------------- | ------------------------------------------ |
| Upstream changed unrelated content                            | Accept new upstream                        |
| Local `mode=replace` target unchanged                         | Re-apply replacement                       |
| Local `mode=insert` anchor unchanged                          | Reinsert local block                       |
| Upstream changed overridden block                             | Re-evaluate semantically                   |
| Upstream now solves local problem                             | Report override as possibly obsolete       |
| New upstream behavior conflicts ambiguously with local intent | Stop and report                            |
| Formatting differs accidentally                               | Restore upstream formatting                |
| Generated template contains maintenance marker                | Move maintenance metadata outside template |
| `superpowers:<name>` unavailable                              | Try bare `<name>`                          |
| Both skill identities unavailable                             | Treat skill as unavailable                 |
| Matching execution skill exists                               | Treat it as one execution option           |
| Native/framework execution exists                             | Treat it as one execution option           |
| Subagent delegation adds little value                         | Do not invent subagents                    |
