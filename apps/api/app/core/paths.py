"""Public paths use trusted deployment configuration, never forwarded/user headers."""
import re

def normalize_mount_prefix(value):
    if value in ('','/'):return ''
    if not isinstance(value,str) or len(value)>200:raise ValueError('Invalid app mount prefix')
    value=value.removesuffix('/')
    if not re.fullmatch(r'/(?:[A-Za-z0-9][A-Za-z0-9_-]{0,63})(?:/[A-Za-z0-9][A-Za-z0-9_-]{0,63})*',value):raise ValueError('Invalid app mount prefix')
    return value

def public_path(path):
    if not isinstance(path,str) or not path.startswith('/') or path.startswith('//'):raise ValueError('An app-local absolute path is required')
    from .config import get_settings
    prefix=get_settings().app_mount_prefix
    if not prefix or path==prefix or path.startswith(prefix+'/'):return path
    return prefix+path
