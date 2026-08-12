import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).parents[1] / "scripts" / "mutation_engine.py"
_SPEC = importlib.util.spec_from_file_location("arafix_mutation_engine", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MUTATION = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MUTATION
_SPEC.loader.exec_module(_MUTATION)

apply_mutation = _MUTATION.apply_mutation
generate_cases = _MUTATION.generate_cases


def test_supported_mutations_are_explicit_and_reproducible() -> None:
    text = "المتاحف، غيرها لا"
    first = generate_cases([("s1", text)], seed=2)
    second = generate_cases([("s1", text)], seed=2)

    assert first == second
    assert first
    assert {case.recoverability for case in first} == {
        "supported",
        "conditional-density",
    }
    assert any(case.recoverability == "supported" for case in first)
    assert any(case.recoverability == "conditional-density" for case in first)
    assert all(case.expected == text for case in first)


def test_mutation_is_conservative_when_evidence_is_absent() -> None:
    assert apply_mutation("نص بلا ياء", "pdf_al_meem_confusion") is None
    assert apply_mutation("نص بلا فاصلة", "punctuation_attachment") is None


def test_mutation_cases_keep_category_and_original_provenance() -> None:
    cases = generate_cases([("page-1", "هذا، نص فيه ياء")], seed=0)

    assert all(case.case_id.startswith("page-1::") for case in cases)
    assert all(case.original != case.mutated for case in cases)
    assert {case.category for case in cases} >= {"spacing", "punctuation"}
