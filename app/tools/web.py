import os

from dotenv import load_dotenv
from tavily import TavilyClient


load_dotenv()

api_key = os.getenv("TAVILY_API_KEY")

if not api_key:
    raise RuntimeError(
        "娌℃湁鎵惧埌 TAVILY_API_KEY锛岃妫€鏌?.env 鏂囦欢"
    )

client = TavilyClient(api_key=api_key)


def web_search(query: str, max_results: int = 5) -> dict:
    """
    鎼滅储浜掕仈缃戯紝骞惰繑鍥炵粨鏋勫寲鎼滅储缁撴灉銆?
    """

    response = client.search(
        query=query,
        search_depth="advanced",
        max_results=max_results,
        include_answer=False,
        include_raw_content=False,
        topic="news",
    )

    results = response.get("results", [])

    return {
        "query": query,
        "results": [
            {
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "published_date": result.get("published_date"),
                "content": result.get("content", ""),
            }
            for result in results
        ],
    }
