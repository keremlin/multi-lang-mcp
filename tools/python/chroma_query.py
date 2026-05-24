import sys
import json
import os


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"success": False, "error": "No input provided on stdin"}))
        sys.exit(1)

    try:
        params = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"success": False, "error": f"Invalid JSON: {exc}"}))
        sys.exit(1)

    collection_name = params.get("collection")
    query_text = params.get("query_text")
    n_results = int(params.get("n_results", 5))
    where = params.get("where")

    if not collection_name:
        print(json.dumps({"success": False, "error": "Missing required field: collection"}))
        sys.exit(1)
    if not query_text:
        print(json.dumps({"success": False, "error": "Missing required field: query_text"}))
        sys.exit(1)

    try:
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

        host = os.getenv("CHROMA_HOST", "127.0.0.1")
        port = int(os.getenv("CHROMA_PORT", "8001"))
        model = os.getenv("CHROMA_EMBEDDING_MODEL", "all-MiniLM-L6-v2")

        client = chromadb.HttpClient(host=host, port=port)
        ef = SentenceTransformerEmbeddingFunction(model_name=model)
        collection = client.get_collection(name=collection_name, embedding_function=ef)

        query_kwargs = {
            "query_texts": [query_text],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            query_kwargs["where"] = where

        results = collection.query(**query_kwargs)

        hits = []
        for i, doc_id in enumerate(results["ids"][0]):
            hits.append({
                "id": doc_id,
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })

        print(json.dumps({
            "success": True,
            "data": {"collection": collection_name, "query": query_text, "results": hits},
        }))
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
