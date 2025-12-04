from pathlib import Path

EXPORT_PATH = Path(__file__).parent.parent / "output"

def export_file_path(filename: str, format: str,) -> Path:
    EXPORT_PATH.mkdir(parents=True, exist_ok=True)
    file_path = EXPORT_PATH / f"{filename}.{format}"
    return file_path