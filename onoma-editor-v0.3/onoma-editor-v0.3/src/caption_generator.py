from __future__ import annotations
from pathlib import Path
import config

def _t(s):
    s=max(0,s); h=int(s//3600); m=int((s%3600)//60); return f'{h}:{m:02d}:{s%60:05.2f}'
def _bgr(c):
    c=c.replace('&H','').replace('&',''); return c[2:] if len(c)==8 else c
def _header():
    bold=-1 if config.CAPTION_BOLD else 0
    return f'''[Script Info]\nTitle: Onoma Editor Captions\nScriptType: v4.00+\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,{config.CAPTION_FONT_NAME},{config.CAPTION_FONT_SIZE},{config.CAPTION_PRIMARY_COLOR},&H000000FF,{config.CAPTION_OUTLINE_COLOR},{config.CAPTION_BACK_COLOR},{bold},0,0,0,100,100,0,0,1,{config.CAPTION_OUTLINE_WIDTH},{config.CAPTION_SHADOW},{config.CAPTION_ALIGNMENT},20,20,{config.CAPTION_MARGIN_V},1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'''
def _chunks(words):
    if not words:return []
    out=[[words[0]]]
    for p,c in zip(words,words[1:]):
        if len(out[-1])>=config.CAPTION_MAX_WORDS_PER_LINE or c['start']-p['end']>=config.CAPTION_BREAK_GAP_SECONDS:out.append([c])
        else:out[-1].append(c)
    return out
def generate_ass_captions(words,output_path,mode=None):
    mode=(mode or config.CAPTION_MODE).lower()
    if mode not in {'chunk','karaoke'}:raise ValueError("Caption mode must be 'chunk' or 'karaoke'")
    lines=[_header()]
    for ch in _chunks(words):
        text=' '.join(w['word'] for w in ch); start=_t(ch[0]['start']); end=_t(ch[-1]['end'])
        if mode=='chunk':lines.append(f'Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n')
        else:
            hi=_bgr(config.CAPTION_HIGHLIGHT_COLOR); base=_bgr(config.CAPTION_PRIMARY_COLOR)
            for i,w in enumerate(ch):
                e=max(w['end'], ch[i+1]['start'] if i+1<len(ch) else w['end'])
                words2=[f'{{\\c&H{hi}&}}{x["word"]}{{\\c&H{base}&}}' if j==i else x['word'] for j,x in enumerate(ch)]
                lines.append(f'Dialogue: 0,{_t(w["start"])},{_t(e)},Default,,0,0,0,,{" ".join(words2)}\n')
    p=Path(output_path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(''.join(lines),encoding='utf-8');return p
def build_ffmpeg_caption_filter(ass_path):
    s=str(Path(ass_path).resolve()).replace('\\','/').replace(':','\\:'); return f"subtitles='{s}'"
