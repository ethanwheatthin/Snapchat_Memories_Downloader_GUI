@echo off
echo Building Snapchat Memories Downloader executable...
pyinstaller --onefile --windowed --name=SnapchatMemoriesDownloader ^
  --hidden-import=av ^
  --hidden-import=mutagen ^
  --hidden-import=mutagen.mp4 ^
  --hidden-import=piexif ^
  --hidden-import=PIL ^
  --hidden-import=PIL.Image ^
  --hidden-import=timezonefinder ^
  --hidden-import=pytz ^
  --hidden-import=tzlocal ^
  --collect-all=av ^
  --collect-data=timezonefinder ^
  --noconsole download_snapchat_memories_gui.py

echo.
echo Build complete! Check the dist folder for SnapchatMemoriesDownloader.exe
pause
