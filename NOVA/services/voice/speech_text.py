import re

from markdown_it import MarkdownIt


def prepare_speech_text(text: str) -> str:
    parser = MarkdownIt("commonmark")
    paragraphs = []
    for token in parser.parse(text or ""):
        if token.type != "inline":
            continue
        parts = []
        for child in token.children or []:
            if child.type in {"text", "code_inline"}:
                parts.append(child.content)
            elif child.type in {"softbreak", "hardbreak"}:
                parts.append(" ")
        paragraph = "".join(parts).strip()
        if paragraph:
            paragraphs.append(paragraph)
    cleaned = " ".join(part if part.endswith((".", "!", "?", ":", ";", ",")) else part + "." for part in paragraphs)
    cleaned = re.sub(r"https?://\S+", "the linked source", cleaned)
    cleaned = cleaned.replace("|", ", ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"\s+([,.!?;:])", r"\1", cleaned)
    cleaned = re.sub(r"([,;:])(?=[^\s\d/])", r"\1 ", cleaned)
    for abbreviation in ("CV", "API", "UI", "SQL", "AI"):
        cleaned = re.sub(rf"\b{abbreviation}\b", " ".join(abbreviation), cleaned)
    return cleaned