import os
from pathlib import Path

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
        print(f'Found zip: {zip_path} -> extracting/processing to {out_dir}')
        merged = process_zip_overlay(zip_path, str(out_dir))
        if merged:
            print('Merged files:')
            for f in merged:
                print(' -', f)
        else:
            print('No merged files created (check zip contents or pillow installation).')
