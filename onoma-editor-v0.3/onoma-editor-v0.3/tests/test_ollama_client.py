import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
import ollama_client

def test_retry_validation(monkeypatch):
    calls=[]
    monkeypatch.setattr(ollama_client,'generate',lambda *a,**k: calls.append(1) or ('bad' if len(calls)==1 else 'ok'))
    assert ollama_client.generate_validated('x',lambda s:s if s=='ok' else (_ for _ in ()).throw(ValueError('bad')))=='ok'
