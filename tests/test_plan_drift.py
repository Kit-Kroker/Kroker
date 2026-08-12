"""Plan drift: what the planner expected to be touched vs what was.

A SIGNAL, never a gate. files_hint is named a hint; a planner that guessed
wrong is a normal outcome, and the drift is interesting precisely because it
is not an error."""
from sdlc.models import DevTask, compute_plan_drift


def _task(**kw):
    return DevTask(id="t1", title="t", description="d",
                   acceptance_criteria=["ac"], **kw)


def test_exact_adherence_reports_zero_drift():
    d = compute_plan_drift(_task(files_hint=["a.py", "b.py"]),
                           ["a.py", "b.py"])
    assert d is not None
    assert d.files_hinted == 2
    assert d.files_touched == 2
    assert d.hinted_untouched == []
    assert d.touched_unhinted == []


def test_unhinted_file_is_reported():
    d = compute_plan_drift(_task(files_hint=["a.py"]), ["a.py", "c.py"])
    assert d.touched_unhinted == ["c.py"]
    assert d.hinted_untouched == []


def test_hinted_but_untouched_file_is_reported():
    d = compute_plan_drift(_task(files_hint=["a.py", "b.py"]), ["a.py"])
    assert d.hinted_untouched == ["b.py"]


def test_lists_are_sorted_for_stable_records():
    # NOTE (E-83 plan deviation): the plan specified files_hint=[] here, but
    # an empty hint means NOT MEASURED (test_no_hint_is_not_measured below).
    # Use a non-overlapping hint so touched_unhinted is the sorted diff list.
    d = compute_plan_drift(_task(files_hint=["other.py"]), ["z.py", "a.py"])
    assert d.touched_unhinted == ["a.py", "z.py"]


def test_paths_are_compared_normalised():
    """A planner writing 'src\\app.py' and a diff reporting 'src/app.py' is
    the same file. Reporting it as drift would manufacture a finding."""
    d = compute_plan_drift(_task(files_hint=["src\\app.py"]), ["src/app.py"])
    assert d.hinted_untouched == []
    assert d.touched_unhinted == []


def test_no_hint_is_not_measured():
    """An empty files_hint means the planner made no prediction. Zero drift
    would claim perfect adherence to a prediction that was never made."""
    assert compute_plan_drift(_task(files_hint=[]), ["a.py"]) is None


def test_no_diff_is_not_measured():
    assert compute_plan_drift(_task(files_hint=["a.py"]), []) is None
