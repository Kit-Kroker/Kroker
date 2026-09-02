# records/

Design exports, verbatim, one directory per session: `<YYYY-MM-DD>-<topic>/`.

These are raw Claude Design output (`*.dc.html` plus the `support.js`
runtime they load). They live here rather than under `docs/` on purpose:
they are a dated record of what a design looked like on a day, not
documentation anyone maintains. Nothing here is edited after it lands. If
a design is revised, that is a new dated directory.

Full dates, not months -- a topic can be revisited twice in one month, and
a date-ordered listing is the whole point of the directory.

What is *extracted* from a record -- design tokens, components, and the
feature-clause document for each component -- lives with the UI code and
is maintained there. The record is the source, never the reference.

Records are exempt from the file-size ceiling (`AGENTS.md`): they are not
authored here and cannot be split without ceasing to be what they vendor.
