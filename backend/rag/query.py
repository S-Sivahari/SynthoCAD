import json
from .db import get_collection

def query_cad_templates(prompt: str, n_results: int = 3):
    """
    Queries the vector store for CAD templates matching the prompt.
    
    Args:
        prompt: Natural language description (e.g., "A simple table").
        n_results: Number of matches to return (default: 3).
        
    Returns:
        List of dicts containing:
        - "description": The stored description.
        - "json": The parsed CAD JSON.
        - "json_path": Path to the JSON file.
        - "similarity": Similarity score (implicitly, as results are ranked).
    """
    collection = get_collection()
    
    results = collection.query(
        query_texts=[prompt],
        n_results=n_results
    )
    
    # Process results into a cleaner list
    output = []
    
    if not results or not results['ids']:
        return []
        
    for i in range(len(results['ids'][0])):
        desc = results['documents'][0][i]
        meta = results['metadatas'][0][i]
        
        # Load JSON content
        # It's stored as a string in metadata
        json_str = meta.get('json_content', '{}')
        
        # In case it's not stored or empty, try loading from path if available (fallback)
        if not json_str or json_str == '{}':
             path = meta.get('source_json_path')
             if path:
                 try:
                     with open(path, 'r') as f:
                         json_str = f.read()
                 except: pass

        try:
            parsed_json = json.loads(json_str)
        except:
            parsed_json = {}
            
        output.append({
            "description": desc,
            "json": parsed_json,
            "json_path": meta.get('source_json_path', ''),
            "id": results['ids'][0][i]
        })
        
    return output

if __name__ == "__main__":
    import argparse
    import sys
    
    # Add project root to path for relative imports if run as script
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    
    parser = argparse.ArgumentParser(description="Query CAD Templates RAG")
    parser.add_argument("prompt", help="Description of the object")
    parser.add_argument("--n", type=int, default=1, help="Number of results")
    
    args = parser.parse_args()
    
    matches = query_cad_templates(args.prompt, n_results=args.n)
    
    print(f"\n--- Results for '{args.prompt}' ---")
    if not matches:
        print("No matches found. (Make sure you've run ingest.py first!)")
    
    for m in matches:
        print(f"\n[Match ID: {m['id']}]")
        print(f"Found via Description: {m['description']}")
        print(f"JSON Path: {m['json_path']}")
        # print(f"JSON Preview: {json.dumps(m['json'], indent=2)[:200]}...")
