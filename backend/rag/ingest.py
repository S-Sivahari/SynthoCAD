import os
import glob
import json
from tqdm import tqdm
from .db import get_collection

# Batches live inside the rag/ package itself
RAG_DIR    = os.path.dirname(os.path.abspath(__file__))
BATCH_DIR  = os.path.join(RAG_DIR, "batches")
# Parquet files sit at the project root (two dirs above rag/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(RAG_DIR))
PARQUET_FILES = [
    os.path.join(PROJECT_ROOT, "train-00000-of-00002.parquet"),
    os.path.join(PROJECT_ROOT, "train-00001-of-00002.parquet"),
]


# ── Parquet index ─────────────────────────────────────────────────────────

def _load_parquet_index() -> dict[str, str]:
    """Build a dict mapping 8-digit stem -> cadquery code string.

    deepcad_id looks like '0000/00006371'; the stem is the last segment.
    Only the two ``cadquery`` and ``deepcad_id`` columns are read to keep
    memory usage low even for ~150 k rows.
    """
    index: dict[str, str] = {}
    try:
        import pyarrow.parquet as pq
    except ImportError:
        print("  [warn] pyarrow not installed — cadquery column will be skipped")
        return index

    for pq_path in PARQUET_FILES:
        if not os.path.exists(pq_path):
            print(f"  [warn] Parquet not found: {pq_path}")
            continue
        print(f"  Loading parquet index from {os.path.basename(pq_path)}...")
        table = pq.read_table(pq_path, columns=["deepcad_id", "cadquery"])
        for did, cq in zip(
            table.column("deepcad_id").to_pylist(),
            table.column("cadquery").to_pylist(),
        ):
            if did and cq:
                stem = did.split("/")[-1]   # '0000/00006371' -> '00006371'
                index[stem] = cq
        print(f"    {len(index)} entries loaded so far")

    return index


# -- Embedding-document builder -------------------------------------------

def _build_doc(json_data: dict, cadquery: str = "") -> str:
    """Convert an SCL JSON (+ optional CadQuery code) into a compact,
    semantically-rich text string suitable for embedding.  Uses:
      - description.shape  (when non-empty)
      - sketch primitive counts (lines / arcs / circles)
      - operation type (extrude vs revolve)
      - bounding dimensions from the description block
      - boolean final_shape
      - first comment line(s) from the CadQuery code (when available)
    """
    parts       = json_data.get("parts") or {}
    n_parts     = len(parts)
    final_shape = (json_data.get("final_shape") or "").strip()

    tokens = [f"{n_parts}-part model"]

    for part_name, part in parts.items():
        sketch     = part.get("sketch") or {}
        extrusion  = part.get("extrusion") or {}
        revolution = part.get("revolution") or {}
        desc_blk   = part.get("description") or {}

        # named shape hint
        shape_name = (desc_blk.get("shape") or "").strip()

        # primitive counts
        lines = arcs = circles = 0
        for face in sketch.values():
            if not isinstance(face, dict):
                continue
            for loop in face.values():
                if not isinstance(loop, dict):
                    continue
                for prim_name in loop:
                    p = prim_name.lower()
                    if "line"     in p: lines   += 1
                    elif "arc"    in p: arcs    += 1
                    elif "circle" in p: circles += 1

        prim_parts = []
        if lines:   prim_parts.append(f"{lines} lines")
        if arcs:    prim_parts.append(f"{arcs} arcs")
        if circles: prim_parts.append(f"{circles} circles")
        prim_str = ", ".join(prim_parts) or "no primitives"

        # operation
        op_tokens = []
        if extrusion:
            depth = (
                (extrusion.get("extrude_depth_towards_normal") or 0.0) +
                (extrusion.get("extrude_depth_opposite_normal") or 0.0)
            )
            scale = extrusion.get("sketch_scale") or 1.0
            L = desc_blk.get("length", scale)
            W = desc_blk.get("width",  scale)
            H = desc_blk.get("height", depth)
            op_tokens.append(f"extruded {L:.3f}x{W:.3f}x{H:.3f}")
        if revolution:
            angle = revolution.get("revolve_angle", 360)
            op_tokens.append(f"revolved {angle} deg")
        op_str = ", ".join(op_tokens) or "no-op"

        part_desc = f"{part_name}: "
        if shape_name:
            part_desc += f"{shape_name}, "
        part_desc += f"sketch({prim_str}), {op_str}"
        tokens.append(part_desc)

    if final_shape:
        tokens.append(f"boolean: {final_shape}")

    # Append first meaningful comment from CadQuery code as a semantic hint
    if cadquery:
        for line in cadquery.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") and len(stripped) > 2:
                tokens.append(stripped)
                break

    return "; ".join(tokens)


# -- Ingestion ------------------------------------------------------------

def ingest_data(batch_limit: int | None = None, chunk_size: int = 200):
    """Ingest all batch JSONs from rag/batches/ into ChromaDB.

    Args:
        batch_limit:  If set, only process the first N batches (useful for
                      quick smoke-tests, e.g. ``ingest_data(batch_limit=5)``).
        chunk_size:   Number of documents to upsert in one call.
    """
    collection   = get_collection()
    cq_index     = _load_parquet_index()   # stem -> cadquery code
    cq_hits      = 0

    json_files = sorted(
        glob.glob(os.path.join(BATCH_DIR, "**", "*.json"), recursive=True)
    )

    if not json_files:
        print(f"No JSON files found under {BATCH_DIR}")
        return

    if batch_limit is not None:
        seen_batches: set[str] = set()
        filtered: list[str] = []
        for path in json_files:
            batch_name = os.path.basename(os.path.dirname(path))
            if batch_name not in seen_batches:
                if len(seen_batches) >= batch_limit:
                    break
                seen_batches.add(batch_name)
            filtered.append(path)
        json_files = filtered

    print(f"Ingesting {len(json_files)} JSON files from {BATCH_DIR}...")

    ids:       list[str]  = []
    documents: list[str]  = []
    metadatas: list[dict] = []
    skipped = 0

    for json_path in tqdm(json_files, unit="file"):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                raw = f.read()
            json_data = json.loads(raw)
        except Exception as e:
            print(f"  Skip (parse error) {json_path}: {e}")
            skipped += 1
            continue

        batch_name = os.path.basename(os.path.dirname(json_path))
        stem       = os.path.splitext(os.path.basename(json_path))[0]
        doc_id     = f"{batch_name}_{stem}"
        png_path   = os.path.splitext(json_path)[0] + ".png"
        cadquery   = cq_index.get(stem, "")
        if cadquery:
            cq_hits += 1

        doc = _build_doc(json_data, cadquery=cadquery)

        ids.append(doc_id)
        documents.append(doc)
        metadatas.append({
            "batch":        batch_name,
            "stem":         stem,
            "json_path":    json_path,
            "image_path":   png_path if os.path.exists(png_path) else "",
            "json_content": raw,
            "cadquery":     cadquery,
        })

        if len(ids) >= chunk_size:
            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            ids, documents, metadatas = [], [], []

    if ids:
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    total = collection.count()
    print(f"Done. Skipped {skipped}. CadQuery matched: {cq_hits}. Total items in DB: {total}")


if __name__ == "__main__":
    ingest_data()
