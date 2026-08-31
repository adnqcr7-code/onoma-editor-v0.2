from __future__ import annotations
import shutil,subprocess
from dataclasses import dataclass,field
from pathlib import Path
import config
MIN_WINDOW_SECONDS=.05
@dataclass
class TimedOverlay:
    png_path:Path; windows:list[tuple[float,float]]; topic:str=''; source:str=''
@dataclass
class OverlayChain:
    input_args:list[str]=field(default_factory=list); filter_parts:list[str]=field(default_factory=list); final_label:str='v0'; count:int=0

def _render(svg,png):
    backend=config.OVERLAY_RENDER_BACKEND
    if backend in ('auto','cairosvg'):
        try:
            import cairosvg;cairosvg.svg2png(url=str(svg),write_to=str(png),scale=config.OVERLAY_RENDER_SCALE);return
        except Exception:
            if backend=='cairosvg':raise
    if backend in ('auto','pymupdf'):
        try:
            import fitz; doc=fitz.open(str(svg)); pix=doc[0].get_pixmap(matrix=fitz.Matrix(config.OVERLAY_RENDER_SCALE,config.OVERLAY_RENDER_SCALE),alpha=True); pix.save(str(png));doc.close();return
        except Exception:
            if backend=='pymupdf':raise
    if shutil.which('rsvg-convert'):
        subprocess.run(['rsvg-convert','--zoom',str(config.OVERLAY_RENDER_SCALE),'--output',str(png),str(svg)],check=True);return
    raise RuntimeError('No SVG renderer available. Install cairosvg or pymupdf.')

def compute_output_windows(orig_start,orig_end,keep_segments):
    out=[];offset=0.0
    for seg in keep_segments:
        L=seg.end-seg.start; a=max(orig_start,seg.start); b=min(orig_end,seg.end)
        if b-a>MIN_WINDOW_SECONDS:out.append((offset+a-seg.start,offset+b-seg.start))
        offset+=L
    return out

def prepare_overlays(placements,keep_segments,work_dir):
    work=Path(work_dir);work.mkdir(parents=True,exist_ok=True);out=[]
    for i,p in enumerate(placements):
        windows=compute_output_windows(p.start,p.end,keep_segments)
        if not windows:continue
        png=work/f'overlay_{i:03d}.png'
        try:_render(p.svg_path,png)
        except Exception as e:print(f'[overlay_renderer] WARNING: {e}');continue
        out.append(TimedOverlay(png,windows,p.topic,p.source))
    return out

def _pos(pos,m):
    return {'bottom_right':(f'W-w-{m}',f'H-h-{m}'),'bottom_left':(f'{m}',f'H-h-{m}'),'top_right':(f'W-w-{m}',f'{m}'),'top_left':(f'{m}',f'{m}'),'center':('(W-w)/2','(H-h)/2'),'full':('0','0')}[pos]
def build_overlay_chain(overlays,video_width,video_height,output_duration,base_label='capv',first_input_index=1):
    if not overlays:return OverlayChain(final_label=base_label)
    x,y=_pos(config.OVERLAY_POSITION,config.OVERLAY_MARGIN_PX); args=[];parts=[];cur=base_label
    for n,o in enumerate(overlays):
        idx=first_input_index+n;args += ['-loop','1','-t',f'{output_duration:.3f}','-i',str(o.png_path)]
        scale=f'scale={video_width}:{video_height}' if config.OVERLAY_POSITION=='full' else f'scale={int(video_width*config.OVERLAY_WIDTH_FRACTION)//2*2}:-2'
        enable='+'.join(f'between(t,{a:.3f},{b:.3f})' for a,b in o.windows); nxt=f'ovl{n}'
        parts.append(f'[{idx}:v]{scale}[s{n}];[{cur}][s{n}]overlay=x={x}:y={y}:enable=\'{enable}\'[{nxt}]');cur=nxt
    return OverlayChain(args,parts,cur,len(overlays))
