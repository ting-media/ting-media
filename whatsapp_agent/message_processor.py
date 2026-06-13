"""
Message Processor - Parse & analyze messages
"""
from typing import Dict, List
from datetime import datetime
import uuid
import re

from config import TASK_KEYWORDS

class MessageProcessor:
    @staticmethod
    def process_whatsapp_message(msg: Dict) -> Dict:
        """
        Process a WhatsApp message and extract metadata

        Input: {
            'id': '...',
            'from': '...',
            'timestamp': '...',
            'type': 'text',
            'text': '...',
            'sender': '...'
        }

        Output: Enhanced message dict
        """
        processed = {
            'id': msg.get('id'),
            'platform': 'whatsapp',
            'platform_id': msg.get('id'),
            'sender': msg.get('sender', msg.get('from', 'Unknown')),
            'sender_id': msg.get('from'),
            'content': msg.get('text', ''),
            'timestamp': MessageProcessor._parse_timestamp(msg.get('timestamp')),
            'metadata': {
                'type': msg.get('type'),
                'original': msg
            }
        }

        # Extract features
        processed['has_task'] = MessageProcessor._has_task(processed['content'])
        processed['task_keywords'] = MessageProcessor._extract_keywords(processed['content'])
        processed['is_question'] = MessageProcessor._is_question(processed['content'])
        processed['urgency'] = MessageProcessor._estimate_urgency(processed['content'])

        return processed

    @staticmethod
    def process_gmail_message(msg: Dict) -> Dict:
        """
        Process a Gmail message and extract metadata

        Input: {
            'id': '...',
            'from': '...',
            'to': '...',
            'subject': '...',
            'date': '...',
            'body': '...',
            'timestamp': '...',
            'labels': [...]
        }

        Output: Enhanced message dict
        """
        processed = {
            'id': msg.get('id'),
            'platform': 'gmail',
            'platform_id': msg.get('id'),
            'sender': msg.get('from'),
            'sender_id': msg.get('from'),
            'content': f"Subject: {msg.get('subject')}\n\n{msg.get('body', '')}",
            'timestamp': MessageProcessor._parse_timestamp(msg.get('timestamp', msg.get('date'))),
            'metadata': {
                'subject': msg.get('subject'),
                'to': msg.get('to'),
                'labels': msg.get('labels', []),
                'original': msg
            }
        }

        # Extract features
        processed['has_task'] = MessageProcessor._has_task(processed['content'])
        processed['task_keywords'] = MessageProcessor._extract_keywords(processed['content'])
        processed['is_question'] = MessageProcessor._is_question(processed['content'])
        processed['urgency'] = MessageProcessor._estimate_urgency(processed['content'])

        return processed

    @staticmethod
    def _parse_timestamp(ts: str) -> datetime:
        """Parse timestamp from various formats"""
        if not ts:
            return datetime.now()

        # If it's already a datetime
        if isinstance(ts, datetime):
            return ts

        # Try parsing as ISO
        try:
            return datetime.fromisoformat(ts.replace('Z', '+00:00'))
        except:
            pass

        # Try other common formats
        formats = [
            '%a, %d %b %Y %H:%M:%S %z',  # Gmail format
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S',
        ]

        for fmt in formats:
            try:
                return datetime.strptime(ts, fmt)
            except:
                pass

        return datetime.now()

    @staticmethod
    def _has_task(content: str) -> bool:
        """Check if message contains a task"""
        content_lower = content.lower()
        return any(keyword.lower() in content_lower for keyword in TASK_KEYWORDS)

    @staticmethod
    def _extract_keywords(content: str) -> List[str]:
        """Extract task keywords from content"""
        content_lower = content.lower()
        found = []

        for keyword in TASK_KEYWORDS:
            if keyword.lower() in content_lower:
                found.append(keyword)

        return found

    @staticmethod
    def _is_question(content: str) -> bool:
        """Check if message is a question"""
        return content.strip().endswith('?')

    @staticmethod
    def _estimate_urgency(content: str) -> str:
        """Estimate urgency level: low, normal, high, urgent"""
        content_lower = content.lower()

        urgent_keywords = ['דחוף', 'urgent', 'asap', 'critical', 'חרום', 'מיד', 'now']
        high_keywords = ['חשוב', 'important', 'priority', 'high', 'significant']

        if any(k in content_lower for k in urgent_keywords):
            return 'urgent'
        elif any(k in content_lower for k in high_keywords):
            return 'high'
        elif content.count('!') > 1:
            return 'high'
        else:
            return 'normal'

    @staticmethod
    def extract_task_from_message(msg: Dict) -> Dict:
        """
        Extract task details from a message

        Returns a task dict that can be stored
        """
        task_id = f"task_{uuid.uuid4().hex[:8]}"

        # Try to extract title from content
        content = msg['content']
        lines = content.split('\n')
        title = lines[0][:100] if lines else "Task"

        # If subject exists, use it
        if 'metadata' in msg and 'subject' in msg['metadata']:
            title = msg['metadata']['subject']

        return {
            'id': task_id,
            'title': title,
            'description': content[:500],  # First 500 chars
            'source_message_id': msg['id'],
            'platform': msg['platform'],
            'status': 'open',
            'priority': msg.get('urgency', 'normal'),
            'metadata': {
                'keywords': msg.get('task_keywords', []),
                'is_question': msg.get('is_question', False)
            }
        }
