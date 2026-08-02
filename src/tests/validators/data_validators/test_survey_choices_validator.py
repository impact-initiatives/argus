from argus.validators.data_validators.survey_choices_validator import (
    SurveyChoicesCheck,
)
from tests.helpers import build_excel_data, build_schema_with_process, do_basic_checks


def get_validator(schema):
    """Create a UniqueColumn validator instance"""
    return SurveyChoicesCheck(schema=schema)


class TestSurveyChoices:
    def test_valid_data(
        self,
    ):
        schema = build_schema_with_process(
            {"clean_data": ["uuid"], "survey": ["type", "name"], "choices": ["list_name", "name"]},
            process_details={},
            process_sheet="",
            process_column="",
        )
        data = build_excel_data(
            {
                "clean_data": [
                    ("uuid", [1, 2, 3]),
                    ("gender", ["male", "female", "other"]),
                    ("items", ["rice pasta", "pasta super_food", "flour"]),
                    (
                        "question3",
                        [
                            1,
                            2,
                            3,
                        ],
                    ),
                ],
                "survey": [
                    ("type", ["select_one gender", "select_multiple item", "integer"]),
                    ("name", ["gender", "items", "question3"]),
                ],
                "choices": [
                    ("list_name", ["gender", "gender", "gender", "item", "item", "item", "item"]),
                    ("name", ["male", "female", "other", "rice", "pasta", "flour", "super_food"]),
                ],
            }
        )
        validor = get_validator(schema)
        result = validor.validate(data)

        do_basic_checks(result, 0)

    def test_missing_sheet_data(
        self,
    ):
        schema = build_schema_with_process(
            {"clean_data": ["uuid"], "survey": ["type", "name"], "choices": ["list_name", "name"]},
            process_details={},
            process_sheet="",
            process_column="",
        )
        data = build_excel_data(
            {
                "clean_data": [
                    ("uuid", [1, 2, 3]),
                    ("gender", ["male", "female", "other"]),
                    ("items", ["rice pasta", "pasta super_food", "flour"]),
                    (
                        "question3",
                        [
                            1,
                            2,
                            3,
                        ],
                    ),
                ],
                "survey_missing": [
                    ("type", ["select_one gender", "select_multiple item", "integer"]),
                    ("name", ["gender", "items", "question3"]),
                ],
                "choices": [
                    ("list_name", ["gender", "gender", "gender", "item", "item", "item", "item"]),
                    ("name", ["male", "female", "other", "rice", "pasta", "flour", "super_food"]),
                ],
            }
        )
        validor = get_validator(schema)
        result = validor.validate(data)

        do_basic_checks(result, 1)

    def test_missing_column_data(
        self,
    ):
        schema = build_schema_with_process(
            {"clean_data": ["uuid"], "survey": ["type", "name"], "choices": ["list_name", "name"]},
            process_details={},
            process_sheet="",
            process_column="",
        )
        data = build_excel_data(
            {
                "clean_data": [
                    ("uuid", [1, 2, 3]),
                    ("gender", ["male", "female", "other"]),
                    ("items", ["rice pasta", "pasta super_food", "flour"]),
                    (
                        "question3",
                        [
                            1,
                            2,
                            3,
                        ],
                    ),
                ],
                "survey": [
                    ("type_missing", ["select_one gender", "select_multiple item", "integer"]),
                    ("name", ["gender", "items", "question3"]),
                ],
                "choices": [
                    ("list_name", ["gender", "gender", "gender", "item", "item", "item", "item"]),
                    ("name", ["male", "female", "other", "rice", "pasta", "flour", "super_food"]),
                ],
            }
        )
        validor = get_validator(schema)
        result = validor.validate(data)

        do_basic_checks(result, 1)

    def test_missing_id_column(
        self,
    ):
        schema = build_schema_with_process(
            {"clean_data": ["uuid"], "survey": ["type", "name"], "choices": ["list_name", "name"]},
            process_details={},
            process_sheet="",
            process_column="",
            unique_columns=False,
        )
        data = build_excel_data(
            {
                "clean_data": [
                    ("uuid", [1, 2, 3]),
                    ("gender", ["male", "female", "other"]),
                    ("items", ["rice pasta", "pasta super_food", "flour"]),
                    (
                        "question3",
                        [
                            1,
                            2,
                            3,
                        ],
                    ),
                ],
                "survey": [
                    ("type", ["select_one gender", "select_multiple item", "integer"]),
                    ("name", ["gender", "items", "question3"]),
                ],
                "choices": [
                    ("list_name", ["gender", "gender", "gender", "item", "item", "item", "item"]),
                    ("name", ["male", "female", "other", "rice", "pasta", "flour", "super_food"]),
                ],
            }
        )
        validor = get_validator(schema)
        result = validor.validate(data)

        do_basic_checks(result, 1)

    def test_invalid_select_one_data(
        self,
    ):
        schema = build_schema_with_process(
            {"clean_data": ["uuid"], "survey": ["type", "name"], "choices": ["list_name", "name"]},
            process_details={},
            process_sheet="",
            process_column="",
        )
        data = build_excel_data(
            {
                "clean_data": [
                    ("uuid", [1, 2, 3]),
                    ("gender", ["invalid_gender", "female", "other"]),
                    ("items", ["rice pasta", "pasta super_food", "flour"]),
                    (
                        "question3",
                        [
                            1,
                            2,
                            3,
                        ],
                    ),
                ],
                "survey": [
                    ("type", ["select_one gender", "select_multiple item", "integer"]),
                    ("name", ["gender", "items", "question3"]),
                ],
                "choices": [
                    ("list_name", ["gender", "gender", "gender", "item", "item", "item", "item"]),
                    ("name", ["male", "female", "other", "rice", "pasta", "flour", "super_food"]),
                ],
            }
        )
        validor = get_validator(schema)
        result = validor.validate(data)

        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert result[0].details["invalid_value"][0] == "invalid_gender"

    def test_invalid_select_multiple_data(
        self,
    ):
        schema = build_schema_with_process(
            {"clean_data": ["uuid"], "survey": ["type", "name"], "choices": ["list_name", "name"]},
            process_details={},
            process_sheet="",
            process_column="",
        )
        data = build_excel_data(
            {
                "clean_data": [
                    ("uuid", [1, 2, 3]),
                    ("gender", ["male", "female", "other"]),
                    ("items", ["rice apples", "pasta super_food", "flour"]),
                    (
                        "question3",
                        [
                            1,
                            2,
                            3,
                        ],
                    ),
                ],
                "survey": [
                    ("type", ["select_one gender", "select_multiple item", "integer"]),
                    ("name", ["gender", "items", "question3"]),
                ],
                "choices": [
                    ("list_name", ["gender", "gender", "gender", "item", "item", "item", "item"]),
                    ("name", ["male", "female", "other", "rice", "pasta", "flour", "super_food"]),
                ],
            }
        )
        validor = get_validator(schema)
        result = validor.validate(data)

        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert result[0].details["invalid_value"][0] == "rice apples"

    def test_choice_data(
        self,
    ):
        schema = build_schema_with_process(
            {"clean_data": ["uuid"], "survey": ["type", "name"], "choices": ["list_name", "name"]},
            process_details={},
            process_sheet="",
            process_column="",
        )
        data = build_excel_data(
            {
                "clean_data": [
                    ("uuid", [1, 2, 3]),
                    ("gender", ["male", "female", "other"]),
                    ("items", ["rice flour", "pasta super_food", "flour"]),
                    (
                        "question3",
                        [
                            1,
                            2,
                            3,
                        ],
                    ),
                ],
                "survey": [
                    ("type", ["select_one gender", "select_multiple item", "integer"]),
                    ("name", ["gender", "items", "question3"]),
                ],
                "choices": [
                    ("list_name", ["gender", "gender", "gender", "item", "item", "item", "item"]),
                    (
                        "name",
                        ["male man", "female", "other", "rice", "pasta", "flour", "super_food"],
                    ),
                ],
            }
        )
        validor = get_validator(schema)
        result = validor.validate(data)

        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert result[0].details["invalid_value"][0] == "male"
