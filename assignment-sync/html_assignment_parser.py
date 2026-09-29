import json
import os
import re
from datetime import datetime
from html import unescape
from pathlib import Path
from google import genai

import config


ASSIGNMENT_FIELDS = ("title", "due", "description", "course", "link")


def load_html_inputs(paths):
    pages = []
    for path in paths:
        html_path = Path(path)
        pages.append({
            "source": str(html_path),
            "html": html_path.read_text(encoding="utf-8"),
        })
    return pages


def extract_assignments_from_pages(pages):
    assignments = []
    for page in pages:
        page_assignments = extract_assignments_from_html(
            page["html"],
            source=page["source"],
        )
        assignments.extend(page_assignments)
        print(f"  Found {len(page_assignments)} possible assignments in: {page['source']}")
    return assignments


def extract_assignments_from_html(html, source="Unknown source"):
    text = html_to_text(html)

    if config.USE_AI_PARSER:
        ai_results = parse_with_ai(text, source)
        print(ai_results)
        if ai_results:
            print(normalize_assignments(ai_results, source))
            return normalize_assignments(ai_results, source)

    heuristic_results = parse_with_heuristics(text, source)
    return normalize_assignments(heuristic_results, source)


def html_to_text(html):
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("BeautifulSoup not found, using regex-based HTML to text conversion. ")
        without_scripts = re.sub(
            r"<(script|style|noscript).*?</\1>",
            "",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        text = re.sub(r"<[^>]+>", "\n", without_scripts)
        return "\n".join(
            line.strip()
            for line in unescape(text).splitlines()
            if line.strip()
        )

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    return "\n".join(
        line.strip()
        for line in soup.get_text("\n").splitlines()
        if line.strip()
    )


def parse_with_ai(text, source):
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    response = client.models.generate_content(
        model = "gemma-4-31b-it",
        contents =
        "Extract homework assignments from webpage text. "
        "Return only JSON with an 'assignments' array. Each item must have "
        "title, due, description, course, and link. Use null when unknown."
        "Don't include the word json in the beginning of your response.\n\n"
        f"Source: {source}\n\nPage text:\n{text[:config.MAX_HTML_TEXT_CHARS]}"
    )
    # response = ollama.chat(
    #     model="mistral",
        # messages=[
        #     {
        #         "role": "system",
        #         "content": "You are a JSON extraction assistant. Return ONLY valid JSON, no explanations."
        #     },
        #     {
        #         "role": "user",
        #         "content": f"""Extract homework assignments from this text. Return ONLY this JSON structure:
        #         {{
        #             "assignments": [
        #                 {{
        #                     "title": "name",
        #                     "due_date": "YYYY-MM-DD",
        #                     "course": "code",
        #                     "description": "text"
        #                 }}
        #             ]
        #         }}

        #         Text: {text[:config.MAX_HTML_TEXT_CHARS]}"""
        #                     },
        #                 ])
    # response_1 = client.chat.completions.create(
    #     model=config.OPENAI_MODEL,
    #     temperature=0,
    #     messages=[
    #         {
    #             "role": "system",
    #             "content": (
    #                 "Extract homework assignments from webpage text. "
    #                 "Return only JSON with an 'assignments' array. Each item must have "
    #                 "title, due, description, course, and link. Use null when unknown."
    #             ),
    #         },
    #         {
    #             "role": "user",
    #             "content": f"Source: {source}\n\nPage text:\n{text[:config.MAX_HTML_TEXT_CHARS]}",
    #         },
    #     ],
    # )
    client.close()

    try:
        data = json.loads(response.text)
    except json.JSONDecodeError:
        print("AI parser returned invalid JSON:")
        print(response.text)
        return []
    
    return data.get("assignments", [])


def parse_with_heuristics(text, source):
    lines = text.splitlines()
    assignments = []

    for index, line in enumerate(lines):
        due_dt = find_due_date(line)
        if not due_dt:
            continue

        title = find_nearby_title(lines, index)
        description = find_nearby_description(lines, index)
        course = find_course_name(lines)

        assignments.append({
            "title": title or "Untitled assignment",
            "due": due_dt.isoformat(),
            "description": description,
            "course": course,
            "link": source,
        })

    return assignments


def find_due_date(text):
    due_patterns = [
        r"(?:due|deadline|closes|available until|until)\s*:?\s*(.+)",
        r"(.+\b(?:AM|PM|am|pm)\b)",
        r"(\b\d{1,2}/\d{1,2}/\d{2,4}\b.*)",
    ]

    for pattern in due_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        try:
            return parse_fuzzy_date(match.group(1))
        except (ValueError, OverflowError):
            continue

    return None


def find_nearby_title(lines, due_index):
    for index in range(due_index - 1, max(due_index - 6, -1), -1):
        candidate = lines[index].strip()
        if looks_like_title(candidate):
            return candidate
    return None


def looks_like_title(text):
    if len(text) < 3 or len(text) > 120:
        return False
    lowered = text.lower()
    ignored = ("due", "deadline", "points", "grade", "submitted", "available")
    return not any(word in lowered for word in ignored)


def find_nearby_description(lines, due_index):
    description_lines = []
    for index in range(due_index + 1, min(due_index + 4, len(lines))):
        candidate = lines[index].strip()
        if candidate and not find_due_date(candidate):
            description_lines.append(candidate)
    return " ".join(description_lines) or None


def find_course_name(lines):
    for line in lines[:20]:
        lowered = line.lower()
        if "course" in lowered or "class" in lowered:
            return line
    return "Unknown Course"


def normalize_assignments(raw_assignments, source):
    normalized = []
    for item in raw_assignments:
        due_dt = parse_due_value(item.get("due"))
        if not due_dt:
            continue

        normalized.append({
            "name": item.get("title") or item.get("name") or "Untitled assignment",
            "due": due_dt,
            "description": item.get("description") or "",
            "course": item.get("course") or "Unknown Course",
            "link": item.get("link") or source,
            "source": source,
        })

    return dedupe_assignments(normalized)


def parse_due_value(value):
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return parse_fuzzy_date(str(value))
    except (ValueError, OverflowError):
        print(f"Could not parse due date: {value}")
        return None


def parse_fuzzy_date(value):
    try:
        import importlib
        date_parser = importlib.import_module("dateutil.parser")
    except Exception:
        print("dateutil not found, using limited standard library date parsing. ")
        return parse_with_standard_library(value)

    return date_parser.parse(value, fuzzy=True)


def parse_with_standard_library(value):
    cleaned = value.strip().replace("Z", "+00:00")
    formats = [
        "%B %d, %Y %I:%M %p",
        "%b %d, %Y %I:%M %p",
        "%B %d %Y %I:%M %p",
        "%b %d %Y %I:%M %p",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%y %I:%M %p",
        "%m/%d/%Y",
        "%m/%d/%y",
    ]

    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        pass

    for date_format in formats:
        try:
            return datetime.strptime(cleaned, date_format)
        except ValueError:
            continue

    raise ValueError(f"Could not parse date: {value}")


def dedupe_assignments(assignments):
    seen = set()
    unique = []
    for assignment in assignments:
        key = (
            assignment["name"].strip().lower(),
            assignment["course"].strip().lower(),
            assignment["due"].isoformat(),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(assignment)
    return unique
