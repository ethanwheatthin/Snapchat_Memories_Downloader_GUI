"""
Test that return values across modules follow consistent contracts.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pathlib import Path
import tempfile
import video_utils
import snap_utils
import downloader


def test_video_conversion_return_contract():
    """Test that video conversion functions return (bool, Path|str) consistently."""
    # Test sanitize_path returns Path or None
    result = video_utils.sanitize_path("test.mp4")
    assert result is None or isinstance(result, Path), f"sanitize_path should return Path or None, got {type(result)}"
    
    # Test validate_video_file returns (bool, dict)
    with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
        temp_path = Path(f.name)
        f.write(b'\\x00' * 2000)  # Write enough bytes
        f.flush()
        
        is_valid, info = video_utils.validate_video_file(temp_path)
        assert isinstance(is_valid, bool), "First return should be bool"
        assert isinstance(info, dict), "Second return should be dict"
        assert 'error' in info, "Info dict should have 'error' key"


def test_snap_utils_return_contracts():
    """Test snap_utils functions return expected types."""
    # parse_date should return datetime
    from datetime import datetime
    result = snap_utils.parse_date("2023-01-15 10:30:00 UTC")
    assert isinstance(result, datetime), f"parse_date should return datetime, got {type(result)}"
    
    # get_file_extension should return str
    ext = snap_utils.get_file_extension("Video")
    assert isinstance(ext, str), f"get_file_extension should return str, got {type(ext)}"
    assert ext.startswith('.'), "Extension should start with dot"
    
    # validate_downloaded_file should return bool
    with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
        # Write valid MP4 header
        f.write(b'\\x00\\x00\\x00\\x20ftypisom' + b'\\x00' * 1000)
        f.flush()
        
        result = snap_utils.validate_downloaded_file(f.name)
        assert isinstance(result, bool), f"validate_downloaded_file should return bool, got {type(result)}"


def test_downloader_return_contract():
    """Test downloader returns (bool, None|list) as documented."""
    # Test the return type (we can't test actual downloads without network)
    # Just verify the function signature and documentation match
    import inspect
    sig = inspect.signature(downloader.download_media)
    
    # Check parameters match documentation
    params = list(sig.parameters.keys())
    assert 'url' in params, "download_media should have url parameter"
    assert 'output_path' in params, "download_media should have output_path parameter"
    assert 'max_retries' in params, "download_media should have max_retries parameter"
    assert 'progress_callback' in params, "download_media should have progress_callback parameter"
    assert 'date_obj' in params, "download_media should have date_obj parameter"
    
    # Check docstring mentions return contract
    doc = downloader.download_media.__doc__
    assert doc is not None, "download_media should have docstring"
    # Should document the return values
    assert 'Returns' in doc or 'return' in doc.lower(), "Docstring should document return values"


def test_path_return_types():
    """Test that functions returning paths are consistent."""
    # sanitize_path returns Path
    result = video_utils.sanitize_path("test.mp4")
    if result is not None:
        assert isinstance(result, Path), f"Expected Path, got {type(result)}"
    
    # All conversion functions should return Path on success (second tuple element)
    # We can't test actual conversions, but we can verify the pattern


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
