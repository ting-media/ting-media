"""
Task Linker - Link tasks between WhatsApp and Gmail
"""
from typing import List, Dict, Tuple
from difflib import SequenceMatcher
import anthropic

from config import CLAUDE_MODEL, ANTHROPIC_API_KEY

class TaskLinker:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    def link_tasks(self, whatsapp_tasks: List[Dict], gmail_tasks: List[Dict]) -> List[Tuple[str, str, float]]:
        """
        Find correlations between WhatsApp and Gmail tasks using Claude

        Returns:
            List of (whatsapp_task_id, gmail_task_id, confidence) tuples
        """
        if not whatsapp_tasks or not gmail_tasks:
            return []

        # First try simple keyword matching
        simple_links = self._simple_match(whatsapp_tasks, gmail_tasks)

        # Then use Claude for more complex correlations
        claude_links = self._claude_match(whatsapp_tasks, gmail_tasks)

        # Combine and deduplicate
        all_links = simple_links + claude_links
        unique_links = {}

        for wa_id, gmail_id, confidence in all_links:
            key = tuple(sorted([wa_id, gmail_id]))
            if key not in unique_links or unique_links[key] < confidence:
                unique_links[key] = (wa_id, gmail_id, confidence)

        return list(unique_links.values())

    def _simple_match(self, whatsapp_tasks: List[Dict], gmail_tasks: List[Dict]) -> List[Tuple[str, str, float]]:
        """
        Simple keyword-based matching
        """
        links = []

        for wa_task in whatsapp_tasks:
            wa_title = wa_task.get('title', '').lower()
            wa_desc = wa_task.get('description', '').lower()

            for gmail_task in gmail_tasks:
                gmail_title = gmail_task.get('title', '').lower()
                gmail_desc = gmail_task.get('description', '').lower()

                # Calculate similarity
                title_sim = SequenceMatcher(None, wa_title, gmail_title).ratio()
                desc_sim = SequenceMatcher(None, wa_desc, gmail_desc).ratio()

                avg_sim = (title_sim + desc_sim) / 2

                # If similarity is high, it's likely a match
                if avg_sim > 0.6:
                    links.append((wa_task['id'], gmail_task['id'], avg_sim))

        return links

    def _claude_match(self, whatsapp_tasks: List[Dict], gmail_tasks: List[Dict]) -> List[Tuple[str, str, float]]:
        """
        Use Claude to find semantic correlations between tasks
        """
        if not whatsapp_tasks or not gmail_tasks:
            return []

        # Prepare task summaries for Claude
        wa_summary = "\n\n".join([
            f"WhatsApp Task {i+1} (ID: {t['id']}):\nTitle: {t['title']}\nDescription: {t['description'][:200]}"
            for i, t in enumerate(whatsapp_tasks[:10])  # Max 10 to avoid token limit
        ])

        gmail_summary = "\n\n".join([
            f"Gmail Task {i+1} (ID: {t['id']}):\nTitle: {t['title']}\nDescription: {t['description'][:200]}"
            for i, t in enumerate(gmail_tasks[:10])
        ])

        prompt = f"""
You are a task correlation expert. Your job is to find which WhatsApp tasks and Gmail tasks are about the same thing.

WhatsApp Tasks:
{wa_summary}

Gmail Tasks:
{gmail_summary}

Please identify which tasks from WhatsApp and Gmail are related (discussing the same topic/request).
Return ONLY a JSON array of correlations in this format:
[
  {{"whatsapp_id": "task_xxx", "gmail_id": "task_yyy", "confidence": 0.95, "reason": "Both about..."}},
  ...
]

Only include tasks that are clearly related. If there are no clear correlations, return an empty array [].
"""

        try:
            message = self.client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            response_text = message.content[0].text

            # Parse JSON response
            import json
            import re

            # Extract JSON from response
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                correlations = json.loads(json_match.group())

                links = []
                for corr in correlations:
                    links.append((
                        corr['whatsapp_id'],
                        corr['gmail_id'],
                        corr.get('confidence', 0.8)
                    ))

                return links

        except Exception as e:
            print(f"Claude task linking error: {e}")

        return []

    def get_task_summary(self, whatsapp_tasks: List[Dict], gmail_tasks: List[Dict], linked_pairs: List[Tuple]) -> str:
        """
        Generate a human-readable summary of linked tasks using Claude
        """
        if not whatsapp_tasks and not gmail_tasks:
            return "No tasks found."

        # Build task overview
        wa_count = len(whatsapp_tasks)
        gmail_count = len(gmail_tasks)
        linked_count = len(linked_pairs)

        summary_prompt = f"""
Summarize these tasks and their connections in Hebrew in 2-3 sentences:

WhatsApp Tasks ({wa_count} total):
{chr(10).join([f"- {t['title']}: {t['description'][:100]}" for t in whatsapp_tasks[:5]])}

Gmail Tasks ({gmail_count} total):
{chr(10).join([f"- {t['title']}: {t['description'][:100]}" for t in gmail_tasks[:5]])}

Linked tasks: {linked_count} matches found

Provide a brief, professional summary in Hebrew.
"""

        try:
            message = self.client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=300,
                messages=[
                    {"role": "user", "content": summary_prompt}
                ]
            )

            return message.content[0].text

        except Exception as e:
            print(f"Error generating summary: {e}")
            return f"Found {wa_count} WhatsApp tasks, {gmail_count} Gmail tasks, {linked_count} linked."
