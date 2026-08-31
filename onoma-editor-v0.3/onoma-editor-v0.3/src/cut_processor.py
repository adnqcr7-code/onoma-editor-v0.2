from __future__ import annotations
from dataclasses import dataclass
from command_parser import ParseResult,get_all_command_word_removal_ranges
from config import COMMAND_WORD_PADDING_SECONDS
@dataclass
class KeepSegment:
    start: float; end: float

def _merge(ranges):
    if not ranges:return []
    ranges=sorted(ranges); merged=[ranges[0]]
    for a,b in ranges[1:]:
        x,y=merged[-1]
        if a<=y: merged[-1]=(x,max(y,b))
        else: merged.append((a,b))
    return merged

def build_keep_segments(result,total_duration_seconds):
    removes=[(c.content_start,c.content_end) for c in result.cut_spans]
    removes+=get_all_command_word_removal_ranges(result,COMMAND_WORD_PADDING_SECONDS)
    keep=[]; cursor=0.0
    for a,b in _merge(removes):
        a=max(0.0,a); b=min(total_duration_seconds,b)
        if a>cursor: keep.append(KeepSegment(cursor,a))
        cursor=max(cursor,b)
    if cursor<total_duration_seconds: keep.append(KeepSegment(cursor,total_duration_seconds))
    return [s for s in keep if s.end-s.start>0.01]

def build_ffmpeg_filter_complex(keep_segments):
    if not keep_segments: raise ValueError('No keep segments remain.')
    vp=[];ap=[]
    for i,s in enumerate(keep_segments):
        vp.append(f'[0:v]trim=start={s.start:.3f}:end={s.end:.3f},setpts=PTS-STARTPTS[v{i}]')
        ap.append(f'[0:a]atrim=start={s.start:.3f}:end={s.end:.3f},asetpts=PTS-STARTPTS[a{i}]')
    ins=''.join(f'[v{i}][a{i}]' for i in range(len(keep_segments)))
    return ';'.join(vp+ap+[f'{ins}concat=n={len(keep_segments)}:v=1:a=1[outv][outa]'])
