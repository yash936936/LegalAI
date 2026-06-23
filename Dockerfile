FROM python:3.12-slim

WORKDIR /app

# System deps for ChromaDB + sentence-transformers
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Chroma SQLite fix
RUN pip install pysqlite3-binary

COPY . /app

# Create persistent volume dirs
RUN mkdir -p /app/data /app/chroma_db

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]