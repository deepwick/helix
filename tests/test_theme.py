import re
import shutil
import tomllib
from pathlib import Path

import pytest

from deepwick_spec.ansi import style_of
from deepwick_spec.check_port import check_port
from deepwick_spec.palette import load_palette
from deepwick_spec.tui import capture, tmux_available

REPO = Path(__file__).resolve().parents[1]
SAMPLES = REPO.parent / "spec" / "samples"
PALETTE = load_palette()
C = PALETTE.colors

ROLE_SCOPES = {
    "comment": ["comment"],
    "keyword": ["keyword", "keyword.function", "keyword.storage", "constant.builtin", "variable.builtin", "type.builtin"],
    "controlFlow": ["keyword.control", "keyword.control.import", "keyword.operator"],
    "operator": ["operator", "punctuation"],
    "type": ["type", "constructor", "namespace"],
    "interface": ["type.enum", "type.parameter"],
    "function": ["function", "function.builtin", "function.method", "attribute"],
    "macro": ["function.macro"],
    "variable": ["variable", "variable.parameter", "variable.other.member"],
    "constant": ["constant", "type.enum.variant"],
    "string": ["string", "constant.character"],
    "escape": ["constant.character.escape", "string.special"],
    "regex": ["string.regexp"],
    "number": ["constant.numeric"],
    "tag": ["tag"],
    "preprocessorKeyword": ["keyword.directive"],
    "label": ["label"],
    "heading": ["markup.heading"],
    "link": ["markup.link.text"],
    "inlineCode": ["markup.raw"],
}


def snake(name):
    return re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), name)


def theme():
    with open(REPO / "deepwick.toml", "rb") as f:
        return tomllib.load(f)


def resolve(value):
    """Return (fg palette name, modifiers) for a Helix style value."""
    if isinstance(value, str):
        return value, []
    return value.get("fg"), value.get("modifiers", [])


def test_palette_table_matches_palette_json():
    palette = theme()["palette"]
    assert palette == {snake(k): v for k, v in C.items()}


def test_every_color_reference_is_a_palette_name():
    t = theme()
    names = set(t["palette"])
    for scope, value in t.items():
        if scope == "palette":
            continue
        values = [value] if isinstance(value, str) else [v for k, v in value.items() if k in ("fg", "bg")]
        if isinstance(value, dict) and isinstance(value.get("underline"), dict):
            values.append(value["underline"].get("color"))
        for v in values:
            if v is not None:
                assert v in names, f"{scope}: {v}"


@pytest.mark.parametrize("role", sorted(ROLE_SCOPES))
def test_syntax_roles(role):
    t = theme()
    style = PALETTE.syntax[role]
    for scope in ROLE_SCOPES[role]:
        fg, modifiers = resolve(t[scope])
        assert fg == snake(style.color), scope
        for s in style.style:
            assert {"italic": "italic", "bold": "bold", "strikethrough": "crossed_out"}[s] in modifiers, scope


@pytest.mark.parametrize(
    ("scope", "fg", "bg"),
    [
        ("ui.background", "foreground", "background"),
        ("ui.cursorline.primary", None, "surface"),
        ("ui.selection", None, "selection"),
        ("ui.linenr", "muted", None),
        ("ui.statusline", "foreground", "surface"),
        ("ui.statusline.normal", "background", "blue"),
        ("ui.statusline.insert", "background", "green"),
        ("ui.statusline.select", "background", "magenta"),
        ("ui.popup", "foreground", "surface"),
        ("ui.menu.selected", None, "selection"),
        ("ui.virtual.indent-guide", "overlay", None),
    ],
)
def test_ui_scopes(scope, fg, bg):
    value = theme()[scope]
    value = {"fg": value} if isinstance(value, str) else value
    assert value.get("fg") == fg and value.get("bg") == bg


@pytest.mark.parametrize(("scope", "color"), [("error", "red"), ("warning", "yellow"), ("info", "cyan"), ("hint", "muted")])
def test_diagnostic_colors(scope, color):
    assert resolve(theme()[scope])[0] == color


@pytest.mark.skipif(not (tmux_available() and shutil.which("hx")), reason="requires tmux and helix")
def test_helix_renders_sample_with_deepwick(tmp_path):
    config = tmp_path / "config" / "helix"
    (config / "themes").mkdir(parents=True)
    shutil.copy(REPO / "deepwick.toml", config / "themes" / "deepwick.toml")
    (config / "config.toml").write_text('theme = "deepwick"\n')
    text = capture(
        f"hx {SAMPLES / 'sample.py'}",
        {"XDG_CONFIG_HOME": str(tmp_path / "config"), "XDG_DATA_HOME": str(tmp_path / "data"), "XDG_CACHE_HOME": str(tmp_path / "cache")},
        size=(110, 52),
        wait_for="say_hello",
    )
    hexof = lambda n: C[n].lower()
    comment = style_of(text, "Escape")  # Helix styles each space separately, so check one word
    assert comment["fg"] == hexof("comment") and comment["italic"]
    assert style_of(text, "def")["fg"] == hexof("blue")
    assert style_of(text, "import")["fg"] == hexof("magenta")
    assert style_of(text, "if")["fg"] == hexof("magenta")
    assert style_of(text, "Mood")["fg"] == hexof("teal")
    assert style_of(text, "say_hello")["fg"] == hexof("yellow")
    assert style_of(text, "0.5")["fg"] == hexof("sage")
    assert style_of(text, '"__main__"')["fg"] == hexof("orange")


def test_c_macro_definitions_and_directives():
    t = theme()
    assert resolve(t["function.special"]) == ("magenta", [])
    assert resolve(t["keyword.directive"]) == ("foreground", ["bold"])


def test_port_conventions():
    assert check_port(REPO, PALETTE.allowed_hex()) == []
