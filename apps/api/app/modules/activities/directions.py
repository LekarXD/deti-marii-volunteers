"""Questionnaire directions and skills shared by the role directory and event ranking."""
import json
from functools import lru_cache
from pathlib import Path

FORM = Path(__file__).resolve().parents[1] / 'applications' / 'form_v5.json'
UNKNOWN_DIRECTION = 'Пока не знаю'
# Version 4 had one specialist tile; it is the same direction as the current one.
LEGACY_DIRECTIONS = {'Как специалист': 'Юрист, IT, маркетинг'}


def _field(form, field_id):
    stack = [form]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if item.get('id') == field_id:
                return item
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    raise LookupError(field_id)


@lru_cache
def matching_options():
    form = json.loads(FORM.read_text(encoding='utf-8'))
    directions = [option['label'] for option in _field(form, 'directions')['options'] if option['label'] != UNKNOWN_DIRECTION]
    skills = [option['label'] for group in _field(form, 'skills')['groups'] for option in group['options']]
    return {'directions': directions, 'skills': list(dict.fromkeys(skills))}


def answer_directions(answers):
    values = answers.get('directions') or []
    if isinstance(values, str):
        values = [values]
    return {LEGACY_DIRECTIONS.get(value, value) for value in values if isinstance(value, str)}


def answer_skills(answers):
    # Free-text «other» skills are never compared with authored role skills.
    known = set(matching_options()['skills'])
    values = answers.get('skills') or []
    if isinstance(values, str):
        values = [values]
    return {value for value in values if isinstance(value, str) and value in known}
