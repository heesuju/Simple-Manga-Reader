
import os
import requests
import json
from dotenv import load_dotenv
from src.enums import Language
from src.core.llm_server import LLMServerManager

# Load params from .env (e.g. LLAMA_API_URL)
load_dotenv()

class Translator:
    EXAMPLES = {
        Language.ENG: (
            "Example 1:\n"
            "Text: こんにちは\n"
            "Translation: Hello\n\n"
            "Example 2:\n"
            "Text: 何をしているの？\n"
            "Translation: What are you doing?\n\n"
            "Example 3:\n"
            "Text: やめろ！\n"
            "Translation: Stop it!\n\n"
        ),
        Language.KOR: (
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
    }

    def __init__(self):
        # Dynamically get port from LLMServerManager
        try:
            manager = LLMServerManager.instance()
            port = manager.port
            self.api_url = f"http://localhost:{port}/completion"
        except Exception:
            self.api_url = os.getenv("LLAMA_API_URL", "http://localhost:8080/completion")

    def _perform_translation(self, prompt: str, stop_tokens: list, retries: int = 3) -> str:
        data = {
            "prompt": prompt,
            "n_predict": 100,
            "temperature": 0.1,
            "stop": stop_tokens
        }
        
        for attempt in range(retries):
            try:
                response = requests.post(self.api_url, json=data, timeout=60)
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
                    
                    if content:
                        return content
                else:
                    print(f"Attempt {attempt+1} failed: {response.status_code} - {response.text}")
            except Exception as e:
                print(f"Attempt {attempt+1} error: {e}")
                
        return ""

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
        examples = self.EXAMPLES.get(target_lang, "")

        prompt = (
            f"You are a professional manga translator. Translate the Japanese text below to {target_name}.\n"
            "Output only the final translation. Do not provide lists, or alternatives.\n\n"
            f"{examples}"
            f"Text: {text}\n"
            "Translation:"
        )
        
        return self._perform_translation(prompt, ["\n", "Text:", "Translation:"])

    def translate_contextual(self, text: str, history: list, target_lang: Language = Language.ENG) -> str:
        """
        Translate text using local Llama.CPP with conversation context.
        history: list of tuples (source_text, translated_text)
        """
        if not text or not text.strip():
            return ""

        map_lang = {
            Language.KOR: "Korean",
            Language.ENG: "English"
        }

        target_name = map_lang.get(target_lang, "English")

        # Few-shot examples (Base examples) - Only if no history
        examples = ""
        if not history:
            examples = self.EXAMPLES.get(target_lang, "")

        # Context from history
        context_prompt = ""
        if history:
            context_prompt = "Previous context:\n"
            # Use last 5 items
            recent_history = history[-5:]
            for src, tr in recent_history:
                context_prompt += f"Text: {src}\nTranslation: {tr}\n"
            context_prompt += "\n"

        prompt = (
            f"You are a professional manga translator. Translate the Japanese text below to {target_name}.\n"
            "Output only the final translation. Do not provide lists, or alternatives.\n"
            "Use the previous context to ensure continuity in the conversation.\n\n"
            f"{examples}"
            f"{context_prompt}"
            f"Current Text: {text}\n"
            "Translation:"
        )
        
        return self._perform_translation(prompt, ["\n", "Text:", "Translation:", "Current Text:"])

