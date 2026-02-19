import requests
from typing import Dict, Any, Optional


def sync_call_with_continuation(
    endpoint_url: str,
    headers: Dict[str, str],
    request_body: Dict[str, Any],
    original_prompt: str,
    timeout: int = 180,
    max_continuations: int = 3,
) -> str:
    accumulated_text = ""

    for attempt in range(max_continuations + 1):
        if attempt > 0:
            continuation_prompt = (
                f"{original_prompt}\n\n"
                f"[CONTINUATION] The previous response was cut off. Here is what was generated so far:\n"
                f"---\n{accumulated_text[-2000:]}\n---\n"
                f"Please continue from where you left off. Do not repeat what was already generated."
            )
            request_body = {**request_body, "prompt": continuation_prompt}

        response = requests.post(
            endpoint_url,
            json=request_body,
            headers=headers,
            timeout=timeout,
        )

        if response.status_code != 200:
            raise ValueError(f"PwC GenAI API Error: {response.status_code} - {response.text}")

        result = response.json()
        chunk = _extract_text(result)
        accumulated_text += chunk

        finish_reason = _get_finish_reason(result)
        if finish_reason != "length":
            break

    return accumulated_text


def _extract_text(result: Dict[str, Any]) -> str:
    if "choices" in result and len(result["choices"]) > 0:
        choice = result["choices"][0]
        if "message" in choice and "content" in choice["message"]:
            return choice["message"]["content"]
        if "text" in choice:
            return choice["text"]
    if "text" in result:
        return result["text"]
    if "content" in result:
        return result["content"]
    return ""


def _get_finish_reason(result: Dict[str, Any]) -> Optional[str]:
    if "choices" in result and len(result["choices"]) > 0:
        return result["choices"][0].get("finish_reason", "stop")
    return "stop"
