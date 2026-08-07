---
name: writing-plans
description: Use when you have a spec or requirements for a multi-step task, before touching code
---

# Writing Plans

## Overview

Write comprehensive implementation plans assuming the engineer has zero context for our codebase and questionable taste. Document everything they need to know: which files to touch for each task, code, testing, docs they might need to check, how to test it. Give them the whole plan as bite-sized tasks. DRY. YAGNI. TDD. Frequent commits.

Assume they are a skilled developer, but know almost nothing about our toolset or problem domain. Assume they don't know good test design very well.

**Announce at start:** "I'm using the writing-plans skill to create the implementation plan."

<!-- LOCAL OVERRIDE START: skill reference compatibility; mode=replace -->

**Context:** If working in an isolated worktree, it should have been created at execution time using an available worktree capability. When using a matching skill, resolve `superpowers:using-git-worktrees` first and `using-git-worktrees` otherwise.

<!-- LOCAL OVERRIDE END: skill reference compatibility -->

**Save plans to:** `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md`

- (User preferences for plan location override this default)

## Scope Check

If the spec covers multiple independent subsystems, it should have been broken into sub-project specs during brainstorming. If it wasn't, suggest breaking this into separate plans — one per subsystem. Each plan should produce working, testable software on its own.

## File Structure

Before defining tasks, map out which files will be created or modified and what each one is responsible for. This is where decomposition decisions get locked in.

- Design units with clear boundaries and well-defined interfaces. Each file should have one clear responsibility.
- You reason best about code you can hold in context at once, and your edits are more reliable when files are focused. Prefer smaller, focused files over large ones that do too much.
- Files that change together should live together. Split by responsibility, not by technical layer.
- In existing codebases, follow established patterns. If the codebase uses large files, don't unilaterally restructure - but if a file you're modifying has grown unwieldy, including a split in the plan is reasonable.

This structure informs the task decomposition. Each task should produce self-contained changes that make sense independently.

## Task Right-Sizing

A task is the smallest unit that carries its own test cycle and is worth a
fresh reviewer's gate. When drawing task boundaries: fold setup,
configuration, scaffolding, and documentation steps into the task whose
deliverable needs them; split only where a reviewer could meaningfully
reject one task while approving its neighbor. Each task ends with an
independently testable deliverable.

## Bite-Sized Task Granularity

**Each step is one action (2-5 minutes):**

- "Write the failing test" - step
- "Run it to make sure it fails" - step
- "Implement the minimal code to make the test pass" - step
- "Run the tests and make sure they pass" - step
- "Commit" - step

## Plan Document Header

**Every plan MUST start with this header:**

<!-- LOCAL OVERRIDE: optional execution handoff; target=plan-document-header-agentic-worker-note; mode=replace -->

```markdown
# [Feature Name] Implementation Plan

> [!NOTE]
> **For agentic workers:** `subagent-driven-development` and
> `executing-plans` are optional execution helpers. When resolving either
> skill, prefer the namespaced form (`superpowers:<skill-name>`) when
> available, then the bare `<skill-name>` form.
>
> This name-resolution order does not give those skills priority over the
> current agent or host framework's native execution/delegation capabilities.
> Choose the execution approach based on the implementation plan, user
> instructions, available capabilities, and the host framework's own
> routing/delegation policy. Do not automatically search for or install
> missing skills.
>
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

## Global Constraints

[The spec's project-wide requirements — version floors, dependency limits,
naming and copy rules, platform requirements — one line each, with exact
values copied verbatim from the spec. Every task's requirements implicitly
include this section.]

---
```

## Task Structure

````markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

**Interfaces:**
- Consumes: [what this task uses from earlier tasks — exact signatures]
- Produces: [what later tasks rely on — exact function names, parameter
  and return types. A task's implementer sees only their own task; this
  block is how they learn the names and types neighboring tasks use.]

- [ ] **Step 1: Write the failing test**

```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/path/test.py::test_name -v`
Expected: FAIL with "function not defined"

- [ ] **Step 3: Write minimal implementation**

```python
def function(input):
    return expected
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/path/test.py::test_name -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/path/test.py src/path/file.py
git commit -m "feat: add specific feature"
```
````

## No Placeholders

Every step must contain the actual content an engineer needs. These are **plan failures** — never write them:
- "TBD", "TODO", "implement later", "fill in details"
- "Add appropriate error handling" / "add validation" / "handle edge cases"
- "Write tests for the above" (without actual test code)
- "Similar to Task N" (repeat the code — the engineer may be reading tasks out of order)
- Steps that describe what to do without showing how (code blocks required for code steps)
- References to types, functions, or methods not defined in any task

## Self-Review

After writing the complete plan, look at the spec with fresh eyes and check the plan against it. This is a checklist you run yourself — not a subagent dispatch.

**1. Spec coverage:** Skim each section/requirement in the spec. Can you point to a task that implements it? List any gaps.

**2. Placeholder scan:** Search your plan for red flags — any of the patterns from the "No Placeholders" section above. Fix them.

**3. Type consistency:** Do the types, method signatures, and property names you used in later tasks match what you defined in earlier tasks? A function called `clearLayers()` in Task 3 but `clearFullLayers()` in Task 7 is a bug.

If you find issues, fix them inline. No need to re-review — just fix and move on. If you find a spec requirement with no task, add the task.

## Execution Handoff

<!-- LOCAL OVERRIDE START: optional execution handoff -->

> [!NOTE]
> `subagent-driven-development` and `executing-plans` are optional execution
> helpers in this curated subset. When resolving either skill, prefer the
> namespaced form (`superpowers:<skill-name>`) when available, then the bare
> `<skill-name>` form.
>
> This name-resolution order only determines which matching skill identity to
> use; it does not establish an execution priority. Matching execution skills,
> the current agent's capabilities, and the host framework's native
> execution/delegation mechanisms are all available execution options.
>
> Choose the execution approach based on the actual implementation plan, user
> instructions, available capabilities, and the host framework's own
> delegation/routing policy. Do not use subagents merely because they are
> available, and do not automatically search for or install missing skills.

After saving the plan, determine the appropriate execution handoff.

### When subagent delegation would materially help

If the current agent or host framework supports subagents and the actual plan
would meaningfully benefit from delegation, propose a concrete subagent
composition based on the work in the plan.

Do not blindly create one subagent per task.

Group delegation only where it provides a real benefit, such as:

* independent areas of responsibility
* specialist knowledge
* independent research
* genuinely parallelizable work
* useful context isolation

The proposed roles must come from the actual plan. Do not use a fixed set of
subagent roles merely as a template.

Then offer the user two choices:

1. **Subagent-assisted execution** — execute the plan using the proposed
   delegation structure. Use whichever available subagent/delegation
   mechanism best fits the plan and host framework; an available matching
   `subagent-driven-development` skill is one such option.

2. **Direct execution** — execute the plan in the current agent/session
   without imposing a predefined subagent workflow. An available matching
   `executing-plans` skill may be used when appropriate, but is not required.

### When subagent delegation would not materially help

Do not invent a subagent composition just to provide another option.

Ask the user whether to proceed with direct execution of the implementation
plan.

<!-- LOCAL OVERRIDE END: optional execution handoff -->
