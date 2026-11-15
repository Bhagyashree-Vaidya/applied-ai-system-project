"""Retrieval over the curated pet-care knowledge base in knowledge/*.md.

Each markdown file has a small front-matter block (species, title) and is split into
one chunk per "## " section. Chunks are ranked with BM25 (pure Python, no extra
dependencies). Chunks for species that are not in the household are filtered out, and
chunks for the household's species get a small boost over general ("all") notes.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pawpal_ai.config import ROOT

KNOWLEDGE_DIR = ROOT / "knowledge"
_WORD = re.compile(r"[a-z0-9]+")
_STOP = set("a an and are as at be by can do for from has have how i if in is it its my of on or "
            "our so that the their them then there this to too was what when which who will with "
            "you your any some should does just about into than more most very".split())


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens without stop words, with a light plural strip."""
    out = []
    for w in _WORD.findall(text.lower()):
        if w in _STOP:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


@dataclass(frozen=True)
class Chunk:
    """One knowledge-base section."""

    id: str  # e.g. "rabbit_care#gi-stasis-is-an-emergency"
    species: str  # dog | cat | rabbit | all
    title: str
    heading: str
    text: str

    def cite(self) -> str:
        return f"[{self.id}] {self.heading}: {self.text}"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def load_chunks(directory: Path = KNOWLEDGE_DIR) -> list[Chunk]:
    """Parse every knowledge file into section chunks."""
    chunks = []
    for path in sorted(directory.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        meta, body = {}, raw
        if raw.startswith("---"):
            _, header, body = raw.split("---", 2)
            meta = dict(line.split(":", 1) for line in header.strip().splitlines() if ":" in line)
            meta = {k.strip(): v.strip() for k, v in meta.items()}
        for section in re.split(r"^## ", body, flags=re.MULTILINE)[1:]:
            heading, _, text = section.partition("\n")
            chunks.append(Chunk(f"{path.stem}#{_slug(heading)}", meta.get("species", "all"),
                                meta.get("title", path.stem), heading.strip(), " ".join(text.split())))
    return chunks


class Retriever:
    """BM25 ranking with species filtering and boosting."""

    def __init__(self, chunks: list[Chunk] | None = None, k1: float = 1.5, b: float = 0.75,
                 species_boost: float = 1.3):
        self.chunks = chunks if chunks is not None else load_chunks()
        self.k1, self.b, self.species_boost = k1, b, species_boost
        self._docs = [Counter(tokenize(f"{c.title} {c.heading} {c.heading} {c.text}")) for c in self.chunks]
        self._lens = [sum(d.values()) for d in self._docs]
        self._avg = sum(self._lens) / max(len(self._lens), 1)
        df = Counter(term for d in self._docs for term in d)
        n = len(self._docs)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def by_id(self, chunk_id: str) -> Chunk | None:
        return next((c for c in self.chunks if c.id == chunk_id), None)

    def search(self, query: str, species: set[str] | None = None, k: int = 3,
               min_score: float = 3.0) -> list[tuple[Chunk, float]]:
        """Top-k chunks for `query`. `species` limits results to those species plus 'all'."""
        q = tokenize(query)
        results = []
        for chunk, doc, length in zip(self.chunks, self._docs, self._lens):
            if species and chunk.species not in species and chunk.species != "all":
                continue
            score = 0.0
            for term in q:
                tf = doc.get(term, 0)
                if tf:
                    score += self._idf[term] * tf * (self.k1 + 1) / (
                        tf + self.k1 * (1 - self.b + self.b * length / self._avg))
            if species and chunk.species in species:
                score *= self.species_boost
            if score >= min_score:
                results.append((chunk, round(score, 2)))
        results.sort(key=lambda r: -r[1])
        return results[:k]
