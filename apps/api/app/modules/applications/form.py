"""Versioned source content and server validation, without an invented age gate."""
import json
import re
from datetime import date, datetime
from pathlib import Path
from app.core.errors import ApiError

FORM_VERSION = 5
FORM_VERSIONS = {version:json.loads(Path(__file__).with_name(f"form_v{version}.json").read_text()) for version in (4,5)}
FORM = FORM_VERSIONS[FORM_VERSION]
FIELDS = {field["id"]: field for step in FORM["steps"] for field in step["fields"]}


def visible(condition, answers):
    if not condition:
        return True
    actual = answers.get(condition["field"])
    expected = condition["value"]
    expected = expected if isinstance(expected, list) else [expected]
    actual = actual if isinstance(actual, list) else [actual]
    return bool(set(actual) & set(expected))


def labels(options):
    return [value["label"] if isinstance(value, dict) else value for value in options]


def validate_answers(answers, *, complete=False, form=None):
    fields = {field["id"]:field for step in (form or FORM)["steps"] for field in step["fields"]}
    errors = {}
    clean = {}
    for key, value in answers.items():
        if key not in fields:
            errors[key] = "Неизвестное поле"
            continue
        field = fields[key]
        kind = field["type"]
        if kind in ("tiles", "chips"):
            if not isinstance(value, list) or len(value) > 80 or any(not isinstance(v, str) or len(v) > 200 for v in value):
                errors[key] = "Выберите варианты из списка"
                continue
            value = list(dict.fromkeys(v.strip() for v in value if v.strip()))
        elif kind == "consent":
            if not isinstance(value, bool):
                errors[key] = "Выберите да или нет"
                continue
        else:
            if not isinstance(value, str) or len(value) > (4000 if kind == "textarea" else 320):
                errors[key] = "Проверьте значение поля"
                continue
            value = value.strip()
        clean[key] = value
    for key, field in fields.items():
        if not visible(field.get("showIf"), clean):
            clean.pop(key, None)
            continue
        value = clean.get(key)
        # Consent policy is checked separately from answers.
        if key in ("consentPD", "consentNews"):
            continue
        if complete and field.get("required") and not value:
            errors[key] = "Заполните поле" if field["type"] not in ("tiles", "select") else "Выберите вариант"
        if not value:
            continue
        options = labels(field.get("options", []))
        if field["type"] == "select" and value not in options:
            errors[key] = "Выберите вариант из списка"
        if field["type"] == "tiles":
            if any(v not in options for v in value):
                errors[key] = "Выберите вариант из списка"
            if set(value) & set(field.get("exclusive", [])) and len(value) > 1:
                errors[key] = "Этот вариант выбирается отдельно"
        if field["type"] == "chips":
            groups = [g for g in field.get("groups", []) if visible(g.get("showIf"), clean)]
            allowed = {v for group in groups for v in labels(group["options"])}
            if not field.get("allowOther") and any(v not in allowed for v in value):
                errors[key] = "Выберите доступный навык"
            known = {v for group in field.get("groups", []) for v in labels(group["options"])}
            clean[key] = [v for v in value if v in allowed or (field.get("allowOther") and v not in known)]
        if key == "birthdate":
            try:
                birth = date.fromisoformat(value) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else datetime.strptime(value, "%d.%m.%Y").date()
                if birth > date.today():
                    raise ValueError()
                clean[key] = birth.isoformat()
            except (ValueError, TypeError):
                errors[key] = "Введите настоящую дату рождения: ДД.ММ.ГГГГ"
        if key == "email" and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            errors[key] = "Проверьте электронную почту"
        if key == "phone":
            digits = re.sub(r"\D", "", value)
            if len(digits) != 11 or digits[0] not in "78":
                errors[key] = "Введите телефон: +7 (999) 123-45-67"
            else:
                clean[key] = "+7" + digits[1:]
        if key == "telegram" and not re.fullmatch(r"@?[A-Za-z0-9_]{5,32}", value):
            errors[key] = "Проверьте ник Telegram"
    if errors:
        raise ApiError(422, "validation_error", "Проверьте отмеченные поля", field_errors=errors)
    return clean
