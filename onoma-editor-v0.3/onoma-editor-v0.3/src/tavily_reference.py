from __future__ import annotations
import os,requests
import config

def get_reference_description(concept_topic):
    if not config.TAVILY_ENABLED:return None
    key=os.environ.get(config.TAVILY_API_KEY_ENV_VAR)
    if not key:return None
    try:
        r=requests.post('https://api.tavily.com/search',json={'api_key':key,'query':f'{concept_topic} diagram explanation','search_depth':'basic','max_results':config.TAVILY_MAX_RESULTS,'include_answer':True},timeout=15); r.raise_for_status(); d=r.json()
    except requests.RequestException:return None
    if d.get('answer'):return str(d['answer'])[:800]
    return ' '.join(str(x.get('content',''))[:200] for x in d.get('results',[])[:2]) or None
