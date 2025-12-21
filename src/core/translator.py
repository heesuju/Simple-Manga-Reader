
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

        prompt = f"Translate the following manga text to {target_name}. Output only the translation.\n\nText: {text}\n\nTranslation:"
        
        data = {
            "prompt": prompt,
            "n_predict": 100,
            "temperature": 0.3,
            "stop": ["\n"] # Stop at newline to avoid hallucinations
        }
        
        try:
            response = requests.post(self.api_url, json=data, timeout=10)
            if response.status_code == 200:
                res_json = response.json()
                # Llama.cpp completion endpoint returns 'content' or 'content' in choices?
                # Usually: { "content": "..." } or { "choices": [ { "text": "..." } ] } depending on endpoint /v1 or direct.
                # Default /completion returns: { "content": "..." }
                content = res_json.get("content", "")
                if not content:
                     # Check standard OAI format just in case
                     choices = res_json.get("choices", [])
                     if choices:
                         content = choices[0].get("text", "") or choices[0].get("message", {}).get("content", "")
                
                return content.strip()
            else:
                print(f"Translation API error: {response.status_code} - {response.text}")
                return "[Error]"
        except Exception as e:
            print(f"Translation logic error: {e}")
            return "[Error]"
