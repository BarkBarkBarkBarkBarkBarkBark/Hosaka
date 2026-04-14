from hosaka import main_console


def test_resolve_manifest_alias() -> None:
    target = main_console._resolve_read_target("manifest", current_dir=main_console.APP_ROOT)
    assert target == main_console.MANIFEST_DOC


def test_unknown_command_shows_no_wrong_way(capsys) -> None:
    main_console._unknown_command("bogus")
    captured = capsys.readouterr()
    assert "No Wrong Way" in captured.out
    assert "read <file>" in captured.out


def test_change_directory_relative_path(tmp_path) -> None:
    sub = tmp_path / "alpha"
    sub.mkdir()
    out = main_console._change_directory("alpha", current_dir=tmp_path)
    assert out == sub


def test_update_flow_prints_output(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main_console, "run_update", lambda: (True, "updated"))
    main_console._run_update_flow()
    out = capsys.readouterr().out
    assert "updated" in out
    assert "Update complete." in out
