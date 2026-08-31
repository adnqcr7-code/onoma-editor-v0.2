import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from svg_generator import validate_svg_document

def test_valid_svg():
    assert validate_svg_document('<svg viewBox="0 0 800 600"></svg>')
