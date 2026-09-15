# YAML Pane Component

A text view of a draft graph's YAML with its shape errors. The caller owns
the text's origin (server `serialize`), what applying it means (server
`parse`), the errors, and the dirty state; the component owns the editor, the
canonical-form notice, the byte-cap refusal, and the error list.

## Requirements

### YAML_PANE-1
A YAML Pane emits `update:text` on every edit and `apply` only when the text
is dirty, not busy, and within `maxBytes` UTF-8 bytes. [FR-1205]

### YAML_PANE-2
Each supplied error renders as a row showing its line (and column) when
present, its document path when present, and its message; no errors, no
list. [FR-1205]

### YAML_PANE-3
The pane states that its text is canonical: comments, key order and default
values are not kept across canvas edits (E-76 spec §8.5). [FR-1205]

### YAML_PANE-4
Text above `maxBytes` UTF-8 bytes shows its size against the cap and cannot
be applied; the size counts bytes, not characters. [FR-1205]

## Failure modes

The component never parses YAML: a text that fails the shape parse is the
caller's `errors`, returned by the server.
