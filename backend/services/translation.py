from google.cloud import translate_v2 as translate

def detect_language(text: str) -> str:
    """
    Detect the language of a given text.
    
    Args:
        text: The text to analyze
        
    Returns:
        Language code (e.g., 'si' for Sinhala, 'en' for English)
    """
    client = translate.Client()
    
    result = client.detect_language(text)
    return result['language']


def translate_text(text: str, target_language: str = "en") -> dict:
    """
    Translate text to the target language.
    
    Args:
        text: The text to translate
        target_language: Target language code (default: 'en' for English)
        
    Returns:
        dict with translated text and source language
    """
    client = translate.Client()
    
    # Detect source language
    detection = client.detect_language(text)
    source_language = detection['language']
    
    # If already in target language, return original
    if source_language == target_language:
        return {
            "translated_text": text,
            "source_language": source_language,
            "target_language": target_language,
            "is_translated": False
        }
    
    # Translate
    result = client.translate(text, target_language=target_language)
    
    return {
        "translated_text": result['translatedText'],
        "source_language": source_language,
        "target_language": target_language,
        "is_translated": True
    }


def translate_sinhala_to_english(text: str) -> dict:
    """
    Convenience function to translate Sinhala to English.
    
    Args:
        text: Sinhala text to translate
        
    Returns:
        dict with translated text and metadata
    """
    return translate_text(text, target_language="en")


def translate_english_to_sinhala(text: str) -> dict:
    """
    Convenience function to translate English to Sinhala.
    
    Args:
        text: English text to translate
        
    Returns:
        dict with translated text and metadata
    """
    return translate_text(text, target_language="si")
