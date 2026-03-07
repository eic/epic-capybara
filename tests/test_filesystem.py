from pathlib import Path

from epic_capybara.filesystem import hashdir


def test_hashdir_deterministic(tmp_path):
    """hashdir should return the same hash when called twice on the same directory."""
    (tmp_path / "file1.txt").write_text("hello")
    (tmp_path / "file2.txt").write_text("world")
    assert hashdir(tmp_path) == hashdir(tmp_path)


def test_hashdir_changes_on_new_file(tmp_path):
    """hashdir should return a different hash after a new file is added."""
    (tmp_path / "file1.txt").write_text("hello")
    hash_before = hashdir(tmp_path)
    (tmp_path / "file2.txt").write_text("world")
    hash_after = hashdir(tmp_path)
    assert hash_before != hash_after


def test_hashdir_changes_on_file_content_change(tmp_path):
    """hashdir should return a different hash after a file's content changes."""
    f = tmp_path / "file.txt"
    f.write_text("original")
    hash_before = hashdir(tmp_path)
    f.write_text("modified")
    hash_after = hashdir(tmp_path)
    assert hash_before != hash_after


def test_hashdir_changes_on_filename_change(tmp_path):
    """hashdir should return a different hash when a file is renamed."""
    (tmp_path / "a.txt").write_text("same content")
    hash_a = hashdir(tmp_path)
    (tmp_path / "a.txt").rename(tmp_path / "b.txt")
    hash_b = hashdir(tmp_path)
    assert hash_a != hash_b


def test_hashdir_with_subdirectory(tmp_path):
    """hashdir should include files in subdirectories."""
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "nested.txt").write_text("nested content")
    hash_with_subdir = hashdir(tmp_path)
    (subdir / "another.txt").write_text("more content")
    hash_with_more = hashdir(tmp_path)
    assert hash_with_subdir != hash_with_more


def test_hashdir_returns_hex_string(tmp_path):
    """hashdir should return a valid hex string (MD5 is 32 chars)."""
    (tmp_path / "file.txt").write_text("data")
    result = hashdir(tmp_path)
    assert isinstance(result, str)
    assert len(result) == 32
    assert all(c in "0123456789abcdef" for c in result)
