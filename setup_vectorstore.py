"""
setup_vectorstore.py - builds the knowledge (RAG) index.

  python setup_vectorstore.py

Sources
  knowledge/*.md         curated notes (dataset definitions, pore geometry and kinetic
                         diameters, application heuristics, MOF basics, MOFChat methods),
                         each with its references
  knowledge/papers/*.pdf scientific papers (ChatMOF.pdf). Text is extracted page by page
                         with pypdf; the reference list is skipped.

Chunks are embedded with Sentence-BERT (all-MiniLM-L6-v2, normalised) and stored in
a FAISS inner-product index, so the retrieval score is cosine similarity.
"""

import re

import mofchat  # noqa: F401  (safe torch/faiss import order)

from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.utils import DistanceStrategy
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from mofchat.config import KNOWLEDGE_DIR, KNOWLEDGE_INDEX_DIR, PAPERS_DIRS, TEXT_EMBEDDING_MODEL

SPLITTER = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=150)


def markdown_docs() -> list[Document]:
    docs = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        text = path.read_text()
        title = text.splitlines()[0].lstrip("# ").strip()
        sections = re.split(r"\n(?=## )", text)
        for sec in sections:
            heading = sec.splitlines()[0].lstrip("# ").strip()
            body = sec if sec.startswith("#") else sec
            for chunk in SPLITTER.split_text(body):
                content = chunk if chunk.startswith("#") else f"{heading}\n{chunk}"
                docs.append(Document(page_content=f"[{title}] {content}",
                                     metadata={"source": path.name, "title": title, "section": heading,
                                               "kind": "curated"}))
    return docs


def clean_pdf_text(t: str) -> str:
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t)      # hyphenated line breaks
    t = re.sub(r"(\w)- (\w)", r"\1\2", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def pdf_docs() -> list[Document]:
    docs, seen = [], set()
    for folder in PAPERS_DIRS:
        if not folder.exists():
            continue
        for pdf in sorted(folder.glob("*.pdf")):
            if pdf.name in seen:
                continue
            reader = PdfReader(str(pdf))
            meta = reader.metadata or {}
            title = (meta.get("/Title") or pdf.stem).strip()
            if "metal" not in title.lower() and "mof" not in title.lower():
                continue                      # only MOF literature (skip lecture notes etc.)
            seen.add(pdf.name)
            for pno, page in enumerate(reader.pages, start=1):
                text = clean_pdf_text(page.extract_text() or "")
                cut = re.search(r"\bReferences\s+1\.\s", text)
                if cut:
                    text = text[:cut.start()]
                if len(text) < 200:
                    continue
                for chunk in SPLITTER.split_text(text):
                    docs.append(Document(page_content=chunk,
                                         metadata={"source": pdf.name, "title": title, "page": pno,
                                                   "kind": "paper"}))
                if cut:
                    break
    return docs


def embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name=TEXT_EMBEDDING_MODEL, encode_kwargs={"normalize_embeddings": True})


def main():
    docs = markdown_docs() + pdf_docs()
    print(f"curated chunks: {sum(d.metadata['kind'] == 'curated' for d in docs)}, "
          f"paper chunks: {sum(d.metadata['kind'] == 'paper' for d in docs)} "
          f"({sorted({d.metadata['source'] for d in docs if d.metadata['kind'] == 'paper'})})")
    store = FAISS.from_documents(docs, embeddings(), distance_strategy=DistanceStrategy.MAX_INNER_PRODUCT)
    KNOWLEDGE_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    store.save_local(str(KNOWLEDGE_INDEX_DIR))
    print(f"saved {len(docs)} chunks to {KNOWLEDGE_INDEX_DIR}")


if __name__ == "__main__":
    main()
