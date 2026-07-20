import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastexcel import CalamineCellError

from argus.locales.il8n import _, i18n
from argus.models.resolver import find_dataset_files
from argus.utils.yaml_loader import download_config

from ..config import settings
from ..loaders.base import DataSheetMap
from ..loaders.base_excel_loader import ExcelLoaderData
from ..loaders.excel_loader import ExcelLoader
from ..models.base_dataset import BaseDataset
from ..models.base_dataset_schemas import BaseDatasetSchema
from ..models.dynamic_model import DynamicDataset
from ..models.preprocess import validate_schema
from ..validators.base import BaseValidator, SeverityLevel, ValidationResult


class ValidationPipeline:
    def __init__(self):
        self.set_errors: set[SeverityLevel] = set([SeverityLevel.ADMIN_ERROR, SeverityLevel.ERROR])

    def _setup_schema(self, config_directory: Path, dataset_type: str, locale: str):
        """Initialise schema and validators based on dataset type.

        Raises:
            ValueError: if dataset type not found.
        """
        schema_file = "schema.yaml"
        validator_file = "validators.yaml"
        result = find_dataset_files(
            config_directory, dataset_type, locale, schema_file, validator_file
        )

        if result:
            if result["dataset_type"] != settings.FALLBACK_DATASET:
                dataset = BaseDataset(
                    schema_path=result[schema_file], validator_path=result[validator_file]
                )
            else:
                dataset = DynamicDataset(
                    schema_path=result[schema_file], validator_path=result[validator_file]
                )
        else:
            raise ValueError(
                f"Unable to find files for {schema_file} and {validator_file} for "
                + f"dataset {dataset_type} and locale {locale}."
            )

        return dataset

    def run_all(
        self,
        filepath: Path,
        dataset_type: str,
        locale: str = settings.FALLBACK_LOCALE,
        use_local_config: bool = False,
    ) -> dict[str, Any]:
        """_summary_

        Args:
            filepath (Path): The excel filepath.
            dataset_type (str): dataset type: jmmi, other
            locale (str, optional): language to use for validation messages, if supported.
                Defaults to "en".

        Returns:
            dict[str, Any]: json results
        """
        locale = locale.lower()
        token = i18n.set_locale(locale)
        dataset_type = dataset_type.lower()
        results = self._run(
            filepath, dataset_type, locale=locale, use_local_config=use_local_config
        )
        i18n.reset_locale(token)
        return self._compile_results(results, dataset_type, filepath)

    def _run(
        self, filepath: Path, dataset_type: str, locale: str, use_local_config: bool = False
    ) -> list[ValidationResult]:
        """Orchestrator for the dataset validation pipeline.

        Args:
            filepath (Path): The excel filepath.

        Returns:
            list[ValidationResult]: validation results.

        """
        all_results: list[ValidationResult] = []

        try:
            if use_local_config:
                dataset_config_dir = settings.DATASET_CONFIG_LOCAL_DIR
            else:
                dataset_config_dir = download_config(settings.DATASET_CONFIG_DIR)
            dataset = self._setup_schema(dataset_config_dir, dataset_type, locale)

            if dataset.schema.dataset_type != dataset_type:
                all_results.append(
                    ValidationResult(
                        rule="GetYAMLConfig",
                        message=f"No dataset schema for '{dataset_type}' was found for "
                        + f" version '{dataset_config_dir.name}'. Falling back to "
                        + f"'{dataset.schema.dataset_type}'.",
                        severity=SeverityLevel.WARNING,
                    )
                )
            all_results.append(
                ValidationResult(
                    rule="GetYAMLConfig",
                    message=f"Using schema version '{dataset_config_dir.name}' for "
                    + f"dataset '{dataset.schema.dataset_type}'.",
                    severity=SeverityLevel.ADMIN_INFO,
                )
            )

        except Exception as e:
            all_results.append(
                ValidationResult(
                    rule="GetYAMLConfig",
                    message=f"Error getting the YAML dataset config files: {str(e)}",
                    severity=SeverityLevel.ADMIN_ERROR,
                )
            )
            settings.logger.log_exception(e)
            return all_results

        # pre-validate the schema. checks for duplicate sheet/column
        # names etc

        try:
            validation_errors = validate_schema(dataset.schema)

            if validation_errors:
                all_results.extend(validation_errors)
                return all_results
        except Exception as e:
            all_results.append(
                ValidationResult(
                    rule="SchemaValidation",
                    message=f"Schema validation encountered an error: {str(e)}",
                    severity=SeverityLevel.ADMIN_ERROR,
                    details=vars(dataset.schema),
                )
            )
            settings.logger.log_exception(e)
            return all_results

        # load the excel data
        try:
            loader = ExcelLoader(dataset.schema)
            dataset.data, excel_results = loader.load(
                filepath,
                load_all_sheets=dataset.schema.dataset_type == settings.FALLBACK_DATASET,
            )

            if excel_results:
                all_results.extend(excel_results)

            all_results.append(
                ValidationResult(
                    rule="ExcelFileLoading",
                    message="Data mapping after data load.",
                    severity=SeverityLevel.ADMIN_INFO,
                    details=self._excel_loader_to_dict(dataset.data),
                )
            )
        except CalamineCellError as ce:
            all_results.append(
                ValidationResult(
                    rule="ExcelFileLoading",
                    message=_(
                        "validation_pipeline.calamine_cell_error", file=filepath.name, error=str(ce)
                    ),
                    severity=SeverityLevel.ERROR,
                )
            )
            settings.logger.log_exception(ce)
            return all_results
        except Exception as e:
            all_results.append(
                ValidationResult(
                    rule="ExcelFileLoading",
                    message=f"Loading of the excel file '{filepath.name}'"
                    + f" encountered an error: {str(e)}",
                    severity=SeverityLevel.ADMIN_ERROR,
                )
            )
            settings.logger.log_exception(e)
            return all_results

        if dataset.schema.dataset_type == settings.FALLBACK_DATASET:
            results = dataset.process_data()
            if results:
                all_results.extend(results)

        all_results.append(
            ValidationResult(
                rule="Schema Details",
                message=f"Schema for dataset '{dataset_type}' and file '{filepath}'",
                severity=SeverityLevel.ADMIN_INFO,
                details=vars(dataset.schema),
            )
        )

        # run each of the validators for the dataset.
        for validator in dataset.validators:
            try:
                results = validator.validate(dataset.data)
                if results:
                    all_results.extend(results)

                if not [item for item in results if item.severity in self.set_errors]:
                    all_results.append(
                        ValidationResult(
                            rule=validator.name,
                            message=_("validation_pipeline.passed", name=validator.name),
                            severity=SeverityLevel.PASSED,
                            details=self._get_validator_params(validator),
                        )
                    )
            except Exception as e:
                all_results.append(
                    ValidationResult(
                        rule=validator.name,
                        message=f"Validator '{validator.name}' encountered an error:"
                        + f" {traceback.format_exc()}",
                        severity=SeverityLevel.ADMIN_ERROR,
                        details=self._get_validator_params(validator),
                    )
                )
                settings.logger.log_exception(e)

        return all_results

    def _compile_results(
        self, results: list[ValidationResult], dataset_type: str, filepath: Path
    ) -> dict[str, Any]:
        """Compile validation results into structured output."""
        buckets: dict[str, list[dict[str, Any]]] = {level.value: [] for level in SeverityLevel}
        counts: dict[str, int] = {level.value: 0 for level in SeverityLevel}
        error_count: int = 0

        limit_details_message = _(
            "validation_pipeline.limit_details", count=settings.LIMIT_DETAILS_THRESHOLD
        )

        for result in results:
            was_truncated = False
            if result.details and settings.LIMIT_DETAILS_THRESHOLD > 0:
                # if the number of details needs to be lmited
                for key, value in result.details.items():
                    # checks to see if the value is a list and if it has too many items.
                    if isinstance(value, list) and len(value) > settings.LIMIT_DETAILS_THRESHOLD:
                        # truncate the list
                        result.details[key] = value[: settings.LIMIT_DETAILS_THRESHOLD]
                        was_truncated = True

                # update message
                if was_truncated:
                    result.message = f"{result.message} {limit_details_message}"

            counts[result.severity.value] += 1

            if result.severity in self.set_errors:
                error_count += 1

            buckets[result.severity.value].append(
                {
                    "rule": result.rule,
                    "message": result.message,
                    "severity": result.severity.value,
                    "sheet_name": result.sheet_name,
                    "column_name": result.column_name,
                    "details": result.details,
                }
            )

        success = error_count == 0

        try:
            with open(settings.ARGUS_VERSION_FILE) as f:
                argus_version = f.read().strip()
        except Exception:
            argus_version = "unknown"

        return {
            "success": success,
            "summary": counts,
            **{key: buckets[key] for key in buckets},
            "metadata": {
                "dataset_type": dataset_type,
                "validation_date": datetime.now(UTC).isoformat(timespec="seconds"),
                "version": argus_version,
                "file_name": filepath.name,
            },
        }

    def _get_validator_params(self, validator: BaseValidator) -> dict[str, Any]:
        """Get validator paramaters for logs but exclude schema."""
        return {k: v for k, v in vars(validator).items() if not isinstance(v, BaseDatasetSchema)}

    def _excel_loader_to_dict(self, excel_loader: ExcelLoaderData) -> dict[str, Any]:
        """Convert ExcelLoaderData to dict, excluding data and column fields."""

        def data_sheet_map_to_dict(data_sheet: DataSheetMap) -> dict[str, Any]:
            return {
                "schema_sheet_name": data_sheet.schema_sheet_name,
                "data_sheet_name": data_sheet.data_sheet_name,
                "column_map": data_sheet.column_map,
            }

        return {
            "loaded_sheets": [
                data_sheet_map_to_dict(sheet) for sheet in excel_loader.loaded_sheets
            ],
            "unloaded_sheets": [
                data_sheet_map_to_dict(sheet) for sheet in excel_loader.unloaded_sheets
            ],
            "unexpected_sheets": excel_loader.unexpected_sheets,
        }
