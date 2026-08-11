"""Тест на ABLOCK-маркер: проверяем что омоглифы и entity-рандомизация
не ломают <a> теги в HTML-телах."""
import sys
sys.path.insert(0, '.')

from core.content import _replace_homoglyphs, _randomize_html_entities

html = '''<div style="font-family: Arial; max-width: 560px; margin: 0 auto; padding: 20px;">
<p style="font-size: 15px;">hey John, I stumbled on your profile the other day and I kept thinking about it.</p>
<p style="font-size: 15px;">I can't explain it here. just see for yourself: <a href="https://example.com/link?ref=abc123" style="color: #1A73E8;">https://example.com/link?ref=abc123</a></p>
<p style="font-size: 14px; color: #888;">cheers, Jennifer</p>
<p style="font-size: 14px; color: #888;">btw: <a href="https://example.com/ps?id=xyz" style="color: #1A73E8;">https://example.com/ps?id=xyz</a></p>
</div>'''

print("=== ТЕСТ 1: Омоглифы ===")
for trial in range(20):
    result = _replace_homoglyphs(html)
    if '__ABLOCK' in result:
        print(f"  ❌ ПРОВАЛ (trial {trial}): маркер ABLOCK утёк!")
        # Найти где именно
        idx = result.find('__ABLOCK')
        print(f"     ...{result[max(0,idx-20):idx+30]}...")
        break
    if 'example.com' not in result:
        print(f"  ❌ ПРОВАЛ (trial {trial}): ссылка пропала!")
        break
else:
    print("  ✅ 20/20 — ABLOCK маркеры НЕ утекают, ссылки на месте")

print()
print("=== ТЕСТ 2: Entity Randomization ===")
for trial in range(20):
    result = _randomize_html_entities(html, rate=0.15)  # Высокий rate для надёжности теста
    if '__ENTPROT' in result:
        print(f"  ❌ ПРОВАЛ (trial {trial}): маркер ENTPROT утёк!")
        break
    if 'example.com' not in result:
        print(f"  ❌ ПРОВАЛ (trial {trial}): ссылка повреждена!")
        # Найти <a> тег
        import re
        a_tags = re.findall(r'<a[^>]*>.*?</a>', result, re.DOTALL)
        for t in a_tags:
            print(f"     Найден <a>: {t[:80]}")
        break
    # Проверяем что href не изменён
    if 'href="https://example.com/' not in result:
        print(f"  ❌ ПРОВАЛ (trial {trial}): href повреждён!")
        break
else:
    print("  ✅ 20/20 — entity рандомизация НЕ ломает <a> теги")

print()
print("=== ТЕСТ 3: Полный конвейер (омоглифы → entities) ===")
for trial in range(20):
    step1 = _replace_homoglyphs(html)
    step2 = _randomize_html_entities(step1, rate=0.10)
    if '__ABLOCK' in step2 or '__ENTPROT' in step2:
        print(f"  ❌ ПРОВАЛ (trial {trial}): маркер утёк в финальный результат!")
        break
    if 'example.com' not in step2:
        print(f"  ❌ ПРОВАЛ (trial {trial}): ссылка потеряна!")
        break
else:
    print("  ✅ 20/20 — полный конвейер работает корректно")
