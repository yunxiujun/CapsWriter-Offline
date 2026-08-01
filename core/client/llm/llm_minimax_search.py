"""MiniMax Token Plan web search integration."""
import json
from typing import Any, Dict, List
from urllib import error, request


DEFAULT_SEARCH_ENDPOINT = "https://api.minimaxi.com/v1/coding_plan/search"
CONTROL_OPTION_KEYS = {
    "minimax_web_search",
    "minimax_search_endpoint",
    "minimax_search_max_results",
    "minimax_search_query_max_length",
    "minimax_search_timeout",
}


def prepare_messages(
    messages: List[Dict[str, Any]],
    api_key: str,
    options: Dict[str, Any],
    prompt_prefix_input: str = "",
) -> List[Dict[str, Any]]:
    """Search MiniMax and inject the results before the latest user message."""
    if not options.get("minimax_web_search"):
        return messages
    if not api_key:
        raise RuntimeError("MiniMax Web Search requires an API key")

    query = _extract_query(messages, prompt_prefix_input)
    max_query_length = _bounded_int(
        options.get("minimax_search_query_max_length", 1000), 100, 5000
    )
    query = query[:max_query_length].strip()
    if not query:
        raise RuntimeError("MiniMax Web Search query is empty")

    endpoint = str(
        options.get("minimax_search_endpoint") or DEFAULT_SEARCH_ENDPOINT
    ).strip()
    timeout = _bounded_float(options.get("minimax_search_timeout", 20), 1, 60)
    max_results = _bounded_int(options.get("minimax_search_max_results", 8), 1, 20)
    results = _search(endpoint, api_key, query, timeout)[:max_results]
    if not results:
        raise RuntimeError("MiniMax Web Search returned no usable results")

    search_context = _format_results(results)
    search_message = {
        "role": "system",
        "content": (
            "以下是 MiniMax Web Search 返回的实时搜索结果。回答必须以这些结果为依据，"
            "不得编造事实或网址；引用来源时使用 [标题](URL) 格式。\n\n"
            f"{search_context}"
        ),
    }

    prepared = [dict(message) for message in messages]
    insert_at = len(prepared)
    for index in range(len(prepared) - 1, -1, -1):
        if prepared[index].get("role") == "user":
            insert_at = index
            break
    prepared.insert(insert_at, search_message)
    return prepared


def model_options(options: Dict[str, Any]) -> Dict[str, Any]:
    """Remove CapsWriter-only search controls before calling the model API."""
    return {
        key: value
        for key, value in options.items()
        if key not in CONTROL_OPTION_KEYS
    }


def _extract_query(messages: List[Dict[str, Any]], prompt_prefix_input: str) -> str:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content", "")
        if isinstance(content, list):
            content = "\n".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
        text = str(content)
        if prompt_prefix_input and prompt_prefix_input in text:
            text = text.rsplit(prompt_prefix_input, 1)[-1]
        return text.strip()
    return ""


def _search(
    endpoint: str,
    api_key: str,
    query: str,
    timeout: float,
) -> List[Dict[str, str]]:
    payload = json.dumps({"q": query}, ensure_ascii=False).encode("utf-8")
    search_request = request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "CapsWriter-Offline/1.0",
        },
    )
    try:
        with request.urlopen(search_request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raise RuntimeError(f"MiniMax Web Search HTTP {exc.code}") from exc
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"MiniMax Web Search request failed: {exc}") from exc

    base_resp = data.get("base_resp") or {}
    status_code = base_resp.get("status_code")
    if status_code not in (None, 0, "0"):
        status_msg = base_resp.get("status_msg") or "unknown error"
        raise RuntimeError(
            f"MiniMax Web Search failed ({status_code}): {status_msg}"
        )

    results = []
    for item in data.get("organic") or []:
        url = str(item.get("link") or "").strip()
        title = str(item.get("title") or "").strip()
        if not title or not url.startswith(("http://", "https://")):
            continue
        results.append(
            {
                "title": title,
                "url": url,
                "snippet": str(item.get("snippet") or "").strip()[:800],
                "date": str(item.get("date") or "").strip(),
            }
        )
    return results


def _format_results(results: List[Dict[str, str]]) -> str:
    blocks = []
    for index, item in enumerate(results, 1):
        lines = [f"[{index}] {item['title']}", f"URL: {item['url']}"]
        if item["date"]:
            lines.append(f"日期: {item['date']}")
        if item["snippet"]:
            lines.append(f"摘要: {item['snippet']}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return minimum


def _bounded_float(value: Any, minimum: float, maximum: float) -> float:
    try:
        return max(minimum, min(maximum, float(value)))
    except (TypeError, ValueError):
        return minimum
