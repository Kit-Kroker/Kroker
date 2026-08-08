"""FR-902 framework-default misconfiguration (E-41c)."""
from sdlc.measurement import CollectionState
from sdlc.triage.models import FixClass
from sdlc.triage.signals import misconfig, secrets


def _rules(result):
    return {f.rule for f in result.findings}


def test_permissive_cors_fires_on_fastapi_and_flask_forms():
    fastapi = ('from fastapi import FastAPI\n'
               'app.add_middleware(CORSMiddleware, allow_origins=["*"])\n')
    flask = ('from flask import Flask\n'
             'CORS(app, origins="*")\n')
    assert "permissive_cors" in _rules(misconfig.evaluate({"a.py": fastapi}))
    assert "permissive_cors" in _rules(misconfig.evaluate({"b.py": flask}))


def test_credentialed_wildcard_cors_is_critical():
    text = ('from fastapi import FastAPI\n'
            'app.add_middleware(CORSMiddleware, allow_origins=["*"], '
            'allow_credentials=True)\n')
    f = next(f for f in misconfig.evaluate({"a.py": text}).findings
             if f.rule == "permissive_cors")
    assert f.severity == "critical"


def test_debug_enabled_fires_for_django_and_flask():
    django = "from django.conf import settings\nDEBUG = True\n"
    flask = "from flask import Flask\napp.run(debug=True)\n"
    assert "debug_enabled" in _rules(misconfig.evaluate({"s.py": django}))
    assert "debug_enabled" in _rules(misconfig.evaluate({"a.py": flask}))


def test_debug_false_does_not_fire():
    assert "debug_enabled" not in _rules(
        misconfig.evaluate({"s.py": "from django.conf import x\nDEBUG = False\n"}))


def test_allowed_hosts_wildcard_fires():
    text = "from django.conf import x\nALLOWED_HOSTS = ['*']\n"
    assert "allowed_hosts_wildcard" in _rules(misconfig.evaluate({"s.py": text}))


def test_the_django_placeholder_key_is_misconfig_and_judgement():
    text = ("from django.conf import x\n"
            "SECRET_KEY = 'django-insecure-abc123defg456hijk789lmno'\n")
    f = next(f for f in misconfig.evaluate({"settings.py": text}).findings
             if f.rule == "django_insecure_secret_key")
    assert f.severity == "critical"
    assert f.fix_class is FixClass.JUDGEMENT


def test_secrets_does_not_also_report_the_django_placeholder():
    # Spec section 7: secrets owns credential MATERIAL, misconfig owns
    # generator DEFAULTS. One line must not produce two findings from two
    # signals, or a report double-counts its own severity.
    text = "SECRET_KEY = 'django-insecure-abc123defg456hijk789lmno'\n"
    assert secrets.scan_text("settings.py", text) == []


def test_secrets_still_reports_a_real_secret_key_assignment():
    text = "SECRET_KEY = 'p8Fq2XvR7nZk4LmT9wYc'\n"
    rules = {f.rule for f in secrets.scan_text("settings.py", text)}
    assert "generic_secret_assignment" in rules


def test_world_readable_storage_fires_on_firebase_and_iac():
    firebase = "service firebase.storage {\n  allow read, write: if true;\n}\n"
    iam = '{"Statement": [{"Principal": "*"}]}\n'
    assert "world_readable_storage" in _rules(
        misconfig.evaluate({"storage.rules": firebase}))
    assert "world_readable_storage" in _rules(
        misconfig.evaluate({"policy.json": iam}))


# ---- unauthenticated_app, the whole-app rule --------------------------

def test_unauthenticated_app_fires_once_for_the_repository():
    a = ('from fastapi import FastAPI\napp = FastAPI()\n'
         '@app.post("/items")\ndef create():\n    return 1\n')
    b = ('@app.delete("/items/{i}")\ndef remove(i):\n    return 1\n')
    r = misconfig.evaluate({"a.py": a, "b.py": b})
    assert [f.rule for f in r.findings].count("unauthenticated_app") == 1


def test_declared_auth_anywhere_suppresses_it():
    a = ('from fastapi import FastAPI\napp = FastAPI()\n'
         '@app.post("/items")\ndef create():\n    return 1\n')
    b = 'from fastapi.security import OAuth2PasswordBearer\n'
    assert "unauthenticated_app" not in _rules(
        misconfig.evaluate({"a.py": a, "b.py": b}))


def test_a_read_only_app_does_not_fire():
    a = ('from fastapi import FastAPI\napp = FastAPI()\n'
         '@app.get("/items")\ndef read():\n    return 1\n')
    assert "unauthenticated_app" not in _rules(misconfig.evaluate({"a.py": a}))


def test_no_framework_detected_means_no_whole_app_finding():
    a = '@app.post("/x")\ndef create():\n    return 1\n'
    r = misconfig.evaluate({"a.py": a})
    assert "unauthenticated_app" not in _rules(r)
    assert r.metrics[misconfig.M_FRAMEWORKS].value == 0.0


def test_frameworks_detected_metric_counts_distinct_frameworks():
    r = misconfig.evaluate({"a.py": "import fastapi\n",
                            "b.py": "from flask import Flask\n"})
    assert r.metrics[misconfig.M_FRAMEWORKS].value == 2.0


def test_a_clean_app_yields_no_findings():
    text = ('from fastapi import FastAPI\n'
            'from fastapi.security import HTTPBearer\n'
            'app = FastAPI()\n'
            '@app.get("/health")\ndef health():\n    return "ok"\n')
    r = misconfig.evaluate({"a.py": text})
    assert r.findings == []
    assert r.collected.state is CollectionState.MEASURED
