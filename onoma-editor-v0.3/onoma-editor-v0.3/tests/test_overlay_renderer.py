import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from overlay_renderer import compute_output_windows
from cut_processor import KeepSegment

def test_window_mapping():
    w=compute_output_windows(1,4,[KeepSegment(0,2),KeepSegment(5,8)])
    assert w and w[0][0]==1
