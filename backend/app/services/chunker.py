import re
from dataclasses import dataclass
from typing import Optional

import tiktoken

from app.models.document import Document


@dataclass
class ChunkData:
    text: str
    token_count: int
    chunk_index: int


class SemanticChunker:
    SENTENCE_SPLIT_RE = re.compile(r"(?:\.\s+|!\s+|\?\s+|\n\n+)")

    def __init__(self, chunk_size: int, overlap: int, min_chars: int):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.min_chars = min_chars
        self.encoder = tiktoken.get_encoding("cl100k_base")

    def chunk_document(self, doc: Document) -> list[ChunkData]:
        return self.chunk(doc.content or "")

    def chunk(self, text: str) -> list[ChunkData]:
        cleaned = (text or "").strip()
        if not cleaned:
            return []

        sentences = [s.strip() for s in self.SENTENCE_SPLIT_RE.split(cleaned) if s and s.strip()]
        if not sentences:
            return []

        chunks: list[ChunkData] = []
        current_tokens: list[int] = []
        chunk_index = 0

        for sentence in sentences:
            sentence_tokens = self.encoder.encode(sentence)
            if not sentence_tokens:
                continue
            if len(current_tokens) + len(sentence_tokens) <= self.chunk_size:
                current_tokens.extend(sentence_tokens)
                continue

            chunk = self._build_chunk(current_tokens, chunk_index)
            if chunk:
                chunks.append(chunk)
                chunk_index += 1

            overlap_tokens = current_tokens[-self.overlap :] if self.overlap > 0 else []
            current_tokens = overlap_tokens + sentence_tokens

            if len(current_tokens) > self.chunk_size:
                # If one sentence alone is huge, cap to chunk size and continue.
                chunk = self._build_chunk(current_tokens[: self.chunk_size], chunk_index)
                if chunk:
                    chunks.append(chunk)
                    chunk_index += 1
                current_tokens = current_tokens[self.chunk_size - self.overlap :]

        final_chunk = self._build_chunk(current_tokens, chunk_index)
        if final_chunk:
            chunks.append(final_chunk)

        return chunks

    def _build_chunk(self, token_ids: list[int], chunk_index: int) -> Optional[ChunkData]:
        if not token_ids:
            return None
        text = self.encoder.decode(token_ids).strip()
        if len(text) < self.min_chars:
            return None
        return ChunkData(text=text, token_count=len(token_ids), chunk_index=chunk_index)
