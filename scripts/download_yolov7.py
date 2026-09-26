import requests
import os

# Tải LP_detect_yolov7_500img.pt
url = 'https://github.com/mrzaizai2k/License-Plate-Recognition-YOLOv7-and-CNN/releases/download/Model/LP_detect_yolov7_500img.pt'
output_path = 'models/plate_best.pt'

print('Downloading LP_detect_yolov7_500img.pt...')

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
                if downloaded % (1024 * 1024 * 5) == 0:  # Print every 5MB
                    print(f'Progress: {pct}%...')
    
    print('Download complete!')
    print('Saved to:', output_path)
    print('File size:', os.path.getsize(output_path), 'bytes')
else:
    print('Error:', response.status_code)
