"""Compare held-out character crops and the exact same native video crops."""
import argparse
import json
from pathlib import Path
import time

import cv2
import numpy as np

from app.cv.best_plate import resolve_plate
from app.cv.ocr import read_plate_detailed
from scripts.plate_char_tools import read_char_crop, confirmed_character_plate
from scripts.train_plate_char import configure_numpy_compatibility


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--dataset',required=True)
    p.add_argument('--video-baseline',required=True);p.add_argument('--output',required=True)
    p.add_argument('--device',default='0');args=p.parse_args();out=Path(args.output)
    out.mkdir(parents=True,exist_ok=False);configure_numpy_compatibility()
    from ultralytics import YOLO
    model=YOLO(args.model)
    # Names are part of the contract. A plate/COCO detector is not OCR.
    from scripts.plate_char_tools import CHARACTERS
    if model.names!={i:c for i,c in enumerate(CHARACTERS)}: raise ValueError('wrong character mapping')
    metrics=model.val(data=str(Path(args.dataset)/'data.yaml'),split='test',imgsz=320,batch=8,
                      workers=0,device=args.device,plots=True,project=str(out),name='detector_metrics')
    audit=json.loads((Path(args.dataset)/'audit.json').read_text('utf-8'));rows=[]
    for sample in audit['samples']:
        if sample['split']!='test': continue
        image=cv2.imread(str(Path(args.dataset)/'images'/'test'/sample['image']))
        start=time.perf_counter();chars=read_char_crop(model,image,args.device);char_ms=(time.perf_counter()-start)*1000
        start=time.perf_counter();easy=read_plate_detailed(image);easy_ms=(time.perf_counter()-start)*1000
        rows.append({'image':sample['image'],'expected_from_labels':sample['transcription'],
                     'characters':chars,'easyocr':easy,'character_ms':char_ms,'easyocr_ms':easy_ms,
                     'character_exact':chars['full']==sample['transcription'],
                     'easyocr_exact':easy['full']==sample['transcription']})
        if len(rows)%50==0: print('CROP_EVAL',len(rows),flush=True)
    baseline=json.loads(Path(args.video_baseline).read_text('utf-8'));video=[]
    for row in baseline['records']:
        crop=cv2.imread(str(Path(args.video_baseline).parent/'crops'/row['crop']))
        start=time.perf_counter();chars=read_char_crop(model,crop,args.device);char_ms=(time.perf_counter()-start)*1000
        video.append({**row,'character_ocr':chars,'character_confirmed':confirmed_character_plate(chars),'character_ms':char_ms})
    summary={'candidate':str(Path(args.model).resolve()),'heldout_samples':len(rows),
             'character_exact':sum(r['character_exact'] for r in rows),'easyocr_exact':sum(r['easyocr_exact'] for r in rows),
             'character_ms_p50':float(np.percentile([r['character_ms'] for r in rows][5:],50)),
             'character_ms_p95':float(np.percentile([r['character_ms'] for r in rows][5:],95)),
             'easyocr_ms_p50':float(np.percentile([r['easyocr_ms'] for r in rows][5:],50)),
             'easyocr_ms_p95':float(np.percentile([r['easyocr_ms'] for r in rows][5:],95)),
             'character_detection':{k:float(v) for k,v in metrics.results_dict.items()},
             'limitations':['Test transcripts reconstructed from supplied labels, not all manually verified.',
                           'No training frames from the supplied video were used.',
                           'One repeated plate in video cannot establish general OCR accuracy.']}
    (out/'comparison.json').write_text(json.dumps({'summary':summary,'test_crops':rows,'video_crops':video},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__': main()
