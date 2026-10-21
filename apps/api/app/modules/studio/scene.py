"""Use the canonical P18A schemas; do not create a second backend scene grammar."""
import json
import os
from copy import deepcopy
from pathlib import Path
from functools import lru_cache
from jsonschema import Draft202012Validator, FormatChecker
from app.core.errors import ApiError

@lru_cache
def validator(name):
    explicit=os.getenv('OPORA_STUDIO_SCHEMA_ROOT')
    roots=[Path(explicit)] if explicit else [parent/'packages'/'studio-core' for parent in Path(__file__).resolve().parents]
    path=next((root/name for root in roots if (root/name).is_file()),None)
    if path is None:raise ApiError(503,'studio_schema_unavailable','Контракт сцены не установлен на сервере.')
    return Draft202012Validator(json.loads(path.read_text()),format_checker=FormatChecker())

def validate_scene(value):
    errors=sorted(validator('scene.schema.json').iter_errors(value),key=lambda e:list(map(str,e.path)))
    if errors:raise ApiError(422,'invalid_studio_scene','Проверьте композицию кадра.',field_errors={'.'.join(map(str,e.path)) or 'scene':e.message[:200] for e in errors[:10]})
    return deepcopy(value)

def validate_capture_plan(value):
    errors=list(validator('capture-plan.schema.json').iter_errors(value))
    if errors:raise ApiError(422,'invalid_capture_plan','План записи не соответствует контракту.')
    return deepcopy(value)
