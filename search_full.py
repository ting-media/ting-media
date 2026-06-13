import json
import sys

jsonl_path = r"C:\Users\Z2G4User\.claude\projects\H-----------------------------\ac139313-636b-47c4-8ca8-c4da70d6fa21.jsonl"

matches = []

with open(jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
    for line_num, json_line in enumerate(f):
        try:
            data = json.loads(json_line)
        except:
            continue
        
        # Look specifically for code blocks
        if 'message' in data and isinstance(data['message'], dict):
            if 'content' in data['message']:
                content = data['message']['content']
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and 'text' in block:
                            text = block['text']
                            
                            # Search for Firebase business app code
                            keywords_for_app = [
                                'import React',
                                'import { useEffect',
                                'useSharedState',
                                'const [employees',
                                'const [projects',
                                'import { BrowserRouter',
                                'firebase/auth',
                                'firebase/firestore'
                            ]
                            
                            count = sum(1 for kw in keywords_for_app if kw in text)
                            
                            if count >= 2 and len(text) > 1000:
                                matches.append((line_num, count, len(text), text[:80]))

# Print matches
matches.sort(key=lambda x: (x[1], x[2]), reverse=True)
for line_num, count, text_len, preview in matches[:15]:
    print(f"Line {line_num}: {count} keywords, {text_len} chars | {preview.replace(chr(10), ' ')[:60]}")
