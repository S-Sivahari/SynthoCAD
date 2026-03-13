import json
from .db import get_collection


def query_cad_templates(prompt: str, n_results: int = 3) -> list[dict]:
    """Query ChromaDB for CAD templates matching *prompt*.

    Returns a list of dicts with keys:
        - ``description``  � the embedded text document
        - ``json``         � parsed SCL JSON (dict)
        - ``json_path``    � absolute path to the source JSON file
        - ``image_path``   � absolute path to the paired PNG (may be empty)
        - ``id``           � ChromaDB document ID  (batch_X_NNNNN)
    """
    collection = get_collection()

    if collection.count() == 0:
        return []

    results = collection.query(
        query_texts=[prompt],
        n_results=min(n_results, collection.count()),
    )

    if not results:
        return []

    ids_inner  = (results.get("ids")       or [[]])[0]
    meta_inner = (results.get("metadatas") or [[]])[0]
    docs_inner = (results.get("documents") or [[]])[0]

    if not ids_inner:
        return []

    output: list[dict] = []
    for i, doc_id in enumerate(ids_inner):
        meta     = (meta_inner[i] if i < len(meta_inner) else None) or {}
        json_str = meta.get("json_content", "{}")

        try:
            parsed = json.loads(json_str)
        except Exception:
            parsed = {}

        output.append({
            "description": docs_inner[i] if i < len(docs_inner) else "",
            "json":        parsed,
            "json_path":   meta.get("json_path", ""),
            "image_path":  meta.get("image_path", ""),
            "cadquery":    meta.get("cadquery", ""),
            "id":          doc_id,
        })

    return output


if __name__ == "__main__":
    import argparse, sys, os

    # Allow running as script from any directory
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    parser = argparse.ArgumentParser(description="Query the SynthoCAD RAG store")
    parser.add_argument("prompt", help="Natural-language description, e.g. 'hex bolt M8'")
    parser.add_argument("--n", type=int, default=3, help="Number of results (default: 3)")
    args = parser.parse_args()

    matches = query_cad_templates(args.prompt, n_results=args.n)

    print(f"\n=== Results for: {args.prompt!r} ===")
    if not matches:
        print("No matches. Run python -m rag.ingest to populate the database first.")
        sys.exit(0)

    for m in matches:
        print(f"\n[{m['id']}]")
        print(f"  Description : {m['description']}")
        print(f"  JSON path   : {m['json_path']}")
        if m["image_path"]:
            print(f"  Image       : {m['image_path']}")
