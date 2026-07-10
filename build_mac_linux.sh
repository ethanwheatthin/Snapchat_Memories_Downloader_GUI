#!/usr/bin/env sh
# macOS/Linux counterpart to build_exe.bat. Single source of truth for the
# release build is SnapchatMemoriesDownloader.spec (issue #45); any future
# tweaks belong in the .spec, not in flags here.
set -e

echo "Building Snapchat Memories Downloader..."
pyinstaller --clean SnapchatMemoriesDownloader.spec
echo
echo "Build complete! Check the dist folder:"
echo "  macOS: dist/SnapchatMemoriesDownloader.app"
echo "  Linux: dist/SnapchatMemoriesDownloader"
