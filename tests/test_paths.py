from verreport.paths import module_of, normalize_path


def test_normalize_strips_root_prefix():
    assert normalize_path("/work/src/door/bad.c", root="/work") == "src/door/bad.c"


def test_normalize_root_with_trailing_slash():
    assert normalize_path("/work/src/a.c", root="/work/") == "src/a.c"


def test_normalize_converts_backslashes():
    assert normalize_path(r"C:\ws\src\a.c", root=r"C:\ws") == "src/a.c"


def test_normalize_without_root_keeps_path():
    assert normalize_path("/work/src/a.c") == "/work/src/a.c"


def test_normalize_root_not_prefix_keeps_path():
    assert normalize_path("/other/src/a.c", root="/work") == "/other/src/a.c"


def test_normalize_root_must_match_whole_segment():
    assert normalize_path("/workspace/a.c", root="/work") == "/workspace/a.c"


def test_module_is_parent_directory():
    assert module_of("src/door/bad.c") == "src/door"


def test_module_of_top_level_file():
    assert module_of("main.c") == "(root)"
