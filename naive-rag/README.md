# naive-rag

A minimal Retrieval-Augmented Generation pipeline built from scratch, with no LangChain or LlamaIndex:
naive fixed-size chunking → embed → FAISS → retrieve top-k → grounded generation.
This is the baseline to improve on later with structure-aware chunking, hybrid search and reranking.

The corpus is 24 deep learning papers from January–June 2026, covering RL for reasoning, mixture of experts,
state-space models, diffusion language models, LLM agents and long-context attention.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python fetch_corpus.py   # downloads paper abstracts into corpus/
.venv/bin/python rag.py
```

## Progress

- [x] Step 1: collect the corpus (`fetch_corpus.py`) and load it as `(doc_id, text)` pairs (`load_corpus`)
- [ ] Step 2: naive fixed-size chunking
- [ ] Step 3: embed chunks
- [ ] Step 4: FAISS index
- [ ] Step 5: retrieval
- [ ] Step 6: grounded generation
- [ ] Step 7: `rag_query()` + test questions

## Data and attribution

- **Corpus.** Paper titles, authors and abstracts come from the [arXiv API](https://info.arxiv.org/help/api/index.html).
  The abstracts are **not committed** to this repo; they belong to their authors. Run `fetch_corpus.py` to
  download them locally. Each file links back to its arXiv page.
  arXiv's relevance ranking can change over time, so a later run may return a slightly different set of papers.
- **Embedding model.** [`sentence-transformers/all-MiniLM-L6-v2`](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
  (Apache-2.0). It is downloaded at runtime and not committed.

Thank you to arXiv for use of its open access interoperability.
