import zipfile
from pathlib import Path
from typing import Any

import requests
import yaml
from requests.models import Response

from ..config import settings


def download_config(download_dir: str | Path = "dataset_config"):
    """
    Downloads the latest release, extracts it if necessary,
    filters only .yaml files, and preserves directory structure.
    """

    # 1. Setup Download Directory
    base_path = Path(download_dir)

    try:
        response: Response = requests.get(settings.DATASET_CONFIG_URL)
        response.raise_for_status()
        release_data = response.json()
    except Exception as e:
        raise RuntimeError(f"Error getting latest dataset config release: {e}") from None

    tag_name = release_data["tag_name"]

    # 2. Check if this version has already been processed
    versioned_target: Path = base_path / tag_name
    if versioned_target.exists():
        yaml_files = list(versioned_target.rglob("*.yaml")) + list(versioned_target.rglob("*.yml"))
        if len(yaml_files) > 0:
            return versioned_target

    archive_name = f"{release_data.get('name', tag_name)}.zip"
    archive_path = base_path / f"_temp_{archive_name}"

    # Stream download
    try:
        stream_response = requests.get(release_data["zipball_url"], stream=True)
        stream_response.raise_for_status()

        with open(archive_path, "wb") as f:
            for chunk in stream_response.iter_content(chunk_size=8192):
                _ = f.write(chunk)
    except Exception as e:
        raise RuntimeError(f"Error downloading latest dataset release zip file: {e}") from None

    try:
        versioned_target.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            for file_info in zip_ref.namelist():
                # Check if file ends with .yaml or .yml
                if file_info.lower().endswith(".yaml") or file_info.lower().endswith(".yml"):
                    target_rel_path = Path(file_info)

                    # Strip the GitHub root folder (e.g., "owner-repo-hash/")
                    if len(target_rel_path.parts) > 1:
                        target_rel_path = Path(*target_rel_path.parts[1:])
                    else:
                        continue

                    dest_file = versioned_target / target_rel_path

                    # Security check: prevent path traversal
                    try:
                        _ = dest_file.resolve().relative_to(versioned_target.resolve())
                    except ValueError:
                        continue

                    # Create parent dirs
                    dest_file.parent.mkdir(parents=True, exist_ok=True)

                    # Write file content
                    with zip_ref.open(file_info) as source, open(dest_file, "wb") as target:
                        _ = target.write(source.read())

    except Exception as e:
        raise RuntimeError(f"Error extracting zip files: {e}") from None
    finally:
        # Cleanup temporary archive
        if archive_path.exists():
            archive_path.unlink()

    return versioned_target


def load_file(file_path: str | Path):
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"YAML configuration file not found: {path}")

    base_dir = path.parent

    try:
        with open(path, encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML syntax in {file_path}: {e}") from e

    if not isinstance(raw_data, dict):
        raise ValueError("YAML root must be a dictionary.")

    # 1. Load Import Definitions
    definitions: dict[str, Any] = {}
    imports = raw_data.pop("_imports", [])

    for imp_path in imports:
        full_path = base_dir / imp_path
        if not full_path.exists():
            raise FileNotFoundError(f"Imported component file not found: {full_path}")

        with open(full_path, encoding="utf-8") as f:
            comp_data = yaml.safe_load(f)

        if not isinstance(comp_data, dict) or "definitions" not in comp_data:
            raise ValueError(f"Component file {imp_path} must contain a 'definitions' key.")

        definitions.update(comp_data["definitions"])

    return raw_data, definitions
