from __future__ import annotations
import re,xml.etree.ElementTree as ET
from pathlib import Path
import config
from config import SVG_LIBRARY_DIR,SVG_STYLE_GUIDE
from ollama_client import generate_validated
PROMPT='''Generate one simple educational SVG diagram. Concept: {topic}. Context: {excerpt}. Style:\n{style}\nRequirements: valid self-contained SVG; viewBox="0 0 800 600"; no external assets; readable labels; respond only with SVG.'''
def _extract(raw):
    raw=raw.strip(); m=re.search(r'(<svg.*?</svg>)',raw,re.S); return m.group(1) if m else raw
def validate_svg_document(code):
    code=code.strip()
    if not code.startswith('<svg'):raise ValueError('response does not start with <svg')
    try: root=ET.fromstring(code)
    except ET.ParseError as e:raise ValueError(f'not well-formed XML: {e}')
    if not root.tag.lower().endswith('svg'):raise ValueError('root is not svg')
    if 'viewBox' not in root.attrib:raise ValueError('missing viewBox')
    if not code.endswith('</svg>'):raise ValueError('SVG is truncated')
    return code
def generate_svg(concept_topic,transcript_excerpt,reference_description=None):
    p=PROMPT.format(topic=concept_topic,excerpt=transcript_excerpt[:500],style=SVG_STYLE_GUIDE)
    if reference_description:p+=f'\nReference description for inspiration only: {reference_description[:800]}'
    return generate_validated(p,lambda raw:validate_svg_document(_extract(raw)),temperature=.4,repair_instruction='Return only one complete SVG document with viewBox="0 0 800 600".')
def save_generated_svg(svg_code,filename):
    SVG_LIBRARY_DIR.mkdir(parents=True,exist_ok=True); p=SVG_LIBRARY_DIR/filename; p.write_text(svg_code,encoding='utf-8'); return p
