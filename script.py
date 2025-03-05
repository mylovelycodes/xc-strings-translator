import os
import json
import openai
import argparse
import time

# Read OpenAI API key from the environment variable
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("The OPENAI_API_KEY environment variable is not set!")
openai.api_key = openai_api_key

def parse_xcstrings(file_path):
    """
    Parse the Localizable.xcstrings file (in XC Strings format) and return the entire JSON data.
    
    Expected file format example:
    {
      "version": "1.0",
      "sourceLanguage": "en",
      "strings": {
         "hello_world": {
           "shouldTranslate": true,
           "comment": "Here is a comment for the translator",
           "extractionState": "manual",
           "localizations": {
             "en": {
               "stringUnit": {
                 "state": "translated",
                 "value": "Hello World"
               }
             },
             "pl": { ... },
             "de": { ... }
           }
         },
         ...
      }
    }
    """
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON parsing error. Please check the file format: {e}")
    if not isinstance(data, dict) or "strings" not in data:
        raise ValueError("JSON format error: missing 'strings' field")
    return data

def get_source_text(key, entry, src_lang):
    """
    Get the source text for a given string entry.
    If the entry contains localizations[src_lang] with a valid stringUnit.value,
    return that value; otherwise, return the key itself.
    """
    if isinstance(entry, dict):
        locs = entry.get("localizations", {})
        if src_lang in locs and isinstance(locs[src_lang], dict):
            string_unit = locs[src_lang].get("stringUnit", {})
            if "value" in string_unit and string_unit["value"].strip():
                return string_unit["value"]
    return key

def translate_batch(texts, source_lang, target_lang, debug=False):
    """
    Construct a prompt from the list of texts (batch of 10 entries) and call the OpenAI API.
    The prompt instructs the model to return a JSON array of translation results (e.g.:
    ["Translation1", "Translation2", ...]). Returns a tuple of:
      - a list of translations (parsed from the JSON array)
      - a usage dict containing prompt_tokens, completion_tokens, and total_tokens.
    
    If the request fails (e.g., timeout, 504 error), wait 3 seconds and retry (up to 3 times).
    """
    prompt = (
        f"Please translate the following texts from {source_lang} to {target_lang}.\n"
        "Return the translation results as a JSON array, for example:\n"
        '["Translation1", "Translation2", ...]\n'
        "Ensure that the returned content is valid JSON and consists of only a JSON array.\n"
    )
    for idx, text in enumerate(texts):
        prompt += f"{idx + 1}. {text}\n"
    
    if debug:
        print("DEBUG: Prompt:")
        print(prompt)
    
    max_retries = 3
    attempt = 0
    while attempt < max_retries:
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a professional translation assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
            )
            break  # Exit loop if request succeeds
        except Exception as e:
            attempt += 1
            if debug:
                print("DEBUG: OpenAI API request failed with error:", e)
            if attempt < max_retries:
                print("Request failed, waiting 3 seconds before retrying...")
                time.sleep(3)
            else:
                raise e

    usage = response.get("usage", {})
    raw_translation = response["choices"][0]["message"]["content"].strip()
    
    if debug:
        print("DEBUG: API token usage:", usage)
        print("DEBUG: Raw translation result:")
        print(raw_translation)
    
    try:
        translations = json.loads(raw_translation)
        if not isinstance(translations, list):
            raise ValueError("The returned JSON is not an array")
    except Exception as e:
        if debug:
            print("DEBUG: JSON parsing failed:", e)
            print("DEBUG: Falling back to line-by-line splitting.")
        translations = []
        for line in raw_translation.splitlines():
            line = line.strip()
            if line:
                if line[0].isdigit() and len(line) > 1 and (line[1] == '.' or line[1] == ')'):
                    parts = line.split(maxsplit=1)
                    if len(parts) > 1:
                        line = parts[1]
                translations.append(line)
    if debug:
        print("DEBUG: Parsed translation results:", translations)
    return translations, usage

def update_localizations_for_language(data, translations, target_lang):
    """
    Update each string entry in the JSON data by adding or updating the translation for the given target language.
    The translation is stored under localizations[target_lang] with the state set to "translated".
    The translations parameter is a dictionary with keys as string keys and values as the translated text.
    """
    strings_dict = data.get("strings", {})
    for key, translated_text in translations.items():
        entry = strings_dict.get(key, {})
        if not isinstance(entry, dict):
            entry = {}
        localizations = entry.get("localizations", {})
        localizations[target_lang] = {
            "stringUnit": {
                "state": "translated",
                "value": translated_text
            }
        }
        entry["localizations"] = localizations
        strings_dict[key] = entry
    data["strings"] = strings_dict

def persist_file(file_path, data):
    """
    Write the JSON data back to the file in a formatted manner.
    """
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main():
    parser = argparse.ArgumentParser(
        description="Automatically translate texts in a Localizable.xcstrings file using OpenAI and update the file."
    )
    parser.add_argument("--file", type=str, default="Localizable.xcstrings",
                        help="Path to the Localizable.xcstrings file")
    parser.add_argument("--languages", type=str, default="zh,fr,de",
                        help="Target languages (comma-separated), e.g., zh,fr,de")
    parser.add_argument("--source-language", type=str, default="",
                        help="Source language code; if empty, the 'sourceLanguage' field in the file is used")
    parser.add_argument("--openai-endpoint", type=str, default="https://api.openai.com/v1",
                        help="OpenAI API endpoint (default: https://api.openai.com/v1)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode to print detailed information")
    args = parser.parse_args()

    # Configure OpenAI API endpoint
    openai.api_base = args.openai_endpoint

    file_path = args.file
    data = parse_xcstrings(file_path)
    source_lang = args.source_language or data.get("sourceLanguage", "en")
    print(f"Using source language: {source_lang}")

    strings_dict = data.get("strings", {})

    # Global token usage statistics
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0

    # Process each target language
    target_languages = [lang.strip() for lang in args.languages.split(",") if lang.strip()]
    for target_lang in target_languages:
        if target_lang == source_lang:
            print(f"Skipping source language {source_lang}")
            continue
        print(f"\nStarting translation for target language: {target_lang}")
        # Select keys to translate: skip entries with shouldTranslate=False or those already translated
        keys_to_translate = []
        source_texts = {}
        for key, entry in strings_dict.items():
            if isinstance(entry, dict) and entry.get("shouldTranslate") is False:
                continue
            if isinstance(entry, dict):
                locs = entry.get("localizations", {})
                if target_lang in locs:
                    existing_value = locs[target_lang].get("stringUnit", {}).get("value", "").strip()
                    if existing_value:
                        continue
            text = get_source_text(key, entry, source_lang)
            source_texts[key] = text
            keys_to_translate.append(key)

        total_keys = len(keys_to_translate)
        if total_keys == 0:
            print(f"All entries already have translations for {target_lang}, skipping.")
            continue

        print(f"Number of entries to translate: {total_keys}")
        translations_for_lang = {}
        for i in range(0, total_keys, 10):
            batch_keys = keys_to_translate[i:i+10]
            batch_texts = [source_texts[k] for k in batch_keys]
            print(f"Translating entries {i+1} to {min(i+10, total_keys)} for {target_lang}...")
            translated_batch, usage = translate_batch(batch_texts, source_lang, target_lang, debug=args.debug)
            total_prompt_tokens += usage.get("prompt_tokens", 0)
            total_completion_tokens += usage.get("completion_tokens", 0)
            total_tokens += usage.get("total_tokens", 0)
            for key, trans in zip(batch_keys, translated_batch):
                translations_for_lang[key] = trans
            update_localizations_for_language(data, translations_for_lang, target_lang)
            persist_file(file_path, data)
            print(f"Updated {min(i+10, total_keys)} entries, file written.")
            translations_for_lang = {}
        print(f"Translation for target language {target_lang} completed.")
    
    print("\nTranslation process completed!")
    print(f"Total tokens used: prompt={total_prompt_tokens}, completion={total_completion_tokens}, total={total_tokens}")

if __name__ == "__main__":
    main()