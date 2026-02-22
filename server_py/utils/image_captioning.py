"""Image captioning utility using PwC GenAI Vision LLM.

Sends extracted document images to vertex_ai.gemini-2.5-flash-image
for descriptive captions that become part of the knowledge base content.
"""

import asyncio
from typing import List, Optional, Callable
from utils.doc_parsing import ExtractedImage, ParsedContent
from utils.pwc_llm import call_pwc_genai_async
from core.logging import log_info, log_error


CAPTIONING_PROMPT = """You are analyzing an image extracted from a business document. 
Provide a detailed, factual description of what this image shows. Include:
- Any text, labels, or data visible in the image
- Charts, diagrams, or graphs: describe the type, axes, trends, and key data points
- Architecture diagrams: describe components, connections, and flow
- Screenshots: describe the UI elements, layout, and visible content
- Tables: describe the structure and key data
- Photos: describe the subject and relevant details

Be concise but thorough. Focus on information that would be useful for understanding business requirements and technical documentation.
Do NOT start with "This image shows" - just describe the content directly."""


async def caption_single_image(
    image: ExtractedImage,
    index: int,
    total: int,
) -> Optional[str]:
    try:
        context = f"This image is from {image.source_type} {image.source_page + 1} of a document."
        prompt = f"{context}\n\n{CAPTIONING_PROMPT}"

        response = await call_pwc_genai_async(
            prompt=prompt,
            task_name="kb_image_captioning",
            images=[image.image_bytes],
        )

        if response and response.strip():
            log_info(
                f"Captioned image {index + 1}/{total} ({image.source_type} {image.source_page + 1}): {len(response)} chars",
                "captioning"
            )
            return response.strip()

        log_error(f"Empty caption for image {index + 1}/{total}", "captioning")
        return None

    except Exception as e:
        log_error(f"Error captioning image {index + 1}/{total}: {e}", "captioning")
        return None


async def caption_document_images(
    parsed: ParsedContent,
    on_progress: Optional[Callable[[str, str], None]] = None,
    max_concurrent: int = 3,
) -> ParsedContent:
    if not parsed.images:
        return parsed

    total = len(parsed.images)
    if on_progress:
        on_progress("captioning", f"Captioning {total} extracted images with Vision AI...")

    log_info(f"Starting captioning of {total} images", "captioning")

    semaphore = asyncio.Semaphore(max_concurrent)
    completed = 0

    async def caption_with_semaphore(img: ExtractedImage, idx: int) -> None:
        nonlocal completed
        async with semaphore:
            caption = await caption_single_image(img, idx, total)
            if caption:
                img.caption = caption
            completed += 1
            if on_progress:
                on_progress("captioning_progress", f"Captioned {completed}/{total} images...")

    tasks = [
        caption_with_semaphore(img, i)
        for i, img in enumerate(parsed.images)
    ]
    await asyncio.gather(*tasks, return_exceptions=True)

    captioned_count = sum(1 for img in parsed.images if img.caption)
    log_info(f"Captioning complete: {captioned_count}/{total} images captioned successfully", "captioning")

    if on_progress:
        on_progress("captioning_done", f"Captioned {captioned_count}/{total} images successfully")

    return parsed
