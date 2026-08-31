import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
import config
from concept_segmenter import segment_dd_block

def test_heuristic():
    old=config.CONCEPT_SEGMENTATION_MODE;config.CONCEPT_SEGMENTATION_MODE='heuristic'
    words=[{'word':str(i),'start':i,'end':i+.1,'confidence':1} for i in range(10)]
    try: assert segment_dd_block(words)
    finally: config.CONCEPT_SEGMENTATION_MODE=old
