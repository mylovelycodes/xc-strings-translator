import os
import json
import openai
import argparse
import time

# 从环境变量中读取 OpenAI API 密钥
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("OPENAI_API_KEY 环境变量未设置！")

openai.api_key = openai_api_key

def parse_xcstrings(file_path):
    """
    解析符合 XC Strings 格式的 Localizable.xcstrings 文件，返回整个 JSON 数据字典。
    示例格式：
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
        raise ValueError(f"解析 JSON 失败，请检查文件格式是否正确：{e}")
    if not isinstance(data, dict) or "strings" not in data:
        raise ValueError("JSON 格式错误，缺少 'strings' 字段")
    return data

def get_source_text(key, entry, src_lang):
    """
    获取单个字符串项的源文本：
      - 如果 entry 中存在 localizations[src_lang] 且有 stringUnit.value，则返回该值；
      - 否则返回 key 本身。
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
    将文本列表 texts（每批 10 个词条）构造成一个 prompt 调用 OpenAI 接口，
    要求模型以 JSON 数组格式返回翻译结果（例如：["翻译结果1", "翻译结果2", ...]），
    返回 (翻译结果列表, usage)：
      - 翻译结果列表：解析得到的 JSON 数组
      - usage：字典，包含 prompt_tokens、completion_tokens 和 total_tokens
    如果请求失败（超时、504 错误等），等待 3 秒后重试，最多重试 3 次。
    """
    prompt = (
        f"请将以下文本从{source_lang}翻译成{target_lang}。\n"
        "请以 JSON 数组形式返回翻译结果，例如：\n"
        '["翻译结果1", "翻译结果2", ...]\n'
        "确保返回的内容为有效的 JSON 格式，且只包含一个 JSON 数组。\n"
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
                    {"role": "system", "content": "你是一个专业翻译助手。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
            )
            break  # 请求成功，退出重试循环
        except Exception as e:
            attempt += 1
            if debug:
                print("DEBUG: 调用 OpenAI 接口失败，错误：", e)
            if attempt < max_retries:
                print("请求失败，等待 3 秒后重试...")
                time.sleep(3)
            else:
                raise e

    usage = response.get("usage", {})
    raw_translation = response["choices"][0]["message"]["content"].strip()
    
    if debug:
        print("DEBUG: API 返回的 token 使用情况：", usage)
        print("DEBUG: 原始翻译结果：")
        print(raw_translation)
    
    try:
        translations = json.loads(raw_translation)
        if not isinstance(translations, list):
            raise ValueError("返回的 JSON 不是数组")
    except Exception as e:
        if debug:
            print("DEBUG: JSON 解析失败：", e)
            print("DEBUG: 尝试按行拆分处理。")
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
        print("DEBUG: 解析后的翻译结果：", translations)
    return translations, usage

def update_localizations_for_language(data, translations, target_lang):
    """
    根据翻译结果 translations 更新 JSON 数据中每个字符串条目，
    在 localizations 下以 target_lang 为 key，写入翻译后的内容。
    translations 是一个字典，键为字符串 key，值为翻译后的文本。
    翻译完成后，将状态修改为 "translated"。
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
    将数据写回到文件中，格式化为 JSON。
    """
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main():
    parser = argparse.ArgumentParser(
        description="利用 OpenAI 自动翻译 Localizable.xcstrings 文件中的文本，并将翻译结果写入文件"
    )
    parser.add_argument("--file", type=str, default="Localizable.xcstrings",
                        help="Localizable.xcstrings 文件的路径")
    parser.add_argument("--languages", type=str, default="zh,fr,de",
                        help="目标语言，多个语言用逗号分隔，例如：zh,fr,de")
    parser.add_argument("--source-language", type=str, default="",
                        help="源语言代码；若为空则使用文件中的 'sourceLanguage' 字段")
    parser.add_argument("--openai-endpoint", type=str, default="https://api.openai.com/v1",
                        help="OpenAI 的 API endpoint，默认为 https://api.openai.com/v1")
    parser.add_argument("--debug", action="store_true", help="启用调试模式，打印更多调试信息")
    args = parser.parse_args()

    # 配置 OpenAI API endpoint
    openai.api_base = args.openai_endpoint

    file_path = args.file
    data = parse_xcstrings(file_path)
    source_lang = args.source_language or data.get("sourceLanguage", "en")
    print(f"使用源语言: {source_lang}")

    strings_dict = data.get("strings", {})

    # 统计全局 token 使用量
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0

    # 处理每个目标语言
    target_languages = [lang.strip() for lang in args.languages.split(",") if lang.strip()]
    for target_lang in target_languages:
        if target_lang == source_lang:
            print(f"跳过源语言 {source_lang}")
            continue
        print(f"\n开始翻译目标语言：{target_lang}")
        # 筛选需要翻译的 key：跳过 shouldTranslate=False 或已存在目标翻译的项
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
            print(f"所有条目已存在 {target_lang} 的翻译，跳过。")
            continue

        print(f"待翻译词条数量：{total_keys}")
        translations_for_lang = {}
        for i in range(0, total_keys, 10):
            batch_keys = keys_to_translate[i:i+10]
            batch_texts = [source_texts[k] for k in batch_keys]
            print(f"正在翻译第 {i+1} 到 {min(i+10, total_keys)} 个词条为 {target_lang}...")
            translated_batch, usage = translate_batch(batch_texts, source_lang, target_lang, debug=args.debug)
            total_prompt_tokens += usage.get("prompt_tokens", 0)
            total_completion_tokens += usage.get("completion_tokens", 0)
            total_tokens += usage.get("total_tokens", 0)
            for key, trans in zip(batch_keys, translated_batch):
                translations_for_lang[key] = trans
            update_localizations_for_language(data, translations_for_lang, target_lang)
            persist_file(file_path, data)
            print(f"已更新 {min(i+10, total_keys)} 个词条，写入文件。")
            translations_for_lang = {}
        print(f"目标语言 {target_lang} 翻译完成。")
    
    print("\n翻译完成！")
    print(f"累计使用 token：prompt={total_prompt_tokens}, completion={total_completion_tokens}, total={total_tokens}")

if __name__ == "__main__":
    main()
