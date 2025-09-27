import asyncio
from app.connectorhub.github_connector import GitHubConnector

ACCESS_TOKEN = "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"  # Put your GitHub token here


async def test_connector():
    connector = GitHubConnector(ACCESS_TOKEN)

    print("🔍 Testing search_corpus...")
    results = await connector.search_corpus("README")
    if not results:
        print("[ERROR] No results found")
        return

    print(f"✅ Found {len(results)} results")
    for result in results[:3]:
        print(result)

    first_doc = results[0]
    print("\n📄 Testing fetch_doc...")
    doc = await connector.fetch_doc(first_doc.get("last_modified"))
    if doc:
        print(f"✅ Fetched document path: {doc.get('path')}")
        print(f"Content snippet: {doc.get('content')[:200]}...")
    else:
        print("[ERROR] Failed to fetch document")

    print("\n🔑 Testing check_access...")
    has_access = await connector.check_access(first_doc.get("owner"))
    print(f"Access granted: {has_access}")


if __name__ == "__main__":
    asyncio.run(test_connector())
