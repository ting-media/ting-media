"""
Stable Diffusion Image Generation: Convert slide JSON to carousel images.
Integrates with Stability AI's Stable Diffusion API.
"""

import logging
import requests
import io
from pathlib import Path

from config import Config

logger = logging.getLogger(__name__)

# ── API Configuration ─────────────────────────────────────────────────────────

STABILITY_API_HOST = "https://api.stability.ai"
STABILITY_API_ENDPOINT = f"{STABILITY_API_HOST}/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image"


def _get_api_key() -> str:
    """Get Stable Diffusion API key from config."""
    return Config.get("STABLE_DIFFUSION_API_KEY")


# ── Main Image Generation ─────────────────────────────────────────────────────

def generate_slide_image(slide_json: dict, output_path: Path = None) -> bytes | None:
    """
    Generate a carousel slide image from JSON spec using Stable Diffusion.

    Args:
        slide_json: Dict containing slide design specs (from carousel_generator)
        output_path: Optional path to save PNG file

    Returns:
        Image bytes (PNG) or None on failure
    """
    api_key = _get_api_key()
    if not api_key:
        logger.error("STABLE_DIFFUSION_API_KEY is not configured")
        return None

    # Extract slide content
    slide_num = slide_json.get("slide_number", 1)
    h1 = slide_json.get("text_content", {}).get("h1", "")
    body = slide_json.get("text_content", {}).get("body", "")
    model_name = slide_json.get("model_subject_full_name", "")
    design = slide_json.get("design_system", {})

    # Build Stable Diffusion prompt
    prompt = _build_sd_prompt(
        slide_num=slide_num,
        h1=h1,
        body=body,
        model_name=model_name,
        design=design,
        slide_json=slide_json
    )

    try:
        logger.info("Generating image for slide %d with Stable Diffusion...", slide_num)

        response = requests.post(
            STABILITY_API_ENDPOINT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "image/png",
            },
            json={
                "text_prompts": [
                    {"text": prompt, "weight": 1}
                ],
                "cfg_scale": 7,
                "steps": 30,
                "sampler": "K_DPM_2_ANCESTRAL",
                "width": 768,
                "height": 1344,
            },
        )

        if response.status_code != 200:
            logger.error("Stable Diffusion API error (slide %d): %s", slide_num, response.text)
            return None

        image_bytes = response.content

        # Save to file if path provided
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(image_bytes)
            logger.info("Saved slide %d image to %s", slide_num, output_path)

        return image_bytes

    except Exception as e:
        logger.error("Stable Diffusion error for slide %d: %s", slide_num, e)
        return None


# ── Prompt Building ───────────────────────────────────────────────────────────

def _build_sd_prompt(
    slide_num: int,
    h1: str,
    body: str,
    model_name: str,
    design: dict,
    slide_json: dict,
) -> str:
    """
    Build comprehensive prompt for Stable Diffusion.
    Optimized for photorealistic automotive magazine aesthetic.
    """

    design_bg = design.get("background", "Deep red with subtle texture")
    design_window = design.get("image_window", "Torn paper frame, center dominant")

    prompt = f"""Professional automotive magazine carousel slide {slide_num}

Vehicle: {model_name}
Realistic, professional automotive photography

Design Requirements:
- BACKGROUND: Deep burgundy red (#8B1414) with subtle grain texture
- IMAGE WINDOW: Centered vehicle with torn-paper white border frame (realistic proportions)
- LAYOUT: 1080x1350px (Instagram vertical format)

Typography Layout:
- TOP: Bold headline in Hebrew RTL: "{h1}"
- CENTER: High-quality realistic photo of {model_name}
- BOTTOM: Body text in Hebrew RTL: "{body}"

Style: Editorial automotive magazine aesthetic, professional, clean, journalistic mood, NOT sales/advertising
- NO clickbait, NO superlatives
- Realistic car render with accurate proportions, badging, lighting
- Magazine-quality composition
- Professional color grading

Technical: Photorealistic, high detail, professional lighting, 4K quality"""

    return prompt


# ── Batch Processing ──────────────────────────────────────────────────────────

def generate_carousel_images(
    carousel_jsons: list[dict],
    output_dir: Path,
) -> dict:
    """
    Generate images for all slides in a carousel.

    Args:
        carousel_jsons: List of slide JSON specs
        output_dir: Directory to save PNG files

    Returns:
        {
            "success": bool,
            "images": {1: Path, 2: Path, ...},
            "failed_slides": [slide_numbers],
        }
    """
    images = {}
    failed = []

    for slide_json in carousel_jsons:
        slide_num = slide_json.get("slide_number", 0)
        if not slide_num:
            logger.warning("Slide JSON missing slide_number: %s", slide_json)
            continue

        output_path = output_dir / f"slide_{slide_num}.png"
        image_bytes = generate_slide_image(slide_json, output_path)

        if image_bytes:
            images[slide_num] = output_path
            logger.info("✓ Slide %d generated successfully", slide_num)
        else:
            failed.append(slide_num)
            logger.error("✗ Slide %d generation failed", slide_num)

    return {
        "success": len(failed) == 0,
        "images": images,
        "failed_slides": failed,
        "total": len(carousel_jsons),
        "generated": len(images),
    }
