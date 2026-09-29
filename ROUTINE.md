# One scheduled run

The routine runs three times a day: **08:30, 12:30 and 18:30 Zurich time**. Every run
answers comments and messages; the 12:30 and 18:30 runs may also post. Read
`CLAUDE.md` first.

## The week (Zurich time)

A new company appears every **Friday at 18:00**. One post a day, reels twice a week —
reels bring new people, carousels and single numbers get saved and shared.

| Day | Run | Post (`--was`) | What it is |
|---|---|---|---|
| Friday | 18:30 | `karussell` | the company in seven slides |
| Saturday | 12:30 | `zahl-1` | one striking number |
| Sunday | 18:30 | `reel` | the numbers in twenty seconds |
| Monday | 12:30 | `begriff` | one term, explained with this company |
| Tuesday | 12:30 | `zahl-2` | a second number |
| Wednesday | 18:30 | `reel2` | the same facts from the other side |
| Thursday | 12:30 | `frage` | a question for the comments |

Post only the entry of **today and this run**, and only if `lage` shows it as not yet
posted (`gepostet.<art>` is empty). Never post if `stunden_seit_letztem_beitrag` is
below 3. A missed slot is skipped, not caught up — except `karussell`: if Friday's
failed, post it at the next 12:30 or 18:30 run, and let the rest of the week follow.

## Steps

1. `pip install -q -r requirements.txt`
2. `python -m agent lage` — note `zeit_zuerich`, the company, `gepostet`, open comments
   and messages, `token_tage_uebrig`.
   - Token at 0 days or fewer: stop and report.
   - `firma` shows an error: skip posting, still answer comments and messages.
3. **If a post is due** (see the table):
   1. `python -m agent entwurf` — writes `drehbuch/<week>.json` and prints the
      sections of the company post.
   2. Rewrite the words of **the part you are about to post**, in plain English:
      - `karussell`: `titel`, `branche` (one or two words), `unterzeile` (one true line
        that makes someone stop scrolling), `was`, each scene `headline`, `dafuer`,
        `dagegen`, `caption` (3–6 short sentences), up to 8 `hashtags`.
      - `reel`: `caption` (shorter; it sits under a video).
      - `zahl-1`, `zahl-2`: the entry in `zahlen` — `zahl` (at most 8 characters,
        e.g. `$1.6bn`, `4.5%`, `4x`), `zeile`, `caption`.
      - `begriff`: pick the term this company teaches best (operating margin, free
        cash flow, debt, revenue growth…); `szene.art` is the matching chart
        (`umsatz`, `marge`, `fcf`, `bilanz`).
      - `reel2`: `unterzeile`, the scenes and their headlines, `caption`.
      - `frage`: a question people can answer from the post, no opinion on the stock.
      Use only numbers that appear in the facts.
   3. `python -m agent pruefe drehbuch/<week>.json` until `ok: true`.
   4. `python -m agent posten drehbuch/<week>.json --was <art>`
4. **Comments** — for each entry in `offene_kommentare`: answer with
   `python -m agent antworten --kommentar <id> --text "…"`, hide spam with
   `python -m agent verbergen --kommentar <id>`, or leave it (CLAUDE.md §3).
5. **Messages** — for each entry in `offene_nachrichten`: answer with
   `python -m agent schreiben --an <id> --text "…"`, or leave it.
6. **Summary** (the last thing you write): token days left · what was posted, with the
   link · comments and messages answered · hidden · "Left for a human": each item
   with the link and one line why.
