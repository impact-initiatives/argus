from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import override

import polars as pl

from ..common.list_matching import (
    filter_list,
    get_set_overlap,
    match_list,
    match_list_to_list,
    unique_list,
)
from ..config import settings
from ..loaders.base_excel_loader import BaseExcelLoader
from ..locales.il8n import _
from ..models.base import (
    DynamicSheetMatching,
    SchemaColumnMap,
    SchemaSheetMap,
    SheetClassification,
)
from ..models.base_dataset import BaseDataset
from ..validators.base import BaseValidator, SeverityLevel, ValidationResult
from ..validators.data_validators import (
    CleaningLogToCleanCheck,
    ConsentCheck,
    CrossSheetIdCheck,
    CrossSheetRowSumCheck,
    DataTypeCheck,
    NaNDataCheck,
    RawToCleanToLogCheck,
    SurveyChoicesCheck,
)
from .base_dataset_schemas import BaseDatasetSchema
from .defaults import CONSENT_COLUMN, create_cleaning_log_sheet, create_deletion_log_sheet


@dataclass(slots=True)
class SortedSheets:
    cleaning_log_sheets: list[str] = field(default_factory=list)
    deletion_log_sheets: list[str] = field(default_factory=list)
    clean_sheets: list[str] = field(default_factory=list)
    raw_sheets: list[str] = field(default_factory=list)
    unknown_sheets: list[str] = field(default_factory=list)


class DynamicDataset(BaseDataset):
    """This aims to analyse an excel file and attepts to:
    - idenfity needed sheets, sheet types, sheet relationships
    - build a dataset schema
    - initialise the required validators

    This process focuses on sheets related to loops and non standardised datasets.
      Specifically:
    - possible parent/child clean_data sheets
    - possible parent/child raw_data sheets
    - possible parent/child cleaning_log sheets
    - other non standardised datasets

    Some sheets/columns that are always expected are still specified
      in DynamicDatasetSchema.

    If sheets and columns are named according to the minimum standards checklist
    then this process should have a reasonable chance of succeeding. The less
    the minimum standards checklist is followed, the more likely this process and
    the subsequent validation rules are to produce errors related to not
    finding required sheets or columns.

    Limitations:
    - loops within loops are currently not supported.

    """

    def __init__(self, schema_path: Path | str, validator_path: Path | str) -> None:
        super().__init__(schema_path, validator_path)
        self.schema: BaseDatasetSchema = self.get_schema()
        self.sheet_matching: dict[str, DynamicSheetMatching] = {}
        self.sorted_sheets: SortedSheets = SortedSheets()

    @override
    def process_data(self) -> list[ValidationResult]:
        """Runs all the steps."""
        all_results: list[ValidationResult] = []

        results = self.match_data()
        if results:
            all_results.extend(results)

        results, consent_sheet = self.build_schema()
        if results:
            all_results.extend(results)

        # this must come after build_schema
        # to ensure the complete schema is referenced
        self.validators: list[BaseValidator] = self.get_validators()

        results = self.build_validators(consent_sheet)

        if results:
            all_results.extend(results)

        return all_results

    def build_validators(self, consent_sheet: str | None) -> list[ValidationResult]:
        """builds a list of validators matched to use the dynamically created schema.

        Current assumptions:
        - there is only ever one deletion log and it only lists deleted
          records for the parent object

        """
        results: list[ValidationResult] = []
        rule = "DynamicSchemaCreation_build_validators"

        for sheet, details in self.sheet_matching.items():
            if details.linked_cleaning_log is not None:
                cleaning_log_sheet = details.linked_cleaning_log
            elif len(self.sorted_sheets.cleaning_log_sheets) == 1:
                cleaning_log_sheet = self.sorted_sheets.cleaning_log_sheets[0]
            else:
                cleaning_log_sheet = None

            if details.classification == SheetClassification.CLEAN_DATA_SHEET:
                if cleaning_log_sheet is not None:
                    self.validators.append(
                        CrossSheetIdCheck(
                            schema=self.schema,
                            master_sheet=sheet,
                            child_sheets=[cleaning_log_sheet],
                        )
                    )
                    self.validators.append(
                        CleaningLogToCleanCheck(
                            schema=self.schema,
                            cleaning_log_sheet=cleaning_log_sheet,
                            clean_data_sheet=sheet,
                        )
                    )
                else:
                    results.append(
                        ValidationResult(
                            rule=rule,
                            message=_(
                                "dynamic_model.build_validators.CleaningLogToClean", sheet=sheet
                            ),
                            sheet_name=sheet,
                            severity=SeverityLevel.ERROR,
                        )
                    )

                if details.linked_raw_sheet is not None:
                    self.validators.append(
                        RawToCleanToLogCheck(
                            schema=self.schema,
                            cleaning_log_sheet=cleaning_log_sheet,
                            clean_data_sheet=sheet,
                            raw_data_sheet=details.linked_raw_sheet,
                        )
                    )
                else:
                    results.append(
                        ValidationResult(
                            rule=rule,
                            message=_(
                                "dynamic_model.build_validators.RawToCleanToLog", sheet=sheet
                            ),
                            severity=SeverityLevel.ERROR,
                            sheet_name=sheet,
                        )
                    )
                if details.parent_sheet is not None:
                    self.validators.append(
                        CrossSheetIdCheck(
                            schema=self.schema,
                            master_sheet=details.parent_sheet,
                            child_sheets=[sheet],
                        )
                    )

            elif details.classification == SheetClassification.RAW_DATA_SHEET:
                rowsum_sheets: list[str] = []
                id_check_sheets: list[str] = []
                clean_sheet = None
                master_deletion_log = None
                if details.linked_clean_sheet is not None:
                    rowsum_sheets.append(details.linked_clean_sheet)
                    if details.linked_deletion_log is not None:
                        rowsum_sheets.append(details.linked_deletion_log)
                    elif (
                        len(self.sorted_sheets.deletion_log_sheets) == 1
                        and len(self.sorted_sheets.raw_sheets) > 1
                    ):
                        # one deletion log for multiple sheets. likely to produce
                        # incorrect calculations if child sheets have removed records
                        # but the parent was not removed.
                        master_deletion_log = self.sorted_sheets.deletion_log_sheets[0]

                    id_check_sheets.append(details.linked_clean_sheet)
                    clean_sheet = self.sheet_matching[details.linked_clean_sheet]

                    self.validators.append(
                        CrossSheetRowSumCheck(
                            schema=self.schema,
                            master_sheet=sheet,
                            child_sheets=rowsum_sheets,
                            master_deletion_log=master_deletion_log,
                        )
                    )
                else:
                    results.append(
                        ValidationResult(
                            rule=rule,
                            message=_(
                                "dynamic_model.build_validators.CrossSheetRowSumCheck", sheet=sheet
                            ),
                            severity=SeverityLevel.ERROR,
                            sheet_name=sheet,
                        )
                    )

                if details.parent_sheet is not None:
                    self.validators.append(
                        CrossSheetIdCheck(
                            schema=self.schema,
                            master_sheet=details.parent_sheet,
                            child_sheets=[sheet],
                        )
                    )

                if clean_sheet is not None:
                    if details.parent_sheet is None and details.linked_deletion_log is not None:
                        id_check_sheets.append(details.linked_deletion_log)
                    if cleaning_log_sheet is not None:
                        id_check_sheets.append(cleaning_log_sheet)

                    self.validators.append(
                        CrossSheetIdCheck(
                            schema=self.schema,
                            master_sheet=sheet,
                            child_sheets=id_check_sheets,
                        )
                    )
                else:
                    results.append(
                        ValidationResult(
                            rule=rule,
                            message=_(
                                "dynamic_model.build_validators.CrossSheetIdCheck", sheet=sheet
                            ),
                            severity=SeverityLevel.ERROR,
                            sheet_name=sheet,
                        )
                    )

        if consent_sheet is not None:
            consent_linked_clean_sheet = self.sheet_matching[consent_sheet].linked_clean_sheet
            if consent_linked_clean_sheet is None:
                results.append(
                    ValidationResult(
                        rule=rule,
                        message=_(
                            "dynamic_model.build_validators.ConsentCheck", sheet=consent_sheet
                        ),
                        severity=SeverityLevel.ERROR,
                        sheet_name=consent_sheet,
                    )
                )
            else:
                self.validators.append(
                    ConsentCheck(
                        schema=self.schema,
                        raw_data_sheet=consent_sheet,
                        clean_data_sheet=consent_linked_clean_sheet,
                    )
                )
        else:
            results.append(
                ValidationResult(
                    rule=rule,
                    message=_("dynamic_model.build_validators.consent"),
                    severity=SeverityLevel.ERROR,
                )
            )

        if self.sorted_sheets.clean_sheets:  # check unique
            self.validators.append(
                DataTypeCheck(schema=self.schema, check_sheets=self.sorted_sheets.clean_sheets)
            )

            self.validators.append(
                SurveyChoicesCheck(schema=self.schema, check_sheets=self.sorted_sheets.clean_sheets)
            )
            self.validators.append(
                NaNDataCheck(schema=self.schema, check_sheets=self.sorted_sheets.clean_sheets)
            )
        else:
            results.append(
                ValidationResult(
                    rule=rule,
                    message=_("dynamic_model.build_validators.clean_data"),
                    severity=SeverityLevel.ERROR,
                )
            )

        if not self.sorted_sheets.raw_sheets:
            results.append(
                ValidationResult(
                    rule=rule,
                    message=_("dynamic_model.build_validators.raw_data"),
                    severity=SeverityLevel.ERROR,
                )
            )
        if not self.sorted_sheets.cleaning_log_sheets:
            results.append(
                ValidationResult(
                    rule=rule,
                    message=_("dynamic_model.build_validators.cleaning_log"),
                    severity=SeverityLevel.ERROR,
                )
            )

        if not self.sorted_sheets.deletion_log_sheets:
            results.append(
                ValidationResult(
                    rule=rule,
                    message=_("dynamic_model.build_validators.deletion_log"),
                    severity=SeverityLevel.ERROR,
                )
            )

        # if an id column from a child sheet is not found in the only cleaning log sheet
        if len(self.sorted_sheets.cleaning_log_sheets) == 1:
            no_matched_log = [
                {
                    "sheet": sheet,
                    "id_column": match_data.id_column,
                    "issue": _(
                        "dynamic_model.build_validators.no_matched_log.issue",
                        sheet=self.sorted_sheets.cleaning_log_sheets[0],
                    ),
                }
                for sheet, match_data in self.sheet_matching.items()
                if match_data.classification == SheetClassification.CLEAN_DATA_SHEET
                and match_data.linked_cleaning_log is None
            ]
            if no_matched_log:
                results.append(
                    ValidationResult(
                        rule=rule,
                        message=_(
                            "dynamic_model.build_validators.no_matched_log",
                            count=len(no_matched_log),
                        ),
                        severity=SeverityLevel.ERROR,
                        details=pl.DataFrame(no_matched_log).to_dict(as_series=False),
                    )
                )

        return results

    def build_schema(self) -> tuple[list[ValidationResult], str | None]:
        """Builds a schema based on the matched dataset data."""
        consent_sheet = None
        loader = BaseExcelLoader()
        results: list[ValidationResult] = []
        for sheet, details in self.sheet_matching.items():
            if details.classification != SheetClassification.UNKNOWN:
                # cleaning and deletion logs require other columns
                # TODO: change this to use the default logs stored in the yaml files.
                if details.classification == SheetClassification.CLEANING_LOG_SHEET:
                    new_sheet = create_cleaning_log_sheet(
                        standard_name=sheet, id_column=None, id_column_alt=None
                    )
                    new_sheet.parent_linking_column = details.parent_linking_column
                    new_sheet.parent_sheet = details.parent_sheet
                    _ = self.schema.add_loaded_sheet(new_sheet)

                elif details.classification == SheetClassification.DELETION_LOG_SHEET:
                    if len(details.log_id_column) == 1:
                        # should only be one based on current matching logic
                        new_sheet = create_deletion_log_sheet(
                            standard_name=sheet, id_column=details.log_id_column[0]
                        )
                        new_sheet.parent_linking_column = details.parent_linking_column
                        new_sheet.parent_sheet = details.parent_sheet
                    else:
                        new_sheet = create_deletion_log_sheet(standard_name=sheet, id_column=None)

                    _ = self.schema.add_loaded_sheet(new_sheet)

                else:
                    new_sheet = self.schema.add_loaded_sheet(
                        SchemaSheetMap(
                            standard_name=sheet,
                            parent_sheet=details.parent_sheet,
                            parent_linking_column=details.parent_linking_column,
                        )
                    )
                    # columns always required for parent clean/raw sheets
                    if details.parent_sheet is None:
                        _ = self.schema.add_column_to_sheet(
                            sheet,
                            SchemaColumnMap(standard_name="_id", allow_fuzzy_matching=False),
                        )
                        if details.classification == SheetClassification.CLEAN_DATA_SHEET:
                            _ = self.schema.add_column_to_sheet(
                                sheet,
                                SchemaColumnMap(standard_name="weight", required=False),
                            )

                # in the rare case that a child sheet only has at most one record for each parent
                # then the id column found could accidentially also be the foreign key column
                # i dont think this matters as far as the validation goes(?) but it should
                # be the first column created so that the unique flag is set
                if details.id_column is not None:
                    _ = self.schema.add_column_to_sheet(
                        sheet,
                        SchemaColumnMap(
                            standard_name=details.id_column,
                            is_unique=True,
                            allow_empty_values=False,
                        ),
                    )

                if details.parent_linking_column is not None:
                    _ = self.schema.add_column_to_sheet(
                        sheet,
                        SchemaColumnMap(
                            standard_name=details.parent_linking_column, allow_empty_values=False
                        ),
                    )

                if (
                    details.classification == SheetClassification.RAW_DATA_SHEET
                    and details.parent_sheet is None
                ):
                    consent_sheet = sheet
                    _ = self.schema.add_column_to_sheet(
                        sheet,
                        CONSENT_COLUMN,
                    )
                if (
                    details.classification == SheetClassification.CLEANING_LOG_SHEET
                    or details.classification == SheetClassification.DELETION_LOG_SHEET
                ) and details.log_id_column:
                    # its possible some of these columns will have been added already
                    # but if they have they will not be added again
                    for column in details.log_id_column:
                        _ = self.schema.add_column_to_sheet(
                            sheet, SchemaColumnMap(standard_name=column)
                        )

                new_sheet = self.schema.get_schema_loaded_sheet(sheet)
                assert new_sheet is not None  # added above
                result, column_map = loader.match_excel_columns_to_schema(
                    details.data.columns, new_sheet
                )
                if result:
                    results.extend(result)

                if column_map:
                    self.data.set_column_map_for_loaded_sheet(sheet, column_map)

        return results, consent_sheet

    def match_data(self) -> list[ValidationResult]:
        """Attempts to identify and match sheets and columns required to build a
        schema and for validation rules.

        This process attempts to:
        - identify the type of sheet based on simple name matching. eg log, raw, clean
        - find a unique id column for the sheet, except cleaning log sheets
        - trys to link cleaning log sheets to clean data sheets
        - link parent and child sheets if there are loops
        - link raw data sheets to clean data sheets


        """
        results: list[ValidationResult] = []
        rule = "DynamicSchemaCreation_match_data"

        min_matching_score: float = 0.8
        # get schema sheet names and already matched excel sheet names
        expected_names = self.schema.get_all_sheet_names()
        expected_names.extend(self.data.get_loaded_sheet_excel_names())

        for sheet in self.data.loaded_sheets:
            if sheet.data_sheet_name.lower() in expected_names:
                # dont need to process existing items that should have
                # been matched when loading the data
                continue

            self.sheet_matching[sheet.data_sheet_name] = DynamicSheetMatching(
                data=sheet.data,
                id_column=None,
                id_column_set=None,
                parent_sheet=None,
                base_sheet_name=sheet.data_sheet_name,
            )

            # categorise the sheet based on simple name matching
            # remove the matching term to make linking the sheets easier and more accurate
            sheet_name_lower = sheet.data_sheet_name.lower()
            if any(term in sheet_name_lower for term in settings.CLEANING_LOG_SHEET_SEARCH_TERMS):
                self.sheet_matching[
                    sheet.data_sheet_name
                ].classification = SheetClassification.CLEANING_LOG_SHEET
                self.sheet_matching[
                    sheet.data_sheet_name
                ].base_sheet_name = self._remove_match_term(
                    sheet.data_sheet_name, settings.CLEANING_LOG_SHEET_SEARCH_TERMS
                )
            elif any(term in sheet_name_lower for term in settings.CLEAN_DATA_SHEET_SEARCH_TERMS):
                self.sheet_matching[
                    sheet.data_sheet_name
                ].classification = SheetClassification.CLEAN_DATA_SHEET
                self.sheet_matching[
                    sheet.data_sheet_name
                ].base_sheet_name = self._remove_match_term(
                    sheet.data_sheet_name, settings.CLEAN_DATA_SHEET_SEARCH_TERMS
                )
            elif any(term in sheet_name_lower for term in settings.RAW_DATA_SHEET_SEARCH_TERMS):
                self.sheet_matching[
                    sheet.data_sheet_name
                ].classification = SheetClassification.RAW_DATA_SHEET
                self.sheet_matching[
                    sheet.data_sheet_name
                ].base_sheet_name = self._remove_match_term(
                    sheet.data_sheet_name, settings.RAW_DATA_SHEET_SEARCH_TERMS
                )
            elif any(term in sheet_name_lower for term in settings.DELETION_LOG_SHEET_SEARCH_TERMS):
                self.sheet_matching[
                    sheet.data_sheet_name
                ].classification = SheetClassification.DELETION_LOG_SHEET
                self.sheet_matching[
                    sheet.data_sheet_name
                ].base_sheet_name = self._remove_match_term(
                    sheet.data_sheet_name, settings.DELETION_LOG_SHEET_SEARCH_TERMS
                )

            # try to find a unique column
            # store the set of unique values for later processing
            # some cleaning logs contain columns that could be unique but ignore these
            # as they probably wont be the columns needed for validation processes
            if self.sheet_matching[sheet.data_sheet_name].classification in [
                SheetClassification.CLEAN_DATA_SHEET,
                SheetClassification.RAW_DATA_SHEET,
                # SheetClassification.DELETION_LOG_SHEET
            ]:
                unique_columns: list[str] = self._find_unique_column(sheet.data)
                if len(unique_columns) == 1:
                    id_set: set[int | float | str] = set(
                        sheet.data.select(unique_columns[0]).to_series().unique().to_list()
                    )
                    self.sheet_matching[sheet.data_sheet_name].id_column_set = id_set
                    self.sheet_matching[sheet.data_sheet_name].id_column = unique_columns[0]
                else:
                    # only log this for sheets we are expecting an id for
                    df_unique_cols = pl.DataFrame({"columns": unique_columns}).with_columns(
                        pl.lit(sheet.data_sheet_name).alias("sheet")
                    )
                    results.append(
                        ValidationResult(
                            rule=rule,
                            message=_(
                                "dynamic_model.match_data.id_columns",
                                sheet=sheet.data_sheet_name,
                                count=len(unique_columns),
                            ),
                            severity=SeverityLevel.ERROR,
                            sheet_name=sheet.data_sheet_name,
                            details=df_unique_cols.to_dict(as_series=False),
                        )
                    )

        self._sort_sheets()

        # try to  link the logs to another clean sheet
        self._match_log(
            self.sorted_sheets.cleaning_log_sheets,
            self.sorted_sheets.clean_sheets,
            "cleaning",
            min_matching_score,
        )
        self._match_log(
            self.sorted_sheets.deletion_log_sheets,
            self.sorted_sheets.raw_sheets,
            "deletion",
            min_matching_score,
        )

        self._match_child_parent(self.sorted_sheets.raw_sheets)
        self._match_child_parent(self.sorted_sheets.clean_sheets)

        # map raw data sheets to clean data sheets
        for clean_sheet in self.sorted_sheets.clean_sheets:
            match_clean_sheet = self.sheet_matching[clean_sheet]
            if not match_clean_sheet.id_column_set:
                continue

            best_raw = None
            best_score = -1

            for raw_sheet in self.sorted_sheets.raw_sheets:
                match_raw_sheet = self.sheet_matching[raw_sheet]
                if not match_raw_sheet.id_column_set:
                    continue

                combined_score = self._get_similarity_score(
                    match_clean_sheet.base_sheet_name,
                    match_clean_sheet.id_column_set,
                    match_raw_sheet.base_sheet_name,
                    match_raw_sheet.id_column_set,
                )

                if combined_score > best_score:
                    best_score = combined_score
                    best_raw = raw_sheet

            if best_score > min_matching_score:
                assert best_raw is not None
                self.sheet_matching[clean_sheet].linked_raw_sheet = best_raw
                self.sheet_matching[best_raw].linked_clean_sheet = clean_sheet

        if self.sorted_sheets.unknown_sheets:
            self.data.unexpected_sheets = self.sorted_sheets.unknown_sheets
            for sheet in self.sorted_sheets.unknown_sheets:
                # dont perform additional validation of these sheets
                # they will have their own validation warning in
                # unexpected sheets validator
                self.data.remove_loaded_sheet(sheet)

        # check parent counts if loops. should only be one sheet without a parent
        if len(self.sorted_sheets.clean_sheets) > 1:
            clean_parent_sheets = [
                item
                for item, value in self.sheet_matching.items()
                if value.classification == SheetClassification.CLEAN_DATA_SHEET
                and value.parent_sheet is None
            ]
            if len(clean_parent_sheets) > 1:
                results.append(
                    ValidationResult(
                        rule=rule,
                        message=_(
                            "dynamic_model.match_data.clean_data_parents",
                            count=len(clean_parent_sheets),
                        ),
                        severity=SeverityLevel.ERROR,
                        details={"Unmatched clean data sheets": clean_parent_sheets},
                    )
                )

        if len(self.sorted_sheets.raw_sheets) > 1:
            raw_parent_sheets = [
                item
                for item, value in self.sheet_matching.items()
                if value.classification == SheetClassification.RAW_DATA_SHEET
                and value.parent_sheet is None
            ]
            if len(raw_parent_sheets) > 1:
                results.append(
                    ValidationResult(
                        rule=rule,
                        message=_(
                            "dynamic_model.match_data.raw_data_parents",
                            count=len(raw_parent_sheets),
                        ),
                        severity=SeverityLevel.ERROR,
                        details={"Unmatched raw data sheets": raw_parent_sheets},
                    )
                )

        results.append(
            ValidationResult(
                rule=rule,
                message="Sheet matching results.",
                severity=SeverityLevel.ADMIN_INFO,
                details=pl.DataFrame(
                    [
                        {
                            "key": key,
                            "id_column": m.id_column,
                            "classification": m.classification.value,
                            "parent": m.parent_sheet,
                            "parent_id_column": m.parent_linking_column,
                            "children": m.children,
                            "linked_cleaning_log": m.linked_cleaning_log,
                            "linked_raw_sheet": m.linked_raw_sheet,
                            "linked_clean_sheet": m.linked_clean_sheet,
                            "linked_deletion_log": m.linked_deletion_log,
                            "log_id_column": m.log_id_column,
                        }
                        for key, m in self.sheet_matching.items()
                    ]
                ).to_dict(as_series=False),
            )
        )

        return results

    def _get_similarity_score(
        self,
        source_name: str,
        source_data: set[int | float | str],
        target_name: str,
        target_data: set[int | float | str],
        name_scaler: float = 0.4,
        overlap_scaler: float = 0.6,
    ) -> float:
        """Calculates the similarity between two objects. This could be either
        - two columns and their names or
        - two sheet names and their id columns
        This is done by calculating the similarity of their names and the
        intersection of their id columns and then applying some weights
        to the results.

        Args:
            source_name (str): name of the source item. either a column or sheet name
            source_data (set): the set of source id column values
            target_name (str): name of the target item. either a column or sheet name
            target_data (set): the set of target id column values
            name_scaler (float, optional): weight applied to name. Defaults to 0.4.
            overlap_scaler (float, optional): weight applied to overlap. Defaults to 0.6.

        Returns:
            float: similarity score.
        """
        name_similarity = SequenceMatcher(None, source_name, target_name).ratio()
        overlap = get_set_overlap(source_data, target_data)
        return (name_similarity * name_scaler) + (overlap * overlap_scaler)

    def _find_linking_column(
        self, child_columns: list[str], parent_id_column: str, allow_common_names: bool = False
    ) -> list[str]:
        """Attempts to find name matches between a parent id column and a list of
               child columns.

               Optionaly also checks a list of common names if no match was found.

        Args:
            child_columns (list[str]): list of child columns to search
            parent_id_column (str): name of parent column
            allow_common_names (bool, optional): Option to check for common names.
                Defaults to False.

        Returns:
            list[str] : returns possible name matches if found
        """
        possible_columns: list[str] = []

        literal_matches, alt_matches = match_list_to_list(child_columns, [parent_id_column], True)

        # Partial match
        if alt_matches:
            for alt_match in alt_matches:
                possible_columns.append(alt_match.schema_name)

        #  Exact match
        if literal_matches:
            possible_columns.extend(literal_matches)

        # check common names
        if allow_common_names:
            matching_columns: list[str] = match_list(child_columns, settings.COMMON_ID_COLUMN_NAMES)
            if matching_columns:
                possible_columns.extend(matching_columns)

        if possible_columns:
            possible_columns = unique_list(possible_columns)

        return possible_columns

    def _remove_match_term(self, item: str, search_terms: list[str]):
        for term in search_terms:
            item = item.replace(term, "")

        return item

    def _match_log(
        self,
        log_sheets: list[str],
        match_sheets: list[str],
        log_type: str,
        min_matching_score: float,
    ):
        """Matches a log sheet to its respective data sheet.

        This is either matching cleaning logs to clean data sheets
        or deletion logs to raw data sheets.

        Note: for deletion log only one id column should actually be present
            but multiple canbe stored just to match logic for cleaning logs

        Args:
            log_sheets (list[str]): A list of log sheets
            match_sheets (list[str]): a list of data sheets
            log_type (str): either 'deletion' or 'cleaning'
            min_matching_score (float): minimum required matching score for a match
                to be considered.
        """
        for log_sheet in log_sheets:
            match_sheet_log = self.sheet_matching[log_sheet]

            best_parent = None
            best_score = -1
            best_linking_log_column = None

            for match_sheet in match_sheets:
                match_sheet_data = self.sheet_matching[match_sheet]
                if match_sheet_data.id_column_set is None:
                    continue
                if match_sheet_data.id_column is None:
                    continue

                # one log with multiple id columns
                # so reset this for each sheet
                if len(log_sheets) == 1:
                    best_parent = None
                    best_score = -1
                    best_linking_log_column = None

                # find a linking column
                linking_log_columns = self._find_linking_column(
                    match_sheet_log.data.columns, match_sheet_data.id_column, True
                )
                # compare names and overlapping id values
                if linking_log_columns:
                    for linking_log_column in linking_log_columns:
                        log_set = set(
                            match_sheet_log.data.select(linking_log_column)
                            .filter(
                                pl.any_horizontal(
                                    pl.col(linking_log_column)
                                    .fill_null("")
                                    .str.strip_chars()
                                    .is_in(["", None])
                                    .not_()
                                )
                            )
                            .to_series()
                            .unique()
                            .to_list()
                        )

                        if len(log_sheets) == 1:
                            # match column names when onle one log
                            combined_score = self._get_similarity_score(
                                linking_log_column,
                                log_set,
                                match_sheet_data.id_column,
                                match_sheet_data.id_column_set,
                            )
                        else:
                            # match sheet names when multiple logs
                            # remove search terms from sheet names to improve matching
                            combined_score = self._get_similarity_score(
                                match_sheet_log.base_sheet_name,
                                log_set,
                                match_sheet_data.base_sheet_name,
                                match_sheet_data.id_column_set,
                            )

                        if combined_score > best_score:
                            best_score = combined_score
                            best_parent = match_sheet
                            best_linking_log_column = linking_log_column

                    # one cleaning log with multiple id columns
                    if (
                        best_score > min_matching_score
                        and best_parent is not None
                        and len(log_sheets) == 1
                        and best_linking_log_column is not None
                    ):
                        self.sheet_matching[log_sheet].log_id_column.append(best_linking_log_column)
                        if len(match_sheets) == 1:
                            self.sheet_matching[log_sheet].parent_sheet = best_parent
                            self.sheet_matching[
                                log_sheet
                            ].parent_linking_column = best_linking_log_column

                        if log_type == "cleaning":
                            self.sheet_matching[best_parent].linked_cleaning_log = log_sheet
                        elif log_type == "deletion":
                            self.sheet_matching[best_parent].linked_deletion_log = log_sheet

            # multiple cleaning logs with one id column
            if (
                best_score > min_matching_score
                and best_parent is not None
                and len(log_sheets) > 1
                and best_linking_log_column is not None
            ):
                self.sheet_matching[log_sheet].log_id_column.append(best_linking_log_column)
                self.sheet_matching[log_sheet].parent_sheet = best_parent
                self.sheet_matching[log_sheet].parent_linking_column = best_linking_log_column

                if log_type == "cleaning":
                    self.sheet_matching[best_parent].linked_cleaning_log = log_sheet

                elif log_type == "deletion":
                    self.sheet_matching[best_parent].linked_deletion_log = log_sheet

    def _match_child_parent(self, sheets: list[str]):
        """Attempt to match child parent sheets based on finding possible
        foreign keys between the sheets.

        No name matching is done for this process as the names are likely
        to be very different between child and parent sheets.
        """
        for child_sheet in sheets:
            child_match_sheet = self.sheet_matching[child_sheet]
            if not child_match_sheet.id_column_set:
                continue

            best_parent = None
            best_score = -1
            best_fk_column = None

            for parent_sheet in sheets:
                if parent_sheet == child_sheet:
                    continue
                parent_match_sheet = self.sheet_matching[parent_sheet]
                if not parent_match_sheet.id_column_set:
                    continue

                # Find FK column in child that matches parent's primary ID
                if parent_match_sheet.id_column is not None:
                    # try to find an id column match
                    linking_columns = self._find_linking_column(
                        child_match_sheet.data.columns, parent_match_sheet.id_column
                    )
                    # see what the overlap of id values is
                    if linking_columns:
                        for linking_column in linking_columns:
                            child_set = set(
                                child_match_sheet.data.select(linking_column)
                                .to_series()
                                .unique()
                                .to_list()
                            )
                            overlap = get_set_overlap(child_set, parent_match_sheet.id_column_set)

                            if overlap > best_score:
                                best_score = overlap
                                best_parent = parent_sheet
                                best_fk_column = linking_column

            if best_score > 0.8:
                assert best_parent is not None
                self.sheet_matching[child_sheet].parent_sheet = best_parent
                self.sheet_matching[child_sheet].parent_linking_column = best_fk_column
                self.sheet_matching[best_parent].children.append(child_sheet)

    def _find_unique_column(self, data: pl.DataFrame) -> list[str]:
        """Attempts to find unique columns in a dataframe

        Args:
            data (pl.DataFrame): dataframe to check

        Returns:
            list[str] : returns unique columns if found
        """
        unique_columns: list[str] = []
        majority_unique_columns: list[str] = []

        def _additional_matching(columns: list[str]) -> list[str]:
            """Perform some additional checks to find possible unique columns"""
            matching_columns: list[str] = match_list(columns, settings.COMMON_ID_COLUMN_NAMES)
            if len(matching_columns) == 1:
                return matching_columns
            elif len(matching_columns) > 1:
                # get the first match from COMMON_ID_COLUMN_NAMES
                # COMMON_ID_COLUMN_NAMES is ordered
                return next(
                    (
                        [item]
                        for item in settings.COMMON_ID_COLUMN_NAMES
                        if item in matching_columns
                    ),
                    [],
                )

            # look for modified columns from ID_FILTER_NAMES that are often renamed
            # that should be ignored
            filter_columns = [
                item for item in columns if any(term in item for term in settings.ID_FILTER_NAMES)
            ]
            matching_columns = filter_list(columns, filter_columns)
            if len(matching_columns) == 1:
                return matching_columns

            # child sheets often have a unique column like person
            matching_columns = [column for column in columns if "person" in column]
            if len(matching_columns) == 1:
                return matching_columns

            return matching_columns

        for column in data.columns:
            if column in settings.IGNORE_COLUMNS_FOR_VALIDATION or data[column].dtype.is_temporal():
                # some other columns, often from kobo, will show as unique
                # but these are not wanted
                # exclude temportal columns as unique column candidates
                continue

            # Check if the number of unique values equals the total row count
            unique_count = data.n_unique(subset=[column])
            total_count = len(data)

            if unique_count == total_count:
                unique_columns.append(column)
            elif unique_count / total_count > 0.95:
                # sometimes there can be a few duplicates
                # (which there shouldnt and will cause validation errors later)
                # but still try to find the correct column if no unique ones are found
                majority_unique_columns.append(column)

        unique_columns_len = len(unique_columns)
        majority_unique_columns_len = len(majority_unique_columns)
        if unique_columns_len == 1:
            return unique_columns
        elif unique_columns_len > 1:
            # try to match to common names if more than one match
            alt_match = _additional_matching(unique_columns)
            if alt_match:
                return alt_match
        elif majority_unique_columns_len == 1:
            return majority_unique_columns
        elif majority_unique_columns_len > 1:
            alt_match = _additional_matching(majority_unique_columns)
            if alt_match:
                return alt_match

        return unique_columns

    def _sort_sheets(self):

        self.sorted_sheets = SortedSheets()

        for key, value in self.sheet_matching.items():
            if value.classification == SheetClassification.CLEANING_LOG_SHEET:
                self.sorted_sheets.cleaning_log_sheets.append(key)
            if value.classification == SheetClassification.DELETION_LOG_SHEET:
                self.sorted_sheets.deletion_log_sheets.append(key)
            elif value.classification == SheetClassification.CLEAN_DATA_SHEET:
                self.sorted_sheets.clean_sheets.append(key)
            elif value.classification == SheetClassification.RAW_DATA_SHEET:
                self.sorted_sheets.raw_sheets.append(key)
            elif value.classification == SheetClassification.UNKNOWN:
                self.sorted_sheets.unknown_sheets.append(key)
