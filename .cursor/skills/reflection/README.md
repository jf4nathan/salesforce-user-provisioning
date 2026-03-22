# reflection

Review a Claude Code session to capture lessons learned and improve your `CLAUDE.md`.

## What it does

At the end of a session, run `/reflection`. Claude will:
1. Scan the conversation for mistakes, corrections, and knowledge you shared
2. Produce a structured report of findings
3. Propose ready-to-paste improvements for your `CLAUDE.md`
4. Apply the ones you approve

## Usage

```
/reflection
```

No setup required. Run it at the end of any session where:
- Claude made mistakes or wrong assumptions
- You corrected Claude or provided domain context
- You want to capture knowledge so Claude doesn't repeat the same errors
- You did clean, successful work and want to preserve what you explained along the way

## What it looks for

| Category | What it captures |
|----------|-----------------|
| **Corrections** | Times you told Claude it was wrong |
| **Wrong assumptions** | Cases where Claude assumed something without checking |
| **Dig-deeper prompts** | Times you asked Claude to verify or look deeper |
| **New domain knowledge** | Facts or patterns that emerged from fixing mistakes |
| **Proactive knowledge** | Context you shared during successful work (no mistake needed) |

## Output

A report with:
- Table of corrections and mistakes
- Key learnings from mistakes
- Proactive domain knowledge captured from successful work
- Ready-to-paste content blocks for `CLAUDE.md` (project or global)

You decide which improvements to apply. Claude edits the files directly.
