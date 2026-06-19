from __future__ import annotations

import pytest

from democrai.core.runtime.cli.parser import parse_args


def test_install_engines_parser_minimal():
    args = parse_args(["install-engines", "config.yaml"])

    assert args.command == "install-engines"
    assert args.config_path == "config.yaml"
    assert args.reset_mode == "keep"
    assert args.yes is False
    assert args.json_output is False


@pytest.mark.parametrize("reset_mode", ["keep", "selected"])
def test_install_engines_parser_reset_modes(reset_mode):
    args = parse_args(["install-engines", "config.yaml", "--reset-mode", reset_mode])

    assert args.reset_mode == reset_mode


def test_install_engines_parser_full_yes():
    args = parse_args(["install-engines", "config.yaml", "--reset-mode", "full", "--yes"])

    assert args.reset_mode == "full"
    assert args.yes is True


def test_install_engines_parser_json():
    args = parse_args(["install-engines", "config.yaml", "--json"])

    assert args.json_output is True


def test_install_engines_parser_requires_path():
    with pytest.raises(SystemExit):
        parse_args(["install-engines"])


def test_install_extractors_parser_minimal():
    args = parse_args(["install-extractors", "config.yaml"])

    assert args.command == "install-extractors"
    assert args.config_path == "config.yaml"
    assert args.reset_mode == "keep"
    assert args.yes is False
    assert args.json_output is False


def test_install_extractors_parser_full_yes_json():
    args = parse_args(
        [
            "install-extractors",
            "config.yaml",
            "--reset-mode",
            "full",
            "--yes",
            "--json",
        ]
    )

    assert args.reset_mode == "full"
    assert args.yes is True
    assert args.json_output is True


def test_install_extractors_parser_requires_path():
    with pytest.raises(SystemExit):
        parse_args(["install-extractors"])


def test_setup_parser_minimal():
    args = parse_args(["setup", "setup.yaml"])

    assert args.command == "setup"
    assert args.config_path == "setup.yaml"
    assert args.yes is False
    assert args.json_output is False


def test_setup_parser_yes_json():
    args = parse_args(["setup", "setup.yaml", "--yes", "--json"])

    assert args.yes is True
    assert args.json_output is True


def test_setup_parser_requires_path():
    with pytest.raises(SystemExit):
        parse_args(["setup"])
