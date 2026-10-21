"""Trusted source resolvers rebuild scheduled notices under current domain authorization."""
import importlib
SOURCES={}
def register_notice_source(kind,validate):
    if not kind or len(kind)>80 or not callable(validate):raise ValueError('invalid_notice_source')
    if kind in SOURCES and SOURCES[kind] is not validate:raise ValueError('duplicate_notice_source')
    if len(SOURCES)>=16 and kind not in SOURCES:raise ValueError('notice_source_budget')
    SOURCES[kind]=validate

def notice_source(kind):
    for module in ('app.modules.reporting.notifications',):
        try:importlib.import_module(module)
        except ModuleNotFoundError as error:
            if error.name not in (module,module.rsplit('.',1)[0]):raise
    return SOURCES.get(kind)
