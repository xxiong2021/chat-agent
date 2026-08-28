import os

from dotenv import load_dotenv
from tavily import TavilyClient


load_dotenv()

api_key = os.getenv("TAVILY_API_KEY")

if not api_key:
    raise RuntimeError(
        "没有找到 TAVILY_API_KEY，请检查 .env 文件"
    )

client = TavilyClient(api_key=api_key)


def web_search(query: str, max_results: int = 5) -> str:
    """
    搜索互联网，并返回标题、来源、URL、发布时间和摘要。
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

    if not results:
        return "没有找到相关搜索结果。"

    output = []

    for i, result in enumerate(results, start=1):

        title = result.get("title", "")
        url = result.get("url", "")
        content = result.get("content", "")
        published_date = result.get(
            "published_date",
            "未知"
        )

        output.append(
            f"""
结果 {i}

标题：
{title}

发布时间：
{published_date}

URL：
{url}

摘要：
{content}
""".strip()
        )

    return "\n\n".join(output)
