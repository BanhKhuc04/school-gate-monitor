import requests
import os

# Tải file LP_detector.pt từ repo
url = 'https://raw.githubusercontent.com/trungdinh22/License-Plate-Recognition/main/model/LP_detector.pt'
output_path = 'models/plate_best.pt'

print('Downloading LP_detector.pt from trungdinh22/License-Plate-Recognition...')

response = requests.get(url, stream=True)
print('Status:', response.status_code)

if response.status_code == 200:
    total = int(response.headers.get('content-length', 0))
    print('Size:', total, 'bytes')
    
    with open(output_path, 'wb') as f:
        downloaded = 0
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                pct = downloaded * 100 // total
                print(f'\rProgress: {pct}%', end='', flush=True)
    
    print('\nSaved to:', output_path)
    print('File size:', os.path.getsize(output_path), 'bytes')
else:
    print('Error:', response.status_code, response.text)
