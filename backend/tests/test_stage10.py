from pathlib import Path


def test_deployment_files_exist():
    root = Path("/app")
    assert (root / "Dockerfile").is_file()
    assert (root / "requirements.txt").is_file()
    assert (root / "alembic.ini").is_file()
