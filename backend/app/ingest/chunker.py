from dataclasses import dataclass
from app.config import settings
from app.ingest.meca import ParsedPaper


@dataclass
class Chunk:
    text: str
    section: str
    chunk_index: int


def _split(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    out: list[str] = []
    i = 0
    while i < len(text):
        end = min(i + max_chars, len(text))
        out.append(text[i:end])
        if end == len(text):
            break
        i = end - overlap
    return out


def chunk_paper(paper: ParsedPaper) -> list[Chunk]:
    chunks: list[Chunk] = []
    idx = 0
    max_chars = settings.chunk_max_chars
    overlap = settings.chunk_overlap_chars

    if paper.abstract:
        for piece in _split(paper.abstract, max_chars, overlap):
            chunks.append(Chunk(text=piece, section="abstract", chunk_index=idx))
            idx += 1
    for label, text in paper.sections:
        for piece in _split(text, max_chars, overlap):
            chunks.append(Chunk(text=piece, section=label, chunk_index=idx))
            idx += 1
    return chunks
