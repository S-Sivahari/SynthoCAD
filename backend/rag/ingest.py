import os
import glob
import json
import uuid
from tqdm import tqdm
from .db import get_collection

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESC_DIR = os.path.join(BASE_DIR, "scripts", "local_descriptions")
BATCH_DIR = os.path.join(BASE_DIR, "scripts", "batches")

def ingest_data():
    """Ingests generated descriptions and CAD JSONs into ChromaDB."""
    collection = get_collection()
    
    # 1. Gather all description files
    print(f"Scanning for descriptions in {DESC_DIR}...")
    desc_files = glob.glob(os.path.join(DESC_DIR, "**", "*.txt"), recursive=True)
    
    if not desc_files:
        print("No description files found! Run local_cpu_                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                first.")
        return

    print(f"Found {len(desc_files)} descriptions. Starting ingestion...")
    
    ids = []
    documents = []
    metadatas = []
    
    for desc_path in tqdm(desc_files):
        try:
            # 2. Read Description
            with open(desc_path, "r", encoding="utf-8") as f:
                description = f.read().strip()
            
            if not description: continue
            
            # 3. Find matching JSON
            # Structure: .../local_descriptions/batch_X/file.txt
            # JSON:      .../batches/batch_X/file.json
            
            relative_path = os.path.relpath(desc_path, DESC_DIR) # e.g. batch_0\00000007.txt
            # Extract batch and filename
            parts = relative_path.split(os.sep)
            if len(parts) < 2: continue
            
            batch_name = parts[-2]
            filename = parts[-1]
            base_name = os.path.splitext(filename)[0]
            
            json_path = os.path.join(BATCH_DIR, batch_name, f"{base_name}.json")
            
            if not os.path.exists(json_path):
                print(f"Warning: JSON not found for {base_name}")
                continue
                
            with open(json_path, "r", encoding="utf-8") as f:
                json_content = f.read() # Read as string to store in metadata
            
            # 4. Prepare for Chroma
            # ID: Use the filename (unique across batches technically, but best to include batch name)
            doc_id = f"{batch_name}_{base_name}"
            
            ids.append(doc_id)
            documents.append(description)
            metadatas.append({
                "source_json_path": json_path,
                "batch": batch_name,
                "json_content": json_content,
                "filename": filename
            })
            
            # Ingest in chunks of 100 to avoid memory issues
            if len(ids) >= 100:
                collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
                ids = []
                documents = []
                metadatas = []
                
        except Exception as e:
            print(f"Error processing {desc_path}: {e}")

    # Final batch
    if ids:
         collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
         
    print(f"Ingestion complete. Total items in DB: {collection.count()}")

if __name__ == "__main__":
    ingest_data()
