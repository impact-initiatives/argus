from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from .utils.logging import JIVELogger


class Settings(BaseSettings):
    model_config: SettingsConfigDict = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    MIN_FUZZY_MATCH_SCORE: int = 90
    FUZZY_MATCH_STRING_LENGTH_RATIO: float = 0.7

    # for some validation rules and dynamic model creation
    IGNORE_COLUMNS_FOR_VALIDATION: set[str] = {
        "enum_id",
        "_index",
        "index",
        "_parent_index",
        "parent_index",
        "start",
        "end",
        "audit_url",
        "_id",
        "instance_name",
        "row_index",
    }

    IGNORE_COLUMNS_FOR_MATCHING: set[str] = {
        "enum_id",
        "_index",
        "index",
        "_parent_index",
        "parent_index",
        "start",
        "end",
        "audit_url",
        "instance_name",
        "row_index",
    }

    ID_FILTER_NAMES: set[str] = {"start", "end"}  # , "_index"

    COMMON_ID_COLUMN_NAMES: set[str] = {"uuid", "x_uuid", "person_id"}

    # for dynamic model creation
    CLEAN_DATA_SHEET_SEARCH_TERMS: list[str] = ["clean_data"]
    CLEANING_LOG_SHEET_SEARCH_TERMS: list[str] = ["cleaning_log"]
    RAW_DATA_SHEET_SEARCH_TERMS: list[str] = ["raw_data"]

    # for the NaNCheck validator
    NANCHECK_NUMERIC_VALUES: list[int] = [-999, -99, 99, 999, -88, -888, 88, 888]
    NANCHECK_STRING_VALUES: list[str] = [
        "-999",
        "-99",
        "99",
        "999",
        "-88",
        "-888",
        "88",
        "888",
    ]
    # limits the output of each of the validation results. set below 0 to ignore.
    LIMIT_DETAILS_THRESHOLD: int = -1

    logger: JIVELogger = JIVELogger()

    # for local testing
    # eg Path.cwd() / "dataset_config" / "v2026.06.25.01"
    DATASET_CONFIG_LOCAL_DIR: Path = Path.cwd() / "dataset_config"

    DATASET_CONFIG_DIR: Path = Path.cwd() / "dataset_config"
    DATASET_CONFIG_URL: str = (
        "https://api.github.com/repos/impact-initiatives/argus_schemas/releases/latest"
    )
    Path(DATASET_CONFIG_DIR).mkdir(parents=True, exist_ok=True)

    FALLBACK_PROGRAMME: str = "other"
    FALLBACK_DATASET: str = "other_dataset"
    FALLBACK_LOCALE: str = "en"


settings = Settings()
