import zipfile
z = zipfile.ZipFile('FF76EB33-5E2A-4EF6-8120-D86E7431AF3F.zip')
for n in z.namelist():
    print(n)
