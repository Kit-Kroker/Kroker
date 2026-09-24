# Tokens Component

Design system colour, type, spacing and radius tokens exported by `@kroker/ui`,
in two themes. Dark is declared on `:root` and is the default; light is
declared on `[data-theme='light']`, set on `<html>` by the application.

Values come from the canvas at `records/2026-09-23-design-foundations/`:
three grounds (`--ground-shell`, `--ground-canvas`, `--ground-raised`),
two lines, four inks (`--ink-primary`, `--ink-secondary`, `--ink-muted`,
`--ink-inverse`), five statuses with a tint each (`--status-done`,
`running`, `waiting`, `failed`, `idle`), one overlay shadow and one
backdrop. Theme-invariant scales: `--text-xs..xl` (11/12/13/15/17),
`--space-1..5` (4/8/12/16/24), `--radius-sm/md/lg` (4/8/12), and the two
Plex families. There is no brand accent: the primary action is inverse ink.

The design system owns token definitions and variable names; components and
applications own their layout and structure, consuming tokens through `var(--*)`.
The application owns which theme is active.

## Requirements

### TOKENS-1
Every declared token in the design system resolves to a non-empty value. [FR-1404]

### TOKENS-2
No component stylesheet ships a bare hex color literal outside the token palette. [FR-1404]

### TOKENS-3
Every colour, shadow and backdrop token declared on `:root` is also declared
under `[data-theme='light']`, so switching theme never leaves a token on its
dark value. [FR-1404]

### TOKENS-4
Pass-two names (`--ground-0..5`, `--ink-tertiary`, `--accent*`,
`--status-blocked`, …) are declared only as `var()` aliases of pass-three
tokens, and are removed one release after this change. [FR-1404]

## Failure modes

An undeclared token variable reference falls back to CSS initial value or breaks
visual presentation. Missing token declarations fail presentation testing (TOKENS-1).
Bare hex literals in component stylesheets fail presentation testing (TOKENS-2).
A colour added to `:root` alone renders its dark value in light theme (TOKENS-3).
