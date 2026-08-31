import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from command_parser import parse_commands
from cut_processor import build_keep_segments

def w(word,start,end):return {'word':word,'start':start,'end':end,'confidence':1}

def test_keep_segments_remove_cut():
    words=[w('cut',2,2.1),w('remove',3,4),w('cut',5,5.1)]
    keep=build_keep_segments(parse_commands(words),10)
    assert any(abs(s.start-0)<.01 and abs(s.end-1.85)<.1 for s in keep)
