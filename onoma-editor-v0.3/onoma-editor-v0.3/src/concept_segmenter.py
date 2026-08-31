from __future__ import annotations
import json,re,requests
from dataclasses import dataclass
import config
from ollama_client import generate_validated
from transcribe import WordTimestamp
@dataclass
class ConceptSegment:
    topic:str; start:float; end:float; transcript_excerpt:str
PROMPT='''Analyze this technical tutorial transcript and split it into distinct concept segments. Return ONLY JSON array. Each object needs topic (2-5 words), start_word_index, end_word_index. Do not create new segments for filler or rephrasing. Word list:\n{words}'''
def _extract_json(text):
    text=text.strip(); m=re.search(r'```(?:json)?\s*(\[.*?\])\s*```',text,re.S)
    if m:return m.group(1)
    m=re.search(r'(\[.*\])',text,re.S); return m.group(1) if m else text

def _validate(raw):
    try:data=json.loads(_extract_json(raw))
    except json.JSONDecodeError as e: raise ValueError(f'not valid JSON: {e.msg}')
    if not isinstance(data,list) or not data: raise ValueError('expected a non-empty array')
    if not all(isinstance(x,dict) and {'topic','start_word_index','end_word_index'}<=x.keys() for x in data): raise ValueError('every item needs topic/start_word_index/end_word_index')
    return data

def _heuristic(words):
    if not words:return []
    groups=[[words[0]]]
    for prev,cur in zip(words,words[1:]):
        (groups.append([cur]) if cur['start']-prev['end']>=config.HEURISTIC_PAUSE_GAP_SECONDS else groups[-1].append(cur))
    merged=[groups[0]]
    for g in groups[1:]:
        if len(g)<config.HEURISTIC_MIN_SEGMENT_WORDS: merged[-1].extend(g)
        else: merged.append(g)
    return [ConceptSegment(' '.join(w['word'] for w in g if w['word'] not in {'the','a','an','and','to','of','is','it'}).strip()[:80] or 'unnamed concept',g[0]['start'],g[-1]['end'],' '.join(w['word'] for w in g)) for g in merged]

def _validate_ranges(payload,n):
    out=[]; last_end=-1
    for x in sorted(payload,key=lambda x:int(x['start_word_index'])):
        a=int(x['start_word_index']); b=int(x['end_word_index'])
        if a<0 or b<0 or a>=n or b>=n or b<a: raise ValueError('segment indices are out of range')
        if a<=last_end: raise ValueError('segments overlap or are not strictly ordered')
        last_end=b
        out.append((str(x['topic']).strip()[:80],a,b))
    return out

def segment_dd_block(words):
    if not words:return []
    if config.CONCEPT_SEGMENTATION_MODE=='heuristic': return _heuristic(words)
    if config.CONCEPT_SEGMENTATION_MODE!='ollama': raise ValueError('ONOMA_SEGMENTATION_MODE must be ollama or heuristic')
    wl='\n'.join(f'{i}: {w["word"]}' for i,w in enumerate(words))
    try: payload=generate_validated(PROMPT.format(words=wl),_validate,temperature=0.1)
    except requests.RequestException:
        if config.CONCEPT_SEGMENTATION_FALLBACK:return _heuristic(words)
        raise
    ranges=_validate_ranges(payload,len(words))
    return [ConceptSegment(topic,words[a]['start'],words[b]['end'],' '.join(w['word'] for w in words[a:b+1])) for topic,a,b in ranges]
