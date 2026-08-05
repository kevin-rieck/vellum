# Domain Docs

## Before exploring, read these

- `CONTEXT.md` at the repo root.
- `docs/adr/` — read ADRs that touch the area being worked on.

If these files don't exist, proceed silently. Do not suggest creating them upfront.

## File structure

This is a single-context repo:

/
├── CONTEXT.md
├── docs/adr/
└── src/

## Use the glossary's vocabulary

Use terms as defined in `CONTEXT.md`; do not substitute synonyms it explicitly avoids. If a needed term is absent, reconsider the terminology or note the gap for `/domain-modeling`.

## Flag ADR conflicts

Explicitly flag output that contradicts an existing ADR rather than silently overriding it.
