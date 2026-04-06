"""Tests for env_vars parsing utilities."""

import pytest

from app.utils.env_vars import parse_env_pairs, parse_env_text


class TestParseEnvPairs:
    def test_empty_tuple(self):
        assert parse_env_pairs(()) is None

    def test_single_pair(self):
        assert parse_env_pairs(("KEY=value",)) == {"KEY": "value"}

    def test_multiple_pairs(self):
        result = parse_env_pairs(("A=1", "B=2"))
        assert result == {"A": "1", "B": "2"}

    def test_value_with_equals(self):
        assert parse_env_pairs(("TOKEN=abc=def",)) == {"TOKEN": "abc=def"}

    def test_invalid_pair(self):
        with pytest.raises(ValueError, match="Invalid env var"):
            parse_env_pairs(("NOEQUALS",))


class TestParseEnvText:
    def test_empty_string(self):
        assert parse_env_text("") is None

    def test_whitespace_only(self):
        assert parse_env_text("  \n  ") is None

    def test_single_line(self):
        assert parse_env_text("KEY=value") == {"KEY": "value"}

    def test_multiple_lines(self):
        result = parse_env_text("A=1\nB=2\n")
        assert result == {"A": "1", "B": "2"}

    def test_blank_lines_skipped(self):
        result = parse_env_text("A=1\n\n\nB=2")
        assert result == {"A": "1", "B": "2"}

    def test_value_with_equals(self):
        assert parse_env_text("TOKEN=abc=def") == {"TOKEN": "abc=def"}

    def test_invalid_line(self):
        with pytest.raises(ValueError, match="Invalid env var"):
            parse_env_text("NOEQUALS")
