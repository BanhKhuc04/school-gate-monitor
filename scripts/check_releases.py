import requests
import os

# Kiểm tra Releases của mrzaizai2k
url = 'https://api.github.com/repos/mrzaizai2k/License-Plate-Recognition-YOLOv7-and-CNN/releases'
response = requests.get(url)
print('Status:', response.status_code)

if response.status_code == 200:
    releases = response.json()
    if releases:
        for release in releases:
            print('Release:', release['tag_name'])
            print('Assets:')
            for asset in release.get('assets', []):
                print('  -', asset['name'], '-', asset['size'], 'bytes')
                print('    Download URL:', asset['browser_download_url'])
    else:
        print('No releases found')
else:
    print('Error:', response.text)
