---
name: reflection
description: Analyze the current conversation to extract learnings from user corrections, wrong assumptions, new domain knowledge, and proactive context shared during successful work, then propose generalized AGENTS.md and Cursor rule improvements. Use at the end of a working session to capture lessons learned. Use when the user asks to reflect on the conversation, learn from mistakes, or improve agent guidance.
---

# Conversation Reflection

Analyze the current conversation to identify mistakes, corrections, proactive domain knowledge shared during successful work, and new learnings, then produce a structured report with proposed rule and AGENTS.md improvements.

## When To Use

- End of a working session to capture lessons learned
- After a conversation with multiple corrections or new learnings
- When the user explicitly asks to reflect, summarize mistakes, or improve agent rules

## Workflow

### Step 1: Scan the Conversation

Review the full conversation history and categorize each significant interaction into one of these buckets:

**Bucket A - User Corrections**: Instances where the user explicitly said the agent was wrong, corrected a claim, or provided the right answer after the agent gave a wrong one.
- Look for phrases like: "no, that's wrong", "actually it's...", "that's not how it works", "incorrect", "not quite"

**Bucket B - Wrong Assumptions**: Instances where the agent made assumptions that turned out to be incorrect, even if the user didn't explicitly call them out. This includes:
- Inferring behavior from names instead of checking actual configuration or code
- Assuming how a system works without verifying
- Guessing at field meanings or object relationships
- Stating something confidently that later proved false

**Bucket C - Dig-Deeper Prompts**: Instances where the user asked the agent to verify, look deeper, or not trust surface-level information. These signal areas where the agent's default behavior was insufficient.
- Look for: "can you check the actual code?", "don't assume", "verify that", "are you sure?", "look at the metadata"

**Bucket D - New Domain Knowledge (from mistakes)**: Facts, patterns, or concepts that emerged from correcting mistakes or wrong assumptions. This includes:
- How specific automations or integrations work internally
- Business logic nuances
- Naming convention traps (e.g., field API names that don't match their purpose)
- Team-specific conventions or processes

**Bucket E - Proactive Domain Knowledge (from successful work)**: Knowledge the user shared as context during tasks that completed successfully — not triggered by a mistake. Scan for this even when the conversation had zero errors. This includes:
- Operational context the user provided to explain *why* a change is needed (e.g., "this flow fires on every edit and causes timeouts")
- System behavior explained by the user (e.g., "that field is populated by a HubSpot sync, not user input")
- Configuration patterns and their effects (e.g., "record types control which picklist values are available")
- Debugging patterns the user demonstrated (e.g., "check the automation debug logs first")
- Relationships between config changes and runtime behavior
- Cause-and-effect knowledge from incident context (e.g., "we set X to 2 but it caused Y, so revert to 1")
- Look for: user explaining context before giving instructions, user describing failure symptoms, user sharing why a previous change didn't work

### Step 2: Summarize Findings

For **Buckets A, B, C, D** (mistake-triggered items), capture:
1. **What happened**: Brief description of the exchange
2. **What was wrong**: The specific incorrect assumption or error
3. **Root cause**: Why the mistake happened (e.g., "inferred from field name", "assumed standard behavior", "didn't check the metadata")

For **Bucket E** (proactive knowledge), capture:
1. **What happened**: Brief description of what the user explained
2. **What was learned**: The specific operational or domain knowledge
3. **Why it's valuable**: How knowing this in advance would improve future behavior (e.g., "would prevent misdiagnosis", "would allow correct config recommendation")

### Step 3: Generalize Into Rule Improvements

Transform the specific learnings into **generalized guidance** that would prevent similar mistakes across future sessions. The guidance should be:

- **General, not specific**: "Check field metadata to verify behavior" rather than "The XYZ field is populated by HubSpot sync"
- **Actionable**: Written as clear instructions the agent can follow
- **Scoped**: Each improvement should target either project-level or user-level rules based on applicability

**Targeting rules:**
- **Project-level** (`AGENTS.md` or `.cursor/rules/*.mdc`): Improvements specific to this repository, team's data assets, or domain. Use `AGENTS.md` for general conventions; create/update a `.cursor/rules/*.mdc` file for topic-specific guidance.
- **User-level** (Cursor Settings > Rules for AI): Improvements that apply to any project (general investigation habits, analysis discipline). Present these as text for the user to paste into their settings.

### Step 4: Read Current Rule Files

Before proposing changes, read the relevant files to:
1. Check if similar guidance already exists (avoid duplication)
2. Identify the right section to place new content
3. Match the existing writing style and formatting

Read these files:
- `AGENTS.md` (project conventions)
- Any relevant `.cursor/rules/*.mdc` files
- Note existing user rules (visible in system context) for deduplication

### Step 5: Produce the Report

Output a structured report with the following sections:

---

#### Report Format

```markdown
# Conversation Reflection Report

## Corrections & Mistakes

| # | What Happened | What Was Wrong | Root Cause |
|---|---------------|----------------|------------|
| 1 | ... | ... | ... |

## Key Learnings (from mistakes)

| # | Learning | Source (Bucket) | Generalized Principle |
|---|----------|-----------------|----------------------|
| 1 | ... | Correction / Assumption / Dig-Deeper / New Knowledge | ... |

## Proactive Domain Knowledge (from successful work)

| # | Context Shared by User | What Was Learned | Why It's Valuable |
|---|----------------------|------------------|-------------------|
| 1 | ... | ... | ... |

## Proposed Rule Improvements

### Project-Level (`AGENTS.md` or `.cursor/rules/*.mdc`)

**Target file**: [AGENTS.md or specific .mdc file]
**Section**: [which existing section to add to, or new section name]
**Rationale**: [why this helps]

\```
[ready-to-paste content block]
\```

### User-Level (Cursor Settings > Rules for AI)

**Rationale**: [why this helps]

\```
[ready-to-paste content block]
\```

## Summary

- **Total corrections**: N
- **Total new learnings (from mistakes)**: N
- **Total proactive domain learnings**: N
- **Rule changes proposed**: N (M project-level, K user-level)
```

---

### Step 6: Offer to Apply

After presenting the report, ask the user:
1. Which proposed improvements to apply
2. Whether any should be adjusted before applying
3. Whether to apply to project-level rules, user-level rules, or both

For project-level changes, use the `StrReplace` or `Write` tool to apply approved changes to `AGENTS.md` or `.cursor/rules/*.mdc` files. For user-level changes, present the text for the user to paste into Cursor Settings > Rules for AI.

## Guidelines

- **Do not invent learnings**: Only report actual mistakes, corrections, or knowledge explicitly shared by the user. Do not fabricate incidents or infer knowledge the user didn't provide.
- **A clean conversation is not an empty reflection**: If there were no mistakes, the Corrections section will be empty — but still scan for Bucket E (proactive knowledge). A conversation can be mistake-free and still contain valuable domain knowledge worth capturing.
- **Be honest about severity**: Not every correction is an AGENTS.md-worthy improvement. Minor misunderstandings or typos are not worth codifying. Focus on patterns that would recur.
- **Deduplicate**: If multiple corrections stem from the same root cause, group them under one improvement.
- **Preserve existing content**: When adding to AGENTS.md or rule files, append or insert — never remove existing guidance unless it directly contradicts a correction.
- **Match formatting**: Follow the existing markdown style of the target file (headers, bullet styles, code blocks).

## Updating This Skill

When running this skill, update this file with errors, edge cases, improved workflows, and any changes to Cursor rule conventions, AGENTS.md structure, or reflection patterns that affect the workflow.
