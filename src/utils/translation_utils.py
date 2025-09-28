import deepl
import os
import requests
import re

def deepl_translate(text: str, source_lang: str = "ES", target_lang: str = "EN-US") -> str:
    """
    Translates text using a local LibreTranslate API.

    Args:
        text: The text to translate.
        source_lang: The source language code (e.g., "en").
        target_lang: The target language code (e.g., "ko").

    Returns:
        The translated text, or an error message if translation fails.
    """
    auth_key = os.getenv("DEEPL_API_KEY")
    
    try:
        translator = deepl.Translator(auth_key)
        result = translator.translate_text(text, source_lang=source_lang, target_lang=target_lang)
        return result.text
    except Exception as e:
        return f"Translation failed: {e}"

def translate_text(text: str, model: str = "jan-nano-4b-Q4_K_M.gguf") -> str:
    """
    Translates text using a URL-based translation service.

    Args:
        text: The text to translate.
        model: The model to use for translation.

    Returns:
        The translated text, or an error message if translation fails.
    """
    try:
        prompt = f"""
You are an expert translator specializing in manga. The following text is from a manga and was transcribed by an OCR engine, so it may contain typos or misrecognized characters. Your task is to first correct any typos in the source text and then translate it to English, preserving the original meaning and tone.

Source Text: "{text}"

Translation:"""

        messages = [
            {
                "role": "user",
                "content": "/no_think"
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        payload = {
            "messages": messages,
            "model": model
        }
        response = requests.post("http://localhost:8080/v1/chat/completions", json=payload)
        response.raise_for_status()  # Raise an exception for bad status codes
        content = response.json()["choices"][0]["message"]["content"]
        content = content.split("</think>")[-1]
        content = content.split("Translation:")[-1]
        content = str(content).strip()
        if content.startswith('"') and content.endswith('"'):
            content = content[1:-1]
        return content
    except Exception as e:
        return f"Translation failed: {e}"

def translate_texts(texts: list[str], model: str = "models/jan-nano-4b-Q4_K_M.gguf") -> list[str]:
    """
    Translates a list of texts using a URL-based translation service, maintaining context.

    Args:
        texts: A list of texts to translate.
        model: The model to use for translation.

    Returns:
        A list of translated texts.
    """
    if not texts:
        return []

    try:
        prompt = """
You are an expert translator specializing in manga. I will provide you with a list of text bubbles from a single page. Please translate each text bubble to English. The text was transcribed by an OCR engine and may contain typos. Use the context from other bubbles on the page to improve the translation.

Here are the text bubbles:
"""
        for i, text in enumerate(texts):
            prompt += f'{i+1}. "{text}"\n'
        
        prompt += "\nPlease provide the translations in the same order, one per line, without the numbers."

        messages = [
            {
                "role": "user",
                "content": "/no_think"
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        payload = {
            "messages": messages,
            "model": model
        }
        response = requests.post("http://localhost:8080/v1/chat/completions", json=payload)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        content = content.split("</think>")[-1].strip()

        if "Here are the translations:" in content:
            content = content.split("Here are the translations:")[1].strip()

        translated_texts = content.split('\n')
        translated_texts = [re.sub(r'^\d+\.\s*', '', txt).strip() for txt in translated_texts]
        
        # remove quotes
        translated_texts = [txt[1:-1] if txt.startswith('"') and txt.endswith('"') else txt for txt in translated_texts]

        if len(translated_texts) != len(texts):
            print(f"Warning: Bulk translation returned {len(translated_texts)} items, expected {len(texts)}. Falling back to individual translations.")
            return [translate_text(text) for text in texts]

        return translated_texts
    except Exception as e:
        print(f"Bulk translation failed: {e}. Falling back to individual translations.")
        return [translate_text(text) for text in texts]
