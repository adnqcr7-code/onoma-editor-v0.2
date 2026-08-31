from __future__ import annotations
from typing import Callable
import requests
import config

def generate(prompt, *, temperature=0.4, model=None):
    response=requests.post(f'{config.OLLAMA_HOST}/api/generate',json={'model':model or config.OLLAMA_MODEL,'prompt':prompt,'stream':False,'options':{'temperature':temperature}},timeout=config.OLLAMA_REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status(); return response.json().get('response','')

def generate_validated(prompt,validator,*,temperature=0.4,model=None,repair_instruction='Respond again with only the requested output.',on_retry=None):
    current=prompt; last_raw=''; reason=''
    for attempt in range(1,1+max(0,config.OLLAMA_MAX_REPAIR_ATTEMPTS)+1):
        raw=generate(current,temperature=temperature,model=model); last_raw=raw
        try:return validator(raw)
        except ValueError as exc:
            reason=str(exc)
            if attempt>config.OLLAMA_MAX_REPAIR_ATTEMPTS: break
            if on_retry:on_retry(attempt,reason)
            current=f'{prompt}\n\nPrevious response:\n{raw[:2000]}\n\nRejection: {reason}\n{repair_instruction}'
    raise ValueError(f'Ollama output failed validation after retries. {reason}\n{last_raw[:2000]}')
