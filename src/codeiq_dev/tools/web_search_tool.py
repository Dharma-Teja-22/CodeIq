from ddgs import DDGS
import requests
from codeiq_dev.core.settings import JINA_API_KEY
import truststore
truststore.inject_into_ssl()

def DDGSearch(query: str):
    """
    Perform a web search using DuckDuckGo and return top 3 search results.

    Args:
        query (str): The search query or terms to look up.

    Returns:
        list: List of up to 3 search result dicts (title, href, body) or empty list.
    """
    if not query:
        return []
    try:
        results = DDGS().text(query, max_results=3)
        if not results:
            return []
        
        # Keep only the top 3 results and extract essential fields
        trimmed_results = []
        for r in results[:3]:
            trimmed_results.append({
                "title": r.get("title", ""),
                "href": r.get("href", ""),
                "body": r.get("body", "")[:500], # Keep concise snippet
            })
        return trimmed_results
    except Exception as e:
        return [{"error": f"DuckDuckGo search failed: {str(e)}"}]


def read_url(target_url: str):
    """
    Read a webpage and convert its content into clean markdown using Jina AI Reader.

    Args:
        target_url (str): The web page URL to fetch.

    Returns:
        str: Markdown content of the webpage or an error message.
    """
    try:
        headers = {
            "Authorization": f"Bearer {JINA_API_KEY}",
            "Accept": "application/json"
        }
        reader_url = f"https://r.jina.ai/{target_url}"
        response = requests.get(reader_url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        # Return the clean markdown content or fallback to full response
        content = data.get("data", {}).get("content") or data.get("content") or str(data)
        # Limit size to prevent blowing context window (e.g. ~1000 chars)
        if len(content) > 1000:
            return content[:1000] + "\n... [Webpage content truncated]"
        return content
    except Exception as e:
        return f"Failed to fetch webpage content via Jina Reader: {str(e)}"
