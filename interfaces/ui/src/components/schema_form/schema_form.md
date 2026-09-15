# Schema Form Component

A generic form over a JSON Schema document. The caller owns the schema
(served by the backend from pydantic `model_json_schema()`), the value, the
errors, and what applying an edit means; the component owns rendering each
schema construct as a control and the touched-fields-only value it emits.
No Kroker field name appears in the component (E-76 spec U8).

## Requirements

### SCHEMA_FORM-1
A Schema Form renders one control per property of the root object schema, in
schema order, recursing into nested objects as fieldsets. [FR-1205]

### SCHEMA_FORM-2
`string`, `number`/`integer`, `boolean`, string `enum`, arrays of strings,
nested objects, the nullable `anyOf: [X, {type: null}]` pattern and local
`$ref` into `$defs` render as native controls; any other construct renders a
JSON snippet field, parsed with `JSON.parse`, whose invalid text stays local
and emits nothing. [FR-1205]

### SCHEMA_FORM-3
A nullable `anyOf` and a `$ref` enum render as native controls, not the
fallback; against the backend's recorded catalog, no `RoleConfig` or
`GateConfig` property renders the fallback (pinned in the dashboard tier, the
only tier that may import the recording). [FR-1205]

### SCHEMA_FORM-4
An untouched field is never written: rendering does not materialize a
default; setting one field under an absent object creates that object with
that field only; clearing a field removes its key, and an object emptied that
way is removed unless the supplied value already held it. [FR-1205]

### SCHEMA_FORM-5
Each supplied error renders beside the control at its dot path; an error at
path `''` renders at the top of the form. `readonly` and `readonlyPaths`
suppress edits. [FR-1205]

## Failure modes

The form never validates a value: bounds and patterns in the schema are
hints; shape errors come back from the server as `errors`.
