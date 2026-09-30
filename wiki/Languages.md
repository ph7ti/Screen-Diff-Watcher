# Languages (i18n)

**English** · [Português (Brasil)](Idiomas.md)

The **GUI is translatable** through **JSON catalogs inside the package** (`screen_watch/i18n/*.json`); the
**CLI and the diagnostic `logging` remain in fixed English** (the GUI log panel too, because
it is log). Initial languages: **`pt-BR`** (fallback) and **`en-US`**.

## Dynamic discovery

Any valid `screen_watch/i18n/xx-YY.json` file starts appearing in the window selector and in
`--language`, without changing code. The `_meta` must carry:

- `code` — equal to the file name (e.g.: `pt-BR`);
- `name` — native name shown in the combo (e.g.: "Português (Brasil)");
- `fallback` — `"pt-BR"`.

The keys of the new language must cover the same set as `pt-BR` (`en-US` serves as the reference);
`validate-i18n` reports missing/extra keys.

## Language choice (precedence)

```
--language TAG  >  state.json["language"]  >  ui.language from the YAML  >  auto (OS locale)
```

- `auto` uses `QLocale.system()` with a fallback to `locale`/`LANG`.
- Matching: exact (`pt-BR`) → same language (`pt` → `pt-BR`) → `pt-BR` fallback.
- The change applies **on the next start** (no live retranslation). The window selector writes
  `state.json["language"]`.
- An unknown `ui.language` generates a warning and falls back to `auto` (it is not an error).

In the v2 YAML:

```yaml
ui:
  language: auto        # auto | pt-BR | en-US | any discovered tag
```

```powershell
python -m screen_watch --language en-US gui        # opens the GUI in English
python -m screen_watch validate-i18n               # validates keys, error.*, help.* and _meta
```

## Add a language

1. Copy `src/screen_watch/i18n/en-US.json` to `src/screen_watch/i18n/<new-tag>.json`.
2. Adjust the `_meta` (`code` = file name, native `name`, `fallback: "pt-BR"`).
3. Translate the values (not the keys). Keep `error.*` and `help.*` complete.
4. Run `python -m screen_watch validate-i18n` until it is `ok`.
5. The language appears by itself in the selector and in `--language` (discovery is at runtime).

## Errors translated by code

Application errors have **stable codes** (`errors.py::ERROR_CODES`, e.g.:
`runtime.tesseract_missing`): the GUI shows the translated message (`error.<code>`) from the catalog; the
CLI/log show the text in English. `str(exc)` is always English; `render_error(exc)` does the translation.

## Hover help

Each control of the window has a tooltip with **purpose + example** after ~2 s of hover, with the text
coming from the `help.*` keys of the catalog.

## CI

CI runs `validate-i18n` in addition to `ruff` and `pytest`, so an incomplete catalog breaks the build.

## Related

- [Configuration](Configuration.md) — `ui.language` and precedence
- [GUI and tray](GUI-and-Tray.md) — the language selector
- [doc/00 §12.6](../doc/00-Architecture_and_Specification.md) — design decisions
