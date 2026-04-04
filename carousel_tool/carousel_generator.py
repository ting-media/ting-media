"""
Carousel generator: sends article to Claude API and parses the response
into 8 slides, 8 JSON outputs, and a social copy brief.
"""

import json
import logging
import re

from anthropic import Anthropic

from config import Config

logger = logging.getLogger(__name__)

# ── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """# Role
You are a content editor and social media strategist for an Israeli automotive magazine. You are an expert in crafting carousel-based stories that transform in-depth articles into compelling social media content. You understand automotive journalism, the subtleties of Israeli market positioning, and how to create narrative flow that drives engagement without compromising editorial integrity.

# Task
Your primary function is to:
1. Read and deeply analyze the automotive article provided
2. Extract the core narrative, journalistic angle, vehicle strengths, and implicit tensions
3. Build a social media carousel (4-6 slides) that compels readers to stop, read, and click through to the full article
   - Minimum 4 slides, maximum 6 slides
   - Choose slide count based on article depth and information density
   - More complex articles → 6 slides; simpler news → 4 slides
4. Generate structured JSON outputs for each slide compatible with the Gemini image generation engine

# Instructions
## Core Behavioral Rules
**Before Writing:**
- Read the entire article thoroughly before composing any slide copy
- Identify the journalistic angle, technical specifications, vehicle positioning, and narrative tension
- Map the story arc: introduction → context → substance → intrigue → call to action
- Extract all factual data (prices, ranges, charging times, dimensions, specifications) exactly as written
- Identify what works well and what creates subtle friction — hint at friction without explicit criticism

**Writing Tone & Voice:**
- Write as an editorial voice, never as an advertiser or marketing copywriter
- Maintain a neutral, journalistic, composed, and credible tone
- Use natural, flowing Hebrew appropriate for automotive magazine publication
- Ensure each slide feels like part of one continuous story, not disconnected information cards
- Each slide builds narrative momentum toward the full article

**Forbidden Language & Patterns:**
- Never use: "revolution," "game-changer," "market-disrupting," "category-defining," "insane deal," "true magic," "can't-miss vehicle"
- Never write marketing briefs or ad-speak
- Avoid clickbait formulations like "Wait till you see what's wrong" or "It's great, but there's a catch"
- No cheap qualifiers or false drama
- No English language in the slides (Hebrew only in body copy)
- No generic car photography or AI-rendered generics — use actual article images or realistic renders of the specific model

**Carousel Structure Requirements (4-6 slides):**
**Slide 1 (Hook):** Deliver a strong but journalistic hook. Stop the scroll, create curiosity, establish the story. No generic opening.
**Middle Slides (2–N-1):** Build the narrative progressively. Layer information with meaning. If this is a road test, contextualize specs within real-world significance. If this is a news item, provide market context and why the move matters. Weave in subtle hints of tension or complexity without stating them directly — let readers sense there's more to discover in the full article.
**Final Slide (N):** End with a sophisticated, understated call-to-action. Point readers to the full article without sales language. Frame it as "the complete picture" or "deeper context," not as a sales opportunity.
**Slide count logic:** Decide based on article substance: 4 slides for simpler news, 5-6 for in-depth reviews or complex stories.

**Content Density:**
- Keep each slide's text concise and readable on mobile
- Prioritize readability and flow over information density
- Use only specifications, prices, ranges, charging data, or equipment details if they genuinely serve the story
- If details feel disconnected from narrative meaning, omit them

**Handling Implicit Criticism:**
- Never state criticism or reservations directly or bluntly
- Hint at limitations with sophistication and subtlety — create curiosity that pulls readers into the article
- Example: Instead of "It's expensive," say "A positioning that asks important questions about the segment"
- The goal is intrigue, not manipulation

## Slide-by-Slide Specifications
Each slide must follow this exact structure:
```
שקף מספר [X]
כותרת
טקסט
```

**Headline requirements:**
- Short, sharp, clear
- No advertising language
- Unique to each slide — progressive revelation

**Body text requirements:**
- Scannable on mobile
- Flows naturally in Hebrew
- Formatted for easy reading on a social slide
- No walls of text

## Output Format (follow exactly)

**Step 1: Complete carousel (4-6 slides)**
Output all slides sequentially:
```
שקף מספר 1
[כותרת]
[טקסט]

שקף מספר 2
[כותרת]
[טקסט]
...
שקף מספר N (where N = 4, 5, or 6)
[כותרת]
[טקסט]
```

**Step 2: JSON outputs**
For each slide, output:
```
שקף [X]
```json
{ JSON object }
```
```

**Step 3: Social copy brief**
After all JSONs, output a section starting with:
## תקציר סושיאל
- **כותרת לפוסט:** ...
- **תיאור (2-3 שורות):** ...
- **האשטגים:** ...
- **המלצת שעת פרסום:** ...
- **טיפ לאינסטגרם:** ...

## JSON Structure (for each slide)
```json
{
  "slide_number": [X],
  "task": "Create [X]th slide of automotive magazine carousel",
  "goal": "Deliver specific narrative beat while maintaining editorial credibility",
  "model_subject_full_name": "[Full model name in English]",
  "use_attached_image_if_available": true,
  "image_handling": {
    "if_user_attaches_image": "Use attached image as primary visual element; maintain proportions, accurate badging, correct design lines, authentic lighting",
    "if_no_image_attached": "Generate realistic render of the specific model. Not generic SUV. Not cartoon. Not stylized. Realistic automotive photography standard"
  },
  "canvas": {
    "dimensions": "1080x1350px (Instagram feed vertical)",
    "safe_area_text": "900x1200px (accounting for platform cutoff)",
    "layout": "Image-dominant center window with text hierarchy below and above"
  },
  "design_system": {
    "background": "Deep red with subtle, rich texture. Elegant and refined, not flat or cheap",
    "image_window": "Central or dominant placement with torn-paper-style frame border. Realistic proportions for the specific vehicle",
    "typography": {
      "language": "Hebrew RTL",
      "headline_font": "Bold, sharp, editorial weight. Hierarchy clear and immediate",
      "body_font": "Regular weight, high legibility on mobile, professional spacing"
    },
    "layout": "Clear hierarchy: headline → image → body text. Organized, clean, editorial composition",
    "fail_safe_hebrew": "If rendering issues occur, leave clean text areas for manual override. Do not force broken characters into final output"
  },
  "text_content": {
    "h1": "[Exact headline from carousel]",
    "body": "[Exact body text from carousel]",
    "cta_implied": "Progression toward full article reading"
  },
  "visual_direction": "Modern automotive magazine aesthetic. Systems-driven, clean, sharp, journalistic, expertly designed. Realistic vehicle rendering. Editorial mood, not sales mood. High production value. Professional automotive publication standard",
  "avoid": [
    "Cartoon or stylized vehicle rendering",
    "Wrong badge or incorrect model badging",
    "Generic SUV — must be the specific model from the article",
    "Sales banner look or aggressive advertising mood",
    "Cheap ad feel or overloaded composition",
    "Unnecessary icons or graphic clutter",
    "English typography on slide body",
    "Obvious clickbait framing",
    "Oversize numbers in advertising style",
    "Generic Facebook ad aesthetic",
    "Sensationalist mood or tone"
  ]
}
```
"""


# ── Main generation function ──────────────────────────────────────────────────

def generate_carousel(article: dict) -> dict | None:
    """
    Send article to Claude API and return parsed carousel data.

    Returns:
        {
            "article": dict,
            "slides": [{"number": int, "title": str, "body": str}, ...],
            "jsons": [dict, ...],
            "social_brief": str,
            "raw_content": str,
        }
        or None on failure.
    """
    api_key = Config.anthropic_api_key()
    if not api_key:
        logger.error("ANTHROPIC_API_KEY is not configured")
        return None

    client = Anthropic(api_key=api_key)

    image_list = "\n".join(f"- {u}" for u in article.get("image_urls", []))
    user_message = (
        f"להלן הכתבה לעיבוד:\n\n"
        f"**כותרת:** {article['title']}\n"
        f"**URL:** {article['url']}\n"
        f"**תאריך:** {article.get('date', '')}\n"
        f"**קישורי תמונות:**\n{image_list or 'לא זמינות'}\n\n"
        f"**תוכן הכתבה:**\n{article['body']}\n\n"
        "---\n\n"
        "אנא צור את הפלט המלא לפי ההוראות:\n"
        "1. 4-6 שקפים בעברית (בחר כמות לפי עומק הכתבה)\n"
        "2. JSON output לכל שקף\n"
        "3. תקציר סושיאל"
    )

    try:
        logger.info("Sending article to Claude: %s", article["title"][:60])
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as e:
        logger.error("Claude API error: %s", e)
        return None

    raw = response.content[0].text
    logger.info("Received response (%d chars)", len(raw))

    return _parse_response(raw, article)


# ── Response parser ───────────────────────────────────────────────────────────

def _parse_response(content: str, article: dict) -> dict:
    slides = _parse_slides(content)
    jsons = _parse_jsons(content)
    social_brief = _parse_social_brief(content)

    # If JSON blocks are missing but slides exist, build minimal JSONs from slides
    if not jsons and slides:
        jsons = [_build_minimal_json(s, article) for s in slides]

    logger.info(
        "Parsed: %d slides, %d JSONs, social_brief=%s",
        len(slides), len(jsons), bool(social_brief)
    )

    return {
        "article": article,
        "slides": slides,
        "jsons": jsons,
        "social_brief": social_brief,
        "raw_content": content,
    }


def _parse_slides(content: str) -> list[dict]:
    """Extract שקף מספר X blocks from content."""
    slides = []
    # Pattern: שקף מספר N  then title on next line, then body until next שקף or end
    pattern = re.compile(
        r"שקף מספר\s+(\d+)\s*\n"   # "שקף מספר X"
        r"([^\n]+)\n"               # title (one line)
        r"([\s\S]*?)"               # body (multiline)
        r"(?=שקף מספר\s+\d+|```json|##\s+תקציר|\Z)",
        re.MULTILINE,
    )
    for m in pattern.finditer(content):
        slides.append({
            "number": int(m.group(1)),
            "title": m.group(2).strip(),
            "body": m.group(3).strip(),
        })

    # Sort by slide number
    slides.sort(key=lambda s: s["number"])
    return slides


def _parse_jsons(content: str) -> list[dict]:
    """Extract all ```json ... ``` code blocks."""
    blocks = []
    pattern = re.compile(r"```json\s*\n([\s\S]*?)\n```", re.MULTILINE)
    for m in pattern.finditer(content):
        raw_json = m.group(1).strip()
        try:
            data = json.loads(raw_json)
            blocks.append(data)
        except json.JSONDecodeError as e:
            logger.warning("Skipping malformed JSON block: %s", e)

    # Sort by slide_number if present
    blocks.sort(key=lambda b: b.get("slide_number", 99))
    return blocks


def _parse_social_brief(content: str) -> str:
    """Extract the social copy brief section."""
    m = re.search(r"##\s+תקציר סושיאל([\s\S]+?)$", content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    # Fallback: everything after the last ```
    last_fence = content.rfind("```")
    if last_fence != -1:
        tail = content[last_fence + 3:].strip()
        if len(tail) > 30:
            return tail
    return ""


def _build_minimal_json(slide: dict, article: dict) -> dict:
    """Fallback: build a minimal JSON block from a slide dict."""
    return {
        "slide_number": slide["number"],
        "task": f"Create {slide['number']}th slide of automotive magazine carousel",
        "goal": "Deliver narrative beat while maintaining editorial credibility",
        "model_subject_full_name": article.get("title", "Unknown Model"),
        "use_attached_image_if_available": True,
        "image_handling": {
            "if_user_attaches_image": "Use attached image as primary visual element",
            "if_no_image_attached": "Generate realistic render of the specific model",
        },
        "canvas": {
            "dimensions": "1080x1350px (Instagram feed vertical)",
            "safe_area_text": "900x1200px",
            "layout": "Image-dominant center window with text hierarchy",
        },
        "design_system": {
            "background": "Deep red with subtle, rich texture",
            "image_window": "Central placement with torn-paper-style frame border",
            "typography": {
                "language": "Hebrew RTL",
                "headline_font": "Bold, sharp, editorial weight",
                "body_font": "Regular weight, high legibility on mobile",
            },
            "layout": "Clear hierarchy: headline → image → body text",
            "fail_safe_hebrew": "Leave clean text areas for manual override if needed",
        },
        "text_content": {
            "h1": slide["title"],
            "body": slide["body"],
            "cta_implied": "Progression toward full article reading",
        },
        "visual_direction": (
            "Modern automotive magazine aesthetic. Editorial mood, not sales mood. "
            "Realistic vehicle rendering. High production value."
        ),
        "avoid": [
            "Cartoon or stylized vehicle rendering",
            "Wrong badge or incorrect model badging",
            "Generic SUV — must be the specific model",
            "Sales banner look or aggressive advertising mood",
            "English typography on slide body",
            "Sensationalist mood or tone",
        ],
    }
