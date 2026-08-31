import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from caption_generator import generate_ass_captions

def test_caption_output(tmp_path):
    words=[{'word':'hello','start':0,'end':.4,'confidence':1},{'word':'world','start':.45,'end':.8,'confidence':1}]
    out=generate_ass_captions(words,tmp_path/'a.ass','karaoke')
    text=out.read_text()
    assert '[Events]' in text and 'hello' in text and 'world' in text
