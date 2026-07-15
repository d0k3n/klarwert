# Dashboard Dark Theme Redesign

## Overview

Redesign visual completo do dashboard TradeRepublic — dark mode com design system próprio em CSS puro, sem dependências externas. O foco é aparência profissional, legibilidade e consistência visual.

## Color Palette

### Background & Surface
- Background principal: `#0d1117`
- Cards / superfície: `#161b22`
- Bordas / hover: `#21262d` / `#30363d`

### Semantic Colors
- Lucro / positivo: `#3fb950`
- Perda / negativo: `#f85149`
- Aviso / neutro: `#d29922`

### Accent Colors
- Azul principal (links, destaques): `#58a6ff`
- Roxo (dividendos): `#bc8cff`
- Ciano (juros): `#79c0ff`
- Laranja (fees): `#ffa657`
- Verde (depósitos): `#7ee787`
- Rosa (variação): `#f778ba`

### Typography
- Títulos / dados numéricos: `'SF Mono', 'JetBrains Mono', monospace`
- Corpo: `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`
- Cor do texto: `#e6edf3`
- Texto secundário: `#8b949e`

## Components

### Header
- Background `#0d1117` com borda inferior `#21262d`
- Título do dashboard à esquerda + mini-resumo (total invested, positions count)
- Botão "Reload Data" estilizado (borda verde, hover glow sutil)
- Timestamp "Last updated"

### Summary Cards
- Grid responsivo com `repeat(auto-fill, minmax(200px, 1fr))`
- Card individual: bg `#0d1117`, borda `#30363d`, border-radius 8px
- Label uppercase, letter-spacing, cor `#8b949e`
- Valor em monospace, peso 700, tamanho 1.3rem
- Cor do valor varia conforme semântica (verde lucro, vermelho perda, roxo dividendos, etc.)
- Ícone SVG opcional para cada métrica

### Section Headers
- Título da seção em 1.1rem, peso 600
- Badge com contagem (ex: `12`) — bg `#21262d`, border-radius 10px
- Total/P&L alinhado à direita

### Tables
- Background da tabela: `#161b22`
- Header: bg `#0d1117`, texto uppercase, 0.7rem, letter-spacing, cor `#8b949e`
- Setas de ordenação ao lado do nome da coluna
- Linhas com hover highlight
- Zebrado sutil (alterna `#161b22` / `#0d1117`)
- Bordas entre linhas: `#21262d`
- Badges para Asset Class (Stocks=verde, Funds=azul, Derivatives=laranja)
- Valores numéricos em monospace
- Preços em ciano (`#79c0ff`)

### Grouped Table Sections
- Grupo expansível com background `#0d1117` e índice (ex: `▲ Stocks (2)`)
- Cada grupo tem seu próprio mini-header e linhas

### Filters
- Select "Group by" estilizado (bg `#0d1117`, borda `#30363d`)
- Input de busca com placeholder
- Chips de Asset Class (pill-style, border-radius 12px, clicáveis)

### Charts (Chart.js)
- Fundo do canvas: transparente
- Grid lines: `#21262d`
- Paleta para doughnut: `#58a6ff`, `#3fb950`, `#d29922`, `#bc8cff`, `#ffa657`, `#79c0ff`, `#f778ba`, `#e6edf3`
- Bar charts: verde `#3fb950` / vermelho `#f85149`
- Cash flow: depósitos `#7ee787`, retiradas `#f85149`, dividendos `#bc8cff`
- Tooltips: bg `#21262d`, texto `#e6edf3`
- Legend: `#8b949e`

## Responsiveness
- Cards: colapsam para 2 colunas (tablet) e 1 coluna (mobile)
- Tabelas: scroll horizontal em viewports estreitas
- Layout max-width 1400px centralizado

## Files to Modify

1. **`static/style.css`** — Rewrite completo com CSS custom properties, dark theme, responsivo
2. **`static/dashboard.js`** — Atualizar paleta de cores dos charts, ajustes de tooltip
3. **`templates/index.html`** — Ajustes mínimos no HTML (adicionar classes, estrutura de header)

## Non-Goals
- Não adicionar frameworks CSS (Bootstrap, Tailwind)
- Não alterar lógica de negócio (engine.py, parser.py, app.py)
- Não mudar comportamento das tabelas (sort, group, filter continuam iguais)
- Não adicionar novas funcionalidades — apenas redesign visual
