import json
import os
import requests
from datetime import datetime
from pathlib import Path
import platform
import subprocess
import shutil
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# For setting file timestamps
try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    import piexif
    HAS_PIEXIF = True
except ImportError:
    HAS_PIEXIF = False

# For setting video metadata without ffmpeg
try:
    from mutagen.mp4 import MP4
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False

# ==================== Core Functions (from original script) ====================

def parse_date(date_str):
    """Parse date string from JSON format to datetime object."""
    return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S UTC")

def parse_location(location_str):
    """Parse location string to get latitude and longitude."""
    if not location_str or location_str == "N/A":
        return None, None
    
    try:
        coords = location_str.split(": ")[1]
        lat, lon = coords.split(", ")
        return float(lat), float(lon)
    except:
        return None, None

def decimal_to_dms(decimal):
    """Convert decimal degrees to degrees, minutes, seconds format for EXIF."""
    is_positive = decimal >= 0
    decimal = abs(decimal)
    
    degrees = int(decimal)
    minutes = int((decimal - degrees) * 60)
    seconds = ((decimal - degrees) * 60 - minutes) * 60
    
    return ((degrees, 1), (minutes, 1), (int(seconds * 100), 100))

def set_image_exif_metadata(file_path, date_obj, latitude, longitude):
    """Set EXIF metadata for image files."""
    if not HAS_PIEXIF:
        return
    
    try:
        try:
            img = Image.open(file_path)
            img_format = img.format
            img.close()
        except Exception:
            return
        
        if img_format not in ['JPEG', 'JPG']:
            return
        
        try:
            exif_dict = piexif.load(file_path)
        except:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
        
        date_str = date_obj.strftime("%Y:%m:%d %H:%M:%S").encode('ascii')
        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = date_str
        exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = date_str
        exif_dict["0th"][piexif.ImageIFD.DateTime] = date_str
        
        if latitude is not None and longitude is not None:
            lat_dms = decimal_to_dms(latitude)
            lon_dms = decimal_to_dms(longitude)
            
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = lat_dms
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = b"N" if latitude >= 0 else b"S"
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = lon_dms
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = b"E" if longitude >= 0 else b"W"
        
        exif_bytes = piexif.dump(exif_dict)
        img = Image.open(file_path)
        img.save(file_path, "JPEG", exif=exif_bytes, quality=95)
        img.close()
        
    except Exception:
        pass

def check_ffmpeg():
    """Check if ffmpeg is available on the system."""
    return shutil.which('ffmpeg') is not None

def set_video_metadata(file_path, date_obj, latitude, longitude):
    """Set metadata for video files using mutagen (no ffmpeg required)."""
    if not HAS_MUTAGEN:
        return False
    
    try:
        video = MP4(file_path)
        
        # Set creation date in ISO format
        creation_time = date_obj.strftime("%Y-%m-%dT%H:%M:%SZ")
        video["\xa9day"] = creation_time  # Date tag
        
        # Add location if available (using custom tags)
        if latitude is not None and longitude is not None:
            # Store as ISO 6709 format string
            location_str = f"{latitude:+.6f}{longitude:+.6f}/"
            video["----:com.apple.quicktime:location-ISO6709"] = location_str.encode('utf-8')
            
            # Also store individual coordinates
            video["----:com.apple.quicktime:latitude"] = str(latitude).encode('utf-8')
            video["----:com.apple.quicktime:longitude"] = str(longitude).encode('utf-8')
        
        video.save()
        return True
        
    except Exception:
        return False

def set_file_timestamps(file_path, date_obj):
    """Set file modification and access times."""
    timestamp = date_obj.timestamp()
    
    try:
        os.utime(file_path, (timestamp, timestamp))
    except Exception:
        pass

def download_media(url, output_path):
    """Download media file from URL."""
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        with open(output_path, 'rb') as f:
            magic = f.read(12)
            
        is_html = magic[:5].lower() == b'<!doc' or magic[:5].lower() == b'<html'
        
        if is_html:
            os.remove(output_path)
            return False
        
        return True
    except Exception:
        return False

def get_file_extension(media_type):
    """Determine file extension based on media type."""
    if media_type == "Image":
        return ".jpg"
    elif media_type == "Video":
        return ".mp4"
    else:
        return ".bin"

# ==================== GUI Application ====================

class SnapchatDownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Snapchat Memories Downloader")
        self.root.geometry("700x700")
        self.root.resizable(True, True)
        self.root.minsize(700, 600)
        
        # Variables
        self.json_path = tk.StringVar()
        self.output_path = tk.StringVar(value="downloads")
        self.is_downloading = False
        self.stop_download = False
        
        # Configure style
        self.setup_styles()
        
        # Build UI
        self.create_widgets()
        
        # Center window
        self.center_window()
    
    def setup_styles(self):
        """Configure ttk styles for a modern look."""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Colors
        bg_color = "#f5f6fa"
        primary_color = "#3742fa"
        secondary_color = "#5f27cd"
        success_color = "#00d2d3"
        text_color = "#2f3542"
        
        # Configure root background
        self.root.configure(bg=bg_color)
        
        # Frame style
        style.configure("Card.TFrame", background="white", relief="flat")
        style.configure("Main.TFrame", background=bg_color)
        
        # Label styles
        style.configure("Title.TLabel", background="white", foreground=text_color, 
                       font=("Segoe UI", 18, "bold"))
        style.configure("Subtitle.TLabel", background="white", foreground="#747d8c", 
                       font=("Segoe UI", 10))
        style.configure("Header.TLabel", background="white", foreground=text_color, 
                       font=("Segoe UI", 11, "bold"))
        style.configure("Info.TLabel", background="white", foreground="#747d8c", 
                       font=("Segoe UI", 9))
        style.configure("Status.TLabel", background="white", foreground=text_color, 
                       font=("Segoe UI", 9))
        
        # Button styles
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), 
                       padding=10, relief="flat")
        style.map("Primary.TButton",
                 foreground=[("active", "white"), ("!active", "white"), ("disabled", "#a4b0be")],
                 background=[("active", secondary_color), ("!active", primary_color), ("disabled", "#dfe4ea")])
        
        style.configure("Secondary.TButton", font=("Segoe UI", 9), 
                       padding=8, relief="flat")
        
        style.configure("Stop.TButton", font=("Segoe UI", 9, "bold"), 
                       padding=8, relief="flat")
        style.map("Stop.TButton",
                 foreground=[("active", "white"), ("!active", "white"), ("disabled", "#a4b0be")],
                 background=[("active", "#c23616"), ("!active", "#e84118"), ("disabled", "#dfe4ea")])
        
        # Progressbar style
        style.configure("Custom.Horizontal.TProgressbar", 
                       troughcolor=bg_color, 
                       background=success_color, 
                       thickness=20)
    
    def center_window(self):
        """Center the window on the screen."""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def create_widgets(self):
        """Create and layout all widgets."""
        # Main container
        main_frame = ttk.Frame(self.root, style="Main.TFrame", padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header card
        header_card = ttk.Frame(main_frame, style="Card.TFrame", padding=20)
        header_card.pack(fill=tk.X, pady=(0, 20))
        
        title_label = ttk.Label(header_card, text="Snapchat Memories Downloader", 
                               style="Title.TLabel")
        title_label.pack(anchor=tk.W)
        
        subtitle_label = ttk.Label(header_card, 
                                   text="Download your Snapchat memories with metadata preservation", 
                                   style="Subtitle.TLabel")
        subtitle_label.pack(anchor=tk.W, pady=(5, 0))
        
        # Input card
        input_card = ttk.Frame(main_frame, style="Card.TFrame", padding=20)
        input_card.pack(fill=tk.X, pady=(0, 20))
        
        # JSON file selection
        json_label = ttk.Label(input_card, text="JSON File", style="Header.TLabel")
        json_label.pack(anchor=tk.W, pady=(0, 8))
        
        json_frame = ttk.Frame(input_card, style="Card.TFrame")
        json_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.json_entry = ttk.Entry(json_frame, textvariable=self.json_path, 
                                    font=("Segoe UI", 9), width=50)
        self.json_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        json_btn = ttk.Button(json_frame, text="Browse...", 
                             command=self.browse_json, style="Secondary.TButton")
        json_btn.pack(side=tk.LEFT)
        
        json_info = ttk.Label(input_card, 
                             text="Select your memories_history.json file from Snapchat export", 
                             style="Info.TLabel")
        json_info.pack(anchor=tk.W, pady=(0, 15))
        
        # Output directory selection
        output_label = ttk.Label(input_card, text="Output Directory", style="Header.TLabel")
        output_label.pack(anchor=tk.W, pady=(0, 8))
        
        output_frame = ttk.Frame(input_card, style="Card.TFrame")
        output_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_path, 
                                      font=("Segoe UI", 9), width=50)
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        output_btn = ttk.Button(output_frame, text="Browse...", 
                               command=self.browse_output, style="Secondary.TButton")
        output_btn.pack(side=tk.LEFT)
        
        output_info = ttk.Label(input_card, 
                               text="Choose where to save your downloaded memories", 
                               style="Info.TLabel")
        output_info.pack(anchor=tk.W, pady=(0, 20))
        
        # Buttons
        button_frame = ttk.Frame(input_card, style="Card.TFrame")
        button_frame.pack(fill=tk.X)
        
        self.download_btn = ttk.Button(button_frame, text="Start Download", 
                                      command=self.start_download, 
                                      style="Primary.TButton")
        self.download_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_btn = ttk.Button(button_frame, text="⏹ Stop", 
                                   command=self.stop_download_func, 
                                   style="Stop.TButton", state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT)
        
        # Progress card
        self.progress_card = ttk.Frame(main_frame, style="Card.TFrame", padding=20)
        self.progress_card.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        progress_label = ttk.Label(self.progress_card, text="Download Progress", 
                                   style="Header.TLabel")
        progress_label.pack(anchor=tk.W, pady=(0, 15))
        
        # Progress bar
        self.progress_bar = ttk.Progressbar(self.progress_card, 
                                           style="Custom.Horizontal.TProgressbar",
                                           mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 10))
        
        # Status label
        self.status_label = ttk.Label(self.progress_card, 
                                     text="Ready to download", 
                                     style="Status.TLabel")
        self.status_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Log area
        log_frame = ttk.Frame(self.progress_card, style="Card.TFrame")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_text = tk.Text(log_frame, height=8, wrap=tk.WORD, 
                               font=("Consolas", 9), bg="#f8f9fa", 
                               fg="#2f3542", relief=tk.FLAT, 
                               yscrollcommand=scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)
    
    def browse_json(self):
        """Open file dialog to select JSON file."""
        filename = filedialog.askopenfilename(
            title="Select Snapchat Memories JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filename:
            self.json_path.set(filename)
    
    def browse_output(self):
        """Open dialog to select output directory."""
        directory = filedialog.askdirectory(title="Select Output Directory")
        if directory:
            self.output_path.set(directory)
    
    def log(self, message):
        """Add message to log area."""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def update_progress(self, current, total):
        """Update progress bar."""
        progress = (current / total) * 100
        self.progress_bar['value'] = progress
        self.status_label.config(text=f"⬇ Downloading {current} of {total}...", foreground="#00d2d3")
        self.root.update_idletasks()
    
    def start_download(self):
        """Start the download process."""
        if self.is_downloading:
            return
        
        json_file = self.json_path.get()
        output_dir = self.output_path.get()
        
        if not json_file:
            messagebox.showerror("Error", "Please select a JSON file")
            return
        
        if not os.path.exists(json_file):
            messagebox.showerror("Error", f"JSON file not found: {json_file}")
            return
        
        if not output_dir:
            messagebox.showerror("Error", "Please select an output directory")
            return
        
        # Clear log
        self.log_text.delete(1.0, tk.END)
        
        # Update UI state with visual feedback
        self.is_downloading = True
        self.stop_download = False
        self.download_btn.config(state=tk.DISABLED, text="⏳ Downloading...")
        self.stop_btn.config(state=tk.NORMAL)
        self.progress_bar['value'] = 0
        self.status_label.config(text="🔄 Starting download...", foreground="#00d2d3")
        
        # Start download in separate thread
        thread = threading.Thread(target=self.download_thread, 
                                 args=(json_file, output_dir))
        thread.daemon = True
        thread.start()
    
    def stop_download_func(self):
        """Stop the download process."""
        self.stop_download = True
        self.stop_btn.config(state=tk.DISABLED, text="⏹ Stopping...")
        self.status_label.config(text="⚠ Stopping download...", foreground="#f39c12")
        self.log("⚠ Stopping download...")
    
    def download_thread(self, json_file, output_dir):
        """Download process running in separate thread."""
        try:
            # Create output directory
            output_path = Path(output_dir)
            output_path.mkdir(exist_ok=True)
            
            # Load JSON
            self.log(f"Loading JSON from: {json_file}")
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Get media items
            media_items = data.get("Saved Media", [])
            total = len(media_items)
            self.log(f"Found {total} media items to download\n")
            
            if total == 0:
                self.log("⚠ No media items found in JSON file")
                self.download_complete()
                return
            
            # Process each item
            success_count = 0
            error_count = 0
            
            for idx, item in enumerate(media_items, 1):
                if self.stop_download:
                    self.log("\n⚠ Download stopped by user")
                    break
                
                self.update_progress(idx, total)
                self.log(f"[{idx}/{total}] Processing...")
                
                # Extract metadata
                date_str = item.get("Date", "")
                media_type = item.get("Media Type", "Unknown")
                location_str = item.get("Location", "")
                download_url = item.get("Media Download Url", "")
                
                if not download_url:
                    self.log("  ⚠ No download URL found, skipping\n")
                    error_count += 1
                    continue
                
                # Parse date and location
                try:
                    date_obj = parse_date(date_str)
                except:
                    self.log("  ⚠ Invalid date format, skipping\n")
                    error_count += 1
                    continue
                    
                latitude, longitude = parse_location(location_str)
                
                # Generate filename
                date_formatted = date_obj.strftime("%Y%m%d_%H%M%S")
                extension = get_file_extension(media_type)
                filename = f"{date_formatted}_{idx}{extension}"
                file_path = output_path / filename
                
                self.log(f"  File: {filename}")
                self.log(f"  Type: {media_type}")
                
                # Download file
                if download_media(download_url, str(file_path)):
                    self.log("  ✓ Downloaded")
                    
                    # Set metadata
                    if media_type == "Image" and extension.lower() in ['.jpg', '.jpeg']:
                        if HAS_PIEXIF:
                            set_image_exif_metadata(str(file_path), date_obj, latitude, longitude)
                            self.log("  ✓ Set EXIF metadata")
                    elif media_type == "Video":
                        if set_video_metadata(str(file_path), date_obj, latitude, longitude):
                            self.log("  ✓ Set video metadata")
                    
                    # Set file timestamps
                    set_file_timestamps(str(file_path), date_obj)
                    
                    success_count += 1
                else:
                    self.log("  ✗ Download failed")
                    error_count += 1
                
                self.log("")  # Empty line
            
            # Final summary
            self.log("=" * 50)
            self.log(f"Download Complete!")
            self.log(f"Success: {success_count}")
            self.log(f"Failed: {error_count}")
            self.log(f"Total: {total}")
            self.log(f"Output: {output_dir}")
            self.log("=" * 50)
            
            if not self.stop_download:
                messagebox.showinfo("Complete", 
                                   f"Downloaded {success_count} of {total} files\n"
                                   f"Output: {output_dir}")
            
        except Exception as e:
            self.log(f"\n✗ Error: {str(e)}")
            messagebox.showerror("Error", f"An error occurred:\n{str(e)}")
        
        finally:
            self.download_complete()
    
    def download_complete(self):
        """Reset UI after download completes."""
        self.is_downloading = False
        self.download_btn.config(state=tk.NORMAL, text="Start Download")
        self.stop_btn.config(state=tk.DISABLED, text="⏹ Stop")
        if self.stop_download:
            self.status_label.config(text="⚠ Download stopped", foreground="#f39c12")
        else:
            self.status_label.config(text="✅ Download complete", foreground="#27ae60")

# ==================== Main ====================

def main():
    """Main function to run the GUI."""
    root = tk.Tk()
    app = SnapchatDownloaderGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
