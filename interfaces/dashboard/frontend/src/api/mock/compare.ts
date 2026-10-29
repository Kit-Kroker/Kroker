// 018 T072 (R-9, read-routes rule 4): the compare mock replays the
// recorded fixture (F/api/__fixtures__/read/compare.json) through the
// same mapper the http client uses - the mock answers exactly what the
// route serves.
import fixture from '../__fixtures__/read/compare.json'
import { mapCompare } from '../http-read'
import type { Compare } from '../read-types'

export function mockCompare(): Compare {
  return mapCompare(fixture as never)
}
