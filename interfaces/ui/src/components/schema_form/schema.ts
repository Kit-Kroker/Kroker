// The JSON Schema subset schema_form renders natively (E-76 spec §8.3):
// string, number/integer (with bounds), boolean, enum, a nullable
// anyOf [X, {type: null}], arrays of strings, nested objects, and local
// $ref -> $defs. Anything else is `unsupported` and renders a JSON snippet.
// This module knows JSON Schema, never a Kroker model: no field name of
// RoleConfig or GateConfig appears in TypeScript.

export type Schema = Record<string, unknown>

export type Field =
  | { kind: 'string'; nullable: boolean; pattern?: string; default?: unknown; title?: string }
  | { kind: 'number' | 'integer'; nullable: boolean; minimum?: number; maximum?: number; exclusiveMinimum?: number; exclusiveMaximum?: number; default?: unknown; title?: string }
  | { kind: 'boolean'; nullable: boolean; default?: unknown; title?: string }
  | { kind: 'enum'; nullable: boolean; values: string[]; default?: unknown; title?: string }
  | { kind: 'string-array'; nullable: boolean; default?: unknown; title?: string }
  | { kind: 'object'; nullable: boolean; properties: { name: string; field: Field; required: boolean }[]; title?: string }
  | { kind: 'unsupported'; nullable: boolean; schema: Schema; title?: string }

const isObj = (v: unknown): v is Schema => v !== null && typeof v === 'object' && !Array.isArray(v)

export function resolveRef(schema: Schema, defs: Record<string, Schema>): Schema {
  const ref = schema.$ref
  if (typeof ref !== 'string') return schema
  const match = /^#\/\$defs\/(.+)$/.exec(ref)
  const target = match ? defs[match[1]] : undefined
  if (!target) return { __unresolved: ref }
  // Sibling keys next to a $ref (pydantic puts `default` there) win.
  const { $ref: _ref, ...siblings } = schema
  return { ...resolveRef(target, defs), ...siblings }
}

export function classify(input: Schema, defs: Record<string, Schema>, seen: string[] = []): Field {
  const meta = { default: input.default, title: typeof input.title === 'string' ? input.title : undefined }
  if (typeof input.$ref === 'string') {
    if (seen.includes(input.$ref)) return { kind: 'unsupported', nullable: false, schema: input, ...meta }
    const resolved = resolveRef(input, defs)
    return classify(resolved, defs, [...seen, input.$ref as string])
  }
  if (Array.isArray(input.anyOf)) {
    const branches = input.anyOf.filter(isObj)
    const nulls = branches.filter((b) => b.type === 'null')
    const rest = branches.filter((b) => b.type !== 'null')
    if (branches.length === input.anyOf.length && nulls.length === 1 && rest.length === 1) {
      const inner = classify(rest[0], defs, seen)
      if (inner.kind !== 'unsupported') return { ...inner, nullable: true, ...defined(meta) } as Field
    }
    return { kind: 'unsupported', nullable: false, schema: input, ...meta }
  }
  if (Array.isArray(input.enum) && input.enum.every((v) => typeof v === 'string')) {
    return { kind: 'enum', nullable: false, values: input.enum as string[], ...meta }
  }
  switch (input.type) {
    case 'string':
      return { kind: 'string', nullable: false, pattern: typeof input.pattern === 'string' ? input.pattern : undefined, ...meta }
    case 'number':
    case 'integer':
      return {
        kind: input.type, nullable: false, ...meta,
        ...pickNumbers(input, ['minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum']),
      }
    case 'boolean':
      return { kind: 'boolean', nullable: false, ...meta }
    case 'array':
      return isObj(input.items) && input.items.type === 'string'
        ? { kind: 'string-array', nullable: false, ...meta }
        : { kind: 'unsupported', nullable: false, schema: input, ...meta }
    case 'object': {
      const props = isObj(input.properties) ? input.properties : {}
      const required = Array.isArray(input.required) ? (input.required as string[]) : []
      return {
        kind: 'object', nullable: false, title: meta.title,
        properties: Object.entries(props).filter(([, s]) => isObj(s)).map(([name, s]) => ({
          name, field: classify(s as Schema, defs, seen), required: required.includes(name),
        })),
      }
    }
    default:
      return { kind: 'unsupported', nullable: false, schema: input, ...meta }
  }
}

function defined(meta: { default: unknown; title?: string }) {
  return Object.fromEntries(Object.entries(meta).filter(([, v]) => v !== undefined))
}

function pickNumbers(s: Schema, keys: string[]): Record<string, number> {
  return Object.fromEntries(keys.filter((k) => typeof s[k] === 'number').map((k) => [k, s[k] as number]))
}

/** True when no leaf anywhere under `field` renders the JSON fallback. */
export function fullySupported(field: Field): boolean {
  if (field.kind === 'unsupported') return false
  if (field.kind === 'object') return field.properties.every((p) => fullySupported(p.field))
  return true
}

// --- values: only touched paths are ever written (SCHEMA_FORM-4) -------------------

export type Path = (string | number)[]

export function getPath(value: unknown, path: Path): unknown {
  let cur: unknown = value
  for (const key of path) {
    if (cur === null || typeof cur !== 'object') return undefined
    cur = (cur as Record<string | number, unknown>)[key]
  }
  return cur
}

/**
 * A copy of `value` with `path` set to `next`. `undefined` REMOVES the key.
 * An object emptied by a removal is removed too, unless `base` already held
 * that object (so an authored `gate: {}` survives, and a role the user
 * created and then cleared returns to absent, not `role: {}`).
 */
export function setPath(value: Record<string, unknown>, path: Path, next: unknown, base: unknown): Record<string, unknown> {
  const root = JSON.parse(JSON.stringify(value)) as Record<string, unknown>
  let cur: Record<string | number, unknown> = root
  for (const key of path.slice(0, -1)) {
    if (cur[key] === null || typeof cur[key] !== 'object') cur[key] = {}
    cur = cur[key] as Record<string | number, unknown>
  }
  const last = path[path.length - 1]
  if (next === undefined) delete cur[last]
  else cur[last] = next
  if (next === undefined) {
    for (let depth = path.length - 1; depth > 0; depth--) {
      const objPath = path.slice(0, depth)
      const obj = getPath(root, objPath)
      if (obj && typeof obj === 'object' && Object.keys(obj).length === 0 && getPath(base, objPath) === undefined) {
        delete (getPath(root, objPath.slice(0, -1)) as Record<string | number, unknown>)[objPath[objPath.length - 1]]
      } else {
        break
      }
    }
  }
  return root
}
