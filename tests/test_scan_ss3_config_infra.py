"""SS3's computed half: what the deployment declares about itself. The
framework-defaults category is triage's misconfig, cited not copied (D2)."""

from __future__ import annotations

from sdlc.assessment.scan.models import (
    C_DB_SECURITY,
    C_ENV_DIVERGENCE,
    C_EXPOSED_PORTS,
    C_FRAMEWORK_DEFAULTS,
    C_LOG_MASKING,
    ScanSignalId,
)
from sdlc.assessment.scan.signals import config_infra
from sdlc.measurement import CollectionState

BLOBS = {
    "Dockerfile": "FROM python:3.12\nEXPOSE 8000\nEXPOSE 5432\n",
    "docker-compose.yml": (
        "services:\n"
        "  db:\n"
        "    image: postgres:16\n"
        "    environment:\n"
        "      POSTGRES_HOST_AUTH_METHOD: trust\n"
        "    ports:\n"
        "      - '5432:5432'\n"
    ),
    ".env.development": "DEBUG=true\nDATABASE_URL=postgres://u:p@localhost/db?sslmode=disable\n",
    ".env.production": "DEBUG=true\n",
    "src/audit.py": "import logging\nlogging.info('token=%s', token)\n",
}


def test_exposed_ports_are_recorded_and_a_datastore_port_is_higher():
    out = config_infra.evaluate(BLOBS)
    ports = [o for o in out.security if o.category == C_EXPOSED_PORTS]
    assert {o.path for o in ports} == {"Dockerfile", "docker-compose.yml"}
    datastore = [o for o in ports if "5432" in o.evidence]
    assert datastore and all(o.severity_hint == "high" for o in datastore)


def test_database_security_rules_fire_on_the_compose_and_the_url():
    out = config_infra.evaluate(BLOBS)
    rules = {o.rule for o in out.security if o.category == C_DB_SECURITY}
    assert "ss3_db_trust_auth" in rules
    assert "ss3_db_ssl_disabled" in rules
    assert "ss3_db_credentials_in_url" in rules


def test_an_unsafe_value_in_a_production_env_file_is_recorded():
    out = config_infra.evaluate(BLOBS)
    unsafe = [o for o in out.security if o.rule == "ss3_unsafe_value_in_environment"]
    assert [o.path for o in unsafe] == [".env.production"]
    assert "DEBUG" in unsafe[0].detail


def test_a_key_present_in_one_environment_and_missing_in_another_is_recorded():
    out = config_infra.evaluate(BLOBS)
    missing = [o for o in out.security if o.rule == "ss3_env_key_missing"]
    assert any("DATABASE_URL" in o.detail for o in missing)
    assert all(o.path == ".env.production" for o in missing)


def test_divergence_needs_two_environment_files():
    """P3-D11: with one env file there is nothing to compare, which is
    unmeasurable rather than 'no divergence'."""
    out = config_infra.evaluate({".env": "DEBUG=true\n"})
    category = out.row.categories[C_ENV_DIVERGENCE]
    assert category.state is CollectionState.NOT_COLLECTED
    assert "two" in category.reason


def test_a_sensitive_value_reaching_a_log_call_is_recorded():
    out = config_infra.evaluate(BLOBS)
    logs = [o for o in out.security if o.category == C_LOG_MASKING]
    assert [o.path for o in logs] == ["src/audit.py"]


def test_a_tree_with_no_infrastructure_files_is_a_measured_zero_for_ports():
    """We read every config path in the tree; no EXPOSE anywhere is an
    answer, not a gap."""
    out = config_infra.evaluate({".env": "A=1\n", ".env.prod": "A=1\n"})
    assert out.row.categories[C_EXPOSED_PORTS].state is CollectionState.MEASURED
    assert out.row.categories[C_EXPOSED_PORTS].value == 0.0


def test_the_inherited_category_is_declared_as_pending():
    out = config_infra.evaluate(BLOBS)
    pending = out.row.categories[C_FRAMEWORK_DEFAULTS]
    assert pending.state is CollectionState.NOT_COLLECTED
    assert "D7" in pending.reason


def test_every_observation_declares_ss3():
    out = config_infra.evaluate(BLOBS)
    assert out.security
    assert all(o.signal is ScanSignalId.SS3 for o in out.security)


def test_is_config_path_selects_infrastructure_and_environment_files():
    for path in (
        "Dockerfile",
        "docker-compose.yml",
        ".env.production",
        "k8s/deployment.yaml",
        "infra/main.tf",
        "appsettings.Production.json",
    ):
        assert config_infra.is_config_path(path) is True
    assert config_infra.is_config_path("src/app.py") is False


def test_a_log_call_in_a_test_file_is_not_attributed_to_the_product():
    """A fixture that logs a throwaway token is the test's own business; an
    observation attributed to the product is a finding a client cannot
    trust (QS3's rule, one signal over)."""
    out = config_infra.evaluate(
        dict(BLOBS, **{"tests/conftest.py": "import logging\nlogging.info('token=%s', token)\n"})
    )
    assert all(o.path != "tests/conftest.py" for o in out.security)
