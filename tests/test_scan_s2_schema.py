"""S2: tables, FK edges and the clusters they form. BrownKit clusters "by FK
connectivity + naming"; both halves are here, and the naming half is
naming.normalize so S5 can merge an S2 cluster with the S1 package and the S3
controller that share its name."""

from __future__ import annotations

from sdlc.assessment.scan.models import MemberKind
from sdlc.assessment.scan.signals import schema
from sdlc.measurement import CollectionState

SQL = {
    "migrations/0001_orders.sql": (
        "CREATE TABLE orders (\n"
        "  id SERIAL PRIMARY KEY,\n"
        "  customer_id INTEGER NOT NULL REFERENCES customers(id),\n"
        "  total NUMERIC(10,2)\n"
        ");\n"
        "CREATE TABLE order_items (\n"
        "  id SERIAL PRIMARY KEY,\n"
        "  order_id INTEGER NOT NULL REFERENCES orders(id)\n"
        ");\n"
    ),
    "migrations/0002_customers.sql": (
        "CREATE TABLE customers (\n"
        "  id SERIAL PRIMARY KEY,\n"
        "  email VARCHAR(255) NOT NULL,\n"
        "  phone VARCHAR(32)\n"
        ");\n"
    ),
}


def test_tables_are_declared_with_their_fields():
    decls = schema.declarations(SQL)
    by_name = {d.name: d for d in decls}
    assert set(by_name) == {"orders", "order_items", "customers"}
    assert "email" in by_name["customers"].fields
    assert by_name["orders"].rule == "s2_sql_create_table"
    assert by_name["orders"].path == "migrations/0001_orders.sql"


def test_orders_and_order_items_cluster_on_the_head_token():
    """'orders' + 'order_items' + 'order_events' is ONE candidate. The head
    token is what those names actually agree on, which is why S3 groups on it
    too (D9's worked example, one signal over)."""
    out = schema.evaluate(SQL)
    ids = {c.local_id for c in out.sources}
    assert "S2-order" in ids
    order = next(c for c in out.sources if c.local_id == "S2-order")
    tables = {m.value for m in order.members if m.kind is MemberKind.DB_TABLE}
    assert tables == {"orders", "order_items"}


def test_a_foreign_key_raises_the_contribution_and_is_counted():
    out = schema.evaluate(SQL)
    order = next(c for c in out.sources if c.local_id == "S2-order")
    assert order.metrics[schema.M_FK_EDGES].state is CollectionState.MEASURED
    assert order.metrics[schema.M_FK_EDGES].value >= 1.0
    assert order.confidence_contribution.value == "high"


def test_a_singleton_table_is_low_and_still_reported():
    out = schema.evaluate(SQL)
    customers = next(c for c in out.sources if c.local_id == "S2-customer")
    assert customers.confidence_contribution.value in {"low", "medium"}


def test_a_foreign_key_does_not_merge_two_named_clusters():
    """P3-D13: orders REFERENCES customers, and union-find over that would
    collapse a normalized schema into one component -- every table reaches
    every other one eventually. Naming clusters; the FK corroborates."""
    out = schema.evaluate(SQL)
    assert {c.local_id for c in out.sources} == {"S2-order", "S2-customer"}
    order = next(c for c in out.sources if c.local_id == "S2-order")
    assert "customers" not in {m.value for m in order.members}


def test_orm_models_are_declarations_too():
    blobs = {
        "app/models/payment.py": (
            "from sqlalchemy import Column, ForeignKey, Integer, String\n"
            "class Payment(Base):\n"
            "    __tablename__ = 'payments'\n"
            "    id = Column(Integer, primary_key=True)\n"
            "    card_last4 = Column(String(4))\n"
            "    order_id = Column(Integer, ForeignKey('orders.id'))\n"
        )
    }
    decls = schema.declarations(blobs)
    assert [d.name for d in decls] == ["payments"]
    assert "card_last4" in decls[0].fields
    out = schema.evaluate(blobs)
    assert any(c.local_id == "S2-payment" for c in out.sources)


def test_a_prisma_schema_is_parsed():
    blobs = {
        "prisma/schema.prisma": (
            "model User {\n"
            "  id    Int     @id @default(autoincrement())\n"
            "  email String  @unique\n"
            "  posts Post[]\n"
            "}\n"
            "model Post {\n"
            "  id       Int  @id\n"
            "  author   User @relation(fields: [authorId], references: [id])\n"
            "  authorId Int\n"
            "}\n"
        )
    }
    decls = schema.declarations(blobs)
    assert {d.name for d in decls} == {"User", "Post"}
    assert "email" in dict((d.name, d.fields) for d in decls)["User"]


def test_a_repository_with_no_schema_is_a_gap_not_a_zero():
    """D5: an ORM we cannot fingerprint looks exactly like an application with
    no database, and only one of those is safe to assert."""
    out = schema.evaluate({"src/app.py": "print('hello')\n"})
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert out.sources == []
    assert "not a repository with no schema" in out.row.collected.reason


def test_a_fixture_schema_under_tests_is_not_a_capability():
    """P3-D9: a CREATE TABLE inside a test fixture describes the test, not the
    product."""
    out = schema.evaluate({"tests/fixtures/seed.sql": "CREATE TABLE widgets (id INT);\n"})
    assert out.row.collected.state is CollectionState.NOT_COLLECTED


def test_output_is_byte_identical_across_input_orderings():
    reference = schema.evaluate(SQL).model_dump_json()
    reversed_blobs = dict(reversed(list(SQL.items())))
    assert schema.evaluate(reversed_blobs).model_dump_json() == reference
