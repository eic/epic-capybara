import gzip
import json
import re
from pathlib import Path

import pytest
import skhep_testdata
from click.testing import CliRunner

from epic_capybara.cli.bara import bara, match_filter


def test_match_filter_no_filters():
    assert match_filter("Jet_Px", [], []) is True


def test_match_filter_with_matching_match():
    patterns = [re.compile("Jet.*")]
    assert match_filter("Jet_Px", patterns, []) is True


def test_match_filter_with_non_matching_match():
    patterns = [re.compile("Jet.*")]
    assert match_filter("NJet", patterns, []) is False


def test_match_filter_with_unmatch():
    patterns = [re.compile("Jet.*")]
    assert match_filter("Jet_Px", [], patterns) is False
    assert match_filter("NJet", [], patterns) is True


def test_match_filter_match_and_unmatch():
    match = [re.compile("Jet.*")]
    unmatch = [re.compile("Jet_Px")]
    assert match_filter("Jet_Py", match, unmatch) is True
    assert match_filter("Jet_Px", match, unmatch) is False
    assert match_filter("NJet", match, unmatch) is False


def test_bara_single_file_float(tmp_path):
    """Test bara with a single ROOT file using floating-point leaf data."""
    path = skhep_testdata.data_path("uproot-HZZ.root")
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(bara, [path, "--match", "Jet_Px"])
        assert result.exit_code == 0, result.output
        assert Path("capybara-reports/index.html").exists()
        assert Path("capybara-reports/Jet_Px.json.gz").exists()
        with gzip.open("capybara-reports/Jet_Px.json.gz", "rt") as fp:
            data = json.load(fp)
        assert "doc" in data


def test_bara_single_file_integer(tmp_path):
    """Test bara with a single ROOT file using integer leaf data."""
    path = skhep_testdata.data_path("uproot-HZZ.root")
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(bara, [path, "--match", "NJet"])
        assert result.exit_code == 0, result.output
        assert Path("capybara-reports/index.html").exists()
        assert Path("capybara-reports/NJet.json.gz").exists()


def test_bara_two_identical_files_float(tmp_path):
    """Test bara comparing two identical ROOT files with float data (no differences expected)."""
    path = skhep_testdata.data_path("uproot-HZZ.root")
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(bara, [path, path, "--match", "Jet_Px"])
        assert result.exit_code == 0, result.output
        assert Path("capybara-reports/index.html").exists()
        assert Path("capybara-reports/Jet_Px.json.gz").exists()


def test_bara_two_identical_files_integer(tmp_path):
    """Test bara comparing two identical ROOT files with integer data (no differences expected)."""
    path = skhep_testdata.data_path("uproot-HZZ.root")
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(bara, [path, path, "--match", "NJet"])
        assert result.exit_code == 0, result.output
        assert Path("capybara-reports/index.html").exists()
        assert Path("capybara-reports/NJet.json.gz").exists()


def test_bara_unmatch_filter(tmp_path):
    """Test bara with an unmatch filter to exclude certain leaves."""
    path = skhep_testdata.data_path("uproot-HZZ.root")
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(bara, [path, "--match", "NJet|NMuon", "--unmatch", "NMuon"])
        assert result.exit_code == 0, result.output
        assert Path("capybara-reports/NJet.json.gz").exists()
        assert not Path("capybara-reports/NMuon.json.gz").exists()


def test_bara_multiple_branches(tmp_path):
    """Test bara produces one report file per branch collection."""
    path = skhep_testdata.data_path("uproot-HZZ.root")
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(bara, [path, "--match", "NJet|NMuon|NElectron"])
        assert result.exit_code == 0, result.output
        assert Path("capybara-reports/NJet.json.gz").exists()
        assert Path("capybara-reports/NMuon.json.gz").exists()
        assert Path("capybara-reports/NElectron.json.gz").exists()
        assert Path("capybara-reports/index.html").exists()
