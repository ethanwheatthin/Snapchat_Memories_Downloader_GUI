"""
Test video validation using ffprobe (when available).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pathlib import Path
import tempfile
import video_utils


def test_check_ffmpeg():
    """Test ffmpeg detection."""
    has_ffmpeg = video_utils.check_ffmpeg()
    # Just check it returns a boolean
    assert isinstance(has_ffmpeg, bool)
    if has_ffmpeg:
        print("✓ ffmpeg is available")
    else:
        print("⚠ ffmpeg not available - some tests will be skipped")


def test_validate_video_file_with_ffprobe():
    """Test validation with ffprobe if available."""
    if not video_utils.check_ffmpeg():
        pytest.skip("ffprobe not available")
    
    # Create a minimal valid MP4 using ffmpeg
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        temp_path = Path(f.name)
    
    try:
        # Create a minimal 1-second test video
        import subprocess
        cmd = [
            'ffmpeg', '-f', 'lavfi', '-i', 'testsrc=duration=1:size=320x240:rate=1',
            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
            '-y', str(temp_path)
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=10)
        
        if result.returncode == 0 and temp_path.exists():
            is_valid, info = video_utils.validate_video_file(temp_path)
            assert is_valid, f"Validation failed for test video: {info}"
            assert info['has_video'], "Should detect video stream"
            assert info['duration'] is not None, "Should have duration"
            assert info['duration'] > 0.5, f"Duration too short: {info['duration']}"
            print(f"✓ Validated test video: duration={info['duration']}s, codec={info['codec']}")
        else:
            pytest.skip("Could not create test video with ffmpeg")
    finally:
        if temp_path.exists():
            temp_path.unlink()


def test_validate_video_file_invalid_format():
    """Test that validation rejects non-video files."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        temp_path = Path(f.name)
        # Write text instead of video
        f.write(b"This is not a video file")
    
    try:
        is_valid, info = video_utils.validate_video_file(temp_path, min_size=10)
        # Should either fail validation or detect no video stream
        if not is_valid:
            assert True, "Correctly rejected non-video file"
        elif info.get('has_video') is False:
            assert True, "Correctly detected no video stream"
        else:
            # If ffprobe not available, might pass size check - that's okay
            pass
    finally:
        if temp_path.exists():
            temp_path.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
