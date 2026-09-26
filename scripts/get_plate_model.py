import requests

# Lấy danh sách file trong thư mục model của repo
url = 'https://api.github.com/repos/trungdinh22/License-Plate-Recognition/contents/model'
response = requests.get(url)
print('Status:', response.status_code)

if response.status_code == 200:
    files = response.json()
    for f in files:
        print('  -', f['name'])
else:
    print('Error:', response.text)
