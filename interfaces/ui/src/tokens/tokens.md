# Tokens Component

Design system color and typography tokens exported by `@kroker/ui`. Provides
CSS custom properties defining the palette and font stack used by the console
and showcase.

The design system owns token definitions and variable names; components and
applications own their layout and structure, consuming tokens through `var(--*)`.

## Requirements

### TOKENS-1
Every declared token in the design system resolves to a non-empty value. [FR-1404]

### TOKENS-2
No component stylesheet ships a bare hex color literal outside the token palette. [FR-1404]

## Failure modes

An undeclared token variable reference falls back to CSS initial value or breaks
visual presentation. Missing token declarations fail presentation testing (TOKENS-1).
Bare hex literals in component stylesheets fail presentation testing (TOKENS-2).
