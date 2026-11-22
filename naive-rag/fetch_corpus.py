"""Step 1a: download a small corpus of 2026 deep learning papers from arXiv.

Each paper becomes one plain-text file in corpus/: title, authors, date, link, abstract.
Run once; after that the pipeline only reads the local files.
"""
import re
import subprocess
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

CORPUS_DIR = Path(__file__).parent / "corpus"
ATOM = "{http://www.w3.org/2005/Atom}"
DATE_RANGE = "submittedDate:[202601010000 TO 202606302359]"  # Jan–Jun 2026

# A few current topics; 4 papers each → ~24 docs.
TOPICS = {
    "reasoning": 'abs:"reasoning" AND abs:"reinforcement learning" AND cat:cs.CL',
    "moe": 'abs:"mixture of experts" AND cat:cs.LG',
    "state-space": 'abs:"state space model" AND cat:cs.LG',
    "diffusion-lm": 'abs:"diffusion language model"',
    "agents": 'abs:"LLM agents" AND abs:"tool use"',
    "long-context": 'abs:"long context" AND abs:"attention" AND cat:cs.CL',
}
PER_TOPIC = 4


def fetch(query: str, n: int) -> list[dict]:
    params = urllib.parse.urlencode({
        "search_query": f"({query}) AND {DATE_RANGE}",
        "start": 0,
        "max_results": n,
        "sortBy": "relevance",
    })
    url = f"https://export.arxiv.org/api/query?{params}"
    for attempt in range(4):
        try:
            # curl rather than urllib: urllib truncated responses behind a proxy
            body = subprocess.run(["curl", "-sSf", "--max-time", "60", url],
                                  capture_output=True, check=True).stdout
            root = ET.fromstring(body)
            break
        except Exception as err:  # flaky connection / rate limit → back off and retry
            print(f"  retry {attempt + 1}: {err}")
            time.sleep(5 * (attempt + 1))
    else:
        raise RuntimeError(f"arXiv fetch failed for: {query}")
    papers = []
    for e in root.findall(f"{ATOM}entry"):
        clean = lambda s: re.sub(r"\s+", " ", s).strip()
        papers.append({
            "id": e.find(f"{ATOM}id").text.rsplit("/", 1)[-1],
            "title": clean(e.find(f"{ATOM}title").text),
            "abstract": clean(e.find(f"{ATOM}summary").text),
            "published": e.find(f"{ATOM}published").text[:10],
            "authors": [a.find(f"{ATOM}name").text for a in e.findall(f"{ATOM}author")],
        })
    return papers


def main():
    CORPUS_DIR.mkdir(exist_ok=True)
    seen = set()
    for topic, query in TOPICS.items():
        papers = fetch(query, PER_TOPIC)
        for p in papers:
            if p["id"] in seen:
                continue
            seen.add(p["id"])
            authors = ", ".join(p["authors"][:5]) + (" et al." if len(p["authors"]) > 5 else "")
            text = (
                f"Title: {p['title']}\n"
                f"Authors: {authors}\n"
                f"Published: {p['published']}\n"
                f"arXiv: https://arxiv.org/abs/{p['id']}\n\n"
                f"{p['abstract']}\n"
            )
            safe_id = p["id"].replace("/", "_")
            (CORPUS_DIR / f"{topic}__{safe_id}.txt").write_text(text)
        print(f"{topic:13s} {len(papers)} papers")
        time.sleep(3)  # arXiv asks for ≥3s between API calls
    print(f"\nSaved {len(seen)} documents to {CORPUS_DIR}")


if __name__ == "__main__":
    main()
