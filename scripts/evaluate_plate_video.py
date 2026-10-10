"""Reproducible offline video/OCR comparison. No camera, DB or live-model writes."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np

from app.cv.best_plate import make_candidate, resolve_plate
from app.cv.ocr import read_plate_detailed
from scripts.plate_char_tools import read_char_crop, confirmed_character_plate


def main():
    p=argparse.ArgumentParser();p.add_argument('--video',required=True);p.add_argument('--output',required=True)
    p.add_argument('--character-model');p.add_argument('--device',default='0')
    p.add_argument('--fps',type=float,default=5);p.add_argument('--imgsz',type=int,default=640)
    p.add_argument('--no-overlay-models',action='store_true')
    p.add_argument('--region-scan',action='store_true',help='Current pipeline fallback on one native vehicle/person region')
    args=p.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    (out/'crops').mkdir();from ultralytics import YOLO
    plate=YOLO('models/plate_best.pt')
    person=helmet=None
    if not args.no_overlay_models:
        person=YOLO('yolov8n.pt');helmet=YOLO('models/backups/helmet_best_20260930_090903.pt')
    elif args.region_scan:
        person=YOLO('yolov8n.pt')
    char=YOLO(args.character_model) if args.character_model else None
    video=cv2.VideoCapture(args.video)
    if not video.isOpened(): raise ValueError('video cannot be decoded')
    fps=video.get(cv2.CAP_PROP_FPS);step=max(1,round(fps/args.fps))
    w,h=int(video.get(3)),int(video.get(4));total=int(video.get(7))
    writer=cv2.VideoWriter(str(out/'annotated.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),fps/step,(w,h))
    if not writer.isOpened(): raise ValueError('video encoder failed')
    records=[];latencies=[];seq=0;visible_frames=0;sampled=0;region_scans=0;region_recovered=0
    last_scan=-1.;scan_index=0
    while True:
        ok=video.grab()
        if not ok: break
        if seq%step:
            seq+=1;continue
        ok,frame=video.retrieve()
        if not ok: break
        display=frame.copy();t=seq/fps;start=time.perf_counter()
        result=plate.predict(frame,imgsz=args.imgsz,device=args.device,conf=.25,verbose=False)[0]
        latencies.append((time.perf_counter()-start)*1000)
        person_result=person.predict(frame,imgsz=640,device=args.device,conf=.35,verbose=False)[0] if person else None
        plate_boxes=list(zip(result.boxes.xyxy.cpu().tolist(),result.boxes.conf.cpu().tolist()))
        if args.region_scan and not plate_boxes and t-last_scan>=.5 and person_result is not None:
            objects=[(person_result.names[int(c)],xy) for xy,c in zip(person_result.boxes.xyxy.cpu().tolist(),person_result.boxes.cls.cpu().tolist())]
            regions=[xy for name,xy in objects if name in ('motorcycle','bicycle')] or [xy for name,xy in objects if name=='person']
            if regions:
                xy=regions[scan_index%len(regions)];scan_index+=1;last_scan=t
                x1,y1,x2,y2=xy;px=(x2-x1)*.1;py=(y2-y1)*.1
                a,b,c,d=max(0,int(x1-px)),max(0,int(y1-py)),min(w,int(x2+px)),min(h,int(y2+py))
                if c>a and d>b and (c-a)*(d-b)<=.8*w*h:
                    region_scans+=1
                    scan=plate.predict(frame[b:d,a:c],imgsz=640,device=args.device,conf=.25,verbose=False)[0]
                    for box,score in zip(scan.boxes.xyxy.cpu().tolist(),scan.boxes.conf.cpu().tolist()):
                        plate_boxes.append(([box[0]+a,box[1]+b,box[2]+a,box[3]+b],score))
                    if plate_boxes:region_recovered+=1
        candidates=[]
        for xy,score in plate_boxes:
            cand=make_candidate(frame,xy,score,seq,t)
            if cand is None: continue
            candidates.append((cand,xy))
            x1,y1,x2,y2=map(int,xy);cv2.rectangle(display,(x1,y1),(x2,y2),(255,210,0),2)
            cv2.putText(display,f'plate box {score:.2f}',(x1,max(15,y1-6)),0,.45,(255,210,0),1)
        if candidates: visible_frames+=1
        if seq%round(fps)==0:
            for index,(cand,xy) in enumerate(candidates):
                crop_name=f'{seq:06d}_{index}.png';cv2.imwrite(str(out/'crops'/crop_name),cand.crop)
                start=time.perf_counter();raw=read_plate_detailed(cand.crop);ocr_ms=(time.perf_counter()-start)*1000
                resolved=resolve_plate(raw)
                row={'frame_seq':seq,'time_seconds':t,'crop':crop_name,'bbox':xy,
                     'crop_width':cand.crop_width,'crop_height':cand.crop_height,'quality':cand.quality_score,
                     'detector_conf':cand.detector_conf,'easyocr':raw,'easyocr_confirmed':resolved.text,
                     'easyocr_ms':ocr_ms,'expected':None}
                if char:
                    start=time.perf_counter();chars=read_char_crop(char,cand.crop,args.device)
                    row.update(character_ocr=chars,character_confirmed=confirmed_character_plate(chars),
                               character_ms=(time.perf_counter()-start)*1000)
                records.append(row)
                text=raw.get('full','') or 'unreadable'
                cv2.putText(display,'OCR trial: '+text,(20,h-35),0,.7,(255,255,255),2)
                if char:
                    cv2.putText(display,'Character OCR trial: '+(chars.get('full','') or 'unreadable'),(20,h-65),0,.7,(0,255,255),2)
        if person:
            for model,allowed,color in ((person,{'person','motorcycle','bicycle'},(30,230,30)),
                                         (helmet,None,(20,160,255))):
                if model is None:continue
                res=person_result if model is person else model.predict(frame,imgsz=640,device=args.device,conf=.35,verbose=False)[0]
                for xy,c,score in zip(res.boxes.xyxy.cpu().tolist(),res.boxes.cls.cpu().tolist(),res.boxes.conf.cpu().tolist()):
                    name=res.names[int(c)]
                    if allowed and name not in allowed: continue
                    a,b,c,d=map(int,xy);cv2.rectangle(display,(a,b),(c,d),color,2)
                    cv2.putText(display,f'{name} {score:.2f}',(a,max(18,b-7)),0,.48,color,1)
        cv2.putText(display,f'OFFLINE TEST  {t:.1f}s  native crop / detector {args.imgsz}',(20,30),0,.65,(255,255,255),2)
        writer.write(display);sampled+=1
        if sampled%100==0: print('VIDEO_PROGRESS',seq,'/',total,'OCR_crops',len(records),flush=True)
        seq+=1
    video.release();writer.release()
    summary={'video':str(Path(args.video).resolve()),'sha256':hashlib.file_digest(open(args.video,'rb'),'sha256').hexdigest(),
             'source_fps':fps,'frames':total,'width':w,'height':h,'duration_seconds':total/fps,
             'sampled_frames':sampled,'frames_with_plate_box':visible_frames,'ocr_crops':len(records),
             'plate_inference_ms_p50':float(np.percentile(latencies[5:],50)),
             'plate_inference_ms_p95':float(np.percentile(latencies[5:],95)),
             'detector_imgsz':args.imgsz,'character_model':args.character_model,
             'region_scans':region_scans,'region_recovered_frames':region_recovered,
             'note':'Box confidence/number of detections is NOT OCR accuracy. No violations or student matching were emitted.'}
    (out/'results.json').write_text(json.dumps({'summary':summary,'records':records},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__': main()
