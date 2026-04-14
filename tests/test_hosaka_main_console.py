from hosaka import main_console


def test_resolve_manifest_alias() -> None:
    target = main_console._resolve_read_target("manifest")
    assert target == main_console.MANIFEST_DOC


def test_unknown_command_shows_no_wrong_way(capsys) -> None:
    main_console._unknown_command("bogus")
    captured = capsys.readouterr()
    assert "No Wrong Way" in captured.out
    assert "read <file>" in captured.out
