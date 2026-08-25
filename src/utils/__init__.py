import pathlib
import tomllib

PYPROJECT_PATH = pathlib.Path(__file__).parent / "pyproject.toml"


def get_project_version() -> str:
    if PYPROJECT_PATH.exists():
        with open(PYPROJECT_PATH, "rb") as f:
            pyproject_data = tomllib.load(f)
            # Standard pyproject.toml location: [project] -> version
            return pyproject_data.get("project", {}).get("version", "0.1.0")
    return "0.1.0"
