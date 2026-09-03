from sdlc.workflows.feature import FeatureWorkflow
from sdlc.workflows.question_host import QuestionHost


def test_question_host_is_on_the_mro():
    assert issubclass(FeatureWorkflow, QuestionHost)
    assert hasattr(FeatureWorkflow, "ask_and_wait")


def test_answer_question_keeps_its_handler_name():
    # The signal name IS the method name -- it is a wire contract. Renaming
    # it while moving modules silently breaks every client that signals a run.
    handler = FeatureWorkflow.answer_question
    definition = getattr(handler, "__temporal_signal_definition", None)
    assert definition is not None
    assert definition.name == "answer_question"


def test_question_state_is_owned_by_the_host():
    assert "_question_answers" in QuestionHost.__init__.__code__.co_names
    assert "_pending_questions" in QuestionHost.__init__.__code__.co_names
