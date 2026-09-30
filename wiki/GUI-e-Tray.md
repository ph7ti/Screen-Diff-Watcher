# GUI e tray

`python -m screen_watch gui` (ou o atalho instalado; no Linux o comando é
`screen-diff-watcher-gui`) abre a janela, cujo layout segue o mockup `UI.txt`.

## A janela

- **Coluna Monitoramento** (esquerda): **Iniciar** / **Parar** / **Re-armar** / **Minimizar para o
  tray**, os seletores de **Modo** (`light`/`default`/`advanced`), **Perfil** e **Idioma**, e os
  controles de arming — **Armar ações**, **Desarmar**, **Armar por…** — com o estado visível.
- **Grupo Seleções** (direita): lista de `app-data/selections/*.json` e a legenda da ROI. Cada item
  mostra o **nome do aplicativo**, a **região monitorada** e o **modo** (ex.:
  `Seleção WhatsApp — Região 120,340 400x80 — advanced`). Duplo clique inicia/para.
- **Linha de ações de arquivo**: **Novo Target** / **Remover** / **Recarregar** / **Abrir YAML** /
  **Prints**, mais o checkbox **Gravar prints (evidências)**.
- **Ações da sessão (aplicam no próximo start)**: checklist com as ações resolvidas, contador
  "N de M selecionadas" e a coluna de botões (`Nova ação…`, `Editar…`, `Remover Ação`, `Armar Ação`,
  `Executar ação`).
- **Rodapé**: status/último resultado e o **Log**, num `QSplitter` redimensionável.

## Modo, perfil e idioma

- O **modo** escolhido vale para a próxima execução e é gravado no JSON da seleção.
- O **perfil** (se houver mais de um no YAML) vale **no próximo start** e é gravado em
  `state.json`; o tray tem submenu equivalente.
- O **idioma** é escolhido pelo seletor e gravado em `state.json["language"]`; a troca vale **no
  próximo start**. O catálogo inicial tem `pt-BR` e `en-US` (ver [Idiomas](Idiomas.md)).

## Armar/desarmar

As ações rodam em **ensaio** por padrão (só registram o que fariam). **Armar ações** executa de
verdade; **Armar por…** limita por tempo e desarma sozinho; **Desarmar** volta ao ensaio. Os botões
de arming só ficam ativos com uma sessão em execução (o arming é por sessão e começa desarmado).
`Esc` (hotkey `abort`) interrompe uma ação em andamento. Detalhes em
[Ações pseudo-humanas](Acoes-Pseudo-Humanas.md).

## Ajuda no hover

Passar o mouse por ~2 s sobre qualquer controle mostra um tooltip com **propósito e exemplo** (texto
do catálogo de idiomas, chaves `help.<controle>.*`).

## Prints (evidências)

O checkbox **Gravar prints (evidências)** controla os prints do monitoramento e persiste em
`state.json["evidence_enabled"]` (tem precedência sobre o YAML; funciona até com config v1). O botão
**Executar ação** sempre grava um print da execução. O botão **Abrir pasta de prints** abre a pasta
efetiva no gerenciador de arquivos — se os prints do loop estiverem desligados, ele avisa no log.
Detalhes em [Evidências](Evidencias.md).

## Novo Target (overlay)

- A lista de janelas usa o **nome do aplicativo no estilo Gerenciador de Tarefas**
  (`FileDescription`/`ProductName` do executável, com fallback para o nome do `.exe`) e **oculta
  janelas que não são de aplicativos ativos** (invisíveis, ocultas pelo DWM, tool windows, janelas
  filhas/auxiliares e sem título).
- O overlay abre **uma janela por monitor**: arraste com o botão esquerdo; botão direito cancela.
- **Remover** apaga um ou mais JSONs de seleção selecionados (seleção múltipla com Ctrl/Shift).

## Editor de ações

Os botões **Nova ação…**, **Editar…** e **Remover Ação** criam/editam ações gravadas em
`overrides.actions` do JSON da seleção — ou seja, funcionam **mesmo com config v1**, sem migração.
Há reordenação com Subir/Descer e drag&drop, duplicação de passos e o botão **Localizar posição do
mouse…** para preencher `x`/`y`. Passo a passo em
[Ações pseudo-humanas](Acoes-Pseudo-Humanas.md).

## Tray

O ícone na bandeja oferece: mostrar/ocultar, minimizar, iniciar/parar, armar/desarmar, seleção de
perfil e sair. No GNOME pode não aparecer sem extensão de tray (a janela continua funcional).

## Como funciona por dentro

O loop roda em thread separada; a GUI só recebe eventos/resultados por uma fila consumida por
`QTimer` — callbacks de tray/hotkey nunca chamam Qt de dentro da thread do listener. O **Parar**
encerra o loop e fecha o backend antes de sair.
