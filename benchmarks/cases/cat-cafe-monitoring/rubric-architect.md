# Architect rubric — cat-cafe-monitoring

Score the architecture artifact 0.0..1.0 on these components; return
`{"score": <mean>, "components": {...}}`.

- **data_model (0.2):** telemetry reading (cat id, coordinates, breathing
  rate, timestamp) and floor-plan zones (type + coordinates) are both defined
- **activity_classification (0.2):** a stated rule or method for each of the
  six activities, combining distance-to-zone with breathing rate. Naming the
  activities without saying how each is distinguished does not count
- **risk_rule (0.2):** an explicit, numeric risk rule over breathing rate —
  not "flag anomalies". The threshold's origin is stated
- **realtime_and_history (0.2):** a transport choice for the live view (poll
  vs SSE vs WebSocket) with rationale, and a storage approach that answers a
  24h history query
- **decisions_documented (0.2):** boring, mainstream stack; each non-trivial
  choice has rationale + alternatives considered
