import os
import re
from pathlib import Path
from typing import List, Tuple

from langchain_community.document_loaders import PyPDFLoader, TextLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings

# ── SMART Path Resolution ─────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

# FIXED: Automatically checks the parent directory if 'data' isn't found here.
# This bypasses the "double folder" issue when extracting zips or cloning.
if not DATA_DIR.exists():
    parent_data = BASE_DIR.parent / "data"
    if parent_data.exists():
        print(f"[RAG] Found 'data' folder in parent directory. Using: {parent_data}")
        DATA_DIR = parent_data
    else:
        print(f"[RAG] WARNING: 'data' folder not found in {BASE_DIR} or {BASE_DIR.parent}!")
        print(f"[RAG] Please ensure your 8 PDFs are inside a folder named 'data'.")

CHROMA_DIR = BASE_DIR / "chroma_db"
COLLECTION_NAME = "indian_law"

# FIXED: Add google_api_key parameter and use updated model
EMBEDDINGS = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    google_api_key=os.getenv("GOOGLE_API_KEY")
)
EMBED_PROVIDER = "google"

# FIXED: Added missing load_documents function
def load_documents() -> List[Document]:
    """Loads PDF and TXT documents from the data directory."""
    if not DATA_DIR.exists():
        print(f"[RAG] Data directory '{DATA_DIR}' not found.")
        return []
    
    pdf_loader = DirectoryLoader(DATA_DIR, glob="**/*.pdf", loader_cls=PyPDFLoader)
    text_loader = DirectoryLoader(DATA_DIR, glob="**/*.txt", loader_cls=TextLoader)
    
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

# FIXED: Added missing chunk_documents function
def chunk_documents(docs: List[Document]) -> List[Document]:
    """Splits documents into smaller chunks for embedding."""
    if not docs:
        return []
    
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )
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
            embedding_function=EMBEDDINGS
        )
    else:
        print("[RAG] Building ChromaDB from chunks...")
        store = Chroma.from_documents(chunks, EMBEDDINGS, **kwargs)

    return store

def reciprocal_rank_fusion(
    dense_docs: List[Document],
    sparse_docs: List[Document],
    top_n: int = 5,
    k: int = 60
) -> List[Document]:
    """Merges dense and sparse retrieval results using Reciprocal Rank Fusion (RRF)."""
    fused_scores = {}
    doc_map = {}

    for rank, doc in enumerate(dense_docs):
        doc_id = doc.metadata.get("source", "") + str(doc.page_content[:50])
        if doc_id not in fused_scores:
            fused_scores[doc_id] = 0
            doc_map[doc_id] = doc
        fused_scores[doc_id] += 1 / (rank + k)

    for rank, doc in enumerate(sparse_docs):
        doc_id = doc.metadata.get("source", "") + str(doc.page_content[:50])
        if doc_id not in fused_scores:
            fused_scores[doc_id] = 0
            doc_map[doc_id] = doc
        fused_scores[doc_id] += 1 / (rank + k)

    sorted_docs = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
    return [doc_map[doc_id] for doc_id, score in sorted_docs[:top_n]]

class HybridRetriever:
    """Manages the Hybrid RAG pipeline (Dense + BM25 + RRF)."""

    def __init__(self):
        self._vectorstore = None
        self._bm25 = None
        self._initialized = False
        self._cache = {}

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

    def retrieve(self, query: str, top_k: int = 5) -> Tuple[List[Document], str]:
        """Retrieves documents using semantic cache, hybrid search, or fallback."""
        self.initialize()

        cache_key = query.strip().lower()
        if cache_key in self._cache:
            return self._cache[cache_key], "cache"

        if self._vectorstore and self._bm25:
            try:
                dense_docs = self._vectorstore.similarity_search(query, k=8)
                sparse_docs = self._bm25.invoke(query)

                fused = reciprocal_rank_fusion(dense_docs, sparse_docs, top_n=top_k)
                if fused:
                    self._cache[cache_key] = fused
                    return fused, "hybrid"
            except Exception as e:
                print(f"[RAG] Retrieval error: {e}")

        return [], "fallback"

    def format_context(self, docs: List[Document]) -> str:
        """Formats retrieved documents into a string context for the LLM."""
        if not docs:
            return "No relevant legal context found."

        context_parts = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "Unknown")
            context_parts.append(f"[Source {i}: {source}]\n{doc.page_content}")

        return "\n\n---\n\n".join(context_parts)

retriever = HybridRetriever()