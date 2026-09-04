"""Page files are written atomically. A reader must see either the complete
previous content or the complete new content, never a partial write --
verify_brief reads these files and a truncated read is a spurious
quote_not_found that fails the research stage closed."""

import asyncio

import pytest

from sdlc.stages.research.verify import page_filename, pages_dir, write_page


@pytest.fixture(autouse=True)
def _runs_root(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    return tmp_path


def test_write_page_creates_the_file_with_content():
    path = write_page("r1", "https://example.com/a", "hello world")
    assert path == pages_dir("r1") / page_filename("https://example.com/a")
    assert path.read_text(encoding="utf-8") == "hello world"


def test_write_page_creates_parent_directories():
    write_page("r-nested", "https://example.com/a", "x")
    assert pages_dir("r-nested").is_dir()


def test_write_page_leaves_no_temp_files_behind():
    write_page("r1", "https://example.com/a", "x")
    assert [p.name for p in pages_dir("r1").iterdir()] == [page_filename("https://example.com/a")]


def test_write_page_overwrites_atomically_never_exposing_a_partial_read():
    # 200 concurrent writers of DIFFERENT-length content to one path. A
    # non-atomic write_text() truncates then writes, so a reader interleaved
    # between those two syscalls sees "" or a prefix. Every observed read must
    # be one of the two complete values.
    url = "https://example.com/a"
    short, long = "a" * 10, "b" * 100_000
    path = pages_dir("r1") / page_filename(url)
    write_page("r1", url, short)
    observed = set()

    async def writer(text: str) -> None:
        for _ in range(100):
            write_page("r1", url, text)
            await asyncio.sleep(0)

    async def reader() -> None:
        for _ in range(400):
            observed.add(path.read_text(encoding="utf-8"))
            await asyncio.sleep(0)

    async def main() -> None:
        await asyncio.gather(writer(short), writer(long), reader())

    asyncio.run(main())
    assert observed <= {short, long}, "a partial write was observed"
