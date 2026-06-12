#!/usr/bin/env python3
"""Step 15 release description and translation template generator."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


STEP_DIR_NAME = "15_sort_release_description"
SAFE_RE = re.compile(r"[^A-Za-z0-9_]+")
DEFAULT_OPENAI_MODEL = "gpt-5.5"

LANGUAGES: list[dict[str, str]] = [
    {"code": "en", "section": "English", "label": "English", "deepl": "EN-GB"},
    {"code": "zh_hans", "section": "Chinese_Simp", "label": "Chinese Simplified", "deepl": "ZH-HANS"},
    {"code": "zh_hant", "section": "Chinese_Trad", "label": "Chinese Traditional", "deepl": "ZH-HANT"},
    {"code": "ja", "section": "Japanese", "label": "Japanese", "deepl": "JA"},
    {"code": "ko", "section": "Korean", "label": "Korean", "deepl": "KO"},
    {"code": "de", "section": "German", "label": "German", "deepl": "DE"},
    {"code": "es", "section": "Spanish", "label": "Spanish", "deepl": "ES"},
    {"code": "fr", "section": "French", "label": "French", "deepl": "FR"},
    {"code": "pl", "section": "Polish", "label": "Polish", "deepl": "PL"},
    {"code": "pt", "section": "Portuguese", "label": "Portuguese", "deepl": "PT-PT"},
    {"code": "ru", "section": "Russian", "label": "Russian", "deepl": "RU"},
    {"code": "tr", "section": "Turkish", "label": "Turkish", "deepl": "TR"},
]

FEATURES: dict[str, list[str]] = {
    "en": [
        "Faceposing (includes eyes)",
        "Fingerposing",
        "Jigglebones",
        "Adjustable Bodygroups",
        "First person view model (c_arms)",
        "Friendly and Enemy NPCs found under [b]{work}[/b]",
        "Adjusted Hitboxes",
        "Realistic Ragdoll Parameters",
        "Ragdoll Physics for hair, clothes and skirt",
        "Optimized for NVIDIA RTX-Remix",
    ],
    "zh_hans": [
        "面部表情（包括眼睛）",
        "手指绑骨",
        "飘动骨骼",
        "可调整的身体组",
        "第一人称手臂模型 (c_arms)",
        "友好和敌对的NPC，在生成菜单的[b]{work}[/b]项目下",
        "正确的受击判定盒",
        "拟真的布娃娃参数",
        "头发，衣服，裙子的物理模型",
        "已对NVIDIA RTX-Remix优化",
    ],
    "zh_hant": [
        "臉部表情（包括眼睛）",
        "手指綁骨",
        "飄動骨骼",
        "可調整的身體組件",
        "第一人稱手臂模型 (c_arms)",
        "友好和敵對的NPC，在生成菜單的[b]{work}[/b]項目下",
        "正確的受擊判定盒",
        "擬真的布娃娃參數",
        "頭髮，衣服，裙子的物理模型",
        "已對NVIDIA RTX-Remix優化",
    ],
    "ja": [
        "フェイスポーズ（目を含む）",
        "フィンガーポーズ",
        "揺れ骨",
        "調整可能な身体部分",
        "ファーストパーソンアームモデル (c_arms)",
        "敵味方両方のNPC、[b]{work}[/b]タブで見つかります",
        "調整済みヒットボックス",
        "現実的なラグドールパラメーター",
        "髪、服、スカートの物理モデル",
        "NVIDIA RTX-Remixに最適化済み",
    ],
    "ko": [
        "얼굴 포징(눈 포함)",
        "손가락 포즈",
        "흔들리는 뼈대",
        "조정 가능한 신체 부위",
        "1인칭 팔 모델(c_arms)",
        "적과 아군 NPC, [b]{work}[/b] 탭에서 찾을 수 있습니다",
        "조정된 히트박스",
        "현실적인 래그돌 매개변수",
        "헤어, 의상 및 치마의 물리 모델",
        "NVIDIA RTX-Remix에 최적화됨",
    ],
}

HEADINGS = {
    "en": ("Features:", "Credits:", "Generated Content Disclosure:"),
    "zh_hans": ("此模组包含:", "参照与鸣谢:", "AI生成内容披露:"),
    "zh_hant": ("此模組包含:", "參照與鳴謝:", "AI生成內容揭露:"),
    "ja": ("このモジュールには以下の内容が含まれます:", "Credits:", "人工知能生成コンテンツの開示:"),
    "ko": ("이 모듈에는 다음이 포함됩니다:", "Credits:", "AI 생성 콘텐츠 공개:"),
}

DISCLOSURE = {
    "en": (
        "The author combined generative AI and precoded Python scripts, to port the model into Garry's Mod, refine screenshots and icons, "
        "and compose this addon description. The author reviewed and edited the content for quality assurance purpose only and could not "
        "prevent the potential deficiencies, misinformation and errors contained in the final product. If further information regarding "
        "the extent or nature of AI involvement is required, please comment to the corresponding author. Sincerely."
    ),
    "zh_hans": (
        "作者使用了生成式AI和预编写的Python脚本，将模型移植到 Garry's Mod 中，完善了截图和图标，并撰写了本模组说明。"
        "作者仅出于质量保证目的对内容进行了审核和编辑，无法避免最终产品中可能存在的纰漏、虚构信息和谬误。"
        "如需进一步了解人工智能参与制作的程度，请向作者留言。此致"
    ),
    "zh_hant": (
        "在本作品的準備過程中，作者使用了人工智慧和預先編寫的Python腳本，將模型移植到 Garry's Mod 中，完善了截圖和圖標，"
        "並撰寫了本模組說明。作者僅出於品質保證目的對內容進行了審核和編輯，無法避免最終產品中可能存在的紕漏、虛構資訊和謬誤。"
        "如需進一步了解人工智慧參與製作的程度，請向作者留言。此致"
    ),
    "ja": (
        "本作品の作成過程において、生成型人工知能、および事前に作成されたPythonスクリプトを使用し、モデルをGarry's Modに移植しました。"
        "また、スクリーンショットとアイコンを改善し、本コンポーネントの追加説明を執筆しました。著者は品質保証の目的でコンテンツの審査と編集を実施しましたが、"
        "最終製品に存在する可能性のある不備、虚偽の情報、誤りについては責任を負いかねます。人工知能の制作への関与の程度に関する詳細な情報が必要な場合は、著者にメッセージをお送りください。敬具"
    ),
    "ko": (
        "이 작품의 제작 과정에서 생성형 AI와 사전 작성된 Python 스크립트를 결합하여 모델을 Garry's Mod로 포팅하고, "
        "스크린샷과 아이콘을 개선하며, 이 애드온 설명을 작성했습니다. 저자는 품질 보증 목적으로 콘텐츠를 검토하고 편집했지만 "
        "최종 제품에 포함된 잠재적인 결함, 잘못된 정보 및 오류를 방지할 수 없었습니다. AI 참여의 범위나 성격에 대한 추가 정보가 필요한 경우 해당 저자에게 댓글을 남겨주세요. 감사합니다."
    ),
}

LANGUAGE_LIST = {
    "en": "Mod Description also available in Chinese (中文), English (English), French (Français), German (Deutsch), Japanese (日本語), Korean (한국어), Polish (Język Polski), Portuguese (Português), Spanish (Español), Turkish (Türkçe), and Russian (Русский)",
    "zh_hans": "模组描述也有中文（中文）、英语(English)、法语（Français）、德语、日语（日本語）、韩语（한국어）、波兰语（Język Polski）、葡萄牙语（Português），西班牙语（Español），土耳其语（Türkçe）和俄语（Русский）版本。如存在翻译错误的专有名词，请以英文版为准。",
    "zh_hant": "模組描述也有中文（中文）、英語(English)、法語（Français）、德語、日語（日本語）、韓語（한국어）、波蘭語（Język Polski）、葡萄牙語（Português），西班牙語（Español），土耳其語和俄語版本（Русский）。如有翻譯錯誤的專有名詞，請以英文版為準。",
}


def emit(message: str) -> None:
    print(f"[Step15 Release] {message}", flush=True)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def safe_slug(value: str, fallback: str = "model") -> str:
    text = SAFE_RE.sub("_", str(value or "").strip().lower())
    text = re.sub(r"_+", "_", text).strip("_")
    return text or fallback


def workspace_root_for_input(input_path: Path) -> Path:
    path = input_path.resolve()
    if path.is_file():
        path = path.parent
    if path.name == STEP_DIR_NAME:
        return path.parent
    if path.name == "14_sort_qc_compile":
        return path.parent
    if (path / "14_sort_qc_compile").exists():
        return path
    for parent in [path] + list(path.parents):
        if (parent / "14_sort_qc_compile").exists():
            return parent
    return path


def paths_for_input(input_path: Path) -> dict[str, Path]:
    workspace_root = workspace_root_for_input(input_path)
    output_dir = workspace_root / STEP_DIR_NAME
    return {
        "workspace_root": workspace_root,
        "step14_dir": workspace_root / "14_sort_qc_compile",
        "output_dir": output_dir,
        "analysis": output_dir / "release_description_analysis.json",
        "plan": output_dir / "release_description_plan.json",
        "report": output_dir / "release_description_report.json",
        "files": output_dir / "release_description_files.json",
        "translations": output_dir / "translations.json",
        "template": output_dir / "Translation Templates Write.txt",
        "log": output_dir / "release_description.log",
    }


def detect_step14_metadata(step14_dir: Path, workspace_root: Path) -> dict[str, Any]:
    plan = read_json(step14_dir / "qc_plan.json")
    report = read_json(step14_dir / "qc_report.json")
    files = read_json(step14_dir / "qc_files.json")
    warnings: list[str] = []
    if not plan:
        warnings.append("Step 14 plan was not found; only workspace-name defaults are available.")
    inputs = plan.get("inputs") if isinstance(plan.get("inputs"), dict) else {}
    addon_dir = str(report.get("addon_dir") or plan.get("addon_dir") or "")
    files_list = files.get("files") if isinstance(files.get("files"), list) else []
    has_carms = bool(inputs.get("step10_dir")) or any("c_arms" in str(row).lower() for row in files_list)
    has_vrd = bool(inputs.get("step11_vrd"))
    has_icons = bool(inputs.get("step13_dir"))
    return {
        "author": str(plan.get("author") or "sheepylord"),
        "character_category": str(plan.get("character_category") or ""),
        "category_readable": str(plan.get("category_readable") or plan.get("character_category") or ""),
        "model_name": str(plan.get("model_name") or safe_slug(workspace_root.name)),
        "display_name": str(plan.get("display_name") or plan.get("model_name") or workspace_root.name),
        "addon_dir": addon_dir,
        "has_carms": has_carms,
        "has_vrd": has_vrd,
        "has_icons": has_icons,
        "jiggle_count": int(report.get("jiggle_count", 0) or 0),
        "warnings": warnings,
    }


def default_plan(input_path: Path, overrides: dict[str, str] | None = None) -> dict[str, Any]:
    overrides = overrides or {}
    paths = paths_for_input(input_path)
    meta = detect_step14_metadata(paths["step14_dir"], paths["workspace_root"])
    character_name = overrides.get("character_name_readable") or meta.get("display_name") or paths["workspace_root"].name
    work_title = overrides.get("character_work_readable") or meta.get("category_readable") or meta.get("character_category") or ""
    author = overrides.get("author") or meta.get("author") or "sheepylord"
    model_creator = overrides.get("model_creator") or ""
    warnings = list(meta.get("warnings", []))
    if not model_creator:
        warnings.append("Model creator / rights holder is not set.")
    if not work_title:
        warnings.append("Source work title is not set.")
    if not meta.get("has_carms"):
        warnings.append("Step 10 c_arms output was not detected; c_arms feature text can be edited manually if needed.")
    if not meta.get("has_vrd"):
        warnings.append("Step 11 VRD output was not detected.")
    if not meta.get("has_icons"):
        warnings.append("Step 13 icon output was not detected.")
    return {
        "kind": "release_description",
        "step": 15,
        "input_path": str(input_path.resolve()),
        "workspace_root": str(paths["workspace_root"]),
        "output_dir": str(paths["output_dir"]),
        "character_name_readable": str(character_name),
        "character_work_readable": str(work_title),
        "author": str(author),
        "model_creator": model_creator,
        "quote_text": overrides.get("quote_text", ""),
        "quote_language": overrides.get("quote_language", "english"),
        "quote_author": overrides.get("quote_author", ""),
        "image_url": overrides.get("image_url", "https://i.imgur.com/fVVaDCS.gif"),
        "rtx_link": overrides.get("rtx_link", "https://github.com/SheepyLord/RTX-remix_GMod_Package"),
        "openai_model": overrides.get("openai_model") or os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        "description_en": overrides.get("description_en", ""),
        "quote_original_text": overrides.get("quote_original_text", ""),
        "translations": {lang["code"]: {"description": "", "quote_text": "", "quote_author": ""} for lang in LANGUAGES if lang["code"] != "en"},
        "operation": overrides.get("operation", "write"),
        "warnings": warnings,
        "detected": meta,
    }


def openai_key() -> str:
    return os.environ.get("MCI_SESSION_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""


def deepl_key() -> str:
    return (os.environ.get("MCI_SESSION_DEEPL_API_KEY") or os.environ.get("DEEPL_API_KEY") or "").strip()


def call_openai_description(plan: dict[str, Any]) -> str:
    key = openai_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    character = str(plan.get("character_name_readable") or "").strip()
    work = str(plan.get("character_work_readable") or "").strip()
    prompt = (
        "Create release-description metadata for a Garry's Mod PM/NPC addon. "
        "Return strict JSON only with keys: description_en, quote_text, quote_original_text, quote_author. "
        "description_en must be one concise English paragraph in this pattern when facts are knowable: "
        "[character name] ([original native name if known], [romanization/pronunciation if known], Lit. [literal meaning if known]) "
        "is a [role/type] in [source work]. [one short factual character description]. "
        "Do not invent uncertain lore; if exact native name, romanization, literal meaning, or role is unknown, omit that part naturally. "
        "quote_text should be an English translation of a short public-domain literary quote or an original thematic line that represents the character. "
        "quote_original_text should be the same quote in the character/work's native language when appropriate. "
        "quote_author should be the English attribution for a public-domain quote, or empty for an original line. "
        "Do not quote copyrighted game dialogue or song lyrics. "
        f"Character: {character}. Source work: {work}."
    )
    model = str(plan.get("openai_model") or os.environ.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL)
    payload = {
        "model": model,
        "input": prompt,
        # Reasoning models spend reasoning tokens from this budget, so keep
        # headroom above the expected visible output length.
        "max_output_tokens": 2000,
    }
    if re.match(r"^(gpt-5|o\d)", model):
        payload["reasoning"] = {"effort": "low"}
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = compact_error_body(exc.read())
        detail = f"OpenAI request failed: HTTP {exc.code} {exc.reason}; model={model}"
        if body:
            detail += f"; response={body}"
        raise RuntimeError(detail) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI request failed: network error: {exc.reason}; model={model}") from exc
    text = str(data.get("output_text") or "").strip()
    if text:
        parsed = extract_json_object(text)
        if parsed:
            apply_openai_metadata(plan, parsed)
            return cleanup_ai_text(str(parsed.get("description_en") or ""))
        return cleanup_ai_text(text)
    for item in data.get("output", []) if isinstance(data.get("output"), list) else []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
            if isinstance(content, dict) and content.get("text"):
                content_text = str(content.get("text"))
                parsed = extract_json_object(content_text)
                if parsed:
                    apply_openai_metadata(plan, parsed)
                    return cleanup_ai_text(str(parsed.get("description_en") or ""))
                return cleanup_ai_text(content_text)
    raise RuntimeError("OpenAI response did not contain output text.")


def apply_openai_metadata(plan: dict[str, Any], parsed: dict[str, Any]) -> None:
    quote_text = cleanup_ai_text(str(parsed.get("quote_text") or plan.get("quote_text") or ""))
    quote_original = str(parsed.get("quote_original_text") or plan.get("quote_original_text") or "").strip()
    quote_author = cleanup_ai_text(str(parsed.get("quote_author") or plan.get("quote_author") or ""))
    if quote_text:
        plan["quote_text"] = quote_text
    if quote_original:
        plan["quote_original_text"] = quote_original
    if quote_author:
        plan["quote_author"] = quote_author


def extract_json_object(text: str) -> dict[str, Any]:
    text = str(text or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def cleanup_ai_text(text: str) -> str:
    text = text.strip().strip("\"'")
    text = re.sub(r"\s+", " ", text)
    # Strip only trailing bracketed annotations (e.g. "[citation]"); the prompt
    # pattern legitimately contains '[' mid-text, so never cut at the first one.
    text = re.sub(r"\s*\[[^\]]*\]\s*$", "", text)
    return text.strip()


def deepl_endpoint(key: str) -> str:
    override = os.environ.get("DEEPL_API_URL", "").strip()
    if override:
        override = override.rstrip("/")
        return override if override.endswith("/v2/translate") else override + "/v2/translate"
    host = "api-free.deepl.com" if key.endswith(":fx") else "api.deepl.com"
    return f"https://{host}/v2/translate"


def compact_error_body(raw: bytes | str, limit: int = 700) -> str:
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="replace")
    else:
        text = str(raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def deepl_failure_message(exc: BaseException, endpoint: str, target_lang: str, source_lang: str, text_len: int) -> str:
    host = urllib.parse.urlparse(endpoint).netloc or endpoint
    source = source_lang or "auto"
    if isinstance(exc, urllib.error.HTTPError):
        body = compact_error_body(exc.read())
        detail = f"HTTP {exc.code} {exc.reason}".strip()
        if body:
            detail += f"; response={body}"
        return f"{detail}; endpoint={host}; source_lang={source}; target_lang={target_lang}; text_chars={text_len}"
    if isinstance(exc, urllib.error.URLError):
        return f"Network error: {exc.reason}; endpoint={host}; source_lang={source}; target_lang={target_lang}; text_chars={text_len}"
    return f"{exc}; endpoint={host}; source_lang={source}; target_lang={target_lang}; text_chars={text_len}"


def call_deepl(text: str, target_lang: str, source_lang: str = "EN") -> str:
    key = deepl_key()
    if not key:
        raise RuntimeError("DEEPL_API_KEY is not set.")
    text = str(text or "").strip()
    if not text:
        return ""
    endpoint = deepl_endpoint(key)
    payload_data = {"text": text, "target_lang": target_lang}
    source_lang = str(source_lang or "").strip().upper()
    if source_lang:
        payload_data["source_lang"] = source_lang
    payload = urllib.parse.urlencode(payload_data).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"DeepL-Auth-Key {key}"},
        method="POST",
    )
    attempts = 4
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
            break
        except Exception as exc:
            retryable = isinstance(exc, urllib.error.HTTPError) and (exc.code == 429 or exc.code >= 500)
            if retryable and attempt < attempts:
                delay = 2 ** attempt
                emit(f"DeepL HTTP {exc.code}; retrying in {delay}s (attempt {attempt}/{attempts - 1}).")
                time.sleep(delay)
                continue
            raise RuntimeError(deepl_failure_message(exc, endpoint, target_lang, source_lang, len(text))) from exc
    translations = data.get("translations")
    if isinstance(translations, list) and translations and isinstance(translations[0], dict):
        return str(translations[0].get("text") or "").strip()
    raise RuntimeError(
        f"DeepL response did not contain translated text; endpoint={urllib.parse.urlparse(endpoint).netloc}; "
        f"source_lang={source_lang or 'auto'}; target_lang={target_lang}; "
        f"response_keys={sorted(data.keys()) if isinstance(data, dict) else type(data).__name__}"
    )


def localized_static(code: str) -> tuple[list[str], tuple[str, str, str], str]:
    features = FEATURES.get(code, FEATURES["en"])
    headings = HEADINGS.get(code, HEADINGS["en"])
    disclosure = DISCLOSURE.get(code, DISCLOSURE["en"])
    return features, headings, disclosure


def title_for_language(plan: dict[str, Any], code: str, row: dict[str, Any] | None = None) -> str:
    work = str(plan.get("character_work_readable") or "").strip()
    character = str(plan.get("character_name_readable") or "").strip()
    title = f"{work} - {character}" if work else character
    if code == "en":
        return title
    translated_title = str((row or {}).get("title") or "").strip()
    return f"{translated_title} ({title})" if translated_title and translated_title != title else title


def section_for_language(plan: dict[str, Any], lang: dict[str, str]) -> str:
    code = lang["code"]
    row = plan.get("translations", {}).get(code) if isinstance(plan.get("translations"), dict) else {}
    row = row if isinstance(row, dict) else {}
    title = title_for_language(plan, code, row)
    description = str((plan.get("description_en") if code == "en" else row.get("description")) or "").strip()
    quote_text = str((plan.get("quote_text") if code == "en" else row.get("quote_text")) or "").strip()
    quote_original = str(plan.get("quote_original_text") or "").strip()
    quote_author = str((plan.get("quote_author") if code == "en" else row.get("quote_author")) or "").strip()
    work = str(plan.get("character_work_readable") or "").strip() or "the source work"
    author = str(plan.get("author") or "sheepylord").strip()
    model_creator = str(plan.get("model_creator") or "the original rights holder").strip()
    image_url = str(plan.get("image_url") or "").strip()
    rtx_link = str(plan.get("rtx_link") or "").strip()
    features, headings, disclosure = localized_static(code)
    lines: list[str] = [f"//{lang['section']} \n", f"{title} (PM & NPCs)\n", "\n"]
    lines.append((description or "[Description pending translation.]") + "\n\n")
    if quote_text:
        lines.append(f"[b]{quote_text}[/b]\n")
        if quote_original and quote_original != quote_text:
            lines.append(f"[b]{quote_original}[/b]\n")
        if quote_author:
            lines.append(f" --- {quote_author}\n")
    if image_url:
        lines.append(f"\n[img]{image_url}[/img]\n")
    if rtx_link:
        if code == "zh_hans":
            lines.append(f"\n对 RTX-Remix 感兴趣? 试试我的整合包 [url={rtx_link}] Github: RTX-remix_GMod_Package [/url]\n")
        elif code == "zh_hant":
            lines.append(f"\n對 RTX-Remix 感興趣? 可嘗試我的整合包 [url={rtx_link}] Github: RTX-remix_GMod_Package [/url]\n")
        else:
            lines.append(f"\nInterested in RTX-Remix? Try the snapshot package on [url={rtx_link}] Github: RTX-remix_GMod_Package [/url]\n")
    lines.append("\n" + LANGUAGE_LIST.get(code, LANGUAGE_LIST["en"]) + "\n")
    lines.append(f"\n[h1] {headings[0]} [/h1]\n")
    # The FEATURES lists are positionally parallel across languages:
    # index 2 = Jigglebones, 4 = c_arms, 8 = ragdoll physics for hair/clothes.
    # Drop lines only when Step 14 metadata positively says the feature is
    # absent; fail open (keep the line) when metadata is missing.
    detected = plan.get("detected") if isinstance(plan.get("detected"), dict) else {}
    skip_indexes: set[int] = set()
    if "has_carms" in detected and not detected.get("has_carms"):
        skip_indexes.add(4)
    if "jiggle_count" in detected and int(detected.get("jiggle_count") or 0) <= 0:
        skip_indexes.update({2, 8})
    for index, feature in enumerate(features):
        if index in skip_indexes:
            continue
        lines.append(f"- {feature.format(work=work)}\n")
    lines.append(f"\n[u]{headings[1]}[/u]\n")
    lines.append(f"- {plan.get('character_name_readable')} model by: {model_creator}\n")
    lines.append(f"- Mesh and textures edited by {author.title()}\n")
    lines.append(f"- Porting, rigging, modelling, facial shape keys, mesh edits, materials and compiling:  {author.title()}\n")
    lines.append(f"\n[u]{headings[2]}[/u]\n")
    lines.append(disclosure)
    return "".join(lines).rstrip() + "\n"


def build_template(plan: dict[str, Any]) -> str:
    return "\n".join(section_for_language(plan, lang) for lang in LANGUAGES)


def process_plan(plan: dict[str, Any]) -> dict[str, Any]:
    warnings = [str(item) for item in plan.get("warnings", []) if item] if isinstance(plan.get("warnings"), list) else []
    errors: list[str] = []
    operation = str(plan.get("operation") or "write")
    if not str(plan.get("character_name_readable") or "").strip():
        errors.append("Character name is required.")
    if not str(plan.get("character_work_readable") or "").strip():
        errors.append("Source work title is required.")
    if operation in {"generate_english", "all"}:
        try:
            emit("Requesting English description from ChatGPT/OpenAI.")
            plan["description_en"] = call_openai_description(plan)
            plan["description_source"] = "ChatGPT/OpenAI Responses API"
        except Exception as exc:
            warnings.append(f"OpenAI unavailable; English description remains manual: {exc}")
    if operation in {"translate", "all"}:
        if not str(plan.get("description_en") or "").strip():
            warnings.append("Description is empty; DeepL translation was skipped.")
        elif not deepl_key():
            warnings.append("DEEPL_API_KEY is not set; translations remain manual.")
        else:
            emit("Translating description and quote fields with DeepL.")
            translations = plan.setdefault("translations", {})
            if not isinstance(translations, dict):
                translations = {}
                plan["translations"] = translations
            for lang in LANGUAGES:
                if lang["code"] == "en":
                    continue
                row = translations.setdefault(lang["code"], {})
                if not isinstance(row, dict):
                    row = {}
                    translations[lang["code"]] = row
                try:
                    emit(f"Translating {lang['label']} with DeepL target {lang['deepl']}.")
                    row["deepl_target_lang"] = lang["deepl"]
                    row["description"] = call_deepl(str(plan.get("description_en") or ""), lang["deepl"], source_lang="EN")
                    title = title_for_language(plan, "en")
                    row["title"] = call_deepl(title, lang["deepl"], source_lang="EN") if title else ""
                    quote_original = str(plan.get("quote_original_text") or "").strip()
                    quote_english = str(plan.get("quote_text") or "").strip()
                    quote = quote_original or quote_english
                    quote_source = "native_auto" if quote_original else "english"
                    author = str(plan.get("quote_author") or "").strip()
                    row["quote_text"] = call_deepl(quote, lang["deepl"], source_lang="" if quote_original else "EN") if quote else ""
                    row["quote_source"] = quote_source
                    row["quote_author"] = call_deepl(author, lang["deepl"], source_lang="EN") if author else ""
                    row.pop("translation_error", None)
                    row["status"] = "translated_deepl"
                    emit(f"{lang['label']} translation finished.")
                except Exception as exc:
                    error_text = str(exc)
                    row["status"] = "translation_failed"
                    row["translation_error"] = error_text
                    emit(f"{lang['label']} translation failed: {error_text}")
                    warnings.append(f"{lang['label']} translation failed: {error_text}")
    plan["warnings"] = warnings
    return {"plan": plan, "warnings": warnings, "validation_errors": errors}


def file_entry(path: Path, stage: str, warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": path.name,
        "type": path.suffix.lstrip(".").lower() or "file",
        "size": path.stat().st_size if path.exists() else 0,
        "stage": stage,
        "path": str(path),
        "warnings": warnings or ([] if path.exists() else ["Missing output file."]),
    }


def analyze(input_path: Path, overrides: dict[str, str] | None, analysis_json: Path, plan_json: Path) -> dict[str, Any]:
    paths = paths_for_input(input_path)
    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    plan = default_plan(input_path, overrides)
    analysis = {
        "kind": "release_description_analysis",
        "input_path": str(input_path.resolve()),
        "workspace_root": str(paths["workspace_root"]),
        "step14_dir": str(paths["step14_dir"]),
        "output_dir": str(paths["output_dir"]),
        "languages": LANGUAGES,
        "environment": {
            "openai_key_available": bool(openai_key()),
            "deepl_key_available": bool(deepl_key()),
            "openai_model": plan.get("openai_model"),
        },
        "detected": plan.get("detected", {}),
        "warnings": plan.get("warnings", []),
        "validation_errors": [],
    }
    write_json(analysis_json, analysis)
    write_json(plan_json, plan)
    emit(f"Wrote Step 15 analysis and plan: {paths['output_dir']}")
    return {"analysis": analysis, "plan": plan}


def generate(plan_json: Path, report_json: Path, files_json: Path) -> dict[str, Any]:
    if not plan_json.exists():
        raise FileNotFoundError(plan_json)
    plan = read_json(plan_json)
    result = process_plan(plan)
    output_dir = Path(str(plan.get("output_dir") or plan_json.parent))
    output_dir.mkdir(parents=True, exist_ok=True)
    template_path = output_dir / "Translation Templates Write.txt"
    translations_path = output_dir / "translations.json"
    template = build_template(plan)
    template_path.write_text(template, encoding="utf-8")
    write_json(translations_path, {"languages": LANGUAGES, "translations": plan.get("translations", {})})
    write_json(plan_json, plan)
    report = {
        "kind": "release_description_report",
        "input_path": plan.get("input_path", ""),
        "output_dir": str(output_dir),
        "template": str(template_path),
        "translations": str(translations_path),
        "operation": plan.get("operation", "write"),
        "description_source": plan.get("description_source", "manual"),
        "warnings": result["warnings"],
        "validation_errors": result["validation_errors"] + ([] if template_path.exists() else ["Translation template was not written."]),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    write_json(report_json, report)
    files = {"files": [file_entry(template_path, "template"), file_entry(translations_path, "translations"), file_entry(report_json, "report"), file_entry(plan_json, "plan")]}
    write_json(files_json, files)
    emit(f"Wrote release description template: {template_path}")
    return {"report": report, "files": files, "plan": plan}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["analyze", "generate"], required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--analysis-json", type=Path)
    parser.add_argument("--plan-json", type=Path, required=True)
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--files-json", type=Path)
    parser.add_argument("--character-name", default="")
    parser.add_argument("--work-title", default="")
    parser.add_argument("--author", default="")
    parser.add_argument("--model-creator", default="")
    parser.add_argument("--quote-text", default="")
    parser.add_argument("--quote-original-text", default="")
    parser.add_argument("--quote-language", default="")
    parser.add_argument("--quote-author", default="")
    parser.add_argument("--image-url", default="")
    parser.add_argument("--rtx-link", default="")
    parser.add_argument("--openai-model", default="")
    return parser.parse_args()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    args = parse_args()
    if args.mode == "analyze":
        overrides = {
            "character_name_readable": args.character_name,
            "character_work_readable": args.work_title,
            "author": args.author,
            "model_creator": args.model_creator,
            "quote_text": args.quote_text,
            "quote_original_text": args.quote_original_text,
            "quote_language": args.quote_language,
            "quote_author": args.quote_author,
            "image_url": args.image_url,
            "rtx_link": args.rtx_link,
            "openai_model": args.openai_model,
        }
        overrides = {key: value for key, value in overrides.items() if value}
        if not args.analysis_json:
            raise SystemExit("--analysis-json is required in analyze mode")
        analyze(args.input, overrides, args.analysis_json, args.plan_json)
        return 0
    if not args.report_json or not args.files_json:
        raise SystemExit("--report-json and --files-json are required in generate mode")
    generate(args.plan_json, args.report_json, args.files_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
