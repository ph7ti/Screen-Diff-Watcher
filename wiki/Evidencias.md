# Evidências (prints)
[English](Evidence.md) · **Português (Brasil)**

As evidências são **desabilitadas por padrão**. Quando ligadas, o app grava prints da **janela
inteira** (sem máscara) no baseline e a cada mudança detectada:

```
%TEMP%\screen_watch\captures\<alvo>\<AAAAMMDD-HHMMSS-mmm>_<baseline|change>.png
```

O `<alvo>` é o nome do arquivo de seleção (ex.: `painel`). As execuções de ação gravam com o
sufixo `_action` (ou `_action-<passo>`).

## Como ligar

**Pela janela (mais simples)**: o checkbox **Gravar prints (evidências)** persiste em
`state.json["evidence_enabled"]` e vale **sem editar o YAML** — inclusive com config v1
(`targets:`). Ele tem **precedência** sobre a seção `evidence:` do YAML.

**Pela config (v2)**:

```yaml
evidence:
  enabled: true
  dir: null              # null = %TEMP%/screen_watch/captures
  keep_per_target: 50    # mantém os N mais recentes por alvo
  max_total_mb: 200      # teto total (todos os alvos)
  on_baseline: true      # gravar print do baseline
  on_change: true        # gravar print de cada mudança
  per_step: false        # nas ações: um print por passo (além do print da execução)
```

A **retenção** poda a pasta após cada gravação: por contagem (`keep_per_target`) e por tamanho
(`max_total_mb`).

## Onde ficam

- Padrão: `%TEMP%/screen_watch/captures` (fora do repositório — os prints ficam **só na sua
  máquina**).
- Com `evidence.dir` configurado, os prints vão para lá.
- `python -m screen_watch show-paths` mostra a pasta efetiva na linha `captures:` (com nota quando
  há override).

O botão **Abrir pasta de prints** da janela abre a pasta efetiva no gerenciador de arquivos,
criando-a se ainda não existir; **se os prints do loop estiverem desligados ele avisa no log**.
Abrir pasta/arquivo passa sempre por `platform/shell.py::open_path` (`os.startfile` no Windows,
`open`/`xdg-open` nos demais); se não houver associação/utilitário, a GUI apenas registra
"abra manualmente: <caminho>".

## Gerar prints na hora (sem esperar um evento real)

Estes fluxos gravam **sempre**, mesmo com as evidências do loop desligadas:

```powershell
python -m screen_watch test-evidence --selection painel    # baseline+change; imprime os caminhos
python -m screen_watch test-action --selection painel --armed   # print da execução da ação
```

O botão **Executar ação (3s)** da janela também grava um print ao executar. Nas ações, com
`per_step: true`, é gravado um print por passo e os caminhos aparecem na auditoria
(`logs/actions.jsonl`).

## Falhas

Falhas ao gravar (permissão, disco, janela fora da tela) apenas geram `log.warning`; o monitoramento
continua.

## Relacionados

- [Configuração](Configuracao.md) — a seção `evidence:` e o `state.json`
- [GUI e tray](GUI-e-Tray.md) — checkbox e botões de prints
- [doc/00 §11.5](../doc/00-Documento_de_Arquitetura_e_Especificação.md) — decisões de design
