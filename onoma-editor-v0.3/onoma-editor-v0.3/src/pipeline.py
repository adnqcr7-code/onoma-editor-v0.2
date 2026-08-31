from __future__ import annotations
import argparse,shutil,subprocess,sys
from pathlib import Path
import config
from transcribe import transcribe_and_save,load_transcript
from command_parser import parse_commands
from cut_processor import build_keep_segments,build_ffmpeg_filter_complex
from dd_processor import process_all_dd_blocks
from caption_generator import generate_ass_captions,build_ffmpeg_caption_filter
from overlay_renderer import prepare_overlays,build_overlay_chain

def _duration(p):
    r=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(p)],capture_output=True,text=True,check=True);return float(r.stdout.strip())
def _dims(p):
    r=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','csv=s=x:p=0',str(p)],capture_output=True,text=True,check=True);w,h=r.stdout.strip().split('x');return int(w),int(h)
def _remap(words,segs):
    out=[];off=0.0
    for s in segs:
        for w in words:
            if s.start<=w['start']<s.end:
                shift=off-s.start;out.append({**w,'start':w['start']+shift,'end':w['end']+shift})
        off+=s.end-s.start
    return out

def run_pipeline(input_path,output_path,skip_transcription_if_cached=True):
    if shutil.which('ffmpeg') is None or shutil.which('ffprobe') is None:raise EnvironmentError('ffmpeg and ffprobe must be on PATH.')
    inp=Path(input_path);out=Path(output_path);config.TMP_DIR.mkdir(parents=True,exist_ok=True)
    if not inp.exists():raise FileNotFoundError(inp)
    cache=config.TMP_DIR/f'{inp.stem}.transcript.json'
    words=load_transcript(cache) if skip_transcription_if_cached and cache.exists() else transcribe_and_save(inp,cache)
    parsed=parse_commands(words);duration=_duration(inp);keep=build_keep_segments(parsed,duration)
    try:placements=process_all_dd_blocks(parsed.dd_spans,words)
    except Exception as e:print(f'WARNING: DD processing failed: {e}');placements=[]
    remapped=_remap(words,keep);ass=config.TMP_DIR/f'{inp.stem}.captions.ass';generate_ass_captions(remapped,ass)
    filters=[f'{build_ffmpeg_filter_complex(keep)};[outv]{build_ffmpeg_caption_filter(ass)}[capv]'];extra=[];label='capv'
    if placements:
        try:
            tw,th=_dims(inp);timed=prepare_overlays(placements,keep,config.TMP_DIR);chain=build_overlay_chain(timed,tw,th,sum(s.end-s.start for s in keep),label);filters.extend(chain.filter_parts);extra=chain.input_args;label=chain.final_label
        except Exception as e: print(f'WARNING: overlay compositing failed: {e}')
    filters.append(f'[{label}]format=yuv420p[vout]')
    cmd=['ffmpeg','-y','-i',str(inp),*extra,'-filter_complex',';'.join(filters),'-map','[vout]','-map','[outa]','-c:v',config.OUTPUT_VIDEO_CODEC,'-preset',config.OUTPUT_X264_PRESET,'-crf',str(config.OUTPUT_CRF),'-r',str(config.OUTPUT_FPS),'-c:a',config.OUTPUT_AUDIO_CODEC,str(out)]
    r=subprocess.run(cmd,capture_output=True,text=True)
    if r.returncode:raise RuntimeError(r.stderr[-4000:])
    print(f'Done: {out}')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);p.add_argument('--no-cache',action='store_true');a=p.parse_args()
    try:run_pipeline(a.input,a.output,not a.no_cache)
    except Exception as e:print(f'PIPELINE FAILED: {e}',file=sys.stderr);sys.exit(1)
