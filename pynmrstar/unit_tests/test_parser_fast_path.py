import copy
import os
import unittest

from pynmrstar import definitions, Entry, Saveframe, Loop
from pynmrstar.exceptions import ParsingError

our_path = os.path.dirname(os.path.realpath(__file__))


def state(entry):
    """Everything about an entry's saveframes and loops which adding tags affects."""

    return [(sf.name, sf.category, sf.tag_prefix, [list(t) for t in sf.tags], dict(sf._lc_tags),
             [(lp.category, list(lp.tags), lp.data, dict(lp._lc_tags)) for lp in sf]) for sf in entry]


def rebuild(entry):
    """Build a copy of an entry through the public API, adding every tag with add_tag()."""

    new_entry = Entry.from_scratch(entry.entry_id)
    for sf in entry:
        new_sf = Saveframe.from_scratch(sf.name)
        new_sf.add_tags([(f"{sf.tag_prefix}.{name}", value) for name, value in sf.tags])
        for lp in sf:
            new_loop = Loop.from_scratch()
            new_loop.add_tag([f"{lp.category}.{tag}" for tag in lp.tags])
            if lp.data:
                new_loop.add_data(copy.deepcopy(lp.data))
            new_sf.add_loop(new_loop)
        new_entry.add_saveframe(new_sf)
    return new_entry


class TestParserFastPath(unittest.TestCase):
    """The parser adds tags which Loop.add_tag() and Saveframe.add_tag() would accept unchanged
    without calling them. These check that the result is exactly what those methods produce,
    and that everything else is still handled (and rejected) by them."""

    def assert_same_as_api(self, star):
        entry = Entry.from_string(star)
        self.assertEqual(state(entry), state(rebuild(entry)))
        return entry

    def test_sample_files(self):
        for name in ['bmr15000_3.str', 'bmr15000_3_denormalized.str', 'dos.str', 'nonewlines.str',
                     'edge_cases.str']:
            with open(os.path.join(our_path, 'sample_files', name)) as star_file:
                self.assert_same_as_api(star_file.read())

    def test_tags_split_by_loops(self):
        entry = self.assert_same_as_api("data_1 save_a _A.Sf_category cat _A.Sf_framecode a "
                                        "loop_ _L.x _L.Y 1 2 stop_ _A.after 3 loop_ _M.z 4 stop_ _A.last 5 save_")
        self.assertEqual(entry['a'].category, 'cat')
        self.assertEqual(entry['a']['_A.After'], ['3'])
        self.assertEqual(entry['a']['_L'].tag_index('y'), 1)

    def test_unusual_tags(self):
        # Each of these needs Python's handling of tags, for at least one tag
        self.assert_same_as_api("data_1 save_a _A.Sf_category cat _A.é 1 _A.b 2 loop_ _L.é _L.x 1 2 stop_ save_")
        # Loop.add_tag() strips this from the tag name, as Python considers it whitespace
        self.assert_same_as_api("data_1 save_a _A.Sf_category cat _A.b 1 loop_ _L.x\x1c 1 stop_ save_")
        self.assert_same_as_api("data_1 save_a _A.Sf_category cat _A.b 2 loop_ _L.x _l.Y 1 2 stop_ save_")
        self.assert_same_as_api("data_1 save_a _A.Sf_category cat _A.b 2 loop_ _L.x _L.y 1 2 stop_ "
                                "loop_ _M.x _M.Y 1 2 stop_ save_")

    def test_rejected_tags(self):
        for star in ["data_1 save_a _A.b 1 _A.B 2 save_",
                     "data_1 save_a _A.b 1 loop_ _L.x 1 stop_ _A.B 2 save_",
                     "data_1 save_a _A.b 1 _a.c 2 save_",
                     "data_1 save_a _A.b 1 _A.? 2 save_",
                     "data_1 save_a _A.b 1 _A. 2 save_",
                     "data_1 save_a _A.b 1 _A.c.d 2 save_",
                     # Not whitespace to the tokenizer, but it is to Python's str.split()
                     "data_1 save_a _A.b\x1c 1 save_",
                     "data_1 save_a _A.b 1 loop_ _L.x _L.X 1 2 stop_ save_",
                     "data_1 save_a _A.b 1 loop_ _L.x _M.y 1 2 stop_ save_",
                     "data_1 save_a _A.b 1 loop_ _L.x _L.? 1 2 stop_ save_"]:
            with self.subTest(star=star):
                self.assertRaises(ParsingError, Entry.from_string, star)

    def test_sf_framecode(self):
        self.assert_same_as_api("data_1 save_a _A.Sf_framecode a _A.b 1 save_")
        with self.assertRaises(ParsingError):
            Entry.from_string("data_1 save_a _A.Sf_framecode b _A.c 1 save_", raise_parse_warnings=True)

    def test_null_values_respected(self):
        star = "data_1 save_a _A.b 1 _A.N/A 2 loop_ _L.x 1 stop_ save_"
        Entry.from_string(star)
        definitions.NULL_VALUES.append('N/A')
        try:
            self.assertRaises(ParsingError, Entry.from_string, star)
            self.assertRaises(ParsingError, Entry.from_string, "data_1 save_a _A.b 1 loop_ _L.N/A 1 stop_ save_")
        finally:
            definitions.NULL_VALUES.remove('N/A')

    def test_duplicate_saveframe_names(self):
        with self.assertRaises(ParsingError):
            Entry.from_string("data_1 save_a _A.b 1 save_ save_b _B.b 1 save_ save_a _C.b 1 save_")


if __name__ == '__main__':
    unittest.main()
