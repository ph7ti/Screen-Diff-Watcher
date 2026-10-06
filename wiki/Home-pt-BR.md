# Screen Diff Watcher — Wiki
[English](Home.md) · **Português (Brasil)**

Vigia uma **região retangular (ROI) de uma janela** e avisa quando ela muda — som, popup, Telegram,
webhook/HTTP POST, syslog, log, ntfy, e-mail (SMTP) ou MQTT — no **Windows e no Linux**, sem tocar no
aplicativo vigiado.

Esta wiki reúne os **detalhes de uso e recursos**. A visão geral (o que faz e o que não faz,
plataformas, pré-requisitos, quick start e build) fica no [README](../README.pt-BR.md).

## Páginas

| Página | O que cobre |
|---|---|
| [Instalação](Instalacao.md) | binários (Inno Setup / `.deb`), código-fonte, Tesseract automático, autostart, app-data, diagnóstico `features` |
| [Uso (CLI)](Uso-CLI.md) | referência dos comandos, seleção de ROI, máscaras, calibração, perfis, robustez, ciclo de vida da seleção (criar→editar→validar→rodar) |
| [GUI e tray](GUI-e-Tray.md) | a janela, os botões, arming, ajuda no hover, prints, tray, soneca/silenciar/escalação, múltiplas ROIs |
| [Configuração](Configuracao.md) | `config.yaml` v2 (perfis, overrides), `state.json`, migração v1→v2 |
| [Ações pseudo-humanas](Acoes-Pseudo-Humanas.md) | passos, gatilhos, arming/ensaio, limites, editor da GUI, gravador, auditoria |
| [Alertas](Alertas.md) | som/popup/Telegram/log + webhook/HTTP POST/syslog/ntfy/SMTP/MQTT, soneca/silenciar + escalação, severidade, cooldown, re-arm, `test-alert --list/--only` |
| [Configuração do Telegram](Configuracao-Telegram.md) | passo a passo: criar o bot, obter o chat id, definir o token, editar o YAML e testar |
| [Evidências](Evidencias.md) | prints de baseline/mudança, retenção, pastas, toggle |
| [Idiomas (i18n)](Idiomas.md) | catálogos, precedência, como adicionar um idioma |
| [DPI e limitações](DPI-e-Limitacoes.md) | escala de tela, Wayland, janela ocluída, robustez |
| [Desenvolvimento, testes e CI](Desenvolvimento-Testes-e-CI.md) | testes unitários/integração, CI, release |

## Passo a passo mínimo

Com os binários instalados, use `screen-watch`; do código-fonte, `python -m screen_watch`.

```powershell
screen-watch list-windows                                    # veja o handle da janela-alvo
screen-watch select --handle 12345 --name painel             # desenhe a ROI no overlay
screen-watch test-alert --selection painel                   # confira o alerta
screen-watch run --selection painel                          # monitore
screen-watch gui                                             # ...ou use a GUI com tray
```

A GUI é o caminho mais curto: **Novo Target (overlay)** → desenhe a ROI → **Iniciar**.

O ciclo de vida completo da seleção também existe headless: `list-windows` → `select-manual` →
`edit-selection NOME` → `validate-config --selections` → `run --selection NOME`.

## Pontos de atenção

- **Janela ocluída** não é capturável: a captura lê pixels da tela (limitação das APIs, não bug).
- **Wayland** não é suportado no Linux; rode em X11.
- **Ações** são opt-in, desarmadas por padrão e exigem o extra `input` (`pynput`).
- **Soneca/Silenciar** silenciam os alertas de todas as sessões e persistem no `state.json`; com a
  escalação ligada, o alerta repete até o **Ciente**.
- A GUI monitora **múltiplas ROIs** ao mesmo tempo (checkboxes na lista, até `ui.max_sessions`,
  padrão 4); o `run` do CLI continua single-seleção.
- O **CLI e o log** são em inglês fixo; apenas a GUI passa pelo catálogo de idiomas (pt-BR/en-US).

## Documentos no repositório

- [README](../README.pt-BR.md) — visão geral, plataformas, requisitos, build.
- [doc/00 — Arquitetura e especificação](../doc/00-Documento_de_Arquitetura_e_Especificação.md) —
  fonte única de verdade do design.
- [doc/01 — Build e release](../doc/01-Build_e_Release.md) — pipeline dos instaladores.
- [CHANGELOG](../CHANGELOG.md) — mudanças por versão.

> **Publicar no GitHub Wiki**: as páginas desta pasta (`wiki/`) seguem o formato do GitHub Wiki.
> Para publicar, clone `https://github.com/ph7ti/Screen-Diff-Watcher.wiki.git` e copie o conteúdo de
> `wiki/` para lá (os links `../doc/...` e `../README.md` devem ser ajustados para URLs do
> repositório, ou mantenha as páginas apenas no repositório).
