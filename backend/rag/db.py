import os
import chromadb
from chromadb.utils import embedding_functions

# Path for persistent storage (relative to backend/)
CHROMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chroma_db")
COLLECTION_NAME = "cad_templates"

def get_chroma_client():
    """Returns a persistent ChromaDB client."""
    os.makedirs(CHROMA_PATH, exist_ok=True)
    return chromadb.PersistentClient(path=CHROMA_PATH)

def get_collection():
    """Returns the main CAD templates collection with default embedding function."""
    client = get_chroma_client()
    
    # Use standard Sentence Transformer model for embeddings
    # This automatically downloads and runs the model locally
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef
    )
