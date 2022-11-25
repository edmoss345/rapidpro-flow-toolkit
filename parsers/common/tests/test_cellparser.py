import unittest
from typing import List

from parsers.common.cellparser import CellParser, get_object_from_cell_value, get_separators
from parsers.common.rowparser import ParserModel


class InnerModel(ParserModel):
    str_field: str

class OuterModel(ParserModel):
    inner: InnerModel
    strings: List[str]


class TestCellParser(unittest.TestCase):

    def setUp(self):
        self.parser = CellParser()

    def test_get_object_from_cell_value(self):
        obj = get_object_from_cell_value('condition;a|condition_type;has_any_word|condition_name;A')
        self.assertDictEqual(
            {'condition': 'a', 'condition_type': 'has_any_word', 'condition_name': 'A'},
            obj)

    def test_get_separators(self):
        s_1, s_2, s_3 = get_separators('|;::;|')
        self.assertEqual('|', s_1)
        self.assertEqual(';', s_2)
        self.assertEqual(':', s_3)

        s_1, s_2, s_3 = get_separators('|;|;|')
        self.assertEqual('|', s_1)
        self.assertEqual(';', s_2)
        self.assertIsNone(s_3)

        s_1, s_2, s_3 = get_separators('|:|:|')
        self.assertEqual('|', s_1)
        self.assertEqual(':', s_2)
        self.assertIsNone(s_3)

        s_1, s_2, s_3 = get_separators(';:;:')
        self.assertEqual(';', s_1)
        self.assertEqual(':', s_2)
        self.assertIsNone(s_3)

    def test_parse_as_string(self):
        out = self.parser.parse_as_string('plain string')
        self.assertEqual(out, 'plain string')
        out = self.parser.parse_as_string('{{var}} :)', context={'var' : 15})
        self.assertEqual(out, '15 :)')

        instance = OuterModel(strings=['a', 'b'], inner=InnerModel(str_field='xyz'))
        context = {'instance' : instance}
        out = self.parser.parse_as_string('{{instance.strings[1]}}', context=context)
        self.assertEqual(out, 'b')
        out = self.parser.parse_as_string('{{instance.inner.str_field}}', context=context)
        self.assertEqual(out, 'xyz')

    def test_parse(self):
        out = self.parser.parse('a;b;c')
        self.assertEqual(out, ['a', 'b', 'c'])

        context = {'list' : ['a', 'b', 'c']}
        out = self.parser.parse('{% for e in list %}{{e}}{% endfor %}', context=context)
        self.assertEqual(out, 'abc')
        # Templating comes first, only then splitting into a list
        out = self.parser.parse('{% for e in list %}{{e}};{% endfor %}', context=context)
        self.assertEqual(out, ['a', 'b', 'c', ''])

    def test_parse_native_type(self):
        out = self.parser.parse_as_string('{@(1,2,[3,"a"])@}')
        self.assertEqual(out, (1,2,[3,'a']))
        out = self.parser.parse_as_string('  {@(1,2,[3,"a"])@} ')
        self.assertEqual(out, (1,2,[3,'a']))
        out = self.parser.parse_as_string('{@ ( 1 , 2 , [ 3 , "a" ] ) @}')
        self.assertEqual(out, (1,2,[3,'a']))

        instance = OuterModel(strings=['a', 'b'], inner=InnerModel(str_field='xyz'))
        context = {'instance' : instance}
        out = self.parser.parse_as_string('{@instance@}', context=context)
        self.assertEqual(out, instance)
        out = self.parser.parse_as_string('{@instance.inner@}', context=context)
        self.assertEqual(out, instance.inner)
        out = self.parser.parse_as_string('{@instance.strings@}', context=context)
        self.assertEqual(out, ['a', 'b'])

        class TestObj:
            def __init__(self, value):
                self.value = value
        test_objs = [TestObj('1'), TestObj('2'), TestObj('A')]
        out = self.parser.parse_as_string('{@test_objs@}', context={'test_objs' : test_objs})
        self.assertEqual(out, test_objs)
        out = self.parser.parse_as_string('{@range(1,5)@}')
        self.assertEqual(out, range(1,5))