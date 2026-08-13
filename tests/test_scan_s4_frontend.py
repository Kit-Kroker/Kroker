"""S4: routes as the user meets them. BrownKit groups by user journey, not by
component hierarchy -- so /payments, /payments/:id and /payments/new are ONE
candidate."""
from __future__ import annotations

from sdlc.assessment.scan.models import MemberKind
from sdlc.assessment.scan.signals import frontend
from sdlc.measurement import CollectionState

NEXT_APP = {
    "package.json": '{"dependencies": {"next": "14.2.0", "react": "18.2.0"}}',
    "app/payments/page.tsx": "export default function Page() { return null }\n",
    "app/payments/[id]/page.tsx": "export default function Page() { return null }\n",
    "app/(marketing)/about/page.tsx": "export default function Page() {}\n",
    "app/layout.tsx": "export default function Layout() {}\n",
}


def test_next_app_router_pages_become_routes():
    out = frontend.evaluate(NEXT_APP)
    routes = {m.value for c in out.sources for m in c.members
              if m.kind is MemberKind.FRONTEND_ROUTE}
    assert "/payments" in routes
    assert "/payments/:id" in routes
    # A route group is a layout device, not a URL segment.
    assert "/about" in routes
    # layout.tsx is not a route.
    assert not any(r.endswith("layout") for r in routes)


def test_a_journey_is_one_candidate_not_one_per_route():
    out = frontend.evaluate(NEXT_APP)
    payments = next(c for c in out.sources if c.local_id == "S4-payment")
    values = {m.value for m in payments.members}
    assert values == {"/payments", "/payments/:id"}


def test_react_router_config_routes_are_extracted():
    blobs = {
        "package.json": '{"dependencies": {"react-router-dom": "6.22.0"}}',
        "src/routes.tsx": (
            "export const router = createBrowserRouter([\n"
            "  { path: '/orders', element: <Orders /> },\n"
            "  { path: '/orders/:id', element: <Order /> },\n"
            "]);\n"),
    }
    out = frontend.evaluate(blobs)
    assert out.row.collected.state is CollectionState.MEASURED
    orders = next(c for c in out.sources if c.local_id == "S4-order")
    assert {m.value for m in orders.members} == {"/orders", "/orders/:id"}


def test_a_repository_with_no_frontend_is_a_gap_not_a_zero():
    """BrownKit's own adaptation: has_frontend=false is recorded as
    not-collected with a reason, never as an empty route list (D5)."""
    out = frontend.evaluate({"src/app.py": "print('hi')\n"})
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert out.sources == []
    assert "no frontend framework" in out.row.collected.reason


def test_an_unfingerprinted_frontend_framework_fails_closed():
    """P2-D1, one signal over: extracting only what we recognise would hand a
    partial route set downstream while looking complete."""
    blobs = {
        "package.json": '{"dependencies": {"@angular/core": "17.0.0"}}',
        "src/app/app.component.ts": "export class AppComponent {}\n",
    }
    out = frontend.evaluate(blobs)
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert "angular" in out.row.collected.reason
    assert out.sources == []


def test_sveltekit_routes_are_extracted():
    blobs = {
        "package.json": '{"devDependencies": {"@sveltejs/kit": "2.0.0"}}',
        "src/routes/orders/+page.svelte": "<h1>Orders</h1>\n",
        "src/routes/orders/[id]/+page.svelte": "<h1>Order</h1>\n",
    }
    out = frontend.evaluate(blobs)
    orders = next(c for c in out.sources if c.local_id == "S4-order")
    assert {m.value for m in orders.members} == {"/orders", "/orders/:id"}


def test_output_is_byte_identical_across_input_orderings():
    reference = frontend.evaluate(NEXT_APP).model_dump_json()
    reordered = dict(reversed(list(NEXT_APP.items())))
    assert frontend.evaluate(reordered).model_dump_json() == reference
