"""
Main Agent Logic - Orchestrates fetching, processing, and linking
"""
from typing import List, Dict, Tuple
from datetime import datetime, timedelta
import uuid
import anthropic

from gmail_client import GmailClient
from whatsapp_client import WhatsAppClient
from message_processor import MessageProcessor
from task_linker import TaskLinker
from state_manager import StateManager

from config import (
    ANTHROPIC_API_KEY, CLAUDE_MODEL,
    MONITORED_WHATSAPP_GROUPS, MONITORED_GMAIL_LABELS
)

class WhatsAppGmailAgent:
    def __init__(self):
        self.claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.gmail_client = GmailClient()
        self.whatsapp_client = WhatsAppClient()
        self.message_processor = MessageProcessor()
        self.task_linker = TaskLinker()
        self.state_manager = StateManager()

    def run_sync(self, hours: int = 1) -> Dict:
        """
        Run a complete sync cycle:
        1. Fetch WhatsApp messages
        2. Fetch Gmail messages
        3. Process and extract tasks
        4. Link tasks across platforms
        5. Store in database
        6. Generate summary
        """
        print(f"\n{'='*60}")
        print(f"Starting sync cycle - fetching last {hours} hour(s)")
        print(f"{'='*60}\n")

        start_time = datetime.now()
        sync_id = f"sync_{uuid.uuid4().hex[:8]}"

        # Step 1: Fetch WhatsApp messages
        print("📱 Fetching WhatsApp messages...")
        whatsapp_raw = self._fetch_whatsapp_messages(hours)
        print(f"   Found {len(whatsapp_raw)} WhatsApp messages\n")

        # Step 2: Fetch Gmail messages
        print("📧 Fetching Gmail messages...")
        gmail_raw = self._fetch_gmail_messages(hours)
        print(f"   Found {len(gmail_raw)} Gmail messages\n")

        # Step 3: Process messages
        print("🔄 Processing messages...")
        whatsapp_processed = [
            self.message_processor.process_whatsapp_message(msg)
            for msg in whatsapp_raw
        ]
        gmail_processed = [
            self.message_processor.process_gmail_message(msg)
            for msg in gmail_raw
        ]
        print(f"   Processed {len(whatsapp_processed)} + {len(gmail_processed)} messages\n")

        # Step 4: Store messages and extract tasks
        print("💾 Storing messages and extracting tasks...")
        for msg in whatsapp_processed + gmail_processed:
            self.state_manager.add_message(msg)

        whatsapp_tasks = [
            self.message_processor.extract_task_from_message(msg)
            for msg in whatsapp_processed if msg.get('has_task')
        ]

        gmail_tasks = [
            self.message_processor.extract_task_from_message(msg)
            for msg in gmail_processed if msg.get('has_task')
        ]

        for task in whatsapp_tasks + gmail_tasks:
            self.state_manager.add_task(task)

        print(f"   Created {len(whatsapp_tasks)} WhatsApp tasks + {len(gmail_tasks)} Gmail tasks\n")

        # Step 5: Link tasks across platforms
        print("🔗 Linking tasks across platforms...")
        linked_pairs = self.task_linker.link_tasks(whatsapp_tasks, gmail_tasks)

        for wa_id, gmail_id, confidence in linked_pairs:
            link_id = f"link_{uuid.uuid4().hex[:8]}"
            self.state_manager.link_tasks(wa_id, gmail_id, "related", confidence)
            print(f"   Linked: {wa_id} ↔ {gmail_id} (confidence: {confidence:.2f})")

        if not linked_pairs:
            print("   No task links found\n")
        else:
            print()

        # Step 6: Generate summary
        print("📝 Generating summary...")
        summary = self._generate_summary(whatsapp_processed, gmail_processed, whatsapp_tasks, gmail_tasks, linked_pairs)

        # Step 7: Get analytics
        analytics = self.state_manager.get_analytics(hours=hours)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        result = {
            'sync_id': sync_id,
            'timestamp': start_time.isoformat(),
            'duration_seconds': duration,
            'messages': {
                'whatsapp': len(whatsapp_raw),
                'gmail': len(gmail_raw),
                'total': len(whatsapp_raw) + len(gmail_raw)
            },
            'tasks': {
                'whatsapp': len(whatsapp_tasks),
                'gmail': len(gmail_tasks),
                'linked': len(linked_pairs),
                'total': len(whatsapp_tasks) + len(gmail_tasks)
            },
            'summary': summary,
            'analytics': analytics
        }

        print(f"\n{'='*60}")
        print(f"✓ Sync completed in {duration:.1f}s")
        print(f"{'='*60}\n")

        return result

    def _fetch_whatsapp_messages(self, hours: int) -> List[Dict]:
        """Fetch WhatsApp messages from monitored groups"""
        messages = []

        for group_id in MONITORED_WHATSAPP_GROUPS:
            try:
                group_msgs = self.whatsapp_client.get_messages(group_id, limit=100)
                messages.extend(group_msgs)
                print(f"   - Group {group_id}: {len(group_msgs)} messages")
            except Exception as e:
                print(f"   - Group {group_id}: Error - {e}")

        if not MONITORED_WHATSAPP_GROUPS:
            print("   ⚠️  No WhatsApp groups configured")

        return messages

    def _fetch_gmail_messages(self, hours: int) -> List[Dict]:
        """Fetch Gmail messages from monitored labels"""
        messages = []

        try:
            gmail_raw = self.gmail_client.get_recent_messages(hours=hours)

            for raw_msg in gmail_raw:
                msg_details = self.gmail_client.get_message_details(raw_msg)
                messages.append(msg_details)

            print(f"   - INBOX: {len(messages)} messages")

        except Exception as e:
            print(f"   - INBOX: Error - {e}")

        return messages

    def _generate_summary(self, whatsapp_msgs: List[Dict], gmail_msgs: List[Dict],
                         whatsapp_tasks: List[Dict], gmail_tasks: List[Dict],
                         linked_pairs: List[Tuple]) -> str:
        """Generate AI-powered summary of the sync"""

        prompt = f"""
You are a professional team assistant. Summarize the following sync in Hebrew:

📱 WhatsApp Messages: {len(whatsapp_msgs)}
- Tasks identified: {len(whatsapp_tasks)}
- Top messages:
{chr(10).join([f"  • {msg['sender']}: {msg['content'][:80]}" for msg in whatsapp_msgs[:3]])}

📧 Gmail Messages: {len(gmail_msgs)}
- Tasks identified: {len(gmail_tasks)}
- Top messages:
{chr(10).join([f"  • {msg['sender']}: {msg['content'][:80]}" for msg in gmail_msgs[:3]])}

🔗 Linked Tasks: {len(linked_pairs)}

Provide a concise, professional summary (3-5 sentences) in Hebrew that:
1. Gives an overview of activity
2. Highlights important tasks
3. Notes any linked tasks between platforms
4. Suggests next steps if needed

Keep it brief and actionable.
"""

        try:
            response = self.claude_client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=500,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            return response.content[0].text

        except Exception as e:
            print(f"Error generating summary: {e}")
            return f"Sync completed: {len(whatsapp_msgs)} WhatsApp messages, {len(gmail_msgs)} Gmail messages, {len(linked_pairs)} linked tasks."

    def get_dashboard_data(self) -> Dict:
        """Get all data needed for dashboard"""
        recent_messages = self.state_manager.get_recent_messages(hours=24)
        open_tasks = self.state_manager.get_open_tasks()
        analytics = self.state_manager.get_analytics(hours=24)

        return {
            'recent_messages': recent_messages,
            'open_tasks': open_tasks,
            'analytics': analytics,
            'timestamp': datetime.now().isoformat()
        }

    def close(self):
        """Clean up resources"""
        self.state_manager.close()
