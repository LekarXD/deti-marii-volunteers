import sys
KIT = '/private/tmp/claude-501/-Users-iliapetri--claude-spares-spare-GxUBpt/91fc3645-2cae-45de-9eeb-32a080bb81c1/scratchpad/dm-canvas/kit/helmet.html'
kit = open(KIT, encoding='utf-8').read()
prefix = kit.split('</style>')[0]
for p in sys.argv[1:]:
    s = open(p, encoding='utf-8').read()
    if '<helmet>\n@@KIT_HELMET@@\n' not in s:
        print(p, 'no marker'); continue
    s = s.replace('<helmet>\n@@KIT_HELMET@@\n', prefix, 1)
    open(p, 'w', encoding='utf-8').write(s)
    print(p, 'assembled')
