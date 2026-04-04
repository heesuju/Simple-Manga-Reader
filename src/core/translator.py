
import os
import time
import requests
import json
from src.enums import Language
from src.core.llm_server import LLMServerManager


class Translator:
    # Few-shot examples in the exact Text/Translation format the model must complete.
    # These prime the pattern when no history is available yet.
    EXAMPLES = {
        Language.ENG: (
            "Text: こんにちは\n"
            "Translation: Hello\n\n"
            "Text: 何をしているの？\n"
            "Translation: What are you doing?\n\n"
            "Text: やめろ！\n"
            "Translation: Stop it!\n\n"
            "Text: お前には関係ない。\n"
            "Translation: It's none of your business.\n\n"
        ),
        Language.KOR: (
            "Text: こんにちは\n"
            "Translation: 안녕하세요\n\n"
            "Text: 何をしているの？\n"
            "Translation: 뭐 하고 있어?\n\n"
            "Text: やめろ！\n"
            "Translation: 그만해!\n\n"
            "Text: お前には関係ない。\n"
            "Translation: 너랑 상관없어.\n\n"
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

    def _ensure_server_running(self) -> bool:
        manager = LLMServerManager.instance()
        if manager.is_running():
            return True
        print("LLM server not running, attempting to start...")
        manager.start()
        for _ in range(120):  # up to 60 s
            time.sleep(0.5)
            if manager.check_health():
                print("LLM server ready.")
                return True
        print("LLM server did not become ready in time.")
        return False

    def _perform_translation(self, prompt: str, stop_tokens: list, retries: int = 3) -> str:
        if not self._ensure_server_running():
            return ""
        data = {
            "prompt": prompt,
            "n_predict": 100,
            "temperature": 0.7,
            "top-p": 0.8, 
            "top-k": 20, 
            "min-p": 0,
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

            if attempt < retries - 1:
                time.sleep(1)

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

        examples = self.EXAMPLES.get(target_lang, "")

        prompt = (
            f"Japanese to {target_name} manga translation.\n\n"
            f"{examples}"
            f"Text: {text}\n"
            "Translation:"
        )

        return self._perform_translation(prompt, ["\n", "Text:", "Translation:"])

    def translate_contextual(self, text: str, history: list, target_lang: Language = Language.ENG, page_context: str = "") -> str:
        """
        Translate text using local Llama.CPP with conversation context.
        history: list of tuples (source_text, translated_text)
        page_context: optional scene description to guide the translation
        """
        if not text or not text.strip():
            return ""

        map_lang = {
            Language.KOR: "Korean",
            Language.ENG: "English"
        }

        target_name = map_lang.get(target_lang, "English")

        # Use fixed examples to prime the pattern when there is no history yet.
        # Once history exists it replaces the examples — same format, real context.
        if history:
            shots = ""
            for src, tr in history[-10:]:
                shots += f"Text: {src}\nTranslation: {tr}\n\n"
        else:
            shots = self.EXAMPLES.get(target_lang, "")

        # Scene note sits directly above the current text so the model reads
        # context immediately before it translates.
        scene_note = f"[Scene: {page_context}]\n" if page_context else ""

        prompt = (
            f"Japanese to {target_name} manga translation.\n\n"
            f"{shots}"
            f"{scene_note}"
            f"Text: {text}\n"
            "Translation:"
        )

        return self._perform_translation(prompt, ["\n", "Text:", "Translation:"])

