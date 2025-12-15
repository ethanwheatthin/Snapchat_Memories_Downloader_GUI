import zipfile, sys, os
p = 'FF76EB33-5E2A-4EF6-8120-D86E7431AF3F.zip'
print('path:', os.path.abspath(p))
print('exists:', os.path.exists(p))
if not os.path.exists(p):
    sys.exit(1)
with zipfile.ZipFile(p) as z:
    names = z.namelist()
    print('count:', len(names))
    for n in names:
        print(n)
