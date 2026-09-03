import copy
import inspect
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from argus.models.base_dataset_schemas import BaseDatasetSchema
from argus.utils.yaml_loader import load_file
from argus.validators.base import BaseValidator

from ..config import settings
from ..validators.data_validators import (
    CleaningLogToCleanCheck,
    ConsentCheck,
    CrossSheetIdCheck,
    CrossSheetRowSumCheck,
    DataTypeCheck,
    EmptyColumnCheck,
    NaNDataCheck,
    PiiDataCheck,
    RawToCleanToLogCheck,
    SurveyChoicesCheck,
    UniqueColumnCheck,
)
from ..validators.jmmi_validators import (
    JMMIColumnDataCheck,
    JMMIColumnNameCheck,
    JMMIMebAnalysisCheck,
)
from ..validators.schema_validators import (
    ColumnNameCheck,
    DuplicateSheetMatchCheck,
    MandatoryColumnsCheck,
    MissingSheetsCheck,
    UnexpectedSheetsCheck,
)

# supported rules. new rules need to be added to this list in order for them to
# be supported in the yaml files.
VALIDATOR_REGISTRY = {
    "CleaningLogToCleanCheck": CleaningLogToCleanCheck,
    "ConsentCheck": ConsentCheck,
    "CrossSheetIdCheck": CrossSheetIdCheck,
    "CrossSheetRowSumCheck": CrossSheetRowSumCheck,
    "DataTypeCheck": DataTypeCheck,
    "NaNDataCheck": NaNDataCheck,
    "PiiDataCheck": PiiDataCheck,
    "RawToCleanToLogCheck": RawToCleanToLogCheck,
    "SurveyChoicesCheck": SurveyChoicesCheck,
    "UniqueColumnCheck": UniqueColumnCheck,
    "ColumnNameCheck": ColumnNameCheck,
    "DuplicateSheetMatchCheck": DuplicateSheetMatchCheck,
    "MandatoryColumnsCheck": MandatoryColumnsCheck,
    "MissingSheetsCheck": MissingSheetsCheck,
    "UnexpectedSheetsCheck": UnexpectedSheetsCheck,
    "EmptyColumnCheck": EmptyColumnCheck,
    "JMMIColumnNameCheck": JMMIColumnNameCheck,
    "JMMIMebAnalysisCheck": JMMIMebAnalysisCheck,
    "JMMIColumnDataCheck": JMMIColumnDataCheck,
}


class ResolveDataset:
    def _deep_merge(self, base: dict[str, str], override: dict[str, str]) -> dict[str, str]:
        """
        Deep merges two dictionaries.
        - If both values are dicts, it recurses.
        - If values are lists, it replaces (standard override behavior).
        """
        result: dict[str, Any] = base.copy()
        for key, value in override.items():
            # Skip internal directive keys to avoid them being merged as data
            if key in {"$append_columns"}:
                continue

            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _substitute_vars(self, obj: Any, variables: dict[str, str]) -> Any:
        """Recursively replace {var_name} in all string values."""
        if isinstance(obj, str):
            for var_name, var_val in variables.items():
                obj = obj.replace(f"{{{var_name}}}", var_val)
            return obj
        elif isinstance(obj, dict):
            return {k: self._substitute_vars(v, variables) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._substitute_vars(v, variables) for v in obj]
        return obj

    def _resolve(self, item: Any, definitions: dict[str, str], path: str = "root") -> Any:
        """recursivly parses the file and returns the mapped content"""
        if isinstance(item, list):
            resolved_list: list[Any] = []
            for x in item:
                resolved_item = self._resolve(x, definitions, f"{path}[i]")
                if isinstance(resolved_item, list):
                    # $use pointed at a multi-block definition: splice its contents
                    resolved_list.extend(resolved_item)
                else:
                    resolved_list.append(resolved_item)
            return resolved_list

        if isinstance(item, dict):
            # supported keys used in yaml files
            internal_keys = {"$use", "override", "$append_columns", "variables"}

            if "$use" in item:
                ref_name = item["$use"]
                if ref_name not in definitions:
                    raise ValueError(
                        f"[{path}] Missing definition '{ref_name}'. "
                        + f"Available: [{list(definitions.keys())}]"
                    )

                # 1. Load the base definition
                resolved_content = copy.deepcopy(definitions[ref_name])

                # 2. Recursively resolve the loaded content itself
                # Because the loaded content might contain nested $use references
                resolved_content = self._resolve(
                    resolved_content, definitions, f"{path}(base_{ref_name})"
                )

                # 3. Handle Overrides
                overrides = {}
                for key, value in item.items():
                    if key not in internal_keys:
                        overrides[key] = value

                if overrides:
                    resolved_overrides = self._resolve(overrides, definitions, f"{path}(overrides)")
                    resolved_content = self._deep_merge(resolved_content, resolved_overrides)

                # 4. Handle Directives ($append)
                # These are applied on the CURRENT item, so we need to resolve their values first
                if "$append_columns" in item:
                    new_cols = self._resolve(
                        item["$append_columns"], definitions, f"{path}(append)"
                    )
                    current = resolved_content.get("columns", [])
                    resolved_content["columns"] = current + new_cols

                if "override" in item:
                    override_data = self._resolve(
                        item["override"], definitions, f"{path}(override_block)"
                    )
                    resolved_content = self._deep_merge(resolved_content, override_data)

                if "variables" in item:
                    variables = self._resolve(item["variables"], definitions, f"{path}(variables)")
                    resolved_content = self._substitute_vars(resolved_content, variables)
                    if isinstance(resolved_content, dict):
                        resolved_content.pop("variables", None)
                    elif isinstance(resolved_content, list):
                        for entry in resolved_content:
                            if isinstance(entry, dict):
                                entry.pop("variables", None)

                return resolved_content

            else:
                # No reference at this level. Recurse into all values.
                return {k: self._resolve(v, definitions, f"{path}.{k}") for k, v in item.items()}

        return item

    def resolve_schema(self, schema_path: str | Path) -> BaseDatasetSchema:
        """Converts schema properties stored in a yaml file into a schema class

        Args:
            schema_path (str | Path): location of the yaml file

        Raises:
            Errors if any issues loading the file or mapping the contents

        Returns:
            BaseDatasetSchema: dataset schema based on the yaml file
        """
        raw_data, definitions = load_file(schema_path)

        try:
            resolved_data = self._resolve(raw_data, definitions)
        except Exception as e:
            raise RuntimeError(f"Error resolving schema references: {e}") from None

        # Validate with Pydantic
        try:
            schema_model = BaseDatasetSchema.model_validate(resolved_data)
            return schema_model
        except ValidationError as e:
            error_str = "\n".join([f"{err['loc']}: {err['msg']}" for err in e.errors()])
            raise ValueError(f"Schema validation failed:\n{error_str}") from e

    def resolve_validators(
        self, validator_path: str | Path, schema: BaseDatasetSchema
    ) -> list[BaseValidator]:
        """Converts a list of validation rules and paramaters stored in a yaml file
        into their respective class objects

        Args:
            validator_path (str | Path): location of the yaml file
            schema (BaseDatasetSchema): Schema of the dataset

        Raises:
            ValueError: if there are any issues with the yaml file

        Returns:
            list[BaseValidator]: a list of validation objects
        """
        validators: list[BaseValidator] = []
        ignore_params = ["self", "args", "kwargs"]
        raw_data, _ = load_file(validator_path)
        for item in raw_data["validators"]:
            if not isinstance(item, dict):
                raise ValueError(f"Item {item} is not a dictionary definition.")

            class_name = item.get("type")
            if not class_name:
                raise ValueError(f"Item {item} missing 'type' key.")

            # Check the requested class allowed
            if class_name not in VALIDATOR_REGISTRY:
                available = ", ".join(VALIDATOR_REGISTRY.keys())
                raise ValueError(
                    f"Unknown validator '{class_name}' at {item}. Allowed types: {available}"
                )

            ValidatorClass = VALIDATOR_REGISTRY[class_name]
            init_kwargs = dict(item.get("kwargs", {}))

            # signature validation
            sig = inspect.signature(ValidatorClass.__init__)
            valid_params = set(sig.parameters.keys())
            provided_params = set(init_kwargs.keys())

            # Filter out 'self' which is implicit in signatures but not passed
            (valid_params.discard(param) for param in ignore_params)

            # Check for extra arguments defined in YAML but not in code
            invalid_args = provided_params - valid_params
            if invalid_args:
                raise ValueError(
                    f"Validation Error for '{class_name}' (item {item}): "
                    + f"Received unexpected keyword arguments: {invalid_args}. "
                    + f"Accepted arguments: {valid_params}"
                )

            #  dependency injection
            # If the class signature expects 'schema', inject it.
            if "schema" in valid_params:
                init_kwargs["schema"] = schema

            final_missing = {
                name
                for name, param in sig.parameters.items()
                if param.default == inspect.Parameter.empty
                and name not in ignore_params
                and name not in init_kwargs
            }
            if final_missing:
                raise ValueError(
                    f"Instantiation Error for '{class_name}' (item {item}): "
                    + f"Missing required arguments: {final_missing}. "
                    + "Ensure all required parameters are in the YAML."
                )

            try:
                instance = ValidatorClass(**init_kwargs)
                validators.append(instance)
            except TypeError as e:
                raise ValueError(
                    f"Failed to instantiate '{class_name}' despite validation: {e}"
                ) from e

        return validators


def find_dataset_files(
    root_directory: Path,
    programme_type: str,
    output_type: str,
    locale: str,
    schema_file_name: str,
    validator_file_name: str,
) -> dict[str, Path | str] | None:
    """
    Locates two files based on root directory, locale, and dataset type with fallback logic.

    Both files must exist in the same directory for a match to be valid.
    If only one file exists in a directory, returns None without checking fallbacks.

    Fallback hierarchy:
    1. root_dir / type_of_programme / type_of_output / locale / [file_1, file_2]
    2. (if locale != en) root_dir / type_of_programme / type_of_output / en / [file_1, file_2]
    3. (if type_of_programme != other) root_dir / other / locale / [file_1, file_2]
    4. (if type_of_programme != other AND locale != en) root_dir / other / en / [file_1, file_2]

    Args:
        root_directory: The base directory path.
        locale: The locale code (e.g., 'en', 'fr').
        type_of_programme: The programme type (e.g., 'jmmi', 'other').
        type_of_output: type of output (eg: dataset, analysis)
        schema_file_name: The name of the schema file to find.
        validator_file_name: The name of the validator file to find.

    Returns:
        A tuple of Path objects (schema_file_name, validator_file_name) if both exist the location,
        or None if no match is found (including partial matches).
    """

    def check_location(
        programme_type: str,
        output_type: str,
        locale: str,
    ) -> (
        tuple[Literal[True], dict[str, Path | str]]
        | tuple[Literal[False], None]
        | tuple[None, None]
    ):
        """
        Checks a specific location.
        Returns:
            (True, (path1, path2)) if both exist.
            (False, None) if neither exist (fallback).
            (None, None) if only one exists .
        """

        schema_path = root_directory / programme_type / output_type / locale / schema_file_name
        validator_path = (
            root_directory / programme_type / output_type / locale / validator_file_name
        )

        schema_exists = schema_path.is_file()
        validator_exists = validator_path.is_file()

        if schema_exists and validator_exists:
            return (
                True,
                {
                    schema_file_name: schema_path,
                    validator_file_name: validator_path,
                    "programme_type": programme_type,
                    "output_type": output_type,
                },
            )
        elif not schema_exists and not validator_exists:
            # Neither exists, safe to continue to fallback
            return (False, None)
        else:
            # only one file found. dont continue and return error.
            return (None, None)

    # List of locations to check in order
    # Each entry is (programme_type, output_type, locale)
    checks: list[tuple[str, str, str]] = []

    # 1. Primary: original dataset, original locale
    checks.append((programme_type, output_type, locale))

    # 2. Fallback 1: original dataset, 'en' locale (only if locale != 'en')
    if locale.lower() != settings.FALLBACK_LOCALE:
        checks.append((programme_type, output_type, settings.FALLBACK_LOCALE))

    # 3. Fallback 2: 'other' dataset, original locale (only if dataset != 'other')
    if programme_type != settings.FALLBACK_PROGRAMME:
        checks.append((settings.FALLBACK_PROGRAMME, output_type, locale))

        # 4. Fallback 3: 'other' dataset, 'en' locale
        # (only if dataset != 'other' AND locale != 'en')
        if locale.lower() != settings.FALLBACK_LOCALE:
            checks.append((settings.FALLBACK_PROGRAMME, output_type, settings.FALLBACK_LOCALE))

    # Iterate through potential locations
    for l_type_of_programme, l_type_of_output, l_locale in checks:
        status, result = check_location(
            programme_type=l_type_of_programme, output_type=l_type_of_output, locale=l_locale
        )

        if status is True:
            # files found
            return result
        elif status is None:
            # only one file found
            return None
        else:
            # next fall back
            continue

    return None
