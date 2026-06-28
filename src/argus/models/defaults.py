"""
NOTE: Most defaults are now stored in yaml files in github.
The ones retained here are referenced by dynamic_model.py

If changing the names/alternate names some of these sheets or columns
it might also be necessary to update some of the sheets/columns for the dynamic
scheema in dynamic_model.py too.
"""

from .base import ProcessValueMap, SchemaColumnMap, SchemaSheetMap

CONSENT_COLUMN: SchemaColumnMap = SchemaColumnMap(
    standard_name="consent",
    alternate_names=["consentement"],
    process_values=[
        ProcessValueMap(process_name="consent_check_validation", values=["yes", "oui"])
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
