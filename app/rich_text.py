"""Allowlisted exercise instruction HTML; no attributes or embedded content."""
from html import escape
from html.parser import HTMLParser

ALLOWED = {'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'h2', 'h3', 'ul', 'ol', 'li', 'blockquote'}
BLOCKED = {'script', 'style', 'iframe', 'object', 'embed', 'svg', 'math', 'template', 'noscript'}

class InstructionHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.text = []
        self.stack = []
        self.blocked = []

    def handle_starttag(self, tag, attrs):
        if self.blocked:
            if tag in BLOCKED:
                self.blocked.append(tag)
            return
        if tag in BLOCKED:
            self.blocked.append(tag)
        elif tag in ALLOWED:
            if len(self.stack) >= 128:
                raise ValueError('Слишком сложное форматирование текста')
            self.parts.append('<' + tag + '>')
            if tag != 'br':
                self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag != 'br':
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.blocked:
            if tag == self.blocked[-1]:
                self.blocked.pop()
            return
        if tag in self.stack:
            while self.stack:
                current = self.stack.pop()
                self.parts.append('</' + current + '>')
                if current == tag:
                    break

    def handle_data(self, data):
        if not self.blocked:
            self.parts.append(escape(data))
            self.text.append(data)

def validate_instruction(value, format='text'):
    if not isinstance(value, str) or len(value) > 20000:
        raise ValueError('Техника выполнения: не более 20 000 символов')
    if format not in ('text', 'html'):
        raise ValueError('Неверный формат инструкции')
    if format == 'text':
        return value
    parser = InstructionHTML()
    parser.feed(value)
    parser.close()
    if not ''.join(parser.text).replace('\u200b', '').strip():
        return ''
    while parser.stack:
        parser.parts.append('</' + parser.stack.pop() + '>')
    return ''.join(parser.parts)
