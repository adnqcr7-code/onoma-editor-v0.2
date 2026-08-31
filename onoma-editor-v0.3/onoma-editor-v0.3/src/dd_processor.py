from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from asset_matcher import find_matching_asset,register_asset
from command_parser import CommandSpan
from concept_segmenter import segment_dd_block
from svg_generator import generate_svg,save_generated_svg
from tavily_reference import get_reference_description
import config
@dataclass
class VisualPlacement:
    start:float; end:float; svg_path:Path; topic:str; source:str

def process_dd_block(span,all_words):
    words=[w for w in all_words if span.content_start<=w['start']<span.content_end]
    if not words:return []
    out=[]
    for concept in segment_dd_block(words):
        match=find_matching_asset(concept.topic)
        if match.asset_path:
            out.append(VisualPlacement(concept.start,concept.end,match.asset_path,concept.topic,'library_match')); continue
        try:
            code=generate_svg(concept.topic,concept.transcript_excerpt,get_reference_description(concept.topic) if config.TAVILY_ENABLED else None)
            safe=''.join(c if c.isalnum() else '_' for c in concept.topic.lower()).strip('_')[:40] or 'concept'
            filename=f'generated_{safe}.svg'; path=save_generated_svg(code,filename); register_asset(filename,concept.topic.split(),f'Auto-generated for concept: {concept.topic}')
            out.append(VisualPlacement(concept.start,concept.end,path,concept.topic,'generated'))
        except Exception as exc:
            print(f'[dd_processor] WARNING: visual skipped for {concept.topic!r}: {exc}')
    return out

def process_all_dd_blocks(spans,all_words):
    out=[]
    for s in spans:out.extend(process_dd_block(s,all_words))
    return out
