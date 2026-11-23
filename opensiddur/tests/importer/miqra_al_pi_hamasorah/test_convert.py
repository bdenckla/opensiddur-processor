import json
import unittest
from pathlib import Path
from unittest.mock import patch
import tempfile


from opensiddur.importer.miqra_al_pi_hamasorah.convert import (
    _book_name_he,
    front_matter,
    load_source,
    main,
    read_attributions,
)

COMMIT = "0123456789abcdef0123456789abcdef01234567"

LICENSE = """----
Attribution:

Attribution in English and all languages other than Hebrew shall be to "Hebrew Wikisource" (or an equivalent translation) with a direct link to the following page:

[Miqra according to the Masorah](https://en.wikisource.org/wiki/User:Dovi/Miqra_according_to_the_Masorah#beginning)

----
ייחוס:

הייחוס בעברית יהיה ל"ויקיטקסט" ביחד עם קישור ישיר לדף שבקישור הבא:

[מקרא על פי המסורה](https://he.wikisource.org/wiki/%D7%9E%D7%A7%D7%A8%D7%90#%D7%A8%D7%90%D7%A9)
"""


def _book39(book24_name: str, chapters: dict, sub_book_name: str | None = None) -> dict:
    return {
        "book24_name": book24_name,
        "sub_book_name": sub_book_name,
        "good_ending_plus": None,
        "chapters": chapters,
    }


def _write_source(sourcetexts_root: Path, files: dict[str, list[dict]]) -> None:
    """A miniature MAM-parsed plus download: a manifest, MAM's licence and the given files."""
    data_dir = sourcetexts_root / "miqra_al_pi_hamasorah"
    (data_dir / "plus").mkdir(parents=True, exist_ok=True)
    (data_dir / "manifest.json").write_text(
        json.dumps({"repository": "bdenckla/MAM-basics", "commit": COMMIT, "plus_path": "MAM-parsed/plus"}),
        encoding="utf-8",
    )
    (data_dir / "LICENSE.md").write_text(LICENSE, encoding="utf-8")
    for name, book39s in files.items():
        (data_dir / "plus" / name).write_text(
            json.dumps({"header": {}, "book39s": book39s}, ensure_ascii=False), encoding="utf-8"
        )


def _verse(text: list, nav: list | None = None, label: list | None = None) -> list:
    return [nav or ["__"], label or [], text]


class TestMiqraConvert(unittest.TestCase):
    def _run(self, files: dict[str, list[dict]], book: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sourcetexts_root = tmp_path / "sources"
            _write_source(sourcetexts_root, files)
            project_dir = tmp_path / "project"
            rc = main(
                [
                    "--sourcetexts-root",
                    str(sourcetexts_root),
                    "--project-dir",
                    str(project_dir),
                    "--only-book",
                    book,
                ]
            )
            self.assertEqual(rc, 0)
            return (project_dir / f"{book}.xml").read_text(encoding="utf-8")

    @patch("opensiddur.importer.miqra_al_pi_hamasorah.convert.validate")
    def test_only_book_writes_output(self, mock_validate):
        mock_validate.return_value = (True, [])
        large_bet = {
            "tmpl_name": "מ:אות-מיוחדת-במילה",
            "tmpl_params": {
                "1": [{"tmpl_name": "מ:אות-ג", "tmpl_params": {"1": "בְּ"}}, "רֵאשִׁ֖ית"],
                "2": "בְּרֵאשִׁ֖ית",
                "3": "ב.....",
                "4": "ג",
                "5": "ב/ג",
            },
        }
        genesis = _book39("ספר בראשית", {
            "1": {
                # Parashah in column C, a documented word with a large letter, then a second verse.
                "1": _verse(
                    [{"tmpl_name": "נוסח", "tmpl_params": {"1": large_bet, "2": "test note"}}],
                    nav=[{"tmpl_name": "פפ"}],
                ),
                "2": _verse(["וְהָאָ֗רֶץ הָיְתָ֥ה תֹ֙הוּ֙ וָבֹ֔הוּ"]),
            }
        })
        xml = self._run({"A1-Genesis.json": [genesis]}, "genesis")
        self.assertIn("<tei:TEI", xml)
        self.assertIn('unit="verse"', xml)
        self.assertIn('n="1"', xml)
        self.assertIn("urn:x-opensiddur:text:bible:genesis/1/1", xml)
        self.assertNotIn("<tei:ab>", xml)
        self.assertIn('<tei:p type="open-1">', xml)
        self.assertIn("וְהָאָ֗רֶץ", xml)
        self.assertIn('<tei:head xml:lang="en">', xml)
        self.assertIn("Genesis", xml)
        self.assertIn('rend="large"', xml)
        self.assertIn("בְּ", xml)
        self.assertIn("tei:standOff", xml)
        self.assertIn("test note", xml)
        # Standoff notes must link to the in-text marker for annotation resolution
        self.assertIn('target="#miqra-note-1-ref', xml)
        # A book's header names the source but not its commit, which only the index does.
        self.assertIn("MAM-parsed/plus in https://github.com/bdenckla/MAM-basics, which", xml)
        self.assertNotIn(COMMIT, xml)

    @patch("opensiddur.importer.miqra_al_pi_hamasorah.convert.validate")
    def test_good_ending_is_not_rendered(self, mock_validate):
        # As the sheet's good-ending rows were not: plus keeps it beside the chapters.
        mock_validate.return_value = (True, [])
        isaiah = _book39("ספר ישעיהו", {"1": {"1": _verse(["חֲז֗וֹן"])}})
        isaiah["good_ending_plus"] = {
            "last_chapnver": ["1", "1"],
            "wikitext_element": {
                "tmpl_name": "נוסח",
                "tmpl_params": {
                    "1": {"tmpl_name": "מ:סיום בטוב", "tmpl_params": {"1": "סיום טוב"}},
                    "2": "הערה",
                },
            },
        }
        xml = self._run({"C1-Isaiah.json": [isaiah]}, "isaiah")
        self.assertIn("urn:x-opensiddur:text:bible:isaiah/1/1", xml)
        self.assertNotIn("סיום טוב", xml)
        self.assertNotIn("tei:standOff", xml)

    @patch("opensiddur.importer.miqra_al_pi_hamasorah.convert.validate")
    def test_sub_book_writes_samuel_1(self, mock_validate):
        # BA-Samuel.json holds both books of Samuel, each named by its abbreviation (שמ"א).
        mock_validate.return_value = (True, [])
        samuel = [
            _book39("ספר שמואל", {"1": {"1": _verse(["וַיְהִי אִישׁ אֶחָד"])}}, 'שמ"א'),
            _book39("ספר שמואל", {"1": {"1": _verse(["וַיְהִ֗י אַחֲרֵי֙"])}}, 'שמ"ב'),
        ]
        xml = self._run({"BA-Samuel.json": samuel}, "samuel_1")
        self.assertIn("urn:x-opensiddur:text:bible:samuel_1/1/1", xml)
        self.assertIn("וַיְהִי אִישׁ אֶחָד", xml)
        self.assertNotIn("אַחֲרֵי֙", xml)

    @patch("opensiddur.importer.miqra_al_pi_hamasorah.convert.validate")
    def test_twelve_writes_hosea(self, mock_validate):
        # The Twelve are one book of the 24, each prophet a sub-book named in full (הושע).
        mock_validate.return_value = (True, [])
        twelve = [_book39("ספר תרי עשר", {"1": {"1": _verse(["דְּבַר יְהוָה"])}}, "הושע")]
        xml = self._run({"CA-The-12-Minor-Prophets.json": twelve}, "hosea")
        self.assertIn("urn:x-opensiddur:text:bible:hosea/1/1", xml)
        self.assertIn("דְּבַר יְהוָה", xml)

    @patch("opensiddur.importer.miqra_al_pi_hamasorah.convert.validate")
    def test_megillah_writes_ruth(self, mock_validate):
        # The megillot are named with "מגילת " instead of "ספר ".
        mock_validate.return_value = (True, [])
        ruth = [_book39("מגילת רות", {"1": {"1": _verse(["וַיְהִי בִּימֵי"])}})]
        xml = self._run({"E2-Ruth.json": ruth}, "ruth")
        self.assertIn("urn:x-opensiddur:text:bible:ruth/1/1", xml)
        self.assertIn("וַיְהִי בִּימֵי", xml)

    def test_book_names_resolve_sub_book_abbreviations(self):
        self.assertEqual(_book_name_he(_book39("ספר שמואל", {}, 'שמ"א')), "שמואל א")
        self.assertEqual(_book_name_he(_book39("ספר מלכים", {}, 'מל"ב')), "מלכים ב")
        self.assertEqual(_book_name_he(_book39("ספר דברי הימים", {}, 'דה"א')), "דברי הימים א")

    def test_book_names_keep_full_sub_book_names(self):
        self.assertEqual(_book_name_he(_book39("ספר תרי עשר", {}, "הושע")), "הושע")
        self.assertEqual(_book_name_he(_book39("ספר עזרא", {}, "נחמיה")), "נחמיה")

    def test_book_names_strip_the_book_prefix(self):
        self.assertEqual(_book_name_he(_book39("ספר בראשית", {})), "בראשית")
        self.assertEqual(_book_name_he(_book39("מגילת איכה", {})), "איכה")


class TestFrontMatter(unittest.TestCase):
    def test_the_index_names_the_commit_and_quotes_the_attributions(self):
        with tempfile.TemporaryDirectory() as tmp:
            sourcetexts_root = Path(tmp)
            _write_source(sourcetexts_root, {})
            source = load_source(sourcetexts_root)
        front = front_matter(source)
        self.assertIn(f"at commit {COMMIT}", front)
        self.assertIn("https://en.wikisource.org/wiki/User:Dovi/Miqra_according_to_the_Masorah#beginning", front)
        self.assertIn('shall be to &quot;Hebrew Wikisource&quot;', front)
        self.assertIn("הייחוס בעברית", front)
        self.assertIn(f"at commit {COMMIT}", source.note(with_commit=True))
        self.assertNotIn(COMMIT, source.note())

    def test_a_licence_without_the_attributions_is_refused(self):
        with self.assertRaises(ValueError):
            read_attributions("License: CC-BY-SA 4.0\n")


class TestIndexUrnName(unittest.TestCase):
    def test_the_canon_is_tanakh_and_other_indexes_their_file(self):
        from opensiddur.importer.miqra_al_pi_hamasorah.convert import index_urn_name
        self.assertEqual(index_urn_name("index"), "tanakh")
        self.assertEqual(index_urn_name("the_prophets"), "the_prophets")


class TestHeaderUrn(unittest.TestCase):
    def test_the_header_names_its_entrypoint(self):
        from opensiddur.importer.miqra_al_pi_hamasorah.convert import MIQRA_PROJECT, header
        self.assertIn(f">urn:x-opensiddur:text:bible:amos@{MIQRA_PROJECT}<",
                      header(None, "Amos", entrypoint="amos", source_note="note"))
        self.assertIn(f">urn:x-opensiddur:text:bible:tanakh@{MIQRA_PROJECT}<",
                      header(None, "Tanakh", source_note="note"))

if __name__ == "__main__":
    unittest.main()
