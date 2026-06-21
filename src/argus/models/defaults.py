"""
If changing the names/alternate names some of these sheets or columns
it might also be necessary to update some of the sheets/columns for the dynamic
scheema in dynamic_model.py too.
"""

from .base import ProcessValueMap, SchemaColumnMap, SchemaSheetMap

CHOICES_SHEET: SchemaSheetMap = SchemaSheetMap(
    standard_name="choices",
    allow_fuzzy_matching=False,
    mandatory_columns=[
        SchemaColumnMap(
            standard_name="list_name",
            allow_fuzzy_matching=False,
        ),
        SchemaColumnMap(
            standard_name="name",
            allow_fuzzy_matching=False,
        ),
    ],
)

SURVEY_SHEET: SchemaSheetMap = SchemaSheetMap(
    standard_name="survey",
    allow_fuzzy_matching=False,
    mandatory_columns=[
        SchemaColumnMap(
            standard_name="type",
            allow_fuzzy_matching=False,
            process_values=[
                ProcessValueMap(
                    process_name="data_type_numeric_check", values=["integer", "decimal"]
                ),
                ProcessValueMap(process_name="data_type_temporal_check", values=["date"]),
            ],
        ),
        SchemaColumnMap(
            standard_name="name",
            allow_fuzzy_matching=False,
        ),
        SchemaColumnMap(
            standard_name="calculation",
            allow_fuzzy_matching=False,
        ),
    ],
)
DELETION_LOG_SHEET: SchemaSheetMap = SchemaSheetMap(
    standard_name="deletion_log",
    allow_fuzzy_matching=False,
    mandatory_columns=[
        SchemaColumnMap(
            standard_name="uuid",
            alternate_names=["_uuid"],
            is_unique=True,
            allow_fuzzy_matching=False,
        ),
        SchemaColumnMap(standard_name="reason_deletion"),
        SchemaColumnMap(standard_name="enum_id"),
    ],
)

READ_ME_SHEET: SchemaSheetMap = SchemaSheetMap(standard_name="read_me", allow_fuzzy_matching=False)

SAMPLING_INFO_SHEET: SchemaSheetMap = SchemaSheetMap(
    standard_name="sampling_info",
    allow_fuzzy_matching=False,
    required=False,
    mandatory_columns=[
        SchemaColumnMap(standard_name="strata"),
        SchemaColumnMap(standard_name="population"),
        SchemaColumnMap(standard_name="planned surveys"),
        SchemaColumnMap(standard_name="sampled surveys"),
        SchemaColumnMap(standard_name="modality (in-person / remote / mixed)"),
    ],
)


def create_variable_tracker_sheet(
    standard_name: str = "variable_tracker", alternate_names: list[str] | None = None
):
    if alternate_names is None:
        alternate_names = []
    return SchemaSheetMap(
        standard_name=standard_name,
        alternate_names=alternate_names,
        allow_fuzzy_matching=False,
        mandatory_columns=[
            SchemaColumnMap(standard_name="variable"),
            SchemaColumnMap(standard_name="action"),
            SchemaColumnMap(standard_name="rationale"),
        ],
    )


def create_enumerator_performance_sheet(
    standard_name: str = "enumerator_performance_log", alternate_names: list[str] | None = None
):
    if alternate_names is None:
        alternate_names = []
    return SchemaSheetMap(
        standard_name=standard_name, alternate_names=alternate_names, required=False
    )


CLEAN_DATA_SHEET: SchemaSheetMap = SchemaSheetMap(
    standard_name="clean_data",
    allow_fuzzy_matching=False,
    mandatory_columns=[
        SchemaColumnMap(
            standard_name="uuid",
            alternate_names=["_uuid"],
            is_unique=True,
            allow_fuzzy_matching=False,
        ),
        SchemaColumnMap(
            standard_name="_id",
            allow_fuzzy_matching=False,
        ),
        SchemaColumnMap(standard_name="weight"),
    ],
)
CONSENT_COLUMN: SchemaColumnMap = SchemaColumnMap(
    standard_name="consent",
    alternate_names=["consentement"],
    process_values=[
        ProcessValueMap(process_name="consent_check_validation", values=["yes", "oui"])
    ],
)
RAW_DATA_SHEET: SchemaSheetMap = SchemaSheetMap(
    standard_name="raw_data",
    allow_fuzzy_matching=False,
    mandatory_columns=[
        SchemaColumnMap(
            standard_name="uuid",
            alternate_names=["_uuid"],
            is_unique=True,
            allow_fuzzy_matching=False,
        ),
        SchemaColumnMap(
            standard_name="_id",
            allow_fuzzy_matching=False,
        ),
        CONSENT_COLUMN,
    ],
)


def create_cleaning_log_sheet(
    standard_name: str,
    id_column: str | None,
    id_column_alt: list[str] | None,
    alternate_names: list[str] | None = None,
) -> SchemaSheetMap:
    if alternate_names is None:
        alternate_names = []

    sheet: SchemaSheetMap = SchemaSheetMap(
        standard_name=standard_name,
        alternate_names=alternate_names,
        allow_fuzzy_matching=False,
        mandatory_columns=[
            SchemaColumnMap(standard_name="old_value"),
            SchemaColumnMap(standard_name="new_value"),
            SchemaColumnMap(
                standard_name="change_type",
                process_values=[
                    ProcessValueMap(
                        process_name="cleaning_log_validation",
                        values=["yes", "change_response", "blank_response"],
                    )
                ],
            ),
            SchemaColumnMap(standard_name="variable", alternate_names=["question"]),
        ],
    )

    if id_column is not None:
        _ = sheet.add_mandatory_column(
            SchemaColumnMap(
                standard_name=id_column,
                alternate_names=id_column_alt if id_column_alt is not None else [],
            )
        )
    return sheet
