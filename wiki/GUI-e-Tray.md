# GUI e tray
[English](GUI-and-Tray.md) · **Português (Brasil)**

`python -m screen_watch gui` (ou o atalho instalado; no Linux o comando é
`screen-diff-watcher-gui`) abre a janela, cujo layout segue o mockup `UI.txt`.

## A janela

O painel superior é um **grid 2×2** (Seleções e Ações da sessão à esquerda; Monitoramento e
Detecção e alertas à direita), com o rodapé Status + Log num `QSplitter`:

- **Seleções** (canto superior esquerdo): fileira de botões **Novo Target** / **Remover** /
  **Recarregar** / **Ver local da seleção**, a legenda da ROI, a lista de
  `app-data/selections/*.json` e o campo **Nome da seleção** + **Renomear**. Cada item mostra o
  **nome do aplicativo**, a **região monitorada** e o **modo** (ex.:
  `Seleção WhatsApp — Região 120,340 400x80 — advanced`); uma seleção com **nome** o exibe como
  prefixo (`verificando download - Seleção …`). **Duplo clique reedita a região** (overlay);
  **Enter inicia/para**.
- **Monitoramento** (canto superior direito): **grid de duas colunas** — **Iniciar**/Idioma,
  **Parar**/**Re-armar baseline**, Modo/Perfil, **Armar Ações**/**Desarmar Ações**, **Armar por…**/
  **Minimizar para o tray** — mais o checkbox **Gravar prints (evidências)** e o status de arming.
  **Ver local** agora fica na fileira das **Seleções** (saiu do Monitoramento).
- **Ações da sessão (aplicam no próximo start)** (canto inferior esquerdo): checklist com as ações
  resolvidas, contador "N de M selecionadas" e a fileira horizontal de botões (**Nova ação…**,
  **Editar…**, **Remover Ação**, **Executar ação**).
- **Detecção e alertas** (canto inferior direito): a linha **Verificar texto** (texto,
  **Aparece**/**Desaparece**, **Diferenciar maiúsculas**, **Ignorar acentos**; habilitada **somente
  no `advanced`** e gravada em `overrides.text_watch` da **seleção atual**) e a linha **Som do
  alerta** (campo read-only com o trecho `file: "..."`; **Escolher…** para pré-visualizar,
  **Reproduzir** e **Copiar caminho** — o seletor **não persiste**). Depois de **Escolher…**, um
  popup aponta para o `config.yaml` e o perfil ativo, com **Copiar caminho e abrir YAML** /
  **Só abrir o YAML** / **Fechar**. Trocar o modo para fora do `advanced` limpa o override.
  Detalhes em [Alertas](Alertas.md) e nas [notas da v0.6.0](../doc/releases/v0.6.0.pt-BR.md).
- **Rodapé** (`QSplitter`): o grupo **Status** com status/último resultado e o **Log**, e a coluna
  direita com **Prints** / **Testar alerta…** / **Abrir YAML**.

## Modo, perfil e idioma

- O **modo** escolhido vale para a próxima execução e é gravado no JSON da seleção.
- O **perfil** (se houver mais de um no YAML) vale **no próximo start** e é gravado em
  `state.json`; o tray tem submenu equivalente.
- O **idioma** é escolhido pelo seletor e gravado em `state.json["language"]`; a troca vale **no
  próximo start**. O catálogo inicial tem `pt-BR` e `en-US` (ver [Idiomas](Idiomas.md)).

## Armar/desarmar

As ações rodam em **ensaio** por padrão (só registram o que fariam). **Armar ações** executa de
verdade; **Armar por…** limita por tempo e desarma sozinho; **Desarmar** volta ao ensaio. Os botões
de arming só ficam ativos com uma sessão em execução (o arming é por sessão e começa desarmado). Não
confunda com **Re-armar baseline** (mesma coluna): esse botão só recaptura o baseline da comparação
e nada tem a ver com executar ações. `Esc` (hotkey `abort`) interrompe uma ação em andamento.
Detalhes em [Ações pseudo-humanas](Acoes-Pseudo-Humanas.md).

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
- **Duplo clique** numa seleção **reedita a região** com o mesmo overlay (a janela é localizada pelo
  handle; se sumiu ou está minimizada, use **Novo Target**). A reedição preserva **nome**, **modo** e
  **overrides** e **limpa as máscaras** (eram relativas à ROI antiga). Fica bloqueada com sessão
  rodando.
- **Remover** apaga um ou mais JSONs de seleção selecionados (seleção múltipla com Ctrl/Shift).

## Nome da seleção e Ver local

- **Nome da seleção**: digite o nome de exibição abaixo da lista e confirme com **Renomear** ou
  **Enter**. O rótulo o mostra como prefixo (`verificando download - Seleção App — Região …`) e o
  **arquivo é renomeado** para o slug do nome (`verificando download` → `verificando-download.json`;
  acentos normalizados, máx. 60 caracteres). Um nome existente **nunca é sobrescrito** (conflito
  avisa e nada muda) e renomear é bloqueado com sessão rodando. Scripts com `--selection <nome>`
  precisam do novo nome de arquivo após renomear; `list-selections` e
  `state.json:last_selection` acompanham o novo nome.
- **Ver local** (botão **Ver local da seleção**): desenha a ROI da seleção na tela por ~2 s.
  **Nunca pinta dentro da ROI** (camada escura só fora, borda logo por fora do buraco), não captura
  cliques/foco e fecha sozinho — por isso pode ser usado **com o monitoramento rodando** para
  conferir o que está sendo vigiado. O botão fica na fileira das **Seleções**.

## Editor de máscaras

O botão **Editar máscaras…** (fileira das Seleções) abre um overlay transparente por monitor sobre a
janela alvo: a borda da ROI e as máscaras atuais são desenhadas; **arrastar com o botão esquerdo
adiciona**, **clique direito remove** a máscara sob o cursor, **Enter salva** e **Esc cancela**.
Máscaras são retângulos `[x, y, w, h]` relativos à ROI (pixels físicos), então acompanham a janela.
O editor fica **bloqueado com a sessão rodando** e grava o JSON da seleção de forma atômica onde as
máscaras efetivas vivem: `overrides.masks` se a chave já existe, senão `masks`, senão cria
`overrides.masks` (que tem precedência). Máscaras típicas: relógio, spinner, cursor.

## Preview

Enquanto a sessão roda, o grupo **Monitoramento** mostra duas miniaturas reduzidas: o **baseline** e
o **último frame capturado**. São cópias feitas fora do loop de captura (o buffer de imagem do loop
nunca vai para o Qt) e somem quando a sessão para; nada é gravado.

## Calibração

O botão **Calibração…** abre um gráfico ao vivo do **score** e do **limite** de **cada** comparação
da sessão (não só as mudanças), com pontos coloridos por severidade. **Exportar CSV…** salva as
amostras (timestamp, modo, score, limite, severidade) para análise em planilha e **Limpar** esvazia a
visão. Complementa o `compare-modes` do CLI. Os limites ficam em `defaults.compare_options` do perfil
— veja [Configuração](Configuracao.md).

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
