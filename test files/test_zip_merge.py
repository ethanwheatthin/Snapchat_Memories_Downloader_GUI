import os
from pathlib import Path
from datetime import datetime

from download_snapchat_memories_gui import process_zip_overlay


def find_first_zip(search_dir='.'):
    for entry in os.listdir(search_dir):
        if entry.lower().endswith('.zip'):
            return os.path.join(search_dir, entry)
    return None


if __name__ == '__main__':
    zip_path = find_first_zip('.')
    if not zip_path:
        print('No .zip file found in current directory to test.')
    else:
        out_dir = Path('test_output')
        out_dir.mkdir(exist_ok=True)
        
        # Use a test date for consistent filename generation
        test_date = datetime(2023, 6, 15, 14, 30, 45)
        
        print(f'Found zip: {zip_path} -> extracting/processing to {out_dir}')
        print(f'Using test date: {test_date}')
        merged = process_zip_overlay(zip_path, str(out_dir), test_date)
        if merged:
            print('Merged files:')
            import re
            pattern = re.compile(r"^\d{8}_\d{6}(_\d+)?\.[A-Za-z0-9]+$")
            ok = True
            for f in merged:
                name = os.path.basename(f)
                print(' -', name)
                if not pattern.match(name):
                    print('   ⚠ Filename does not match expected date format:', name)
                    ok = False
            if ok:
                print('All merged filenames match the expected date/time format.')
        else:
            print('No merged files created (check zip contents or pillow installation).')
