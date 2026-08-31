import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from command_parser import parse_commands,CommandType

def w(word,start,end):return {'word':word,'start':start,'end':end,'confidence':1}

def test_cut_pair():
    r=parse_commands([w('hello',0,1),w('cut',1,1.2),w('bad',2,3),w('cut',3,3.2)])
    assert len(r.cut_spans)==1 and r.cut_spans[0].command_type is CommandType.CUT

def test_dd_pair():
    r=parse_commands([w('dd',1,1.1),w('hello',2,3),w('dd',4,4.1)])
    assert len(r.dd_spans)==1

def test_unmatched_warning():
    r=parse_commands([w('cut',1,1.1)])
    assert r.warnings
