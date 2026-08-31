from __future__ import annotations
import os
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / 'assets'
SVG_LIBRARY_DIR = ASSETS_DIR / 'svg'
REFERENCE_DIR = ASSETS_DIR / 'reference'
TMP_DIR = PROJECT_ROOT / '.tmp'

CUT_COMMAND_WORD = 'cut'
DD_COMMAND_WORD = 'dd'
MAX_COMMAND_PAIR_GAP_SECONDS = 600
COMMAND_WORD_PADDING_SECONDS = 0.15

WHISPER_MODEL_SIZE = _env('ONOMA_WHISPER_MODEL', 'large-v3')
WHISPER_DEVICE = _env('ONOMA_WHISPER_DEVICE', 'cuda')
WHISPER_COMPUTE_TYPE = _env('ONOMA_WHISPER_COMPUTE_TYPE', 'float16')
WHISPER_LANGUAGE = _env('ONOMA_WHISPER_LANGUAGE', 'en')

OLLAMA_HOST = _env('OLLAMA_HOST', 'http://localhost:11434')
OLLAMA_MODEL = _env('OLLAMA_MODEL', 'gemma3:12b')
OLLAMA_VISION_MODEL = _env('OLLAMA_VISION_MODEL', OLLAMA_MODEL)
OLLAMA_REQUEST_TIMEOUT_SECONDS = int(_env('ONOMA_OLLAMA_TIMEOUT', '120'))
OLLAMA_MAX_REPAIR_ATTEMPTS = int(_env('ONOMA_OLLAMA_REPAIR_ATTEMPTS', '2'))

CONCEPT_SEGMENTATION_MODE = _env('ONOMA_SEGMENTATION_MODE', 'ollama').lower()
CONCEPT_SEGMENTATION_FALLBACK = True
HEURISTIC_PAUSE_GAP_SECONDS = 0.45
HEURISTIC_MIN_SEGMENT_WORDS = 6

OVERLAY_POSITION = _env('ONOMA_OVERLAY_POSITION', 'bottom_right')
OVERLAY_WIDTH_FRACTION = float(_env('ONOMA_OVERLAY_WIDTH', '0.35'))
OVERLAY_MARGIN_PX = int(_env('ONOMA_OVERLAY_MARGIN', '48'))
OVERLAY_RENDER_BACKEND = _env('ONOMA_OVERLAY_BACKEND', 'auto')
OVERLAY_RENDER_SCALE = float(_env('ONOMA_OVERLAY_SCALE', '2.0'))

CAPTION_MODE = _env('ONOMA_CAPTION_MODE', 'chunk').lower()
CAPTION_HIGHLIGHT_COLOR = '&H008ECF3E'
CAPTION_BREAK_GAP_SECONDS = 0.6
CAPTION_FONT_NAME = _env('ONOMA_CAPTION_FONT', 'Arial Black')
CAPTION_FONT_SIZE = int(_env('ONOMA_CAPTION_SIZE', '72'))
CAPTION_PRIMARY_COLOR = '&H00FFFFFF'
CAPTION_OUTLINE_COLOR = '&H00000000'
CAPTION_BACK_COLOR = '&H00000000'
CAPTION_BOLD = True
CAPTION_OUTLINE_WIDTH = 3
CAPTION_SHADOW = 0
CAPTION_ALIGNMENT = 2
CAPTION_MARGIN_V = 80
CAPTION_MAX_WORDS_PER_LINE = 4
CAPTION_EMPHASIS_COLOR = '&H0000CFFF'

OUTPUT_FPS = 30
OUTPUT_VIDEO_CODEC = 'libx264'
OUTPUT_X264_PRESET = _env('ONOMA_X264_PRESET', 'medium')
OUTPUT_AUDIO_CODEC = 'aac'
OUTPUT_CRF = 18

TAVILY_API_KEY_ENV_VAR = 'TAVILY_API_KEY'
TAVILY_MAX_RESULTS = 3
TAVILY_ENABLED = _env('ONOMA_TAVILY_ENABLED', 'true').lower() in {'1','true','yes','on'}

ASSET_MATCH_MIN_CONFIDENCE = 0.55
ASSET_LIBRARY_INDEX_FILE = SVG_LIBRARY_DIR / 'index.json'
ASSET_FUZZY_FLOOR = 0.60
ASSET_FUZZY_WEIGHT = 0.80

SVG_STYLE_GUIDE = '''
Dark background (near-black, #0a0a0a or transparent).
Thin line weight (1.5-2px strokes), white/light-gray lines.
Minimal color use: accents only in blue or #3ecf8e.
Clean sans-serif labels. No gradients, drop shadows, or decorative clutter.
Keep diagrams readable at small overlay size.
Every label must fit inside its container and elements must not overlap.
Use viewBox="0 0 800 600" and no external assets.
'''
