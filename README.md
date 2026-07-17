
# 🚨 IMPORTANT NOTICE: PROJECT HAS MOVED 🚨

**The newest version of this project has moved!** All future development will take place in a new repository: **[All-In-One-Snapchat-Downloader](https://github.com/ethanwheatthin/All-In-One-Snapchat-Downloader)**. 

There will be no more active development on this current repository. Users looking to download their Snapchat data should head over to the new **[Releases Page and download V.10](https://github.com/ethanwheatthin/All-In-One-Snapchat-Downloader/releases/tag/v10.0.0)**.  

🎥 Check out the new **[YouTube video tutorial](https://www.youtube.com/watch?v=O32IF1Qxg2E)** explaining how to use the new program and what data to select from Snapchat so you can process your Memories and Chat Media all in one go.

***

# Snapchat Memories & Chat Media Download GUI (DEPRECATED)

A user-friendly desktop application (Windows, macOS, and Linux) to download and preserve your Snapchat memories with their original metadata, including exact dates and location information.

![Application Interface](images/application_screen.png)

## 🚀 Quick Start

**Download the official release executable** — The easiest way to use this tool:

🎥 **[YouTube Video Tutorial](https://www.youtube.com/watch?v=DpVOyY-MCLQ)**

1. **Get the `.exe`** from the [latest release](https://github.com/ethanwheatthin/Snapchat_Memories_Downloader_GUI/releases).
2. **Install recommended tools** (optional but highly recommended):
   - [VLC Media Player](https://www.videolan.org/) — for video format conversion.
   - [FFmpeg](https://www.ffmpeg.org/download.html) — for enhanced video overlay merging.
3. **Request your Snapchat data** (see instructions below).
4. **Run the app** and select your `memories_history.json` file.

> **Note:** Do not download the repository ZIP. Use the pre-built `.exe` from the Releases page for the best experience.

## 📋 Overview

This tool downloads all your Snapchat memories using the `memories_history.json` file from your Snapchat data export. It preserves metadata like creation dates, timestamps, and GPS coordinates by embedding them directly into your downloaded media files. It also automatically merges overlay captions and stickers back onto your photos and videos when present.

![Application Interface](images/application_screen.png)

## ✨ Features

- **Simple GUI** — No command line needed; just point and click.
- **Bulk Download** — Download all your memories at once with built-in retry logic.
- **Resume Downloads** — Skip already downloaded files to resume interrupted sessions.
- **Overlay Merging** — Automatically merges caption/sticker overlays back onto photos and videos.
- **Metadata Preservation** — Embeds original dates and GPS coordinates into EXIF data (images) and file metadata (videos).
- **Video Conversion** — Automatic H.264 conversion for better Windows compatibility (requires VLC).
- **File Timestamps** — Sets file modification dates to match memory creation dates.
- **Progress Tracking** — Real-time progress updates and detailed logging.
- **Stop/Resume** — Pause and resume downloads at any time.
- **Process Local Files** — Apply metadata to already-downloaded memories when the Snapchat export does not include download URLs.
- **Process Chat Media** — Merge captions and fix dates/timestamps for the `chat_media/` folder in your export, matching senders and exact times from your chat history.

## 🚀 Getting Started

### Using the Executable (Recommended)

1. **Download** the latest `.exe` from the [Releases page](https://github.com/ethanwheatthin/Snapchat_Memories_Downloader_GUI/releases).
2. **Install optional tools** for best results:
   - **VLC Media Player** ([download](https://www.videolan.org/)) — enables video conversion to H.264.
   - **FFmpeg** ([download](https://www.ffmpeg.org/download.html)) — enhances video overlay merging.
3. **RESTART YOUR COMPUTER AFTER INSTALLING VLC AND FFMPEG.**
4. **Run the application** — Double-click the `.exe` file (click 'Run anyway' if you get a Windows security warning).
5. Follow the usage instructions below.
   >  **Note:** If you keep getting the "no download URL found, skipping" message, please refer to the [Local Processing Guide](#-processing-local-files-no-download-urls). It takes some setup but is the most reliable workaround if the `memories_history.json` download method fails. 

## 📥 How to Get Your Snapchat Data

> **Note:** Snapchat exports expire after 7 days. It is advised to act quickly when you get access to your full export. If you encounter errors, it is best to request a new batch and reprocess that.

1. Open **Snapchat** on your mobile device.
2. Tap your **profile icon** (top-left) → **⚙️ Settings** (top-right).
3. Scroll down to **Privacy Controls** → Tap **My Data**.
4. **Select data to export** — Check the boxes for the memories you want:

   ![Options to Select](images/options_to_select_for_export.png)

5. **Choose a date range** for your memories:

   ![Date Range Selection](images/Date_range.png)

6. Tap **Submit Request**:

   ![Download Export Button](images/download_export_button.png)

7. **Wait 24-48 hours** for Snapchat to prepare your data.
8. **Download the ZIP** when you receive the confirmation email from Snapchat.

> **Note:** If you have multiple ZIP files available for download, only the first (non-numbered) folder contains the `memories_history.json` file. This single JSON file contains all memories from the request, even though it is only located in the first folder.

9. **Extract the ZIP** (right-click → "Extract All..." on Windows):

   ![Unzipped Folder](images/Unzipped_folder.png)

10. Locate `memories_history.json` in the extracted folder (usually in the root or `json` subfolder).

## 📖 How to Use

1. **Launch the Application**

   ![Application Main Screen](images/application_screen.png)

2. **Select JSON File**
   - Click "Browse..." next to "JSON File".
   - Select your `memories_history.json` file.

3. **Choose Output Directory**
   - Click "Browse..." next to "Output Directory".
   - Select where you want to save your memories (default: `downloads` folder).

   ![Select Output Directory](images/Output_directory.png)
   ![Application with Paths Selected](images/application_screen_with_paths.png)

4. **Configure Options (Optional)**
   
   **Resume Options:**
   - **Skip existing files (resume mode)** — Enable this to avoid re-downloading files that already exist.
     - Useful when resuming after an interruption or adding new memories.
     - Validates existing files and only downloads what's missing.
     - Checks for multiple filename patterns (merged overlays, collision-resolved files).
   - **Re-convert existing videos to H.264 if needed** — Only appears when resume mode is enabled.
     - Checks the codec of existing videos and re-converts non-H.264 videos.
     - Ensures all videos are compatible with Windows Media Player and other standard tools.
     - Skips videos already in H.264 format to save time.
   
   **Timezone Handling:**
   - **Use GPS coordinates to determine local timezone** — Recommended, enabled by default.
     - Automatically detects your local timezone from the photo/video GPS location.
     - Files are named and timestamped with local time for easier organization.
     - Falls back to the system timezone when GPS data is unavailable or the checkbox is disabled.

5. **Start Download**
   - Click "Start Download".
   - Monitor progress in the log window.
   - Click "Stop" to pause if needed.

   ![Download in Progress](images/application_screen_with_Download.png)

6. **Access Your Memories**
   - Files are saved in your chosen output directory.
   - Named by creation date: `YYYYMMDD_HHMMSS.jpg` or `YYYYMMDD_HHMMSS.mp4`.
   - Overlays are automatically merged when detected.

## 📂 Processing Local Files (No Download URLs)

Some Snapchat data exports do not include download URLs in `memories_history.json` (the `Media Download Url` field is empty for every entry). This has been confirmed across multiple accounts and does not appear to be a one-off issue. If this happens to you, the standard download mode will skip all files because the URLs simply are not there.

The only option in this case is to download the media files manually from your Snapchat account before your export links expire. This is tedious since Snapchat splits large libraries across many export ZIPs (sometimes 50+ files) that must each be downloaded and extracted one by one.

Once you have the files, Snapchat still includes the actual media inside the `memories/` subfolder of each export ZIP, meaning the metadata (dates, GPS coordinates, overlay merging) can still be applied. This mode does exactly that.

### How to use

1. **Download and extract your Snapchat export ZIP(s)**

   Right-click each ZIP → "Extract All..." to unzip it. If you have multiple export ZIPs, extract them all into one parent folder so the structure looks like this:

   ```text
   snapchat/
   ├── mydata~AAA123/
   │   └── memories/
   ├── mydata~BBB456/
   │   └── memories/
   └── mydata~CCC789/
       └── memories/


Inside each extracted folder, you will find a `memories/` subfolder containing your media files:

2. At the top of the app, switch the **Mode** to **Process Local Files**.
3. **JSON File** — Select your `memories_history.json` as usual.
4. **Memories Folder** — Select one of the following:
* The `memories/` folder from a single export (e.g., `mydata~XXX/memories/`).
* The parent export folder (e.g., `mydata~XXX/`) — the app will find the `memories/` folder automatically.
* A folder containing multiple exports (e.g., `snapchat/`) — the app will discover all `mydata~*/memories/` subfolders and process them in bulk.


5. **Output Directory** — Choose where to save the processed files.
6. Click **Process Local Files**.

The app matches each local file to its JSON entry using the file's modification timestamp, which Snapchat preserves in the export. Correct dates, GPS coordinates, and timezone information are then embedded into each output file.

> **Note:** If you have multiple export ZIPs, place all extracted folders inside one parent directory and point the app at that parent. It will process all of them in a single run.

## 💬 Processing Chat Media (Merge Captions + Fix Metadata)

Snapchat exports can also include a `chat_media/` folder, which contains every photo and video saved in your chats (direct sends, saved snaps, and camera-roll shares). These files come with scrambled names, no usable timestamps, and captions stored as **separate transparent overlay images**.

This mode reassembles them: captions are merged back onto their photos/videos, and correct dates, times, and file timestamps are written to every file.

### Requesting the right export from Snapchat

When requesting your data at [accounts.snapchat.com](https://www.google.com/search?q=https%3A%2F%2Faccounts.snapchat.com) → **My Data**, enable these toggles under "Select data to include":

* **Export JSON Files** — Required for exact timestamps and sender matching.
* **Chat History** — Contains the message records your media files are matched against.
* **Export Chat Media** — The actual photos/videos from your chats.
* **Export Shared Stories** — Recommended; catches media shared via stories.

Then, choose your date range and download/extract the export ZIP as usual. The extracted folder should contain both `chat_media/` and `json/` side by side:

```text
mydata~XXX/
├── chat_media/       ← the media files
├── json/
│   ├── chat_history.json    ← used for exact timestamps + senders
│   └── snap_history.json
└── html/

```

### How to use

1. At the top of the app, switch the **Mode** to **Process Chat Media**.
2. **Chat Media Folder** — Select the `chat_media/` folder from your extracted export (selecting the export folder itself also works). The app will confirm how many files it found and whether it detected your chat history JSON.
3. **Output Directory** — Choose where to save the processed files.
4. Pick an **overlay mode**: merged captions only, originals only, or both.
5. Click **Process Chat Media**.

### What the app does

* **Exact timestamps** — Files are matched to your `chat_history.json` / `snap_history.json` records (typically a 98%+ match rate). It falls back to the video's embedded creation time, then the send time Snapchat stores in the export's file modification times, and finally the filename date at noon local time.
* **Sender info** — The log shows who sent each file and in which conversation.
* **Caption merging** — `media~` and `overlay~` files from the same snap are paired and merged. When several snaps share a date, the app verifies pairings against the export's thumbnails. Captions that can't be confidently paired are never merged onto the wrong photo—they're preserved in an `unmatched_overlays/` folder instead.
* **Metadata fixing** — EXIF dates (images), embedded creation dates (videos), and file created/modified timestamps are all set to the real capture time so files sort correctly in your photo library.
* Output files are named by capture time: `YYYYMMDD_HHMMSS_<n>.jpg` / `.mp4`.

> **Notes:**
> * Chat media contains **no GPS data** (unlike memories), so timestamps use your system timezone and no location is embedded.
> * Thumbnails and metadata sidecar files from the export are consumed during processing but not copied to the output (they contain no unique media).
> * A few files in some exports are stored in an unreadable (likely encrypted) format; these are listed in the log and skipped.
> * If the `json/` folder is missing, the mode still works—it just falls back to embedded video timestamps and filename dates.
> 
> 

## 🔧 Technical Details

### Supported Media Types

* **Images** — JPEG/JPG with EXIF metadata.
* **Videos** — MP4 with embedded metadata.

### Metadata Features

* **Timezone-aware timestamps** — Uses GPS coordinates to determine the correct local time (falls back to system timezone).
* **Creation date/time preservation** — Embedded in EXIF (images) and file metadata (videos).
* **GPS coordinates** — Embedded when available in the original memory.
* **Timezone offset tags** — EXIF 2.31 standard offset fields for proper timezone display.
* **File modification timestamps** — Match local creation time for correct sorting in file managers.
* **Automatic overlay/caption merging** — Combines `-main` and `-overlay` file pairs seamlessly.

### Dependencies

Core libraries:

* `requests` — Network downloads
* `Pillow` — Image processing
* `piexif` — EXIF metadata (optional but recommended)
* `mutagen` — Video metadata (optional but recommended)
* `av` (PyAV) — Video processing (optional)
* `python-vlc` — VLC integration (optional)
* `timezonefinder` — GPS-based timezone detection (optional but recommended)
* `pytz` — Timezone handling (optional but recommended)

> **Note:** The application gracefully handles missing optional packages. If timezone libraries aren't installed, timestamps default to UTC. If EXIF/video metadata libraries are missing, files are still downloaded but without embedded metadata.

### REQUIRED Tools

* **VLC Media Player** — Automatic video conversion to H.264 (highly recommended).
* **FFmpeg** — Enhanced video overlay processing.

## 🍎🐧 Running on macOS and Linux (ALPHA - NEEDS TESTERS)

The app runs on macOS and Linux as well as Windows. Grab the platform build from the [Releases page](https://github.com/ethanwheatthin/Snapchat_Memories_Downloader_GUI/releases) if one is published, or run from source (see below).

**macOS notes:**

* If you use the pre-built `.app`, macOS Gatekeeper will warn about an unsigned app the first time. Right-click the app → **Open** → **Open** to run it.
* If running from source, use Python from [python.org](https://www.python.org/downloads/) or Homebrew (`brew install python-tk`). The Tk that ships with the old system Python is buggy.
* Install [VLC](https://www.videolan.org/) and/or FFmpeg (`brew install ffmpeg`) for video conversion and overlay merging.

**Linux notes:**

* Tkinter is not bundled with most distro Pythons. Install it first:
* Debian/Ubuntu: `sudo apt install python3-tk`
* Fedora: `sudo dnf install python3-tkinter`
* Arch: `sudo pacman -S tk`


* Install VLC and FFmpeg from your package manager (e.g., `sudo apt install vlc ffmpeg`) for video conversion and overlay merging.

## ⚙️ Building from Source

To compile the executable yourself:

```bash
# Install PyInstaller
pip install pyinstaller

# Windows
build_exe.bat

# macOS / Linux
sh build_mac_linux.sh

```

The output is created in the `dist` folder: `SnapchatMemoriesDownloader.exe` on Windows, `SnapchatMemoriesDownloader.app` on macOS, and a `SnapchatMemoriesDownloader` binary on Linux. The build is driven by `SnapchatMemoriesDownloader.spec`, which includes the necessary hidden imports for all dependencies. PyInstaller does not cross-compile—you must build on the OS you are targeting. The GitHub Actions workflow in `.github/workflows/build.yml` builds all three automatically on version tags.

### Running from Source

For developers or advanced users:

```bash
# Clone the repository
git clone [https://github.com/ethanwheatthin/Snapchat_Memories_Downloader_GUI.git](https://github.com/ethanwheatthin/Snapchat_Memories_Downloader_GUI.git)
cd Snapchat_Memories_Downloader_GUI

# Install dependencies
pip install -r requirements.txt

# Run the application
python download_snapchat_memories_gui.py

```

## 🧪 Testing

The project includes comprehensive unit tests to ensure reliability:

```bash
# Install pytest
pip install pytest

# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_filename_sanitization.py -v

# Run with detailed output
python -m pytest tests/ -v --tb=short

```

**Test Coverage:**

* **Filename sanitation** — Ensures no trailing braces or invalid characters in filenames.
* **Atomic conversion** — Verifies temp file → validate → atomic replace workflow.
* **Video validation** — Tests ffprobe-based validation (when available).
* **Return contracts** — Confirms consistent return types across modules.

**For debugging issues**, see [DEBUGGING.md](DEBUGGING.md) for detailed troubleshooting steps, ffprobe commands, and log inspection guidance.

## 📝 Important Notes

* **Storage Space** — Ensure sufficient disk space for all memories.
* **URL Expiration** — Download links expire over time; process your data export promptly.
* **Privacy** — All processing happens locally on your computer; no data is sent elsewhere.
* **Cross-Platform** — Runs on Windows, macOS, and Linux (see the macOS/Linux section above for setup notes).

## 💡 Tips

* **Use Resume Mode** — Enable "Skip existing files" when resuming interrupted downloads.
* **Re-convert as needed** — Use the re-conversion option if you have old HEVC videos that won't play properly.
* **Download regularly** to avoid URL expiration.
* **Organize downloads** by creating subfolders by year/month.
* **Verify metadata** by checking a few files after the initial download.
* **Keep your JSON** — Save a backup copy of `memories_history.json`.

## 🤝 Contributing

Contributions welcome! Feel free to:

* Report bugs via [GitHub Issues](https://github.com/ethanwheatthin/Snapchat_Memories_Downloader_GUI/issues).
* Suggest features.
* Submit pull requests.

## ⚖️ License

This project is provided as-is for personal use. Use responsibly and in accordance with Snapchat's Terms of Service.

## ⚠️ Disclaimer

This tool is not affiliated with, endorsed by, or connected to Snap Inc. or Snapchat. It is an independent utility designed to help users download their own personal data from Snapchat's official data export feature.

**Enjoy preserving your Snapchat memories! 📸🎥**
