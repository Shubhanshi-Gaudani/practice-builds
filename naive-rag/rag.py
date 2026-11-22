"""Naive RAG from scratch: chunk → embed → FAISS → retrieve → generate.
"""
from pathlib import Path

CORPUS_DIR = Path(__file__).parent / "corpus"


# ---------------------------------------------------------------- Step 1: load corpus
def load_corpus(corpus_dir: Path = CORPUS_DIR) -> list[tuple[str, str]]:
    """Read every .txt file into a (doc_id, text) pair. doc_id = filename without .txt."""
    docs = []
    for path in sorted(corpus_dir.glob("*.txt")):
        docs.append((path.stem, path.read_text()))
    return docs


if __name__ == "__main__":
    docs = load_corpus()
    lengths = [len(t) for _, t in docs]
    print(f"Loaded {len(docs)} docs | chars per doc: min {min(lengths)}, "
          f"avg {sum(lengths) // len(lengths)}, max {max(lengths)}\n")
    doc_id, text = docs[0]
    print(f"--- sample: {doc_id} ---\n{text}")
