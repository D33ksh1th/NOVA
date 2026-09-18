import re
from urllib.parse import urldefrag

from services.agent_runtime.policy.url_policy import UrlPolicy, check_url


IMAGE_THUMBNAIL_HOSTS = frozenset({
    "external-content.duckduckgo.com",
    "tse1.mm.bing.net", "tse2.mm.bing.net", "tse3.mm.bing.net", "tse4.mm.bing.net",
    "ts1.mm.bing.net", "ts2.mm.bing.net", "ts3.mm.bing.net", "ts4.mm.bing.net",
})


def allowed_thumbnail(value: str) -> bool:
    return value.startswith("https://") and check_url(value, UrlPolicy(allow_domains=IMAGE_THUMBNAIL_HOSTS)).allowed


def image_matches_source(page: str, title: str, sources: list[dict], query: str) -> bool:
    ignored = {"a", "an", "and", "at", "by", "for", "from", "in", "is", "of", "on", "or", "the", "to", "with",
               "image", "images", "photo", "photos", "picture", "pictures", "home", "official", "website"}
    title_words = set(re.findall(r"\w+", title.casefold())) - ignored
    normalized_title = " ".join(re.findall(r"\w+", title.casefold()))
    for phrase in re.findall(r'"([^"\n]+)"', query):
        normalized_phrase = " ".join(re.findall(r"\w+", phrase.casefold()))
        if normalized_phrase and f" {normalized_phrase} " not in f" {normalized_title} ":
            return False
    for source in sources:
        if urldefrag(source["url"])[0] != urldefrag(page)[0]:
            continue
        source_words = set(re.findall(r"\w+", source["title"].casefold())) - ignored
        numbers = {word for word in source_words if word.isdecimal()}
        if source_words and len(source_words & title_words) >= min(2, len(source_words)) and numbers <= title_words:
            return True
    return False