// 018 T061 (R-7, read-routes rule 4): the shipped-graphs mock replays the
// recorded fixture (F/api/__fixtures__/read/graphs-shipped.json) through
// the same mapper the http client uses - the mock answers exactly what
// the route serves.
import fixture from '../__fixtures__/read/graphs-shipped.json'
import { mapShippedGraphs } from '../http-read'
import type { ShippedGraphs } from '../read-types'

export function mockShippedGraphs(): ShippedGraphs {
  return mapShippedGraphs(fixture as never)
}
