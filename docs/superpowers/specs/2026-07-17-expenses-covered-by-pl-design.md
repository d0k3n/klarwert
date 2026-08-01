# Card: Despesas cobertas pelo P/L realizado

## Visão geral

Adicionar um novo card de resumo no topo do dashboard que exibe a percentagem das despesas pagas com o cartão da Trade Republic que foi coberta pelo lucro/prejuízo realizado (realized P/L). É uma estatística do tipo FIRE: "quanto do meu custo de vida foi pago pelos meus ganhos de trading".

## Decisões confirmadas

- **Despesas** = `total_card_spending` (gasto com cartão). Não inclui fees nem levantamentos.
- **Posição** = primeiro card dentro de `#summary-cards`, empurrando "Total Invested" para a segunda posição.
- **Cálculo base** = `total_realized_pl / total_card_spending * 100`.
- **Capping** = limitado a `100%` quando o P/L realizado supera o gasto no cartão.
- **Cálculo executado inteiramente no front-end** dentro de `renderSummary(s)` em `static/dashboard.js`, a partir dos campos já existentes em `summary` (`total_card_spending`, `total_realized_pl`). Não há alteração em `app.py`, `portfolio/engine.py` nem novos endpoints de API.

## Comportamento detalhado

### Fórmula

```
pl = s.total_realized_pl ?? 0
spending = s.total_card_spending ?? 0

se pl <= 0:
    display = "N/A"
    cls = ""            (neutro)
senão se spending == 0:
    display = "100%"
    cls = "positive"
senão:
    pct = min(100, pl / spending * 100)
    display = `${pct.toFixed(1)}%`
    cls = pct >= 100 ? "positive" : "negative"
```

### Casos limite

| Situação | Display | Classe |
|---|---|---|
| P/L > 0, spending > 0, ratio < 100 | `42.7%` | `negative` (vermelho: cobertura parcial) |
| P/L > 0, spending > 0, ratio >= 100 | `100%` (cap) | `positive` (verde: totalmente financiado) |
| P/L > 0, spending == 0 | `100%` | `positive` (sem despesas, vacuamente financiado) |
| P/L == 0 | `N/A` | neutro |
| P/L < 0 | `N/A` | neutro |

### Razão para o cap em 100%

Decisão do utilizador: quando o P/L realizado cobre totalmente o gasto do cartão, o card satura em 100% em vez de mostrar rácios como 250%. Isto comunica claramente "totalmente coberto" sem ruído numérico.

### Cores

Reutiliza as classes `.positive` (verde `#3fb950`) e `.negative` (vermelho `#f85149`) já definidas no design system dark theme. Nenhuma nova cor/CSS necessária.

## Mudanças de código

### `static/dashboard.js` — `renderSummary(s)`

Atualmente a função monta o array `cards` começando por "Total Invested". A alteração:

1. Calcular `coverage` com a fórmula acima.
2. Inserir no início do array `cards` um novo objeto:
   ```js
   { label: "Expenses covered by P/L", value: coverage, fmt: v => v, cls: () => coverageCls }
   ```
   onde `coverage` já é uma string formatada (`"42.7%"`, `"100%"` ou `"N/A"`) e `coverageCls` é `""`, `"positive"` ou `"negative"`.
3. O `forEach` existente que cria os `.card` permanece inalterado e vai renderizar o novo item em primeiro lugar, empurrando os outros para a direita.

### Arquivos não alterados

- `app.py` — sem mudanças.
- `portfolio/engine.py` — `_compute_summary` já retorna `total_card_spending` e `total_realized_pl`. Sem mudanças.
- `templates/index.html` — `#summary-cards` continua a ser o contentor. Sem mudanças.
- CSS — classes `.positive`, `.negative`, `.card`, `.value` já existem. Sem mudanças.

## Testes

- Teste manual no browser: carregar CSV, verificar que o card aparece em primeiro, com `N/A` quando não há posições fechadas, com `X%` quando há.
- Casos limite a verificar:
  - CSV sem vendas (P/L = 0) → `N/A`.
  - CSV com prejuízo (P/L < 0) → `N/A`.
  - CSV com gasto no cartão e P/L positivo parcial → número com vermelho.
  - CSV com P/L maior que gasto → `100%` verde.
  - CSV com P/L positivo e zero gasto no cartão → `100%` verde.

## Fora de scope

- Períodos customizáveis (ex. só despesas deste mês vs P/L deste mês). Hoje usa totais acumulados, igual aos outros cards de resumo.
- Variação "Card spending + fees" como despesas. Pode ser revisitada depois.
- Breakdown por tipo de despesa ou por mês.
