# one_person_dnd UI Polish Design

## Goal

Refresh the local solo TRPG interface without changing routing or turn behavior. The UI should feel like an active DM table: readable, compact, and play-first, with a stronger visual identity than a generic dark admin app.

## Subject And Audience

Subject: a one-person DND/TRPG control surface where the player reads fiction, acts, rolls, and reviews DM-suggested state changes.

Audience: solo players and local developers who need the app to stay fast, dense, and predictable during repeated play.

Single job: make the next playable action obvious on every main screen.

## Visual System

Palette:

- Obsidian background `#080b10`
- Ink panel `#111820`
- Parchment text/accent `#e4d3b0`
- Ember action accent `#c07643`
- Arcane blue interaction accent `#7aa2f7`
- Verdigris review/success accent `#8fd6b4`

Typography:

- Display: Georgia/Palatino-style serif for page titles and key identity text.
- Body: compact system sans stack for repeat-use UI.
- Utility: monospace stack for IDs, provider details, and dice-like metadata.

Signature:

- A lightweight "ledger rail": thin parchment/ember rules and compact metadata strips that make the app feel like a session log rather than a dashboard template.

## Implementation Scope

- Refresh shared shell styles in `style.css`.
- Make the home page an operational adventure dashboard.
- Polish the game action composer and remove visible shortcut instruction text.
- Keep quick roll directly after the action composer.
- Remove nested `.card` shells from the saves page and replace them with section/snapshot panels.
- Preserve existing IDs, forms, htmx targets, SSE renderer contracts, and template partial contracts.

## Verification

- Add template/CSS tests for the visual system and structural constraints.
- Run `PYTHONPATH=src python -m unittest tests.test_ui_templates` during the red/green cycle.
- Run full compile and test suite.
- Start the local app and inspect `/`, `/models`, `/saves`, and `/game` in desktop and mobile-sized browser viewports.
