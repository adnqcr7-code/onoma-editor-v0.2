import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from asset_matcher import find_matching_asset

def test_asset_match(tmp_path):
    (tmp_path/'neuron.svg').write_text('<svg viewBox="0 0 1 1"/>')
    idx=tmp_path/'index.json';idx.write_text(json.dumps({'neuron.svg':{'tags':['neuron']}}))
    m=find_matching_asset('neuron',idx)
    assert m.asset_path and m.asset_path.name=='neuron.svg'
