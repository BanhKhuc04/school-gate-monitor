"""Audit untrusted ZIP, group augmented originals, write a NEW character dataset."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import random
import re
import stat
import zipfile

import cv2
import numpy as np
import yaml

from scripts.plate_char_tools import CHARACTERS, decode_characters


def source_group(stem):
    return re.sub(r'^\d+(?=(?:xemay|PlateBaza|CarLongPlate)\d+$)', '', stem)


def parse_labels(text):
    boxes=[]
    for line in text.splitlines():
        if not line.strip():
            continue
        parts=line.split()
        if len(parts)!=5 or not parts[0].isdigit():
            raise ValueError('invalid label syntax')
        cls=int(parts[0]);x,y,w,h=map(float,parts[1:])
        if not 0<=cls<36 or not all(math.isfinite(v) for v in (x,y,w,h)):
            raise ValueError('invalid class or nonfinite label')
        if w<=0 or h<=0 or min(x-w/2,y-h/2)<-1e-5 or max(x+w/2,y+h/2)>1+1e-5:
            raise ValueError('box outside image')
        boxes.append((cls,x,y,w,h,1.0))
    return boxes


def prepare(archive,output,seed=20261001):
    archive,output=Path(archive),Path(output)
    if output.exists():
        raise FileExistsError(output)
    samples=[];rejected=[];counts=Counter();seen={};parents={}
    def root(key):
        parents.setdefault(key,key)
        if parents[key]!=key: parents[key]=root(parents[key])
        return parents[key]
    def join(a,b):
        a,b=root(a),root(b)
        parents[max(a,b)]=min(a,b)
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist(); names={i.filename for i in infos}
        if len(names)!=len(infos) or sum(i.file_size for i in infos)>2_000_000_000:
            raise ValueError('duplicate archive entries or expanded archive too large')
        image_names=[PurePosixPath(n.replace('\\','/')).name.casefold() for n in names if n.lower().endswith('.jpg')]
        if len(image_names)!=len(set(image_names)):
            raise ValueError('colliding image names on Windows')
        for i in infos:
            p=PurePosixPath(i.filename.replace('\\','/'))
            if p.is_absolute() or '..' in p.parts or ':' in i.filename or stat.S_ISLNK(i.external_attr>>16):
                raise ValueError('unsafe archive entry')
            if i.file_size>30_000_000:
                raise ValueError('oversized archive entry')
        for name in sorted(names):
            if not name.lower().endswith('.jpg'): continue
            stem=PurePosixPath(name).stem;label=str(PurePosixPath(name).with_suffix('.txt'))
            if stem=='0':
                rejected.append({'image':name,'reason':'alphabet_reference_not_a_plate'});continue
            try:
                if label not in names: raise ValueError('missing label')
                raw=z.read(name);image=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
                if image is None or image.size>30_000_000: raise ValueError('invalid/oversized image')
                text=z.read(label).decode('utf-8-sig');boxes=parse_labels(text)
                if not boxes: raise ValueError('empty character labels')
                digest=hashlib.sha256(image.tobytes()+str(image.shape).encode()).hexdigest()
                decoded=decode_characters(boxes); transcription=decoded['full']
                group=source_group(stem);root(group)
                if re.fullmatch(r'\d{2}[A-Z](?:\d|[A-Z])?\d{4,5}',transcription):
                    join(group,'plate-'+transcription)
                if digest in seen:
                    existing=seen[digest];join(group,existing['group'])
                    if sorted(boxes)!=sorted(existing['boxes']):
                        raise ValueError('duplicate pixels with conflicting labels')
                    rejected.append({'image':name,'reason':'duplicate_pixels'});continue
                row={'archive_entry':name,'image':stem+'.jpg','group':group,'pixel_sha256':digest,
                     'width':image.shape[1],'height':image.shape[0],'label_text':text,
                     'transcription':transcription,'boxes':boxes,'bytes':raw}
                seen[digest]=row;samples.append(row)
            except (ValueError,UnicodeDecodeError) as exc:
                rejected.append({'image':name,'reason':str(exc)})
        if not samples: raise ValueError('no valid images')
        for row in samples: row['group']=root(row['group'])
        groups=sorted({r['group'] for r in samples});random.Random(seed).shuffle(groups)
        n=len(groups);n_train=max(1,int(n*.70));n_val=max(1,int(n*.15)) if n>2 else 0
        mapping={g:('train' if i<n_train else 'val' if i<n_train+n_val else 'test') for i,g in enumerate(groups)}
        output.mkdir(parents=True)
        for split in ('train','val','test'):
            (output/'images'/split).mkdir(parents=True);(output/'labels'/split).mkdir(parents=True)
        for row in samples:
            split=mapping[row['group']];row['split']=split
            (output/'images'/split/row['image']).write_bytes(row.pop('bytes'))
            (output/'labels'/split/Path(row['image']).with_suffix('.txt')).write_text(row.pop('label_text'),encoding='utf-8')
            counts.update(str(int(b[0])) for b in row.pop('boxes'))
    with archive.open('rb') as source:
        archive_hash=hashlib.file_digest(source,'sha256').hexdigest()
    report={'archive':str(archive.resolve()),'archive_sha256':archive_hash,
            'seed':seed,'classes':dict(enumerate(CHARACTERS)),'samples':samples,'rejected':rejected,
            'class_counts':dict(counts),'groups':len(groups),'split_images':dict(Counter(r['split'] for r in samples)),
            'split_groups':dict(Counter(mapping.values())),
            'limitations':['No source video/session IDs in ZIP. Grouping uses filename, exact pixels and supported plate transcription; unknown near duplicates may remain.',
                           'Character labels do not provide full-frame plate bounding boxes.','Automatically reconstructed transcription requires visual audit.']}
    (output/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'data.yaml').write_text(yaml.safe_dump({'path':output.resolve().as_posix(),'train':'images/train',
                    'val':'images/val','test':'images/test','names':dict(enumerate(CHARACTERS))},sort_keys=False),encoding='utf-8')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--zip',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();r=prepare(args.zip,args.output)
    print(json.dumps({k:r[k] for k in ('groups','split_images','split_groups','class_counts')},indent=2))
    print('Rejected:',len(r['rejected']))
