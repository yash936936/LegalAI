# rag_vectorstore.py
import os
import math
from pathlib import Path
from typing import List, Tuple

# FIX: load .env defensively here too, not just in app.py. EMBEDDINGS below
# reads GOOGLE_API_KEY at *import time*, so if this module is ever imported
# before something else has called load_dotenv() (a script, a test, a
# notebook, a different entrypoint), the key would be None and pydantic
# would raise ValidationError. load_dotenv() is idempotent and a no-op if
# the vars are already set, so this is always safe to call.
from dotenv import load_dotenv
load_dotenv()

from langchain_community.document_loaders import PyPDFLoader, TextLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings

# ── Path Resolution ─────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

if not DATA_DIR.exists():
    parent_data = BASE_DIR.parent / "data"
    if parent_data.exists():
        print(f"[RAG] Found 'data' folder in parent directory. Using: {parent_data}")
        DATA_DIR = parent_data
    else:
        print(f"[RAG] WARNING: 'data' folder not found in {BASE_DIR} or {BASE_DIR.parent}!")
        print(f"[RAG] Place your Indian-law PDFs/TXTs inside a folder named 'data'.")

CHROMA_DIR = BASE_DIR / "chroma_db"
COLLECTION_NAME = "indian_law"

# text-embedding-004 is the free-tier embedding model recommended for new
# projects; gemini-embedding-001 also works on the free tier but check
# https://ai.google.dev/gemini-api/docs/embeddings for current limits.
EMBEDDINGS = GoogleGenerativeAIEmbeddings(
    model="models/text-embedding-004",
    google_api_key=os.getenv("GOOGLE_API_KEY"),
)


def load_documents() -> List[Document]:
    """Loads PDF and TXT documents from the data directory."""
    if not DATA_DIR.exists():
        print(f"[RAG] Data directory '{DATA_DIR}' not found.")
        return []

    pdf_loader = DirectoryLoader(str(DATA_DIR), glob="**/*.pdf", loader_cls=PyPDFLoader)
    text_loader = DirectoryLoader(str(DATA_DIR), glob="**/*.txt", loader_cls=TextLoader)

    docs = []
    try:
        pdf_docs = pdf_loader.load()
        docs.extend(pdf_docs)
        print(f"[RAG] Loaded {len(pdf_docs)} PDF documents")
    except Exception as e:
        print(f"[RAG] Error loading PDFs: {e}")

    try:
        text_docs = text_loader.load()
        docs.extend(text_docs)
        print(f"[RAG] Loaded {len(text_docs)} TXT documents")
    except Exception as e:
        print(f"[RAG] Error loading TXTs: {e}")

    return docs


def chunk_documents(docs: List[Document]) -> List[Document]:
    """Splits documents into smaller chunks for embedding."""
    if not docs:
        return []
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_documents(docs)
    print(f"[RAG] Created {len(chunks)} document chunks")
    return chunks


def build_vectorstore(chunks: List[Document]) -> Chroma:
    if not chunks:
        print("[RAG] No chunks to build vectorstore from.")
        return None

    kwargs = dict(collection_name=COLLECTION_NAME, persist_directory=str(CHROMA_DIR))

    if CHROMA_DIR.exists() and any(CHROMA_DIR.iterdir()):
        print("[RAG] Loading existing ChromaDB...")
        store = Chroma(
            persist_directory=str(CHROMA_DIR),
            collection_name=COLLECTION_NAME,
            embedding_function=EMBEDDINGS,
        )
    else:
        print("[RAG] Building ChromaDB from chunks...")
        store = Chroma.from_documents(chunks, EMBEDDINGS, **kwargs)

    return store


def reciprocal_rank_fusion(
    dense_docs: List[Document],
    sparse_docs: List[Document],
    top_n: int = 5,
    k: int = 60,
) -> List[Document]:
    """Merges dense and sparse retrieval results using Reciprocal Rank Fusion (RRF)."""
    fused_scores = {}
    doc_map = {}

    for rank, doc in enumerate(dense_docs):
        doc_id = doc.metadata.get("source", "") + str(doc.page_content[:50])
        fused_scores.setdefault(doc_id, 0)
        doc_map[doc_id] = doc
        fused_scores[doc_id] += 1 / (rank + k)

    for rank, doc in enumerate(sparse_docs):
        doc_id = doc.metadata.get("source", "") + str(doc.page_content[:50])
        fused_scores.setdefault(doc_id, 0)
        doc_map[doc_id] = doc
        fused_scores[doc_id] += 1 / (rank + k)

    sorted_docs = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
    return [doc_map[doc_id] for doc_id, _ in sorted_docs[:top_n]]


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class HybridRetriever:
    """
    Hybrid RAG pipeline (Dense + BM25 + RRF), fronted by a Tier-0 local
    semantic cache. The semantic cache is what makes paraphrased repeat
    questions ("what happens if I'm arrested" vs "rights if arrested")
    hit the cache instead of re-running retrieval + generation — the
    original cache only matched on exact lowercased string equality.
    """

    def __init__(self, sim_threshold: float = 0.93, max_cache_entries: int = 200):
        self._vectorstore = None
        self._bm25 = None
        self._initialized = False
        self._cache: List[Tuple[List[float], str, List[Document]]] = []
        self.sim_threshold = sim_threshold
        self.max_cache_entries = max_cache_entries

    def initialize(self):
        """Lazy initialization of the vectorstore and BM25 index."""
        if self._initialized:
            return

        docs = load_documents()
        if not docs:
            print("[RAG] No documents found. Retriever will operate in fallback mode.")
            self._initialized = True
            return

        chunks = chunk_documents(docs)
        if chunks:
            self._vectorstore = build_vectorstore(chunks)
            self._bm25 = BM25Retriever.from_documents(chunks)
            self._bm25.k = 8

        self._initialized = True
        print("[RAG] Hybrid Retriever initialized successfully.")

    def _cache_lookup(self, query_norm: str):
        """Tier 0: local, zero-API-cost semantic cache lookup."""
        if not self._cache:
            return None, None
        try:
            q_emb = EMBEDDINGS.embed_query(query_norm)
        except Exception as e:
            print(f"[RAG] Cache embedding failed, skipping cache: {e}")
            return None, None

        best_sim, best_docs, best_text = 0.0, None, None
        for cached_emb, cached_text, cached_docs in self._cache:
            sim = _cosine(q_emb, cached_emb)
            if sim > best_sim:
                best_sim, best_docs, best_text = sim, cached_docs, cached_text

        if best_sim >= self.sim_threshold:
            return best_docs, q_emb  # cache hit
        return None, q_emb  # cache miss, but reuse the embedding we just computed

    def retrieve(self, query: str, top_k: int = 5) -> Tuple[List[Document], str]:
        """Retrieves documents using semantic cache, hybrid search, or fallback."""
        self.initialize()
        query_norm = query.strip().lower()

        cached_docs, q_emb = self._cache_lookup(query_norm)
        if cached_docs is not None:
            print("[RAG] Semantic cache hit — skipping retrieval entirely")
            return cached_docs, "cache"

        if self._vectorstore and self._bm25:
            try:
                dense_docs = self._vectorstore.similarity_search(query, k=8)
                sparse_docs = self._bm25.invoke(query)
                fused = reciprocal_rank_fusion(dense_docs, sparse_docs, top_n=top_k)
                if fused:
                    if q_emb is not None:
                        self._cache.append((q_emb, query_norm, fused))
                        if len(self._cache) > self.max_cache_entries:
                            self._cache.pop(0)  # bound memory usage
                    return fused, "hybrid"
            except Exception as e:
                print(f"[RAG] Retrieval error: {e}")

        return [], "fallback"

    def format_context(self, docs: List[Document], max_chars_per_doc: int = 600) -> str:
        """
        Formats retrieved documents into a string context for the LLM.
        Caps each chunk's contribution so 5 retrieved docs don't balloon
        the prompt — the chunker already produces ~1000-char chunks, this
        trims to the most relevant leading portion of each.
        """
        if not docs:
            return "No relevant legal context found."

        context_parts = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "Unknown")
            content = doc.page_content[:max_chars_per_doc]
            context_parts.append(f"[Source {i}: {source}]\n{content}")
        return "\n\n---\n\n".join(context_parts)


retriever = HybridRetriever()