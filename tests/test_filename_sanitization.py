"""
Test filename sanitation and path handling to prevent trailing braces and invalid characters.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pathlib import Path
import tempfile
import video_utils
import snap_utils


def test_sanitize_path_removes_trailing_braces():
    """Test that sanitize_path strips trailing braces from filenames."""
    # Test cases with problematic trailing characters
    test_cases = [
        ("test.mp4}", "test.mp4"),
        ("path/to/file.mp4}}", "file.mp4"),
        ("file.mp4  ", "file.mp4"),  # Trailing spaces
        ("file.mp4\t", "file.mp4"),  # Trailing tab
        ("file.mp4{ }", "file.mp4"),  # Trailing brace and space
    ]
    
    for input_path, expected_name in test_cases:
        result = video_utils.sanitize_path(input_path)
        assert result is not None, f"sanitize_path returned None for {input_path}"
        assert result.name == expected_name, f"Expected {expected_name}, got {result.name}"
        # Ensure no trailing problematic characters
        assert not str(result).endswith('}'), f"Path still ends with brace: {result}"
        assert not str(result).endswith(' '), f"Path still ends with space: {result}"


def test_sanitize_path_returns_absolute():
    """Test that sanitize_path returns absolute paths."""
    result = video_utils.sanitize_path("relative/path.mp4")
    assert result.is_absolute(), f"Path is not absolute: {result}"


def test_sanitize_path_with_none():
    """Test that sanitize_path handles None input."""
    result = video_utils.sanitize_path(None)
    assert result is None, "sanitize_path should return None for None input"


def test_get_file_extension():
    """Test file extension helper returns correct extensions."""
    assert snap_utils.get_file_extension("Image") == ".jpg"
    assert snap_utils.get_file_extension("Video") == ".mp4"
    assert snap_utils.get_file_extension("Unknown") == ".bin"


def test_filename_composition_no_format_injection():
    """Test that filenames don't have format string injection issues."""
    # This tests that we don't have issues like f-strings with user input
    test_filename = "test{malicious}.mp4"
    # Sanitize should handle this
    result = video_utils.sanitize_path(test_filename)
    # The braces should either be stripped or the filename should be safe
    assert '}' not in str(result).split('.')[-2], f"Unsafe braces in filename: {result}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
