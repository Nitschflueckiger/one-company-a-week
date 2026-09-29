# One company a week, from its own annual report

An Instagram page run by a scheduled Claude agent. Every week one US-listed company,
explained only from its Form 10-K (SEC): a carousel, two reels, two single numbers, a
term explained, a question. Education, not investment advice.

- `agent/` — the code the agent calls (`python -m agent …`)
- `CLAUDE.md` — the agent's rules; `ROUTINE.md` — what one scheduled run does
- `docs/medien/` — the pictures and reels, served to Instagram through jsDelivr
- `tests/` — run with `python -m pytest -q tests` (no network)

The environment needs `IG_USER_ID`, `IG_TOKEN`, `IG_TOKEN_ERSTELLT` (date the token was
made, YYYY-MM-DD), `IG_HANDLE`, `MEDIEN_REPO` (owner/name of this repository),
`QUELLE_URL` (the week's company as JSON) and `VERBOTENE_NAMEN` (comma-separated names
that must never appear in a post or reply), plus network access to
`graph.instagram.com`, the host of `QUELLE_URL`, `cdn.jsdelivr.net`, `pypi.org`,
`files.pythonhosted.org` and `github.com`.
