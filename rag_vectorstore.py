# rag_vectorstore.py
import os
import re
from pathlib import Path
from typing import List, Tuple

from langchain_community.document_loaders import PyPDFLoader, TextLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

DATA_DIR = "data"
CHROMA_DIR = "chroma_db"
COLLECTION_NAME = "indian_law"

# ── Embedding via Anthropic (using a lightweight proxy approach) ──────────────
# We use a simple TF-IDF-style embedding via sentence-transformers if available,
# else fall back to Chroma's default embedding function.
try:
    from langchain_community.embeddings import HuggingFaceEmbeddings
    EMBEDDINGS = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={"device": "cpu"},
    )
    EMBED_PROVIDER = "hf"
except Exception:
    # Fallback: Chroma default (no dependency on external embedding API)
    EMBEDDINGS = None
    EMBED_PROVIDER = "chroma_default"


def load_documents() -> List[Document]:
    """Load PDFs and .txt files from the data/ directory."""
    docs: List[Document] = []
    data_path = Path(DATA_DIR)
    if not data_path.exists():
        data_path.mkdir(parents=True)
        return docs

    for fpath in data_path.rglob("*"):
        try:
            if fpath.suffix.lower() == ".pdf":
                loader = PyPDFLoader(str(fpath))
                docs.extend(loader.load())
            elif fpath.suffix.lower() == ".txt":
                loader = TextLoader(str(fpath), encoding="utf-8")
                docs.extend(loader.load())
        except Exception as e:
            print(f"[RAG] Failed to load {fpath}: {e}")

    print(f"[RAG] Loaded {len(docs)} document pages from {DATA_DIR}/")
    return docs


def chunk_documents(docs: List[Document]) -> List[Document]:
    """Hierarchical chunking: large parent chunks + small child chunks."""
    # Parent chunks (semantic sections)
    parent_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=200,
        separators=["\n\n\n", "\n\n", "\n", ".", " "],
    )
    # Child chunks (dense retrieval)
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=60,
        separators=["\n\n", "\n", ".", " "],
    )

    parent_chunks = parent_splitter.split_documents(docs)
    child_chunks = []
    for parent in parent_chunks:
        children = child_splitter.split_documents([parent])
        # Inherit parent metadata
        for child in children:
            child.metadata.update(parent.metadata)
        child_chunks.extend(children)

    print(f"[RAG] Created {len(parent_chunks)} parent chunks, {len(child_chunks)} child chunks")
    return child_chunks


def build_vectorstore(chunks: List[Document]) -> Chroma:
    """Build or load ChromaDB vectorstore."""
    kwargs = dict(
        collection_name=COLLECTION_NAME,
        persist_directory=CHROMA_DIR,
    )
    if EMBEDDINGS:
        kwargs["embedding_function"] = EMBEDDINGS

    if Path(CHROMA_DIR).exists() and any(Path(CHROMA_DIR).iterdir()):
        print("[RAG] Loading existing ChromaDB...")
        store = Chroma(persist_directory=CHROMA_DIR, collection_name=COLLECTION_NAME,
                       embedding_function=EMBEDDINGS)
    else:
        print("[RAG] Building ChromaDB from chunks...")
        if EMBEDDINGS:
            store = Chroma.from_documents(chunks, EMBEDDINGS, **{k: v for k, v in kwargs.items() if k != "embedding_function"})
        else:
            store = Chroma.from_documents(chunks, **kwargs)
        store.persist()

    return store


# ── Reciprocal Rank Fusion ────────────────────────────────────────────────────
def reciprocal_rank_fusion(
    dense_results: List[Document],
    sparse_results: List[Document],
    k: int = 60,
    top_n: int = 5,
) -> List[Document]:
    """RRF fusion of dense (semantic) and sparse (BM25) results."""
    scores: dict[str, float] = {}
    doc_map: dict[str, Document] = {}

    for rank, doc in enumerate(dense_results):
        key = doc.page_content[:120]
        scores[key] = scores.get(key, 0) + 1 / (k + rank + 1)
        doc_map[key] = doc

    for rank, doc in enumerate(sparse_results):
        key = doc.page_content[:120]
        scores[key] = scores.get(key, 0) + 1 / (k + rank + 1)
        doc_map[key] = doc

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [doc_map[key] for key, _ in ranked[:top_n]]


# ── Main HybridRetriever class ────────────────────────────────────────────────
class HybridRetriever:
    """
    Four-tier retrieval waterfall:
    Tier 1: Semantic cache (in-memory, exact query match)
    Tier 2: Dense retrieval (ChromaDB semantic search)
    Tier 3: Sparse retrieval (BM25 keyword search) + RRF fusion
    Tier 4: Fallback (empty context → triggers LLM fallback mode)
    """

    def __init__(self):
        self._cache: dict[str, List[Document]] = {}
        self._vectorstore: Chroma | None = None
        self._bm25: BM25Retriever | None = None
        self._all_chunks: List[Document] = []
        self._initialized = False

    def initialize(self):
        if self._initialized:
            return
        docs = load_documents()
        if not docs:
            print("[RAG] No documents found in data/ — operating in fallback-only mode.")
            self._initialized = True
            return

        chunks = chunk_documents(docs)
        self._all_chunks = chunks
        self._vectorstore = build_vectorstore(chunks)
        self._bm25 = BM25Retriever.from_documents(chunks, k=8)
        self._initialized = True
        print("[RAG] HybridRetriever ready.")

    def retrieve(self, query: str, top_k: int = 5) -> Tuple[List[Document], str]:
        """
        Returns (documents, tier_used).
        tier_used is one of: 'cache', 'hybrid', 'fallback'
        """
        self.initialize()

        # Tier 1: Semantic cache
        cache_key = query.strip().lower()
        if cache_key in self._cache:
            return self._cache[cache_key], "cache"

        # Tier 2 + 3: Hybrid retrieval with RRF
        if self._vectorstore and self._bm25:
            try:
                dense_docs = self._vectorstore.similarity_search(query, k=8)
                sparse_docs = self._bm25.get_relevant_documents(query)
                fused = reciprocal_rank_fusion(dense_docs, sparse_docs, top_n=top_k)
                if fused:
                    self._cache[cache_key] = fused  # Store in cache
                    return fused, "hybrid"
            except Exception as e:
                print(f"[RAG] Retrieval error: {e}")

        # Tier 4: Fallback
        return [], "fallback"

    def format_context(self, docs: List[Document]) -> str:
        """Format retrieved documents into a clean context string."""
        if not docs:
            return "No relevant legal context retrieved."
        parts = []
        for i, doc in enumerate(docs, 1):
            src = doc.metadata.get("source", "Unknown Source")
            page = doc.metadata.get("page", "")
            header = f"[Source {i}: {Path(src).name}{f', Page {page}' if page else ''}]"
            parts.append(f"{header}\n{doc.page_content.strip()}")
        return "\n\n---\n\n".join(parts)


# Singleton instance
retriever = HybridRetriever()
