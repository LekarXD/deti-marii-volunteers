"""Compile authored form fields to the shared prototype controls."""
from html import escape, unescape
import json
import re


def enhance_controls(body, logic, src):
    fields = []

    def attributes(raw):
        return dict(re.findall(r'([\w-]+)="([^"]*)"', raw))

    def binding(raw):
        match = re.fullmatch(r'\{\{([\w.]+)\}\}', raw)
        if not match:
            raise ValueError('Controls require a bound value and handler: ' + raw)
        return match[1]

    def label_for(id):
        match = re.search(r'<label\b[^>]*for="' + re.escape(id) + r'"[^>]*>(.*?)</label>', body, re.S)
        if not match:
            raise ValueError('Control needs a label: ' + id)
        return unescape(re.sub('<[^>]+>', '', match[1]))

    def compile_select(match):
        attrs = attributes(match[1])
        id = attrs['id']
        key = 'ui_' + id.replace('-', '_')
        options = []
        for raw, text in re.findall(r'<option([^>]*)>(.*?)</option>', match[2], re.S):
            title = unescape(text)
            options.append({'id': unescape(attributes(raw).get('value', title)), 'title': title})
        fields.append({'key': key, 'id': id, 'label': label_for(id), 'value': binding(attrs['value']), 'change': binding(attrs['onChange']), 'options': options, 'kind': 'select'})
        return f'''<div class="ui-choice" onKeyDown="{{{{{key}.key}}}}" onBlur="{{{{{key}.blur}}}}"><button type="button" class="input c-trigger" id="{id}" aria-haspopup="listbox" aria-expanded="{{{{{key}.expanded}}}}" aria-controls="{id}-options" onClick="{{{{{key}.toggle}}}}"><span>{{{{{key}.title}}}}</span><span class="c-chevron"></span></button><sc-if value="{{{{{key}.open}}}}"><div class="c-menu" id="{id}-options" role="listbox" aria-label="{escape(label_for(id), quote=True)}"><sc-for list="{{{{{key}.options}}}}" as="o"><button type="button" class="{{{{o.cls}}}}" role="option" aria-selected="{{{{o.selected}}}}" onClick="{{{{o.pick}}}}">{{{{o.title}}}}</button></sc-for></div></sc-if></div>'''

    def compile_date(match):
        attrs = attributes(match[0])
        id = attrs['id']
        key = 'ui_' + id.replace('-', '_')
        fields.append({'key': key, 'id': id, 'label': label_for(id), 'value': binding(attrs['value']), 'change': binding(attrs['onChange']), 'kind': 'date'})
        return f'''<button type="button" class="input c-trigger" id="{id}" aria-haspopup="dialog" onClick="{{{{{key}.open}}}}"><span>{{{{{key}.title}}}}</span>ICON_CALENDAR</button>'''

    body = re.sub(r'<select\b([^>]*)>(.*?)</select>', compile_select, body, flags=re.S)
    body = re.sub(r'<input\b(?=[^>]*type="date")[^>]*>', compile_date, body)
    if not fields:
        return body, logic
    logic = logic.replace('class Component extends DCLogic', 'class Component extends FormControls', 1)
    logic = logic.replace('renderVals()', 'screenVals()', 1)
    logic = 'const UI_FIELDS = ' + json.dumps(fields, ensure_ascii=False) + ';\n' + (src/'form-controls.js').read_text() + '\n' + logic
    if any(f['kind'] == 'date' for f in fields):
        body += '\n' + (src/'date-picker.html').read_text()
    return body, logic
