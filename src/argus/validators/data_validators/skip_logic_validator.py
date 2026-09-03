from typing import override

import polars as pl

from ...common.list_matching import filter_loaded_sheets, match_list
from ...loaders.base_excel_loader import ExcelLoaderData
from ...models.base_dataset_schemas import BaseDatasetSchema
from ...validators.base import BaseValidator, SeverityLevel, ValidationResult
from ..helpers.data_helpers import (
    get_data_loaded_columns,
    get_data_loaded_sheets,
    get_data_sheet_ids,
)
from ..helpers.skip_logic_parser import build_relevance_expression, is_missing


class SkipLogicCheck(BaseValidator):
    def __init__(
        self,
        schema: BaseDatasetSchema,
        survey_sheet: str = "survey",
        survey_relevant_column: str = "relevant",
        survey_name_column: str = "name",
        check_sheets: list[str] | None = None,
    ) -> None:
        """

        Args:
            schema (BaseDatasetSchema): dataset schema
            survey_sheet (str, optional): name of the kobo survey sheet.
                Defaults to 'survey'.
            survey_relevant_column (str, optional): name of the relevant column in the
                kobo survey sheet. Defaults to 'relevant'.
            survey_name_column (str, optional): name of the name column in the
                kobo survey sheet. Defaults to 'name'.
            check_sheets (list[str] | None): list of clean data sheets to check

        """
        self.schema: BaseDatasetSchema = schema
        self.survey_sheet: str = survey_sheet
        self.survey_relevant_column: str = survey_relevant_column
        self.survey_name_column: str = survey_name_column
        self.check_sheets: list[str] = check_sheets if check_sheets is not None else ["clean_data"]

    @property
    @override
    def name(self) -> str:
        return "SkipLogicCheck"

    @override
    def validate(
        self, data: ExcelLoaderData, **kwargs: str | int | float
    ) -> list[ValidationResult]:
        """Checks that the columns/questions in the survey that contain skip logic
        contain:
        - no value when the question was skipped
        - a value when the question was not skipped

        This is done through converting kobo skip logic into polars expressions.

        Limitations:
        This process does not currently support column references that are on
        different sheets. Joining the datasets together is possible but it causes
        the dataset to be quite large (in terms of height) making the process
        computationally expensive. Any columns that are affected by this produce
        a warning.

        Returns:
            list[ValidationResult]: a list of validation results, if any
        """

        results: list[ValidationResult] = []
        failed_conversions: list[dict[str, str]] = []

        all_issues_df: pl.DataFrame = pl.DataFrame(
            [
                pl.Series("sheet", [], dtype=pl.String),
                pl.Series("uuid_column", [], dtype=pl.String),
                pl.Series("uuid", [], dtype=pl.String),
                pl.Series("question", [], dtype=pl.String),
                pl.Series("issue", [], dtype=pl.String),
            ]
        )

        # check all the sheets exist

        result, data_loaded_sheets = get_data_loaded_sheets(
            data=data,
            sheet_names=[self.survey_sheet, *self.check_sheets],
            rule=self.name,
        )

        if result is not None:
            results.append(result)
            return results

        result, data_loaded_columns = get_data_loaded_columns(
            data={
                self.survey_relevant_column: data_loaded_sheets[self.survey_sheet],
                self.survey_name_column: data_loaded_sheets[self.survey_sheet],
            },
            rule=self.name,
        )

        if result is not None:
            results.append(result)
            return results

        filtered_loaded_sheets = filter_loaded_sheets(self.check_sheets, data_loaded_sheets)
        result, data_id_columns = get_data_sheet_ids(
            schema=self.schema, data=filtered_loaded_sheets, rule=self.name
        )

        if result:
            results.extend(result)
            return results

        # filter survey sheet to get columns with skip logic
        survey_relevant_columns_df = (
            data_loaded_sheets[self.survey_sheet]
            .data.filter(
                pl.col(
                    data_loaded_columns[self.survey_relevant_column].data_column_name
                ).str.strip_chars()
                != ""
            )
            .select(
                [
                    pl.col(
                        data_loaded_columns[self.survey_relevant_column].data_column_name
                    ).str.to_lowercase(),
                    pl.col(
                        data_loaded_columns[self.survey_name_column].data_column_name
                    ).str.to_lowercase(),
                ]
            )
        )

        survey_relevant_columns = (
            survey_relevant_columns_df.select(
                data_loaded_columns[self.survey_name_column].data_column_name
            )
            .to_series()
            .to_list()
        )

        if not survey_relevant_columns:
            return results

        for sheet in self.check_sheets:
            # get columns relevant for sheet
            check_columns = set(
                match_list(data_loaded_sheets[sheet].data.columns, survey_relevant_columns)
            )

            if not check_columns:
                continue

            expressions: dict[str, pl.Expr] = {}
            # build an expression for each relevant survey question
            # this only loops through the relevant survey rows so
            # using iter_rows is not too bad
            for row in survey_relevant_columns_df.iter_rows(named=True):
                if (
                    row[data_loaded_columns[self.survey_name_column].data_column_name]
                    not in check_columns
                ):
                    continue

                try:
                    expressions[
                        row[data_loaded_columns[self.survey_name_column].data_column_name]
                    ] = build_relevance_expression(
                        row[data_loaded_columns[self.survey_relevant_column].data_column_name],
                        set(data_loaded_sheets[sheet].data.columns),
                    )
                except Exception as e:
                    # most likely due to column references in other sheets but
                    # will also report errors with the expression builder
                    failed_conversions.append(
                        {
                            "sheet": sheet,
                            "question": row[
                                data_loaded_columns[self.survey_name_column].data_column_name
                            ],
                            "expression": data_loaded_columns[
                                self.survey_relevant_column
                            ].data_column_name,
                            "exception": str(e),
                        }
                    )
                    continue

            if not expressions:
                continue

            check_sheet_id_column = data_id_columns[sheet][0]

            # useful for finind out which columns are causing errors in the
            # below select statements
            # df = data_loaded_sheets[sheet].data
            # for q, expr in expressions.items():
            #     if q not in check_columns:
            #         continue
            #     try:
            #         df.select(expr.alias(q))
            #     except Exception as e:
            #         print(f"OFFENDER: {q!r}\n  {type(e).__name__}: {e}")

            # values when there shouldnt be
            value_exist_df = (
                data_loaded_sheets[sheet]
                .data.lazy()
                .select(
                    [
                        check_sheet_id_column.data_column_name,
                        *(e.alias(q) for q, e in expressions.items() if q in check_columns),
                    ]
                )
                .collect()
                .unpivot(
                    index=check_sheet_id_column.data_column_name,
                    value_name="shown",
                    variable_name=data_loaded_columns[self.survey_name_column].data_column_name,
                )
            )

            # no values when there should be
            value_not_exist_df = (
                data_loaded_sheets[sheet]
                .data.lazy()
                .select(
                    [
                        check_sheet_id_column.data_column_name,
                        *(is_missing(q).alias(q) for q in expressions if q in check_columns),
                    ]
                )
                .collect()
                .unpivot(
                    index=check_sheet_id_column.data_column_name,
                    value_name="missing",
                    variable_name=data_loaded_columns[self.survey_name_column].data_column_name,
                )
            )

            res = value_exist_df.join(
                value_not_exist_df,
                on=[
                    check_sheet_id_column.data_column_name,
                    data_loaded_columns[self.survey_name_column].data_column_name,
                ],
            ).join(
                survey_relevant_columns_df,
                on=data_loaded_columns[self.survey_name_column].data_column_name,
            )

            issues_df = (
                res.filter(pl.col("shown") == pl.col("missing"))
                .with_columns(
                    pl.when(pl.col("missing"))
                    .then(pl.lit(self._("skip_logic_validator.invalid_values.issue.empty_value")))
                    .otherwise(
                        pl.lit(self._("skip_logic_validator.invalid_values.issue.not_empty_value"))
                    )
                    .alias("issue")
                )
                .select(
                    pl.lit(sheet).alias("sheet"),
                    pl.lit(check_sheet_id_column.data_column_name).alias("uuid_column"),
                    pl.col(check_sheet_id_column.data_column_name).cast(pl.String).alias("uuid"),
                    pl.col(data_loaded_columns[self.survey_name_column].data_column_name).alias(
                        "question"
                    ),
                    "issue",
                )
                .sort(["question"])
            )

            all_issues_df = pl.concat([all_issues_df, issues_df])

        if failed_conversions:
            # might have duplicates but not a big issue
            results.append(
                ValidationResult(
                    rule=self.name,
                    message=self._(
                        "skip_logic_validator.failed_conversions",
                        count=len(failed_conversions),
                    ),
                    severity=SeverityLevel.WARNING,
                    details=pl.DataFrame(failed_conversions).to_dict(as_series=False),
                )
            )

        if all_issues_df.height > 0:
            results.append(
                ValidationResult(
                    rule=self.name,
                    message=self._(
                        "skip_logic_validator.invalid_values",
                        count=all_issues_df.height,
                    ),
                    severity=SeverityLevel.ERROR,
                    details=all_issues_df.to_dict(as_series=False),
                )
            )

        return results
