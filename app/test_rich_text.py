import unittest
from rich_text import validate_instruction

class InstructionSecurityTests(unittest.TestCase):
    def test_formatting_round_trip(self):
        value = '<h2>Техника</h2><p><strong>Спина</strong> <em>прямая</em></p><ol><li>Шаг 1</li></ol><ul><li>Совет</li></ul>'
        self.assertEqual(validate_instruction(value, 'html'), value)

    def test_active_content_and_attributes_removed(self):
        self.assertEqual(validate_instruction('<p onclick="bad()">Текст<img src=x onerror=bad()><script>bad()</script><svg onload=bad()></svg><iframe>bad()</iframe></p>', 'html'), '<p>Текст</p>')
        self.assertEqual(validate_instruction('<a href="javascript:bad()">Текст</a>', 'html'), 'Текст')

    def test_entities_stay_text(self):
        self.assertEqual(validate_instruction('&lt;script&gt;bad()&lt;/script&gt;', 'html'), '&lt;script&gt;bad()&lt;/script&gt;')

    def test_legacy_plain_text_is_unchanged(self):
        self.assertEqual(validate_instruction('Угол < 90°\nНовый абзац'), 'Угол < 90°\nНовый абзац')

    def test_empty_html_is_allowed(self):
        for value in ('', '<p><br></p>', '<script>bad()</script>'):
            self.assertEqual(validate_instruction(value, 'html'), '')

    def test_invalid_input_rejected(self):
        for value in ('x' * 20001, None):
            with self.subTest(value=str(value)[:20]), self.assertRaises(ValueError):
                validate_instruction(value, 'html')
        with self.assertRaises(ValueError):
            validate_instruction('Текст', 'unknown')

if __name__ == '__main__':
    unittest.main()
