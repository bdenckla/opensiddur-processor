import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import tempfile


from opensiddur.importer.miqra_al_pi_hamasorah.convert import (
    TANAKH_INDEX,
    _book_name_he,
    _flatten_books,
    front_matter,
    load_source,
    main,
    read_attributions,
)
from opensiddur.importer.miqra_al_pi_hamasorah.miqra_plus import PlusFormatError

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


HEADER = {"book24_name": "ספר", "sub_book_names": None, "chapter_counts": {}}


def _write_source(sourcetexts_root: Path, files: dict[str, list[dict]]) -> Path:
    """A miniature MAM-parsed plus download: MAM's licence, the given files and a manifest
    recording each file's SHA-256. Returns the download's directory."""
    data_dir = sourcetexts_root / "miqra_al_pi_hamasorah"
    (data_dir / "plus").mkdir(parents=True, exist_ok=True)
    contents = {"LICENSE.md": LICENSE.encode("utf-8")}
    for name, book39s in files.items():
        plus_file = {"header": HEADER, "book39s": book39s}
        contents[f"plus/{name}"] = (json.dumps(plus_file, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    for path, data in contents.items():
        (data_dir / path).write_bytes(data)
    entries = [{"path": path, "sha256": hashlib.sha256(data).hexdigest()} for path, data in contents.items()]
    (data_dir / "manifest.json").write_text(
        json.dumps({"repository": "bdenckla/MAM-basics", "commit": COMMIT, "plus_path": "MAM-parsed/plus",
                    "files": entries}),
        encoding="utf-8",
    )
    return data_dir


def _verse(text: list, nav: list | None = None, label: list | None = None) -> list:
    return [nav or ["__"], label or [], text]


def _with_other_books(files: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """The given files and one more, Z-Other-Books.json, holding a one-verse stand-in for every
    book they do not give, since a run converts all 39 books."""
    given = {_book_name_he(book39) for book39s in files.values() for book39 in book39s}
    others = [
        _book39(f"ספר {book.book_name_he}", {"1": {"1": _verse(["א"])}})
        for book in _flatten_books(TANAKH_INDEX)
        if book.book_name_he not in given
    ]
    return {**files, "Z-Other-Books.json": others}


def _convert(sourcetexts_root: Path, project_dir: Path, *args: str) -> int:
    return main(["--sourcetexts-root", str(sourcetexts_root), "--project-dir", str(project_dir), *args])


class TestMiqraConvert(unittest.TestCase):
    def _run(self, files: dict[str, list[dict]], book: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sourcetexts_root = tmp_path / "sources"
            _write_source(sourcetexts_root, _with_other_books(files))
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

    @patch("opensiddur.importer.miqra_al_pi_hamasorah.convert.validate")
    def test_only_book_numbers_the_notes_as_a_full_run_does(self, mock_validate):
        # Exodus's note follows Genesis's, whether Exodus is written alone or with every book.
        mock_validate.return_value = (True, [])
        note = {"tmpl_name": "נוסח", "tmpl_params": {"1": "א", "2": "הערה"}}
        genesis = _book39("ספר בראשית", {"1": {"1": _verse([note])}})
        exodus = _book39("ספר שמות", {"1": {"1": _verse([note])}})
        with tempfile.TemporaryDirectory() as tmp:
            sourcetexts_root = Path(tmp) / "sources"
            _write_source(
                sourcetexts_root,
                _with_other_books({"A1-Genesis.json": [genesis], "A2-Exodus.json": [exodus]}),
            )
            self.assertEqual(_convert(sourcetexts_root, Path(tmp) / "full"), 0)
            self.assertEqual(_convert(sourcetexts_root, Path(tmp) / "one", "--only-book", "exodus"), 0)
            full = (Path(tmp) / "full" / "exodus.xml").read_bytes()
            one = (Path(tmp) / "one" / "exodus.xml").read_bytes()
        self.assertEqual(one, full)
        self.assertIn(b"miqra-note-2", one)
        self.assertNotIn(b'xml:id="miqra-note-1"', one)

    @patch("opensiddur.importer.miqra_al_pi_hamasorah.convert.validate")
    def test_a_missing_book_stops_the_run_before_it_writes(self, mock_validate):
        mock_validate.return_value = (True, [])
        genesis = _book39("ספר בראשית", {"1": {"1": _verse(["א"])}})
        with tempfile.TemporaryDirectory() as tmp:
            sourcetexts_root = Path(tmp) / "sources"
            _write_source(sourcetexts_root, {"A1-Genesis.json": [genesis]})
            project_dir = Path(tmp) / "project"
            with self.assertRaisesRegex(PlusFormatError, "have no Exodus"):
                _convert(sourcetexts_root, project_dir)
            self.assertFalse(project_dir.exists())

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


class TestLoadSource(unittest.TestCase):
    """load_source reads the files the manifest lists, only if they are the files it lists."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sourcetexts_root = Path(self.tmp.name)
        ruth = _book39("מגילת רות", {"1": {"1": _verse(["ויהי בימי"])}})
        self.data_dir = _write_source(self.sourcetexts_root, {"E2-Ruth.json": [ruth]})

    def test_the_listed_files_load(self):
        self.assertEqual(list(load_source(self.sourcetexts_root).book39s), ["רות"])

    def test_a_crlf_copy_loads(self):
        # As Git for Windows checks the committed files out (core.autocrlf).
        for path in self.data_dir.rglob("*"):
            if path.is_file():
                path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        source = load_source(self.sourcetexts_root)
        self.assertEqual(list(source.book39s), ["רות"])
        self.assertIn("הייחוס בעברית", source.attributions["he"].statement)

    def test_a_file_that_differs_from_the_manifest_is_refused(self):
        for name in ("plus/E2-Ruth.json", "LICENSE.md"):
            path = self.data_dir / name
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            with self.subTest(name=name), self.assertRaisesRegex(PlusFormatError, "is not the file"):
                load_source(self.sourcetexts_root)
            path.write_bytes(original)

    def test_a_missing_file_is_refused(self):
        (self.data_dir / "plus" / "E2-Ruth.json").unlink()
        with self.assertRaisesRegex(PlusFormatError, "is missing"):
            load_source(self.sourcetexts_root)

    def test_a_json_file_the_manifest_does_not_list_is_refused(self):
        (self.data_dir / "plus" / "E3-Lamentations.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(PlusFormatError, "does not list"):
            load_source(self.sourcetexts_root)

    def test_a_book39_with_an_unknown_key_is_refused(self):
        ruth = {**_book39("מגילת רות", {"1": {"1": _verse(["ויהי"])}}), "extra": 1}
        _write_source(self.sourcetexts_root, {"E2-Ruth.json": [ruth]})
        with self.assertRaisesRegex(PlusFormatError, "book39"):
            load_source(self.sourcetexts_root)


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
