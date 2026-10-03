"""Separate YOLOv8n character experiment; never overwrites active weights."""
import argparse
import json
from pathlib import Path
import time


def configure_numpy_compatibility():
    # Ultralytics 8.2.103 uses np.trapz in AP metrics. NumPy >=2.4 removed
    # this alias; use its equivalent only in the offline training process.
    import numpy as np
    if not hasattr(np,'trapz'):
        np.trapz=np.trapezoid


def main():
    p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--output',required=True)
    p.add_argument('--epochs',type=int,default=35);p.add_argument('--batch',type=int,default=8)
    p.add_argument('--imgsz',type=int,default=320);p.add_argument('--device',default='0')
    args=p.parse_args();out=Path(args.output).resolve()
    if out.exists(): raise FileExistsError(out)
    configure_numpy_compatibility()
    from ultralytics import YOLO
    model=YOLO('yolov8n.pt');start=time.monotonic()
    def progress(trainer):
        status={'epoch':trainer.epoch+1,'epochs':args.epochs,'elapsed_seconds':time.monotonic()-start,
                'metrics':{k:float(v) for k,v in trainer.metrics.items()}}
        (out/'progress.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
        print('TRAIN_PROGRESS',json.dumps(status),flush=True)
    model.add_callback('on_fit_epoch_end',progress)
    model.train(data=str(Path(args.data).resolve()),project=str(out.parent),name=out.name,
                epochs=args.epochs,patience=8,imgsz=args.imgsz,batch=args.batch,device=args.device,
                workers=0,cache=False,seed=20261001,deterministic=True,optimizer='AdamW',lr0=.001,
                mosaic=0,close_mosaic=0,mixup=0,fliplr=0,flipud=0,degrees=8,shear=3,
                translate=.05,scale=.3,perspective=.0003,plots=True,save=True,exist_ok=False)
    print('CANDIDATE',out/'weights'/'best.pt',flush=True)


if __name__=='__main__':
    main()
