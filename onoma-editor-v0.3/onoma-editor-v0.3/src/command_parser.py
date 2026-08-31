from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from config import CUT_COMMAND_WORD, DD_COMMAND_WORD, MAX_COMMAND_PAIR_GAP_SECONDS
from transcribe import WordTimestamp

class CommandType(str, Enum):
    CUT='cut'; DD='dd'
@dataclass
class CommandSpan:
    command_type: CommandType
    start_word_time: float
    start_word_end_time: float
    end_word_time: float
    end_word_end_time: float
    content_start: float = field(init=False)
    content_end: float = field(init=False)
    def __post_init__(self):
        self.content_start=self.start_word_end_time
        self.content_end=self.end_word_time
@dataclass
class ParseWarning:
    message: str
    word_time: float|None=None
@dataclass
class ParseResult:
    cut_spans: list[CommandSpan]
    dd_spans: list[CommandSpan]
    warnings: list[ParseWarning]

def _find(words, command):
    target=command.strip().lower()
    return [w for w in words if w['word'].strip('.,!?').lower()==target]

def _pair(occ, typ, warnings):
    spans=[]; i=0
    while i+1 < len(occ):
        a,b=occ[i],occ[i+1]
        gap=b['start']-a['start']
        if gap>MAX_COMMAND_PAIR_GAP_SECONDS:
            warnings.append(ParseWarning(f"{typ.value} commands are {gap:.1f}s apart; review this pair.", a['start']))
        spans.append(CommandSpan(typ,a['start'],a['end'],b['start'],b['end']))
        i+=2
    if i<len(occ): warnings.append(ParseWarning(f"Unmatched {typ.value} command at {occ[i]['start']:.1f}s.",occ[i]['start']))
    return spans

def parse_commands(words: list[WordTimestamp]) -> ParseResult:
    warnings=[]
    cuts=_pair(_find(words,CUT_COMMAND_WORD),CommandType.CUT,warnings)
    dds=_pair(_find(words,DD_COMMAND_WORD),CommandType.DD,warnings)
    for c in cuts:
        for d in dds:
            if max(c.content_start,d.content_start) < min(c.content_end,d.content_end):
                warnings.append(ParseWarning(f'CUT {c.content_start:.2f}-{c.content_end:.2f}s overlaps DD {d.content_start:.2f}-{d.content_end:.2f}s.'))
    return ParseResult(cuts,dds,warnings)

def get_all_command_word_removal_ranges(result,padding):
    out=[]
    for s in result.cut_spans+result.dd_spans:
        out.append((s.start_word_time-padding,s.start_word_end_time+padding))
        out.append((s.end_word_time-padding,s.end_word_end_time+padding))
    return sorted(out)
