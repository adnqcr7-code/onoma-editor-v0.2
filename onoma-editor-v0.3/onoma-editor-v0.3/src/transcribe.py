from __future__ import annotations
import json
from pathlib import Path
from typing import TypedDict
from config import WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE, WHISPER_LANGUAGE

class WordTimestamp(TypedDict):
    word: str
    start: float
    end: float
    confidence: float

def transcribe_audio(audio_path: str | Path) -> list[WordTimestamp]:
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f'Audio/video file not found: {path}')
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ImportError('faster-whisper is not installed. Install with pip install faster-whisper.') from exc
    model = WhisperModel(WHISPER_MODEL_SIZE, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
    segments, _ = model.transcribe(str(path), language=WHISPER_LANGUAGE, word_timestamps=True, vad_filter=True)
    words: list[WordTimestamp] = []
    for segment in segments:
        if segment.words is None:
            continue
        for w in segment.words:
            words.append({'word': w.word.strip().lower(), 'start': round(w.start,3), 'end': round(w.end,3), 'confidence': round(getattr(w,'probability',1.0),3)})
    return words

def transcribe_and_save(audio_path, output_json_path):
    words = transcribe_audio(audio_path)
    out = Path(output_json_path); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(words, indent=2, ensure_ascii=False), encoding='utf-8')
    return words

def load_transcript(json_path):
    return json.loads(Path(json_path).read_text(encoding='utf-8'))
