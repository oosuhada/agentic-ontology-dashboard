from pathlib import Path

from app.infra.storage.local_file_uri import local_file_uri_path


def test_local_file_uri_path_decodes_native_absolute_path(tmp_path: Path) -> None:
    source = tmp_path / "canonical" / "asset master.csv"

    assert local_file_uri_path(source.as_uri()) == source


def test_local_file_uri_path_preserves_plain_path(tmp_path: Path) -> None:
    source = tmp_path / "canonical" / "asset_master.csv"

    assert local_file_uri_path(str(source)) == source
