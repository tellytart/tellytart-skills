# tellytart-skills

Skills I use with Claude, published in case they are useful to someone else.

A skill is a folder holding a `SKILL.md` (the instructions Claude follows) plus any scripts
or reference files it needs. Each skill here has its own README covering what it does and
what it needs before it will work.

## Skills

| Skill | What it does |
|---|---|
| [`keyword-mcp`](skills/keyword-mcp/) | Keywords the photos selected in Adobe Lightroom Classic through a Lightroom MCP server, using only the catalog's existing keyword hierarchy. |

## Layout

```
skills/
  <skill-name>/
    SKILL.md      the skill itself
    README.md     prerequisites, installation and notes
    scripts/      helper scripts the skill calls, if any
```

## Using a skill

Read the skill's README first: most of the work is in the prerequisites. These skills
started life on my own setup, so check the paths and defaults suit yours.
