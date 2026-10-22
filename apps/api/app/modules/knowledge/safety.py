"""Urgent child-safety disclosures in a volunteer's mentor question.

The volunteer UI turns ``urgent`` into «Скажи ведущей прямо сейчас» above the answer.
The rule is deliberately narrow: every pattern names harm done TO a child (or by a child
to themself), never ordinary behaviour such as a child hitting a table or taking offence.
«меня» counts only with plural forms («меня бьют» quotes the child); a singular
«девочка меня ударила» is usually the volunteer speaking about themself.
"""
import re

_CHILD = r"(?:его|ее|их)"
_ANY = r"(?:его|ее|их|меня|нас)"
_BEATEN = r"(?:бьют|били|избивают|избили|мучают|наказывают\s+ремнем)"
_OFFENDED = r"(?:обижают|обижали|издеваются|издевались)"
_ONE_HITS = r"(?:бьет|бил|била|избивает|избил|избила|мучает)"
_AT_HOME = r"(?:бьют|бьет|били|бил|била|обижа\w*|избива\w*|издева\w*)"

# Violence, abuse, being hit or hurt at home, sexual contact, self-harm, suicide and threats.
URGENT_PATTERNS = tuple(re.compile(pattern) for pattern in (
    rf"\b{_ANY}\s+(?:\S+\s+){{0,2}}{_BEATEN}|\b{_BEATEN}\s+(?:\S+\s+)?{_ANY}\b",       # «меня дома бьют», «бьют его»
    rf"\b{_CHILD}\s+(?:\S+\s+){{0,2}}{_OFFENDED}",                                    # «его обижают»
    rf"\b{_CHILD}\s+(?:\S+\s+){{0,2}}{_ONE_HITS}\b|\b{_ONE_HITS}\s+(?:\S+\s+)?{_CHILD}\b",  # «отчим её бьёт»
    rf"\b{_AT_HOME}\s+(?:\S+\s+){{0,2}}дома\b|\bдома\s+(?:\S+\s+){{0,2}}{_AT_HOME}",   # «обижают дома»
    r"\bизбива\w*|\bизбил\w*|\bпобо(?:и|ев|ями)\b|\bиздева\w*",
    r"\bнасили[еяюи]\w*|\bнасилу\w*|\bнасилов\w*|изнасил\w*|домога\w*|растл\w*|педофил\w*",
    r"сексуальн\w*|\bсекс\b|интимн\w*|порно\w*|\bтрога\w*\s+(?:\S+\s+){0,2}(?:под\s+одежд\w*|грудь|между\s+ног)",
    r"суицид\w*|самоубий\w*|покончи\w*\s+с\s+собой|покончу\s+с\s+собой|\bубить\s+себя|\bубью\s+себя|\bубьет\s+себя",
    r"не\s+хо(?:чу|чет|чется|тят)\s+(?:больше\s+)?жить|жить\s+не\s+хо(?:чу|чет|чется)|хо(?:чу|чет|тят)\s+умереть",
    r"\bреж(?:ет|у|ут)\s+себя|резать\s+себя|порезал\w*\s+себ\w*|порезы\s+на\s+(?:руках|руке|запясть\w*|ногах)|самоповрежд\w*|селфхарм|причиня\w*\s+себе\s+(?:боль|вред)",
    r"\bповеси(?:ться|тся|лся|лась)\b|выпрыгн\w*\s+из\s+окна|спрыгн\w*\s+с\s+крыши",
    r"угрожа\w*|грозит\w*\s+(?:убить|избить|побить|покалечить)|\bубь(?:ю|ет|ют)\s+(?:тебя|его|ее|их|меня)\b",
))


def is_urgent(text: str) -> bool:
    normalized = text.casefold().replace("ё", "е")
    return any(pattern.search(normalized) for pattern in URGENT_PATTERNS)
