"""
Gemini Image Generation: Convert slide JSON to carousel images.
Integrates with Google's Generative AI API (Nano Banana / Gemini 2).
"""

import json
import logging
import base64
from pathlib import Path

import google.generativeai as genai
from PIL import Image
import io

from config import Config

logger = logging.getLogger(__name__)

# ── API Configuration ─────────────────────────────────────────────────────────

def _init_gemini():
    """Initialize Gemini API with config API key."""
    api_key = Config.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY is not configured")
        return False
    genai.configure(api_key=api_key)
    return True


# ── Main Image Generation ─────────────────────────────────────────────────────

def generate_slide_image(slide_json: dict, output_path: Path = None) -> bytes | None:
    """
    Generate a carousel slide image from JSON spec using Gemini.

    Args:
        slide_json: Dict containing slide design specs (from carousel_generator)
        output_path: Optional path to save PNG file

    Returns:
        Image bytes (PNG) or None on failure
    """
    if not _init_gemini():
        return None

    # Extract slide content
    slide_num = slide_json.get("slide_number", 1)
    h1 = slide_json.get("text_content", {}).get("h1", "")
    body = slide_json.get("text_content", {}).get("body", "")
    model_name = slide_json.get("model_subject_full_name", "")
    design = slide_json.get("design_system", {})

    # Build Gemini vision prompt
    prompt = _build_gemini_prompt(
        slide_num=slide_num,
        h1=h1,
        body=body,
        model_name=model_name,
        design=design,
        slide_json=slide_json
    )

    try:
        logger.info("Generating image for slide %d...", slide_num)
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(
            [prompt],
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
            ),
        )

        if not response.candidates:
            logger.error("No image generated for slide %d", slide_num)
            return None

        # Extract image from response (Gemini returns base64 encoded image)
        image_bytes = _extract_image_from_response(response)
        if not image_bytes:
            logger.error("Failed to extract image from Gemini response for slide %d", slide_num)
            return None

        # Save to file if path provided
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(image_bytes)
            logger.info("Saved slide %d image to %s", slide_num, output_path)

        return image_bytes

    except Exception as e:
        logger.error("Gemini API error for slide %d: %s", slide_num, e)
        return None


# ── Prompt Building ───────────────────────────────────────────────────────────

def _build_gemini_prompt(
    slide_num: int,
    h1: str,
    body: str,
    model_name: str,
    design: dict,
    slide_json: dict,
) -> str:
    """
    Build comprehensive prompt for Gemini image generation.
    Encodes all design requirements, typography, and content.
    """

    design_bg = design.get("background", "Deep red with subtle texture")
    design_window = design.get("image_window", "Torn paper frame, center dominant")
    typography = design.get("typography", {})
    avoid_list = slide_json.get("avoid", [])

    avoid_str = "\n".join(f"  - {item}" for item in avoid_list)

    prompt = f"""You are a professional automotive magazine carousel designer using Gemini 2.0.

## Task: Generate Slide {slide_num} of {slide_json.get("slide_number", "N")}

### Content (Hebrew - RTL)
**Headline (h1):**
{h1}

**Body Text:**
{body}

### Design Specifications

**Canvas:** 1080x1350px (Instagram Feed vertical format)

**Background:**
{design_bg}

**Image Window:**
{design_window}
- Must display the specific vehicle model: {model_name}
- Realistic automotive photography standard
- Proper proportions, accurate badging, correct design lines
- Professional lighting

**Typography:**
- Language: Hebrew (RTL text direction)
- Headline: Bold, sharp, editorial weight
- Body: Regular weight, high legibility on mobile
- Professional spacing and hierarchy

**Layout:**
- Clear visual hierarchy: headline → image → body text
- Organized, clean, editorial composition
- Professional automotive magazine aesthetic

### Strict Requirements (AVOID at all costs)
{avoid_str}

### Visual Direction
Modern automotive magazine aesthetic. Systems-driven, clean, sharp, journalistic, expertly designed. Realistic vehicle rendering. Editorial mood, not sales mood. High production value. Professional automotive publication standard.

### Implementation Notes
1. If Hebrew rendering issues occur, use clean text areas for manual override
2. Vehicle must be realistic and proportionally accurate
3. Maintain professional, editorial tone throughout
4. Do not include any advertising language or sales messaging
5. Ensure text is readable at mobile sizes

**Generate the carousel slide image now. Make it professional, editorial, and compelling.**
"""

    return prompt


# ── Response Parsing ──────────────────────────────────────────────────────────

def _extract_image_from_response(response) -> bytes | None:
    """
    Extract image bytes from Gemini response.
    Gemini may return image in different formats; handle accordingly.
    """
    try:
        # Gemini 2.0 returns image data as base64 in the response
        # Access the generated content
        if hasattr(response, "content") and response.content:
            # For image generation, response typically contains image data
            # Convert from potential base64 or direct bytes
            for part in response.content.parts:
                if hasattr(part, "data"):
                    return part.data  # Direct bytes
                elif hasattr(part, "text") and "image" in part.text.lower():
                    # Fallback: might need to decode base64
                    try:
                        return base64.b64decode(part.text)
                    except:
                        pass

        # Alternative: check response.candidates
        if hasattr(response, "candidates") and response.candidates:
            for candidate in response.candidates:
                if hasattr(candidate.content, "parts"):
                    for part in candidate.content.parts:
                        if hasattr(part, "data"):
                            return part.data

        logger.warning("Could not extract image from Gemini response")
        return None

    except Exception as e:
        logger.error("Error parsing Gemini response: %s", e)
        return None


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
