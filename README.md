# XC Strings Translator

## 1. Overview

XC Strings Translator is a command-line tool designed to automate the translation of Apple XC Strings files (Localizable.xcstrings). This JSON-based localization file format is used in macOS and iOS applications. The tool leverages the OpenAI GPT-3.5-turbo model to translate strings in batches, updates the source file in real time, avoids duplicate translations, and provides detailed debugging and token usage statistics.

## 2. Core Features
- **Automatic Translation:** Uses OpenAI's API to translate texts from the source language to multiple target languages.
- **Real-time File Update:** Updates the Localizable.xcstrings file after each batch translation to save progress and prevent duplicate work in case of interruptions.
- **Avoids Duplicate Translations:** Skips string entries that already have a non-empty translation for the target language.
- **Retry Mechanism:** If an API request fails (e.g., due to timeouts or 504 errors), the tool waits 3 seconds and retries (up to 3 times).
- **JSON-Based Communication:** Requests translations in JSON format to minimize formatting errors.
- **Debug Mode:** When enabled, prints detailed debugging information, including the generated prompt, raw API response, token usage details, and parsed translation results.
- **Token Usage Statistics:** Aggregates and displays the total tokens used during translation, helping you monitor API usage.

## 3. Installation

### Prerequisites
- Python 3.6 or higher
- pip (Python package installer)
- An OpenAI API key (set as the environment variable `OPENAI_API_KEY`)

### Installation Steps
1. **Clone the Repository or Download the Script:**

```bash
   git clone https://github.com/yourusername/xc-strings-translator.git
   cd xc-strings-translator
```

2.	Install Required Packages:
```bash
pip install openai
```

3.	Set Your OpenAI API Key:

```bash
export OPENAI_API_KEY=your_openai_api_key
```

## 4. Usage Guide

### Basic Command

Run the script from the command line as follows:

```bash
python script.py --file /path/to/Localizable.xcstrings --languages zh,fr,de --source-language en
```

#### Command Line Arguments

* --file: Path to the Localizable.xcstrings file (default: Localizable.xcstrings).
* --languages: Comma-separated list of target language codes (e.g., zh,fr,de).
* --source-language: Source language code; if not provided, the script uses the sourceLanguage value from the file (default: en).
* --openai-endpoint: (Optional) OpenAI API endpoint URL (default: https://api.openai.com/v1).
* --debug: Enable debug mode to print detailed debugging information (e.g., generated prompt, raw API response, and token usage details).

#### Languages:

el,he,hi,hu,id,it,ja,ko,ms,nb,pl,pt-BR,pt-PT,ro,ru,sk,sl,es,es-419,es-US,sv,th,tr,uk,vi,ar,ca,zh-HK,zh-Hans,zh-Hant,hr,cs,da,nl,en-AU,en-IN,en-GB,fi,fr-CA,de,zh

### Example

To translate an English Localizable.xcstrings file into Chinese, French, and German with debug information enabled, run:

```bash
python script.py --file ./Localizable.xcstrings --languages zh,fr,de --source-language en --debug
```

The script will:
1.	Parse the input JSON file.
2.	Determine which strings require translation.
3.	Send requests to the OpenAI API in batches (10 strings per batch), expecting JSON array responses.
4.	Update the Localizable.xcstrings file in real time, marking completed translations with "state": "translated".
5.	Print token usage statistics after processing all translations.

## 5. License

This project is licensed under the MIT License.