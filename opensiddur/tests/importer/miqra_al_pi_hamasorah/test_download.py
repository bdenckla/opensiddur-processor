import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from opensiddur.importer.miqra_al_pi_hamasorah import download
from opensiddur.importer.util.pages import (
    miqra_al_pi_hamasorah_data_directory,
    miqra_al_pi_hamasorah_plus_directory,
)

COMMIT = "0123456789abcdef0123456789abcdef01234567"
GENESIS = b'{"header": {}, "book39s": []}\n'
SONG = b'{"header": {}, "book39s": [1]}\n'
LICENSE = b"Attribution: Hebrew Wikisource\n"


class FakeClient:
    """GitHub as the downloader sees it: two directory listings and the raw files."""

    def __init__(self, files: dict[str, bytes], commit: str = COMMIT) -> None:
        self.files = files
        self.commit = commit
        self.requests: list[str] = []

    def _entry(self, path: str) -> dict:
        data = self.files[path]
        return {"name": path.rsplit("/", 1)[1], "type": "file", "size": len(data),
                "sha": download.git_blob_sha(data)}

    def get_json(self, url: str):
        self.requests.append(url)
        directory = url.split("/contents/", 1)[1].split("?", 1)[0]
        prefix = directory.replace("%20", " ") + "/"
        entries = [self._entry(p) for p in self.files if p.startswith(prefix) and "/" not in p[len(prefix):]]
        return entries + [{"name": "provenance.md", "type": "file", "size": 1, "sha": "x"}]

    def get_bytes(self, url: str, *, accept: str | None = None) -> bytes:
        self.requests.append(url)
        if accept == "application/vnd.github.sha":
            return self.commit.encode("ascii")
        path = url.split(f"/{self.commit}/", 1)[1].replace("%20", " ")
        return self.files[path]


def _files() -> dict[str, bytes]:
    return {
        "MAM-parsed/plus/A1-Genesis.json": GENESIS,
        "MAM-parsed/plus/E1-Song of Songs.json": SONG,
        "MAM-parsed/LICENSE.md": LICENSE,
    }


class TestDownloadMiqra(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.sourcetexts_root = Path(self.tmp.name)
        self.data_dir = miqra_al_pi_hamasorah_data_directory(self.sourcetexts_root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _manifest(self) -> dict:
        return json.loads((self.data_dir / "manifest.json").read_text(encoding="utf-8"))

    def test_download_writes_files_and_manifest(self) -> None:
        client = FakeClient(_files())
        result = download.download(self.sourcetexts_root, commit=COMMIT, client=client)

        plus_dir = miqra_al_pi_hamasorah_plus_directory(self.sourcetexts_root)
        self.assertEqual((plus_dir / "A1-Genesis.json").read_bytes(), GENESIS)
        self.assertEqual((plus_dir / "E1-Song of Songs.json").read_bytes(), SONG)
        self.assertEqual((self.data_dir / "LICENSE.md").read_bytes(), LICENSE)
        self.assertFalse((plus_dir / "provenance.md").exists())
        self.assertTrue(result.manifest_written)

        manifest = self._manifest()
        self.assertEqual(manifest["repository"], download.REPOSITORY)
        self.assertEqual(manifest["commit"], COMMIT)
        song = next(f for f in manifest["files"] if f["path"] == "plus/E1-Song of Songs.json")
        self.assertEqual(
            song["url"],
            f"https://raw.githubusercontent.com/bdenckla/MAM-basics/{COMMIT}/MAM-parsed/plus/E1-Song%20of%20Songs.json",
        )
        self.assertEqual(song["bytes"], len(SONG))
        self.assertEqual(song["sha256"], hashlib.sha256(SONG).hexdigest())

    def test_unchanged_run_is_a_no_op(self) -> None:
        download.download(self.sourcetexts_root, commit=COMMIT, client=FakeClient(_files()))
        before = (self.data_dir / "manifest.json").read_bytes()
        client = FakeClient(_files())
        result = download.download(self.sourcetexts_root, commit=COMMIT, client=client)
        self.assertEqual(client.requests, [])
        self.assertFalse(result.manifest_written)
        self.assertEqual((self.data_dir / "manifest.json").read_bytes(), before)

    def test_a_branch_is_resolved_to_its_commit(self) -> None:
        client = FakeClient(_files())
        result = download.download(self.sourcetexts_root, commit="main", client=client)
        self.assertEqual(result.commit, COMMIT)
        self.assertEqual(self._manifest()["commit"], COMMIT)
        self.assertTrue(client.requests[0].endswith("/repos/bdenckla/MAM-basics/commits/main"))

    def test_a_file_that_does_not_match_its_listing_is_refused(self) -> None:
        client = FakeClient(_files())
        client.get_bytes = lambda url, accept=None: b"tampered"
        with self.assertRaises(download.DownloadError):
            download.download(self.sourcetexts_root, commit=COMMIT, client=client)
        self.assertFalse((self.data_dir / "manifest.json").exists())

    def test_only_files_a_previous_download_recorded_are_deleted(self) -> None:
        download.download(self.sourcetexts_root, commit=COMMIT, client=FakeClient(_files()))
        sheets = self.data_dir / "sheets" / "torah.tsv"
        sheets.parent.mkdir(parents=True)
        sheets.write_text("retired\n", encoding="utf-8")
        files = _files()
        del files["MAM-parsed/plus/E1-Song of Songs.json"]
        other = "fedcba9876543210fedcba9876543210fedcba98"
        result = download.download(self.sourcetexts_root, commit=other, client=FakeClient(files, other))
        self.assertEqual(result.deleted, ["plus/E1-Song of Songs.json"])
        self.assertFalse((self.data_dir / "plus" / "E1-Song of Songs.json").exists())
        self.assertTrue(sheets.exists())

    @patch("opensiddur.importer.miqra_al_pi_hamasorah.download.requests.Session")
    def test_dry_run_writes_nothing(self, mock_session) -> None:
        download.download(self.sourcetexts_root, dry_run=True)
        self.assertFalse(self.data_dir.exists())
        mock_session.assert_not_called()

    def test_main_dry_run_exit_code(self) -> None:
        with patch(
            "opensiddur.importer.miqra_al_pi_hamasorah.download.download"
        ) as mock_download:
            code = download.main(
                ["--dry-run", "--sourcetexts-root", str(self.sourcetexts_root)]
            )
        self.assertEqual(code, 0)
        mock_download.assert_called_once()
        self.assertTrue(mock_download.call_args.kwargs["dry_run"])


if __name__ == "__main__":
    unittest.main()
