import os

from crtest import site

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_site_has_submit_page_and_community_table(tmp_path):
    out = tmp_path / "dist"
    site.main(["--cases", os.path.join(ROOT, "cases"), "--results", os.path.join(ROOT, "results"), "--out", str(out)])
    index = (out / "index.html").read_text(encoding="utf-8")
    assert 'id="community-board"' in index and 'href="submit.html"' in index and "static/community.js" in index
    submit = (out / "submit.html").read_text(encoding="utf-8")
    assert "/mcp" in submit and "submit_results" in submit and "crtest.submit" in submit
    js = (out / "static" / "community.js").read_text(encoding="utf-8")
    assert "textContent" in js and "innerHTML" not in js
    assert (out / "cases" / "CR-005" / "text.txt").exists()
