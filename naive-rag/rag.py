"""Naive RAG from scratch: chunk → embed → FAISS → retrieve → generate.
"""
import os
from dataclasses import dataclass
from pathlib import Path

# Keep downloaded models inside the project (must be set before importing transformers)
os.environ.setdefault("HF_HOME", str(Path(__file__).parent / ".hf_cache"))

import numpy as np  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

CORPUS_DIR = Path(__file__).parent / "corpus"

# One model, used everywhere: its tokenizer for chunking, and its encoder for embedding
# both chunks (Step 3) and queries (Step 5). Mixing models between indexing and querying
# is the classic silent RAG bug: no error, just meaningless similarity scores.
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


# Load the model once. Its tokenizer *is* the one the encoder uses, so chunk sizes
# are measured in exactly the units the embedder sees.
embedder = SentenceTransformer(EMBED_MODEL)
tokenizer = embedder.tokenizer


def chunk_document(doc_id: str, text: str, size: int = CHUNK_TOKENS) -> list[Chunk]:
    """Fixed-size token windows, no overlap, no respect for sentences. Deliberately naive.

    We tokenize once with offsets, so each token knows its (start, end) character span in
    the original text. A chunk of tokens [i : i+size] is then text[start_of_first : end_of_last].
    That keeps the original casing and spacing, which tokenizer.decode() would lose
    (MiniLM's tokenizer is uncased: decode would give back lowercase "##word" pieces).
    """
    # verbose=False: the whole doc is >256 tokens, which is fine — that's why we chunk it
    enc = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True, verbose=False)
    offsets = enc["offset_mapping"]
    chunks = []
    for n, i in enumerate(range(0, len(offsets), size)):
        window = offsets[i : i + size]
        start, end = window[0][0], window[-1][1]
        chunks.append(Chunk(f"{doc_id}#{n}", doc_id, text[start:end], len(window)))
    return chunks


def chunk_corpus(docs: list[tuple[str, str]]) -> list[Chunk]:
    return [c for doc_id, text in docs for c in chunk_document(doc_id, text)]


# ---------------------------------------------------------------- Step 3: embed
def embed_texts(texts: list[str]) -> np.ndarray:
    """The ONLY way text becomes a vector in this project: chunks now, queries in Step 5.

    normalize_embeddings=True scales every vector to length 1. For unit vectors,
    dot product == cosine similarity, which is what FAISS IndexFlatIP will compute in Step 4.
    FAISS wants float32, shape (n, dim).
    """
    vecs = embedder.encode(texts, normalize_embeddings=True, convert_to_numpy=True,
                           batch_size=32, show_progress_bar=False)
    return vecs.astype(np.float32)


def embed_chunks(chunks: list[Chunk]) -> np.ndarray:
    # Guard against silent truncation: +2 for the [CLS] and [SEP] the encoder adds.
    limit = embedder.max_seq_length
    too_long = [c.chunk_id for c in chunks if c.n_tokens + 2 > limit]
    assert not too_long, f"chunks over {limit} tokens would be truncated: {too_long}"
    return embed_texts([c.text for c in chunks])


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
    print(f"--- start of {second.chunk_id} ---\n{second.text[:150]}...\n")

    # Step 3: embed every chunk
    vecs = embed_chunks(chunks)
    dim = embedder.get_embedding_dimension()
    norms = np.linalg.norm(vecs, axis=1)
    print(f"Embeddings: shape {vecs.shape}, dtype {vecs.dtype}, model dim {dim}, "
          f"max_seq_length {embedder.max_seq_length}")
    print(f"Vector lengths: min {norms.min():.4f}, max {norms.max():.4f}  (normalized → all 1.0)\n")

    # Sanity check: does the vector space mean anything? Cosine sim = dot product here.
    sims = vecs @ vecs.T
    topic = [c.doc_id.split("__")[0] for c in chunks]
    same_doc, same_topic, diff_topic = [], [], []
    for i in range(len(chunks)):
        for j in range(i + 1, len(chunks)):
            if chunks[i].doc_id == chunks[j].doc_id:
                same_doc.append(sims[i, j])
            elif topic[i] == topic[j]:
                same_topic.append(sims[i, j])
            else:
                diff_topic.append(sims[i, j])
    print("Mean cosine similarity between chunk pairs:")
    print(f"  same paper      {np.mean(same_doc):.3f}")
    print(f"  same topic      {np.mean(same_topic):.3f}")
    print(f"  different topic {np.mean(diff_topic):.3f}")
