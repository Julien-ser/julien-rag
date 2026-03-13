"""
Usage examples for Julien RAG SDK.

This script demonstrates how to use the RAGClient for various operations:
- Basic vector search
- RAG query with answer generation
- Database statistics
- Health checks
"""

import os
from dotenv import load_dotenv
from julien_rag import RAGClient, RAGAPIError

# Load environment variables (optional)
load_dotenv()


def main():
    """Run example usage."""
    # Configuration
    API_BASE_URL = os.getenv("RAG_API_URL", "http://localhost:8000")
    API_KEY = os.getenv("RAG_API_KEY")  # Optional
    ADMIN_TOKEN = os.getenv("RAG_ADMIN_TOKEN")  # Optional, for admin operations

    print("=" * 60)
    print("Julien RAG SDK Usage Examples")
    print("=" * 60)

    # Initialize client
    print("\n1. Initializing client...")
    client = RAGClient(
        base_url=API_BASE_URL,
        api_key=API_KEY,
        admin_token=ADMIN_TOKEN,
    )
    print(f"   Connected to: {API_BASE_URL}")

    try:
        # Health check
        print("\n2. Checking API health...")
        health = client.health_check()
        print(f"   Status: {health.status}")
        print(f"   Time: {health.timestamp}")

        # Get statistics
        print("\n3. Getting database statistics...")
        stats = client.get_stats()
        print(f"   Database status: {stats.status}")
        print(f"   Collections:")
        for coll_name, coll_stats in stats.collections.items():
            count = coll_stats.get("document_count", 0)
            print(f"     - {coll_name}: {count} documents")

        # List sources
        print("\n4. Listing available sources...")
        sources = client.get_sources()
        print(f"   Available sources ({sources.count}):")
        for src in sources.sources:
            print(f"     - {src}")

        # Basic search
        print("\n5. Performing vector search...")
        query = "machine learning project"
        print(f"   Query: '{query}'")
        search_result = client.search(query=query, k=5)

        print(
            f"   Found {search_result.total_results} results in {search_result.query_time:.3f}s"
        )
        print("   Top results:")
        for i, (doc, meta, score) in enumerate(
            zip(
                search_result.documents[:3],
                search_result.metadatas[:3],
                search_result.scores[:3],
            ),
            1,
        ):
            title = meta.get("title", "Untitled")
            source = meta.get("source", "unknown")
            print(f"     {i}. [{score:.3f}] {title} ({source})")
            print(f"        Preview: {doc[:100]}...")

        # RAG query with answer generation
        print("\n6. Performing RAG query (with LLM generation)...")
        rag_query = "What are the main technologies used in this project?"
        print(f"   Query: '{rag_query}'")
        rag_result = client.rag_query(
            query=rag_query,
            k=5,
            return_context=True,  # Include context in response for demonstration
            temperature=0.7,
        )

        print(
            f"   Answer (confidence: {rag_result.confidence:.3f}, time: {rag_result.query_time:.3f}s):"
        )
        print(f"   {'-' * 50}")
        print(f"   {rag_result.answer}")
        print(f"   {'-' * 50}")
        print(f"   Sources ({len(rag_result.sources)}):")
        for src in rag_result.sources:
            print(
                f"     - {src.get('title', 'Untitled')} ({src.get('source', 'unknown')})"
            )
            if src.get("url"):
                print(f"       {src['url']}")

        # Search with filters
        print("\n7. Search with metadata filters...")
        filtered_query = "python"
        filters = {"source": "github_repos"}
        print(f"   Query: '{filtered_query}'")
        print(f"   Filter: {filters}")
        filtered_result = client.search(query=filtered_query, k=3, filters=filters)
        print(f"   Found {filtered_result.total_results} results")

        # Collection-specific search
        print("\n8. Collection-specific search...")
        collection_query = "deployment"
        print(f"   Query: '{collection_query}'")
        print(f"   Collection: 'web_content'")
        collection_result = client.search(
            query=collection_query, k=3, collection="web_content"
        )
        print(f"   Found {collection_result.total_results} results")

        # Optional: Admin refresh (requires ADMIN_TOKEN set)
        if client.admin_token:
            print("\n9. Triggering data refresh (admin)...")
            try:
                refresh_result = client.refresh()
                status = refresh_result.get("status", "unknown")
                message = refresh_result.get("message", "No message")
                print(f"   Status: {status}")
                print(f"   Message: {message}")
                if "stats" in refresh_result:
                    stats = refresh_result["stats"]
                    print(f"   Stats: {stats}")
            except Exception as e:
                print(f"   Refresh failed: {e}")
        else:
            print("\n9. Skipping admin refresh (no ADMIN_TOKEN set)")

        print("\n" + "=" * 60)
        print("Examples completed successfully!")
        print("=" * 60)

    except RAGAPIError as e:
        print(f"\n❌ API Error: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    exit(main())
