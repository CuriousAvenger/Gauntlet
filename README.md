# Gauntlet

A research template for AI agents. Every claim in the report shows how it was checked:
facts carry exact quotes from saved sources, and new ideas carry the tests they passed
or failed, or say they are untested.

## Use it

1. Copy this repo into a new folder for one research problem.
2. Write your question in `AGENTS.md`.
3. Ask your agent to research it. The result is `report.md`.

Works with any agent that has a shell. Needs Python 3.10+.
Optional: set `OPENALEX_API_KEY` (free) for wider literature search.

## How it works

The agent does the reading, thinking and writing by following `.skills/gauntlet/SKILL.md`.
Small scripts check what a model can't be trusted to check itself:

- **Sources** are fetched and saved by Gauntlet, so quotes are matched word for word.
- **Numbers** in a claim must appear in a quote or a test log.
- **Ideas** must quote their closest prior work; duplicates are refused.
- **Tests** run on hidden seeds the agent never sees, and must be replicated independently.
- **Labels** are refused unless the evidence earns them, and re-checked before the report.

Ideas compete in a tournament and evolve over generations, so the report also lists the
most promising untested leads.
