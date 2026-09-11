"""mkdocs hook: classify every relative link on the site.

The site is generated from sources that live all over the repository, so a
link's meaning is fixed by its *repo* path, not by its position in the site
(see the docs-site spec §3). A link whose target is a site page is rewritten
to a markdown-relative href between src paths (mkdocs then converts it to the
final URL). A link whose target is a repo file that is not on the site is
rewritten to a GitHub blob/raw URL. A link whose target exists nowhere in the
repository fails the build — this is the fail-mode decision from spec §2, and
it closes the dead-path class that sank the hand-maintained pages.

Fenced code blocks and inline-code spans are skipped: a backticked
``[x](path)`` is prose, not a link, and a dead one must not fail the build.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

REPO_URL = "https://github.com/Kit-Kroker/Kroker"
BLOB_BASE = f"{REPO_URL}/blob/main/"
RAW_BASE = f"{REPO_URL}/raw/main/"

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}

_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_LINK_RE = re.compile(r"(?P<pre>(!?\[[^\]]*\]\()\s*)(?P<href>[^)\s]+)(?P<post>\s*\))")


class MissingLinkTarget(Exception):
    """A relative link resolves to nothing that exists in the repo."""

    def __init__(self, page: str, href: str, resolved: str) -> None:
        super().__init__(
            f"{page}: link {href!r} resolves to {resolved!r}, "
            "which is neither a site page nor a repo file"
        )
        self.page = page
        self.href = href
        self.resolved = resolved


def is_relative(href: str) -> bool:
    """True for markdown-relative hrefs (no scheme, no leading / or #)."""
    path = href.split("#", 1)[0]
    if not path:
        return False
    if path.startswith(("/", "#")) or "://" in path or href.startswith("mailto:"):
        return False
    return True


def resolve_repo_path(page_repo_path: str, href_path: str) -> str:
    """Resolve href_path the way GitHub does: against the page's repo dir."""
    base_dir = posixpath.dirname(page_repo_path)
    return posixpath.normpath(posixpath.join(base_dir, href_path))


def _suffix(path: str) -> str:
    return posixpath.splitext(path)[1].lower()


def rewrite_href(
    page_repo_path: str,
    page_src_uri: str,
    href: str,
    page_repo_paths: dict[str, str],
    repo_root: Path,
) -> str:
    """Rewrite one href. `page_repo_paths` maps repo path -> src_uri for
    every site page (md and generated static). Absolute URLs and pure
    anchors pass through; dead relative targets raise MissingLinkTarget."""
    if not is_relative(href):
        return href
    path, _, frag = href.partition("#")
    if not path:
        return href  # pure in-page anchor
    resolved = resolve_repo_path(page_repo_path, path)
    if resolved in page_repo_paths:
        target_src = page_repo_paths[resolved]
        rel = posixpath.relpath(target_src, posixpath.dirname(page_src_uri) or ".")
        return f"{rel}#{frag}" if frag else rel
    if (repo_root / resolved).is_file():
        base = RAW_BASE if _suffix(resolved) in IMAGE_SUFFIXES else BLOB_BASE
        return f"{base}{resolved}" + (f"#{frag}" if frag else "")
    if (repo_root / resolved).is_dir():
        return f"{BLOB_BASE}{resolved}"
    raise MissingLinkTarget(page_repo_path, href, resolved)


def rewrite_markdown(
    md: str,
    page_repo_path: str,
    page_src_uri: str,
    page_repo_paths: dict[str, str],
    repo_root: Path,
) -> str:
    """Apply rewrite_href to every md link/image href outside code fences
    and outside inline-code spans."""
    out: list[str] = []
    in_fence = False
    for line in md.splitlines(keepends=True):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue

        def _sub(m: re.Match[str]) -> str:
            href = m.group("href")
            if not is_relative(href):
                return m.group(0)
            new = rewrite_href(page_repo_path, page_src_uri, href, page_repo_paths, repo_root)
            return f"{m.group('pre')}{new}{m.group('post')}"

        # Even parts are outside `` `…` `` inline-code spans, odd parts inside.
        parts = re.split(r"(`[^`]*`)", line)
        rewritten = [
            _LINK_RE.sub(_sub, part) if i % 2 == 0 else part for i, part in enumerate(parts)
        ]
        out.append("".join(rewritten))
    return "".join(out)


def page_repo_paths_from_files(files) -> dict[str, str]:
    """Map every mkdocs File to the repo path its links resolve against.

    Real files sit under docs_dir (docs/), so their repo path is
    "docs/" + src_uri. Files with no abs_src_path are virtual (gen-files)
    and keep their src_uri as repo path — that is the whole point of pulling
    sources in at their repo-relative paths.
    """
    mapping: dict[str, str] = {}
    for f in files:
        if f.abs_src_path is None:
            mapping[f.src_uri] = f.src_uri
        else:
            mapping[f"docs/{f.src_uri}"] = f.src_uri
    return mapping


def on_page_markdown(markdown, *, page, config, files):  # mkdocs hook entry
    """Rewrite relative links before rendering; dead targets fail the build."""
    repo_root = Path(config.config_file_path).parent
    pages = page_repo_paths_from_files(files)
    rev = {v: k for k, v in pages.items()}
    repo_path = rev.get(src_uri := page.file.src_uri) or f"docs/{src_uri}"
    return rewrite_markdown(markdown, repo_path, src_uri, pages, repo_root)
