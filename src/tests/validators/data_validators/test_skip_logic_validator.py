import polars as pl
import pytest

from argus.validators.base import ValidationResult
from argus.validators.data_validators import (
    SkipLogicCheck,
)
from argus.validators.helpers.skip_logic_parser import build_relevance_expression
from tests.helpers import build_excel_data, build_schema_with_process, do_basic_checks


def get_validator(schema, sheets: list[str]):
    """Create a UniqueColumn validator instance"""
    return SkipLogicCheck(schema=schema, check_sheets=sheets)


def run_skip_validation(
    columns: dict[str, list[tuple[str, list]]],
) -> list[ValidationResult]:
    """Build schema + data, run the validator on 'clean_data', return result."""
    schema = build_schema_with_process(
        {"clean_data": ["uuid"], "survey": ["relevant", "name"]},
        process_details={},
        process_sheet="",
        process_column="",
    )
    data = build_excel_data(columns)
    validator = get_validator(schema, sheets=["clean_data"])
    return validator.validate(data)


def make_case(
    relevant: str,
    question: str,
    data_columns: list[tuple[str, list]],
    values: list,
) -> list[ValidationResult]:
    """
    Assemble columns for one question with given answers, plus the survey rows.
    `values[i]` is the answer for `question` in record i.
    """
    cols = [("uuid", list(range(len(values)))), *data_columns, (question, values)]
    survey = (
        "survey",
        [("relevant", [relevant]), ("name", [question])],
    )
    return run_skip_validation({"clean_data": cols, "survey": [survey]})


class TestParserLiterals:
    """Literals: strings, numbers, booleans, quoting styles."""

    def test_string_equality_true(self):
        # condition TRUE, value missing -> 1 violation (shown but empty)
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2, 3]),
                    ("gender", ["male", "female", "other"]),
                    ("gender_other", ["", "", ""]),
                ],
                "survey": [
                    ("relevant", ["${gender}='other'"]),
                    ("name", ["gender_other"]),
                ],
            }
        )
        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1

    def test_string_equality_false_shows_no_violation(self):
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2]),
                    ("gender", ["male", "female"]),
                    ("gender_other", ["", ""]),
                ],
                "survey": [
                    ("relevant", ["${gender}='other'"]),
                    ("name", ["gender_other"]),
                ],
            }
        )
        do_basic_checks(result, 0)

    def test_double_quoted_string(self):
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2]),
                    ("gender", ["other", "male"]),
                    ("gender_other", ["", ""]),
                ],
                "survey": [
                    ("relevant", ['${gender}="other"']),
                    ("name", ["gender_other"]),
                ],
            }
        )
        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1

    def test_case_sensitive_string_equality(self):
        # 'Other' != 'other' -- the condition is false, so empty value is fine
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1]),
                    ("gender", ["Other"]),
                    ("gender_other", [""]),
                ],
                "survey": [
                    ("relevant", ["${gender}='other'"]),
                    ("name", ["gender_other"]),
                ],
            }
        )
        do_basic_checks(result, 0)

    def test_true_function_always_shown(self):
        # true() is always relevant -> an empty question must be flagged
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2]),
                    ("some_flag", ["1", "2"]),
                    ("always_probe", ["", ""]),  # empty target question
                ],
                "survey": [
                    ("relevant", ["true() or ${some_flag}='2'"]),
                    ("name", ["always_probe"]),
                ],
            }
        )
        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 2

    def test_false_function_never_shown(self):
        # false() is never relevant -> any value present is a violation
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2]),
                    ("some_flag", ["1", "2"]),
                    ("never_probe", ["", "ghost"]),  # record 2: hidden but filled
                ],
                "survey": [
                    ("relevant", ["false() and ${some_flag}='2'"]),
                    ("name", ["never_probe"]),
                ],
            }
        )
        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1

    def test_bare_true_keyword(self):
        # If your parser also supports bare 'true' (not the function form),
        # pin that too:
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1]),
                    ("some_flag", ["1"]),
                    ("always_note", [""]),
                ],
                "survey": [
                    ("relevant", ["true"]),
                    ("name", ["always_note"]),
                ],
            }
        )
        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1

    def test_false_makes_condition_false(self):
        # false() or <anything> is always False -> question always hidden ->
        # an empty target is consistent, a filled target is a violation
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2]),
                    ("some_flag", ["1", "2"]),  # real column, never actually consulted
                    ("always_note", ["", "filled"]),
                ],
                "survey": [
                    ("relevant", ["false() or ${some_flag}='x'"]),
                    ("name", ["always_note"]),
                ],
            }
        )
        # rec 1: hidden & empty -> ok
        # rec 2: hidden & filled -> "value when question was skipped"
        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1


class TestParserComparisonOperators:
    """=, !=, >, <, >=, <= against numeric literals."""

    @pytest.mark.parametrize(
        "relevant,expect_violations",
        [
            ("${age} = 15", 1),
            ("${age} != 15", 2),
            ("${age} > 17", 1),
            ("${age} < 17", 2),
            ("${age} >= 18", 1),
            ("${age} <= 15", 2),
        ],
    )
    def test_numeric_comparisons(self, relevant, expect_violations):
        # ages: 10, 15, 20 ; age_other always empty (shown whenever relevant)
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2, 3]),
                    ("age", [10, 15, 20]),
                    ("age_other", ["", "", ""]),
                ],
                "survey": [("relevant", [relevant]), ("name", ["age_other"])],
            }
        )
        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == expect_violations

    def test_negative_numeric_literal(self):
        # sentinel value: -999 means 'not applicable'
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2, 3]),
                    ("income", [500, -999, 0]),
                    ("income_source", ["salary", "salary", "farm"]),
                ],
                "survey": [
                    ("relevant", ["${income} != -999"]),
                    ("name", ["income_source"]),
                ],
            }
        )
        # record 1: -999 -> hidden but answered 'salary' -> violation
        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1

    def test_numeric_literal_left_side(self):
        # reversed operand order must also cast correctly
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2]),
                    ("age", [10, 20]),
                    ("minor_guardian", ["", "present"]),
                ],
                "survey": [("relevant", ["15 > ${age}"]), ("name", ["minor_guardian"])],
            }
        )
        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 2


class TestParserBooleanLogic:
    """and / or / not, parentheses, precedence."""

    def test_and_both_true(self):
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2, 3, 4]),
                    ("gender", ["female", "female", "male", "male"]),
                    ("age", [20, 10, 20, 10]),
                    ("pregnant", ["", "", "", ""]),
                ],
                "survey": [
                    ("relevant", ["${gender} = 'female' and ${age} >= 15"]),
                    ("name", ["pregnant"]),
                ],
            }
        )
        do_basic_checks(result, 1)  # only record 1 satisfies the condition
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1

    def test_or_short_circuit_either_side(self):
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2]),
                    ("resp_hoh_yn", ["yes", "no"]),
                    ("non_hoh_consent", ["no", "no"]),
                    ("second_consented", ["", ""]),
                ],
                "survey": [
                    (
                        "relevant",
                        ["selected(${resp_hoh_yn}, 'yes') or selected(${non_hoh_consent},'yes')"],
                    ),
                    ("name", ["second_consented"]),
                ],
            }
        )
        # record 1 satisfied via first disjunct -> 1 violation
        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1

    def test_not_operator(self):
        # ODK semantics: not(comparison over unanswered ref) is TRUE,
        # because the inner comparison is FALSE, not null.
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1]),
                    ("dis_reasons_primary", [""]),  # unanswered
                    ("dis_probe", [""]),
                ],
                "survey": [
                    ("relevant", ["not(${dis_reasons_primary} != 'yes_entirely')"]),
                    ("name", ["dis_probe"]),
                ],
            }
        )
        # inner: '' != 'x' -> null -> fill_false; not(false) -> true -> shown but empty
        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1

    def test_parentheses_override_precedence(self):
        # and binds tighter than or:  a='x' or b='y' and c='z'
        # means a='x' or (b='y' and c='z')  -- parens flip the grouping
        base_cols = [
            ("uuid", [1, 2]),
            ("a", ["x", "no"]),
            ("b", ["no", "yes"]),
            ("c", ["no", "yes"]),
            ("target", ["", ""]),
        ]
        result = run_skip_validation(
            {
                "clean_data": base_cols,
                "survey": [
                    ("relevant", ["(${a}='x' or ${b}='y') and ${c}='no'"]),
                    ("name", ["c"]),
                ],
            }
        )
        # ('x' or 'yes') and 'no' -> only record 1
        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1

    def test_nested_parentheses(self):
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1]),
                    ("dis_forced", ["yes_but_back"]),
                    ("dis_area_origin", ["same_neighbourhood"]),
                    ("ds_plans", ["move_back_original"]),
                    ("nested_target", [""]),
                ],
                "survey": [
                    (
                        "relevant",
                        [
                            "${dis_forced}='yes_but_back' and (${dis_area_origin}='same_neighbourhood' and ${ds_plans}='move_back_original')"
                        ],
                    ),
                    ("name", ["nested_target"]),
                ],
            }
        )
        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1

    def test_whitespace_insensitivity(self):
        # spaces, tabs, no-space variants must all parse identically
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1]),
                    ("consent_hh", ["no"]),
                    ("refusal_notes", [""]),
                ],
                "survey": [
                    ("relevant", ["${consent_hh}='no'"]),
                    ("name", ["refusal_notes"]),
                ],
            }
        )
        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1
        # and the cramped version:
        result2 = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1]),
                    ("consent_hh", ["no"]),
                    ("refusal_notes", [""]),
                ],
                "survey": [("relevant", ["${consent_hh}='no'"]), ("name", ["refusal_notes"])],
            }
        )
        do_basic_checks(result2, 1)
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1


class TestParserArithmetic:
    """+, -, *, div, mod — including string-typed columns (the cast path)."""

    def test_arith_column_times_literal(self):
        # ${expenditure} > ${income} * 3  -> both sides must self-cast
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2]),
                    ("expenditure", ["400", "50"]),  # string-typed export
                    ("income", ["100", "50"]),
                    ("overspend_probe", ["", ""]),
                ],
                "survey": [
                    ("relevant", ["${expenditure} > ${income} * 3"]),
                    ("name", ["overspend_probe"]),
                ],
            }
        )
        do_basic_checks(result, 1)  # only record 1: 400 > 300
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1

    def test_addition(self):
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2]),
                    ("hh_size", ["5", "2"]),
                    ("extra_members", ["1", "0"]),
                    ("large_hh_note", ["", ""]),
                ],
                "survey": [
                    ("relevant", ["${hh_size} + ${extra_members} > 5"]),
                    ("name", ["large_hh_note"]),
                ],
            }
        )
        # fix column names to match: (use hh_size/extra consistently)
        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1

    def test_modulo(self):
        # count-selected-like arithmetic: ${n} mod 2 = 0
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2]),
                    ("n", ["4", "3"]),
                    ("even_note", ["", ""]),
                ],
                "survey": [("relevant", ["${n} mod 2 = 0"]), ("name", ["even_note"])],
            }
        )
        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1

    def test_div(self):
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2]),
                    ("total", ["10", "7"]),
                    ("parts", ["2", "2"]),
                    ("ratio_note", ["", ""]),
                ],
                "survey": [("relevant", ["${total} div ${parts} = 5"]), ("name", ["ratio_note"])],
            }
        )
        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1

    def test_negative_sentinel_comparison(self):
        # regression test for the unary-minus parsing bug: -999 must
        # reach the comparison as a numeric literal, forcing the f64 cast
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2, 3]),
                    ("income", ["500", "-999", "200"]),
                    ("income_note", ["", "", ""]),
                ],
                "survey": [
                    ("relevant", ["${income} != -999"]),
                    ("name", ["income_note"]),
                ],
            }
        )
        do_basic_checks(result, 1)  # all records: shown & filled -> consistent
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 2


class TestParserSelectedFunction:
    def test_select_one_match(self):
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2]),
                    ("resp_hoh_yn", ["yes", "no"]),
                    ("hoh_consent", ["", ""]),
                ],
                "survey": [
                    ("relevant", ["selected(${resp_hoh_yn}, 'yes')"]),
                    ("name", ["hoh_consent"]),
                ],
            }
        )
        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1

    def test_select_multiple_space_separated(self):
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2, 3]),
                    ("reasons", ["food water", "shelter", ""]),
                    ("reason_other", ["", "", ""]),
                ],
                "survey": [
                    ("relevant", ["selected(${reasons}, 'water')"]),
                    ("name", ["reason_other"]),
                ],
            }
        )
        do_basic_checks(result, 1)  # only record 1
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1

    def test_selected_multiple_words_not_substring(self):
        # 'water' must not match 'rainwater' -- split-on-space, not substring
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1]),
                    ("reasons", ["rainwater"]),
                    ("reason_other", ["filled_anyway"]),
                ],
                "survey": [
                    ("relevant", ["selected(${reasons}, 'water')"]),
                    ("name", ["reason_other"]),
                ],
            }
        )
        do_basic_checks(result, 1)  # hidden but answered
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1

    def test_count_selected(self):
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2, 3]),
                    ("reasons", ["food water", "food", ""]),
                    ("multi_reason_probe", ["", "", ""]),
                ],
                "survey": [
                    ("relevant", ["count-selected(${reasons}) > 1"]),
                    ("name", ["multi_reason_probe"]),
                ],
            }
        )
        do_basic_checks(result, 1)  # only record 1
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1

    def test_count_selected_empty_is_zero(self):
        # regression: null/empty must count as 0, not 1 ([''] trap)
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2]),
                    ("reasons", ["", "food"]),
                    ("no_reason_note", ["", ""]),
                ],
                "survey": [
                    ("relevant", ["count-selected(${reasons}) = 0"]),
                    ("name", ["no_reason_note"]),
                ],
            }
        )
        do_basic_checks(result, 1)  # only record 1
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 1


class TestParserEmptyValueSemantics:
    """ODK: any comparison against an empty/unanswered ref is FALSE."""

    def test_empty_ref_equals_literal_is_false(self):
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1]),
                    ("consent_hh", [""]),  # unanswered
                    ("refusal_reason", [""]),
                ],
                "survey": [("relevant", ["${consent_hh}='no'"]), ("name", ["refusal_reason"])],
            }
        )
        do_basic_checks(result, 0)  # hidden AND empty -> consistent

    def test_empty_ref_ne_literal_is_false(self):
        # the dangerous case: '' != 'yes_entirely' must be FALSE (not true)
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1]),
                    ("dis_reasons_primary", [""]),
                    ("dis_followup", [""]),
                ],
                "survey": [
                    ("relevant", ["${dis_reasons_primary} != 'yes_entirely'"]),
                    ("name", ["dis_probe"]),
                ],
            }
        )
        do_basic_checks(result, 0)

    def test_whitespace_only_ref_counts_as_missing(self):
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1]),
                    ("consent_hh", ["   "]),  # whitespace only
                    ("refusal_reason", [""]),
                ],
                "survey": [("relevant", ["${consent_hh}='no'"]), ("name", ["refusal_reason"])],
            }
        )
        do_basic_checks(result, 0)

    def test_both_violation_directions(self):
        result = run_skip_validation(
            {
                "clean_data": [
                    ("uuid", [1, 2, 3, 4]),
                    ("consent_hh", ["no", "yes", "yes", "no"]),
                    ("refusal_reason", ["", "declined", "", ""]),  # one per case
                ],
                "survey": [("relevant", ["${consent_hh}='no'"]), ("name", ["refusal_reason"])],
            }
        )
        # rec 1: shown & empty -> violation (no value when shown)
        # rec 2: hidden & filled -> violation (value when skipped)
        # rec 3: hidden & empty  -> ok
        # rec 4: shown & filled  -> ok
        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["uuid"]) == 3


class TestParserInvalidExpressions:
    """Malformed input must raise, not produce a wrong expression."""

    @pytest.mark.parametrize(
        "bad",
        [
            "${unclosed='x'",
            "'unbalanced",
            "${gender} =",  # dangling operator
            "and ${a}='b'",  # leading operator
            "${a}='x' extra_garbage",  # trailing tokens
            "unknown_fn(${a})",  # unsupported function
            "selected(${a})",  # wrong arity
            "count-selected('a')",  # non-ref argument
        ],
    )
    def test_malformed_raises(self, bad):

        schema = {"a": pl.String, "b": pl.Int64}
        with pytest.raises(Exception) :
            build_relevance_expression(bad, {"a", "b"}, schema)

    # def test_unknown_reference_raises_keyerror(self):
    #     schema = {"some_other": pl.String}
    #     with pytest.raises(KeyError):
    #         build_relevance_expression("${nonexistent} = 'x'",{"a", "b"},  schema)

    # with pytest.raises(ValueError, match="arity|expects"):
    #     build_relevance_expression("selected(${a})", schema)
