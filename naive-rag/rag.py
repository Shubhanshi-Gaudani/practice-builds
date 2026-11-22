"""Naive RAG from scratch: chunk → embed → FAISS → retrieve → generate.
"""
import os
from dataclasses import dataclass
from pathlib import Path

# Keep downloaded models inside the project (must be set before importing transformers)
os.environ.setdefault("HF_HOME", str(Path(__file__).parent / ".hf_cache"))

from transformers import AutoTokenizer  # noqa: E402

CORPUS_DIR = Path(__file__).parent / "corpus"

# One name, used everywhere: the tokenizer for chunking now, and the embedder in Step 3.
# Mixing models between indexing and querying is the classic silent RAG bug.
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# MiniLM truncates input at 256 tokens (incl. [CLS] + [SEP]). Anything past that is
# silently dropped from the embedding, so chunks must stay under ~254 content tokens.
CHUNK_TOKENS = 200


# ---------------------------------------------------------------- Step 1: load corpus
def load_corpus(corpus_dir: Path = CORPUS_DIR) -> list[tuple[str, str]]:
    """Read every .txt file into a (doc_id, text) pair. doc_id = filename without .txt."""
    docs = []
    for path in sorted(corpus_dir.glob("*.txt")):
        docs.append((path.stem, path.read_text()))
    return docs


# ---------------------------------------------------------------- Step 2: naive chunking
@dataclass
class Chunk:
    chunk_id: str      # e.g. "moe__2601.09043v1#0"
    doc_id: str
    text: str
    n_tokens: int


tokenizer = AutoTokenizer.from_pretrained(EMBED_MODEL)


def chunk_document(doc_id: str, text: str, size: int = CHUNK_TOKENS) -> list[Chunk]:
    """Fixed-size token windows, no overlap, no respect for sentences. Deliberately naive.

    We tokenize once with offsets, so each token knows its (start, end) character span in
    the original text. A chunk of tokens [i : i+size] is then text[start_of_first : end_of_last].
    That keeps the original casing and spacing, which tokenizer.decode() would lose
    (MiniLM's tokenizer is uncased: decode would give back lowercase "##word" pieces).
    """
    enc = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    offsets = enc["offset_mapping"]
    chunks = []
    for n, i in enumerate(range(0, len(offsets), size)):
        window = offsets[i : i + size]
        start, end = window[0][0], window[-1][1]
        chunks.append(Chunk(f"{doc_id}#{n}", doc_id, text[start:end], len(window)))
    return chunks


def chunk_corpus(docs: list[tuple[str, str]]) -> list[Chunk]:
    return [c for doc_id, text in docs for c in chunk_document(doc_id, text)]


if __name__ == "__main__":
    docs = load_corpus()
    print(f"Loaded {len(docs)} docs\n")

    # Peek at what the tokenizer actually sees
    sample = "Mixture-of-Experts routing in Mamba-2"
    print(f"Tokenizer view of {sample!r}:\n  {tokenizer.tokenize(sample)}\n")

    chunks = chunk_corpus(docs)
    sizes = [c.n_tokens for c in chunks]
    print(f"{len(chunks)} chunks | tokens per chunk: min {min(sizes)}, max {max(sizes)}\n")

    # Show one chunk boundary so you can see naive chunking cut mid-sentence
    first, second = [c for c in chunks if c.doc_id == chunks[0].doc_id][:2]
    print(f"--- end of {first.chunk_id} ---\n...{first.text[-150:]}")
    print(f"--- start of {second.chunk_id} ---\n{second.text[:150]}...")
