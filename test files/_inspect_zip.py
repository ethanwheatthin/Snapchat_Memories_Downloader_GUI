import zipfile
import re
from pathlib import Path
z = zipfile.ZipFile('FF76EB33-5E2A-4EF6-8120-D86E7431AF3F.zip')
namelist = [n for n in z.namelist() if not n.endswith('/')]
print('namelist:', namelist)
pattern_main = re.compile(r'(?P<base>.+)-main(?P<ext>\.[^.]+)$', re.IGNORECASE)
pattern_overlay = re.compile(r'(?P<base>.+)-overlay(?P<ext>\.[^.]+)$', re.IGNORECASE)
files_by_key = {}
for member in namelist:
    basename = Path(member).name
    m_main = pattern_main.match(basename)
    m_ov = pattern_overlay.match(basename)
    print('member', member, 'basename', basename, 'm_main', bool(m_main), 'm_ov', bool(m_ov))
    if m_main:
        key = (m_main.group('base'), m_main.group('ext').lower())
        files_by_key.setdefault(key, {})['main'] = member
    elif m_ov:
        key = (m_ov.group('base'), m_ov.group('ext').lower())
        files_by_key.setdefault(key, {})['overlay'] = member

print('files_by_key:', files_by_key)
