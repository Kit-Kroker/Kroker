"""mkdocs hook: classify every relative link on the site.

The site is generated from sources that live all over the repository, so a
link's meaning is fixed by its *repo* path, not by its position in the site
(see the docs-site spec §3). A link whose target is a site page is rewritten
to a markdown-relative href between src paths (mkdocs then converts it to the
final URL). A link whose target is a repo file that is not on the site is
rewritten to a GitHub blob/raw URL. A link whose target exists nowhere in the
repository fails the build — this is the fail-mode decision from spec §2, and
it closes the dead-path class that sank the hand-maintained pages.

Fenced code blocks are skipped. Inline-code spans are not: link text here is
routinely a code span, and protecting backticks would tear those links apart.
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
    """Apply rewrite_href to every md link/image href outside code fences.

    Inline-code spans are NOT protected: in this repo a link's *text* is
    routinely a code span (``[`file.md`](path)``), and splitting a line on
    backticks would tear exactly those links apart. A pseudo-link inside
    backticks is therefore classified like any other — a dead one fails the
    build, which is the honest signal.
    """
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

        out.append(_LINK_RE.sub(_sub, line))
    return "".join(out)


def _is_excluded(f) -> bool:
    """True for exclude_docs files. mkdocs 1.6 marks them with
    File.inclusion == InclusionLevel.EXCLUDED (the enum's name, not its
    int value, is the stable surface); NOT_IN_NAV files stay site pages."""
    inclusion = getattr(f, "inclusion", None)
    if inclusion is not None:
        return getattr(inclusion, "name", str(inclusion)).upper().startswith("EXCLUDED")
    is_exc = getattr(f, "is_excluded", None)  # future-proof fallback
    return bool(is_exc()) if callable(is_exc) else False


def page_repo_paths_from_files(files, docs_dir: Path) -> dict[str, str]:
    """Map every mkdocs File to the repo path its links resolve against.

    Real files sit under docs_dir (docs/), so their repo path is
    "docs/" + src_uri. Virtual files (gen-files) keep their src_uri as repo
    path — that is the whole point of pulling sources in at their
    repo-relative paths. gen-files materialises virtual files in a temp dir,
    so "virtual" means: no abs path, or the abs path is not under docs_dir.

    Excluded files (exclude_docs) stay in the Files collection but are NOT
    site pages — a link to one is a link to a repo file, rewritten to its
    GitHub blob URL, never to a dead site-relative href.
    """
    mapping: dict[str, str] = {}
    for f in files:
        if _is_excluded(f):
            continue
        virtual = f.abs_src_path is None or docs_dir not in Path(f.abs_src_path).parents
        if virtual:
            mapping[f.src_uri] = f.src_uri
        else:
            mapping[f"docs/{f.src_uri}"] = f.src_uri
    return mapping


def on_page_markdown(markdown, *, page, config, files):  # mkdocs hook entry
    """Rewrite relative links before rendering; dead targets fail the build."""
    repo_root = Path(config.config_file_path).parent
    pages = page_repo_paths_from_files(files, Path(config.docs_dir))
    rev = {v: k for k, v in pages.items()}
    repo_path = rev.get(src_uri := page.file.src_uri) or f"docs/{src_uri}"
    return rewrite_markdown(markdown, repo_path, src_uri, pages, repo_root)
