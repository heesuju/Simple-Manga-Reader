
import os
import requests
import json
from dotenv import load_dotenv
from src.enums import Language

# Load params from .env (e.g. LLAMA_API_URL)
load_dotenv()

class Translator:
    def __init__(self):
        self.api_url = os.getenv("LLAMA_API_URL", "http://localhost:8080/completion")

    def translate(self, text: str, target_lang: Language = Language.ENG) -> str:
        """
        Translate text using local Llama.CPP.
        """
        if not text or not text.strip():
            return ""

        map_lang = {
            Language.KOR: "Korean",
            Language.ENG: "English"
        }

        target_name = map_lang.get(target_lang, "English")

        # Few-shot examples
        examples = ""
        
        if target_lang == Language.ENG:
            examples = (
                "Example 1:\n"
                "Text: こんにちは\n"
                "Translation: Hello\n\n"
                "Example 2:\n"
                "Text: 何をしているの？\n"
                "Translation: What are you doing?\n\n"
                "Example 3:\n"
                "Text: やめろ！\n"
                "Translation: Stop it!\n\n"
            )
        elif target_lang == Language.KOR:
            examples = (
                "Example 1:\n"
                "Text: こんにちは\n"
                "Translation: 안녕하세요\n\n"
                "Example 2:\n"
                "Text: 何をしているの？\n"
                "Translation: 뭐 하고 있어?\n\n"
                "Example 3:\n"
                "Text: やめろ！\n"
                "Translation: 그만해!\n\n"
            )

        prompt = (
            f"You are a professional manga translator. Translate the Japanese text below to {target_name}.\n"
            "Output only the final translation. Do not provide lists, or alternatives.\n\n"
            f"{examples}"
            f"Text: {text}\n"
            "Translation:"
        )
        
        data = {
            "prompt": prompt,
            "n_predict": 100,
            "temperature": 0.1, # Lower temperature for deterministic output
            "stop": ["\n", "Text:", "Translation:"] # Stop at newline or prompt injection
        }
        
        try:
            response = requests.post(self.api_url, json=data, timeout=10)
            if response.status_code == 200:
                res_json = response.json()
                content = res_json.get("content", "")
                if not content:
                     choices = res_json.get("choices", [])
                     if choices:
                         content = choices[0].get("text", "") or choices[0].get("message", {}).get("content", "")
                
                # Post-processing
                content = content.strip()
                
                # Remove surrounding quotes if present
                if (content.startswith('"') and content.endswith('"')) or (content.startswith("'") and content.endswith("'")):
                    content = content[1:-1].strip()

                # Take only the first line if multiple leaked through
                if '\n' in content:
                    content = content.split('\n')[0].strip()

                return content
            else:
                print(f"Translation API error: {response.status_code} - {response.text}")
                return "[Error]"
        except Exception as e:
            print(f"Translation logic error: {e}")
            return "[Error]"
