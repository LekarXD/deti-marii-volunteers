"""Source-controlled transactional email purposes; not a user template transport."""
import importlib
from dataclasses import dataclass
from typing import Callable
@dataclass(frozen=True)
class EmailPurpose:
    validate:Callable
    render:Callable
    required_permission:str
PURPOSES:dict[str,EmailPurpose]={}
def register_email_purpose(name,*,validate,render,required_permission):
    if name in ('login','contact_change','register','password_reset','notification') or not name or not callable(validate) or not callable(render) or not required_permission:raise ValueError('invalid_email_purpose')
    prior=PURPOSES.get(name)
    if prior and prior.validate is not validate:raise ValueError('duplicate_email_purpose')
    if len(PURPOSES)>=8 and name not in PURPOSES:raise ValueError('email_purpose_budget')
    PURPOSES[name]=EmailPurpose(validate,render,required_permission)
def email_purpose(name):
    for module in ('app.modules.staff.delivery',):
        try:importlib.import_module(module)
        except ModuleNotFoundError as error:
            if error.name not in (module,module.rsplit('.',1)[0]):raise
    return PURPOSES.get(name)
