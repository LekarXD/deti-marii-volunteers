import re, sys, os
# print non-CSS lines that contain digits after stripping svg/style/class noise
f = sys.argv[1]
mode = sys.argv[2] if len(sys.argv) > 2 else 'digits'
lines = open(f, encoding='utf-8').read().split('\n')
se = next(i for i,l in enumerate(lines) if '</style>' in l)
for i,l in enumerate(lines[se+1:], start=se+2):
    s = re.sub(r'<svg\b.*?</svg>', '<svg/>', l)
    s = re.sub(r'\s(style|class|aria-hidden|viewBox|href|d|fill|stroke[-a-z]*|width|height|x|y|cx|cy|r|rx|points|transform|id|for|role|aria-hidden|aria-controls|aria-selected|aria-pressed|aria-current|aria-labelledby|aria-describedby|aria-expanded|tabindex|type|name)="[^"]*"', '', s)
    if mode == 'all' or re.search(r'\d', s):
        print(f'{i}: {s.strip()}')
