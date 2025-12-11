@echo off
echo Building Snapchat Memories Downloader executable...
pyinstaller --onefile --windowed --name=SnapchatMemoriesDownloader --hidden-import=av --hidden-import=mutagen --hidden-import=piexif --hidden-import=PIL --collect-all=av --noconsole download_snapchat_memories_gui.py
echo.
echo Build complete! Check the dist folder for SnapchatMemoriesDownloader.exe
pause
