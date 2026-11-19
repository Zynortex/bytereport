"""
The tax simulator is off the menu, not deleted.

Its business-type select does not change the result and its rates are
labelled 2024, so it is not shown as a feature until it is fixed. The route
stays, so an old link still opens it.
"""

import pathlib

WEB = pathlib.Path(__file__).resolve().parents[2] / "bytereport-frontend" / "src"


def test_not_in_the_sidebar():
    code = (WEB / "components" / "layout" / "Sidebar.tsx").read_text(encoding="utf-8")
    nav = code[code.index("const NAV = ["):code.index("];", code.index("const NAV = ["))]
    assert "to: \"/tax-simulator\"" not in nav


def test_not_on_the_dashboard():
    code = (WEB / "pages" / "Dashboard.tsx").read_text(encoding="utf-8")
    assert "\"/tax-simulator\"" not in code
    assert "feature_tax_title" not in code


def test_the_route_still_exists():
    code = (WEB / "App.tsx").read_text(encoding="utf-8")
    assert 'path="/tax-simulator"' in code
