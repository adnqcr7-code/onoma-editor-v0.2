from __future__ import annotations
import json
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from config import SVG_LIBRARY_DIR,ASSET_LIBRARY_INDEX_FILE,ASSET_MATCH_MIN_CONFIDENCE,ASSET_FUZZY_FLOOR,ASSET_FUZZY_WEIGHT
@dataclass
class AssetMatch:
    asset_path:Path|None; confidence:float; matched_tags:list[str]
def _load(path=None):
    p=path or ASSET_LIBRARY_INDEX_FILE
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
def _sim(a,b):
    if a==b:return 1.0
    if len(a)>2 and len(b)>2 and a.rstrip('s')==b.rstrip('s'):return .95
    r=SequenceMatcher(None,a,b).ratio(); return r if r>=ASSET_FUZZY_FLOOR else 0.0
def find_matching_asset(topic,index_file=None):
    idx=_load(index_file); best=(0.0,None,[])
    words=[w for w in topic.lower().split() if w]
    for fn,meta in idx.items():
        tags=meta.get('tags',[]); scores=[]; matched=[]
        for cw in words:
            b=0; bt=None
            for tag in tags:
                s=max((_sim(cw,tw) for tw in tag.lower().split()),default=0); s=s if s==1 else s*ASSET_FUZZY_WEIGHT
                if s>b:b=s;bt=tag
            scores.append(b)
            if bt and bt not in matched:matched.append(bt)
        score=sum(scores)/len(words) if words else 0
        if score>best[0]:best=(score,fn,matched)
    if best[1] is None or best[0]<ASSET_MATCH_MIN_CONFIDENCE:return AssetMatch(None,best[0],[])
    return AssetMatch((index_file.parent if index_file else SVG_LIBRARY_DIR)/best[1],best[0],best[2])
def register_asset(filename,tags,description,index_file=None):
    p=index_file or ASSET_LIBRARY_INDEX_FILE; data=_load(p); data[filename]={'tags':tags,'description':description,'status':'candidate'}; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(data,indent=2),encoding='utf-8')
