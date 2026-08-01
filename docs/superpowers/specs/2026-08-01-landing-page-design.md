# Klarwert Landing Page Design

Date: 2026-08-01

## Purpose

A simple, shareable marketing page for Klarwert that links to the GitHub
repository. It exists so strangers who are handed a link can understand what
the project is, why it is trustworthy (local-first), and where to get the code.

## Hosting

- Static page served by GitHub Pages from the `/docs` folder of the repo.
- One-time repo setting: Settings → Pages → Deploy from branch `main`, path `/docs`.
- No build step, no external resources, no JavaScript required.

## Files

- `docs/index.html` — semantic HTML, no JS.
- `docs/style.css` — reuses the app's existing palette:
  - bg `#0d1117`, surface `#161b22`, elevated `#21262d`, border `#30363d`
  - text `#e6edf3`, secondary `#8b949e`, muted `#6e7681`
  - accent `#58a6ff`, positive `#3fb950`

## Sections

1. **Hero** — Klarwert name, tagline "Local-first portfolio analyzer for Trade
   Republic", one-liner, primary button "View on GitHub" linking to
   `https://github.com/d0k3n/klarwert`.
2. **Privacy callout** — "All computation happens on your machine. Your data
   never leaves it."
3. **Feature grid** — compact cards: reconciliation, monthly realized P&L,
   FIFO audit trail, tax report, dividends & income, cash flow & card
   spending, derivative executions, product charts.
4. **Quick start** — four setup steps: clone → venv → install → run.
5. **Footer** — GitHub link and MIT license note.

## Notes

- Mobile-responsive via viewport meta and a flexible grid.
- System font stack, zero external resources (fast, private).
- GitHub link target is the real origin remote `d0k3n/klarwert`, not the
  README's placeholder.

## Verification

- Serve `docs/` locally (`python -m http.server`) and confirm it renders.
- Confirm the GitHub link resolves to the correct repository.
