import os
import deepl

def translate_text(text: str, source_lang: str = "ES", target_lang: str = "EN-US") -> str:
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