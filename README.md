# Clawdmeter — menu bar (SwiftBar)

Mostra o uso do **Claude Code** na barra de menus do Mac, ao lado do relógio — sem hardware.
Adaptação "software-only" do [Clawdmeter](https://github.com/HermannBjorgvin/Clawdmeter) (que roda numa placa ESP32).

![Exemplo](docs/example.png)

```
🦀 42%·18%        ← título: % do limite de sessão (5h) · semanal (7d)
─────────────
Rate limit
Sessão (5h):  42%   reset em 2h 05m
Semanal (7d): 18%   reset em 3d 11h
Status: allowed
─────────────
Gasto (local, custo zero)
Hoje:  0.0M tok    $0.00
Total: 0.0M tok    $0.00
─────────────
Atualizado 09:00:00
Atualizar agora
```

> Os números acima são ilustrativos. O plugin lê **os seus** dados localmente na sua máquina.

## Duas fontes de dados

| Seção | Fonte | Custo |
|---|---|---|
| **Gasto** (tokens/$) | `ccusage -j` lê `~/.claude/projects/**/*.jsonl` localmente | **zero** (nenhuma chamada à API) |
| **Limite** (% 5h/7d) | ping de 1 token na API da Anthropic, lê os headers `anthropic-ratelimit-unified-*` | ~1 token por execução |

O `%` do limite **só existe no servidor**, por isso o ping. O gasto é 100% local.

## Instalação

**Um comando:**

```bash
./install.sh
```

Instala o SwiftBar (se faltar), aponta a pasta de plugins pra `plugins/`, **registra o SwiftBar pra abrir sozinho no login** e abre o app. É idempotente — pode rodar de novo à vontade.

**Na mão, se preferir:**

```bash
brew install --cask swiftbar
defaults write com.ameba.SwiftBar PluginDirectory "$PWD/plugins"
open -a SwiftBar
```

**Depois:** na 1ª execução o macOS pode pedir pra **permitir o acesso ao Keychain** (item "Claude Code-credentials") — clicar em *Permitir sempre*. Pré-requisito: Node/`npx` no PATH (pro ccusage). Mais rápido: `npm i -g ccusage`.

## Por que o plugin fica numa subpasta `plugins/`

O SwiftBar **roda todo arquivo executável** da pasta que ele monitora — e ainda força `+x` neles (opção `MakePluginExecutable`). Se `README.md` ou `install.sh` ficarem junto, ele tenta executá-los como plugin e aparece um **"?"** no menu. Por isso o plugin mora sozinho em `plugins/`, e o resto fica na raiz, fora do alcance do SwiftBar.

## Abrir no login (automático)

O `install.sh` adiciona o SwiftBar aos **Itens de Início** do macOS, então ele volta sozinho depois de reiniciar o Mac. Conferir/remover em *Ajustes do Sistema → Geral → Itens de Início*. Sem isso, ao reiniciar o SwiftBar não reabre e o contador **some da barra** — bastando `open -a SwiftBar` pra trazer de volta.

## Variáveis de ambiente

- `CLAWD_NO_PING=1` — desliga o ping. Fica **100% custo zero** (some o % do limite, mantém o gasto).
- `CLAWD_CCUSAGE_CMD="..."` — comando alternativo do ccusage (default tenta `ccusage -j`, depois `npx --yes ccusage@latest -j`).

Definir pro SwiftBar via:

```bash
defaults write com.ameba.SwiftBar CLAWD_NO_PING -string 1
```

## Cores (threshold do limite)

roxo `<70%` · âmbar `70–89%` · vermelho `≥90%`. O título usa o pior dos dois (`max(5h, 7d)`).

## Ajustar o intervalo

Renomear o arquivo em `plugins/`: `clawd.5m.py` (5 min), `clawd.30s.py` (30s), etc. Cada execução com ping = 1 token.

## Créditos

**Autora:** [Ana G. Soares](https://instagram.com/ana.gsoares). Baseado no [Clawdmeter](https://github.com/HermannBjorgvin/Clawdmeter) de Hermann Björgvin. Licença MIT.
