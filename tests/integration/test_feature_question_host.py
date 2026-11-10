# 020 T026: re-pointed from FeatureWorkflow to GraphWorkflow; the historical rationale is kept.
from sdlc.workflows.graph import GraphWorkflow
from sdlc.workflows.question_host import QuestionHost


def test_question_host_is_on_the_mro():
    assert issubclass(GraphWorkflow, QuestionHost)
    assert hasattr(GraphWorkflow, "ask_and_wait")


def test_answer_question_keeps_its_handler_name():
    # The signal name IS the method name -- it is a wire contract. Renaming
    # it while moving modules silently breaks every client that signals a run.
    handler = GraphWorkflow.answer_question
    definition = getattr(handler, "__temporal_signal_definition", None)
    assert definition is not None
    assert definition.name == "answer_question"


def test_question_state_is_owned_by_the_host():
    assert "_question_answers" in QuestionHost.__init__.__code__.co_names
    assert "_pending_questions" in QuestionHost.__init__.__code__.co_names
