"""
Test atomic conversion flow: temp file -> validate -> atomic replace.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pathlib import Path
import tempfile
import shutil
import video_utils


def test_validate_video_file_basic():
    """Test validate_video_file with basic file checks."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        temp_path = Path(f.name)
        # Write minimal MP4 header (ftyp box)
        f.write(b'\\x00\\x00\\x00\\x20ftypisom\\x00\\x00\\x02\\x00isomiso2mp41' + b'\\x00' * 100)
    
    try:
        # Should pass size check (>1000 bytes)
        is_valid, info = video_utils.validate_video_file(temp_path, min_size=50)
        # Even without ffprobe, should pass size check
        assert is_valid or info['error'] is None or 'ffprobe' in str(info.get('error', '')), \
            f"Validation failed: {info}"
    finally:
        if temp_path.exists():
            temp_path.unlink()


def test_validate_video_file_too_small():
    """Test that validation fails for files that are too small."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        temp_path = Path(f.name)
        f.write(b'tiny')
    
    try:
        is_valid, info = video_utils.validate_video_file(temp_path, min_size=1000)
        assert not is_valid, "Should fail validation for tiny file"
        assert 'too small' in info.get('error', '').lower(), f"Wrong error: {info}"
    finally:
        if temp_path.exists():
            temp_path.unlink()


def test_validate_video_file_nonexistent():
    """Test validation of nonexistent file."""
    fake_path = Path("nonexistent_file_12345.mp4")
    is_valid, info = video_utils.validate_video_file(fake_path)
    assert not is_valid, "Should fail for nonexistent file"
    assert 'not exist' in info.get('error', '').lower(), f"Wrong error: {info}"


def test_atomic_replace_simulation():
    """Test atomic replacement using os.replace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create source and temp files
        source = tmpdir / "source.txt"
        temp = tmpdir / "source.temp.txt"
        target = tmpdir / "target.txt"
        
        source.write_text("original content")
        temp.write_text("new content")
        
        # Atomic replace
        os.replace(str(temp), str(target))
        
        # Verify
        assert target.exists(), "Target should exist after replace"
        assert target.read_text() == "new content", "Target should have new content"
        assert not temp.exists(), "Temp file should not exist after replace"


def test_sanitize_path_in_conversion_pipeline():
    """Test that paths are sanitized in conversion functions."""
    # Test that calling sanitize in convert functions doesn't raise
    result = video_utils.sanitize_path("test.mp4}}")
    assert result is not None
    assert not str(result).endswith('}')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
