# Snapchat Memories Downloader GUI

A user-friendly desktop application to download and preserve your Snapchat memories with their original metadata, including dates and location information.

**Only available on Windows**

**⚠️IMPORTANT DO THIS FIRST!⚠️: The tool will also attempt to reattach any overlay images back onto the original image or video when an overlay/-main pair is present in ZIP exports. ** For optimal processing of videos and captions, having VLC Media Player and FFmpeg installed on your system is highly recommended. VLC assists in smooth video playback and format conversion, while FFmpeg enhances video overlay merging. The program will attempt to reattach your captions and overlays. Having these tools helps the program ensure all media is processed. Download them here:

- [VLC Media Player](https://www.videolan.org/)
- [FFmpeg](https://www.ffmpeg.org/download.html)

## 📋 Overview

This tool helps you download all your Snapchat memories using the `memories_history.json` file from your Snapchat data export. It preserves important metadata like creation dates, timestamps, and GPS coordinates by embedding them directly into the downloaded media files.

![Application Interface](images/application_screen.png)

## ✨ Features

- **Easy-to-use GUI** - Simple desktop interface, no command line needed
- **Bulk Download** - Download all your memories at once
- **Metadata Preservation** - Maintains original dates and GPS locations
- **EXIF Support** - Embeds metadata into image EXIF data (for JPEG files)
- **Video Metadata** - Adds creation date and location to video files
- **Video Conversion** - Automatic H.264 conversion for better Windows compatibility (VLC recommended)
- **File Timestamps** - Sets file modification dates to match when memories were created
- **Progress Tracking** - Real-time download progress and detailed logging
- **Stop/Resume Capable** - Pause downloads at any time

## 🚀 Getting Started

### Using the Executable (Recommended)

1. **Download the executable** - Get the latest `.exe` file from the releases
2. **Run the application** - Double-click the `.exe` file (no installation needed)
3. **Follow the steps below** to download your memories

### Running from Source

If you prefer to run from the Python source code:

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python download_snapchat_memories_gui.py
```

### Recommended: Install VLC for Video Conversion

For optimal video compatibility on Windows, it's **highly recommended** to install VLC Media Player:

1. **Download VLC** from the official website: https://www.videolan.org/
2. **Install VLC** using the default installation options
3. The application will automatically detect VLC and use it for converting videos to H.264 format

**Why VLC?**
- Ensures videos play smoothly on Windows Media Player and Photos app
- Converts HEVC/H.265 videos to widely compatible H.264 format
- No additional configuration needed - works automatically once installed
- Free and open-source

**Note:** The application will still work without VLC, but some videos may not be converted and could have playback issues on certain devices.

## 📥 How to Get Your Snapchat Data

1. Open **Snapchat** on your mobile device
2. Tap your **profile icon** in the top-left corner
3. Tap the **⚙️ Settings** icon in the top-right
4. Scroll down to **Privacy Controls** section
5. Tap **My Data**
6. **Select the data you want** - Make sure to check the appropriate boxes for the memories you want to export:

   ![Options to Select](images/options_to_select_for_export.png)

7. **Choose your date range** - Select the time period for your memories:

   ![Date Range Selection](images/Date_range.png)

8. Tap **Submit Request** at the bottom

   ![Download Export Button](images/download_export_button.png)

9. Wait for Snapchat to prepare your data (usually 24-48 hours)
10. **Download the ZIP file** when you receive the email from Snapchat
11. **Extract the ZIP file** to a location on your computer (right-click → "Extract All..." on Windows)

    ![Unzipped Folder](images/Unzipped_folder.png)

12. Locate the `memories_history.json` file inside the extracted folder (typically in the root or a `json` subfolder)

## 📖 How to Use

1. **Launch the Application**
   - Run the `.exe` file or Python script
   - You'll see the main application window:

   ![Application Main Screen](images/application_screen.png)

2. **Select JSON File**
   - Click "Browse..." next to "JSON File"
   - Navigate to and select your `memories_history.json` file from the extracted Snapchat data folder

3. **Choose Output Directory**
   - Click "Browse..." next to "Output Directory"
   - Select where you want to save your memories (default: `downloads` folder)

   ![Select Output Directory](images/Output_directory.png)

   ![Application with Paths Selected](images/application_screen_with_paths.png)

4. **Start Download**
   - Click "Start Download" button
   - Monitor progress in the log window
   - Wait for completion (you can click "Stop" to pause if needed)

   ![Download in Progress](images/application_screen_with_Download.png)

5. **Access Your Memories**
   - Once complete, find your downloaded memories in the output directory
   - Files are named with their creation date and time: `YYYYMMDD_HHMMSS_#.jpg/mp4`

## 🔧 Technical Details

### Supported Media Types

- **Images** - JPEG/JPG files with EXIF metadata
- **Videos** - MP4 files with embedded metadata

### Metadata Embedded

- **Creation Date/Time** - When the memory was originally created
- **GPS Coordinates** - Location where the memory was captured (if available)
- **File Timestamps** - File modification dates match creation dates

### Dependencies

The application uses the following Python libraries:

- `requests` - For downloading media files
- `Pillow (PIL)` - Image processing
- `piexif` - EXIF metadata manipulation
- `mutagen` - Video metadata handling
- `tkinter` - GUI framework (included with Python)

### Optional but Recommended

- **VLC Media Player** - For automatic video conversion to H.264 format
  - Download from: https://www.videolan.org/
  - Provides best compatibility for videos on Windows devices
  - Not required but highly recommended for optimal results

## ⚙️ Building the Executable

To compile the Python script into an `.exe` file yourself:

```bash
# Install PyInstaller
pip install pyinstaller

# Build the executable
pyinstaller --onefile --windowed --name "Snapchat Memories Downloader" download_snapchat_memories_gui.py
```

The executable will be created in the `dist` folder.

## 🐛 Troubleshooting

### "No media items found"
- Verify you selected the correct `memories_history.json` file
- Make sure the JSON file is from your Snapchat data export

### Download fails for some files
- Some memories may have expired URLs (especially older ones)
- Check your internet connection
- Snapchat may have changed their URL structure

### Metadata not showing
- EXIF data only works with JPEG images
- Video metadata requires compatible players (VLC, Windows Media Player)
- Some apps may strip metadata when importing

### Videos won't play on Windows
- Install VLC Media Player from https://www.videolan.org/
- Enable the "Convert videos to H.264" option in the app
- Re-download the affected videos
- VLC automatically converts HEVC videos to compatible H.264 format

### Windows SmartScreen Warning
- The `.exe` is not code-signed, so Windows may show a warning
- Click "More info" then "Run anyway" to proceed
- This is normal for unsigned applications

## 📝 Notes

- **Internet Required** - Active connection needed to download from Snapchat servers
- **Large Downloads** - If you have many memories, the process may take time
- **Storage Space** - Ensure you have enough disk space for all memories
- **URL Expiration** - Download links may expire after some time; download soon after receiving your data
- **Privacy** - All processing happens locally on your computer

## 🤝 Contributing

Contributions are welcome! Feel free to:
- Report bugs
- Suggest features
- Submit pull requests

## ⚖️ License

This project is provided as-is for personal use. Use responsibly and in accordance with Snapchat's Terms of Service.

## ⚠️ Disclaimer

This tool is not affiliated with, endorsed by, or connected to Snap Inc. or Snapchat. It is an independent utility designed to help users download their own personal data from Snapchat's official data export feature.

## 💡 Tips

- **Regular Backups** - Download your memories periodically to avoid URL expiration
- **Organize** - Create subfolders by year or month after downloading
- **Verify** - Check a few files after download to ensure metadata was preserved
- **Backup the JSON** - Keep a copy of your `memories_history.json` file

---

**Enjoy preserving your Snapchat memories! 📸🎥**
