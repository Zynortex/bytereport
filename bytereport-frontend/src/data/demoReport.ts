/**
 * The demo report's data: a fictional but internally consistent furniture
 * workshop, Q1 2024. Every total is the sum of its parts, monthly figures
 * reconcile to the quarter, and the 13 weekly nets add up to the quarter's
 * profit. Labelled as an example everywhere it appears.
 *
 * Russian, Uzbek and English versions carry identical numbers; the demo page
 * and the landing page pick one by the interface language (getDemo).
 */
import type { AIReport, BusinessInfo, FinancialMetrics } from "@/types";

// ── Russian ──────────────────────────────────────────────────────────────────
// Quarter totals: revenue 4 145 000 · expenses 3 480 000 · profit 665 000.
// Monthly profit 150 000 + (−165 000) + 680 000 = 665 000; the 13 weekly nets
// sum to the same 665 000.

const METRICS_RU: FinancialMetrics = {
  period_start: "2024-01-01",
  period_end:   "2024-03-31",
  total_days:   91,
  total_revenue:   4_145_000,
  total_expenses:  3_480_000,
  profit:            665_000,
  profit_margin:       16.0,
  avg_monthly_revenue:  1_381_667,
  avg_monthly_expenses: 1_160_000,
  avg_monthly_profit:     221_667,
  transaction_count: 198,
  income_count:       64,
  expense_count:     134,
  revenue_by_category: [
    { category: "Корпусная мебель на заказ", total: 2_980_000, percentage: 71.9, transaction_count: 34 },
    { category: "Кухни",                     total:   890_000, percentage: 21.5, transaction_count: 11 },
    { category: "Ремонт и реставрация",      total:   275_000, percentage:  6.6, transaction_count: 19 },
  ],
  expense_by_category: [
    { category: "Материалы",   total: 1_520_000, percentage: 43.7, transaction_count: 47 },
    { category: "Зарплата",    total:   980_000, percentage: 28.2, transaction_count: 12 },
    { category: "Аренда цеха", total:   450_000, percentage: 12.9, transaction_count:  3 },
    { category: "Логистика",   total:   232_000, percentage:  6.7, transaction_count: 28 },
    { category: "Инструмент",  total:   148_000, percentage:  4.3, transaction_count: 22 },
    { category: "Реклама",     total:    96_000, percentage:  2.8, transaction_count:  9 },
    { category: "Прочее",      total:    54_000, percentage:  1.6, transaction_count: 13 },
  ],
  monthly_breakdown: [
    { month: "2024-01", revenue: 1_240_000, expenses: 1_090_000, profit:  150_000, profit_margin:  12.1 },
    { month: "2024-02", revenue: 1_015_000, expenses: 1_180_000, profit: -165_000, profit_margin: -16.3 },
    { month: "2024-03", revenue: 1_890_000, expenses: 1_210_000, profit:  680_000, profit_margin:  36.0 },
  ],
  mom_growth: [
    { month: "2024-02", revenue_growth_pct: -18.1, expense_growth_pct: 8.3, profit_growth_pct: -210.0 },
    { month: "2024-03", revenue_growth_pct:  86.2, expense_growth_pct: 2.5, profit_growth_pct: null },
  ],
  anomalies: [
    {
      category: "Материалы", month: "2024-02", type: "spike",
      severity: "high", value: 620_000, previous_value: 380_000,
      change_pct: 63.2,
      description: "Закупка материалов выросла на 63% в феврале — партия ЛДСП и фурнитуры под заказ на 1.6 млн, оплаченный только в марте.",
    },
    {
      category: "Реклама", month: "2024-03", type: "drop",
      severity: "low", value: 12_000, previous_value: 48_000,
      change_pct: -75.0,
      description: "Расходы на рекламу сократились на 75% в марте — бюджет был направлен на закрытие кассового разрыва февраля.",
    },
  ],
  cashflow_forecast: {
    // The demo states the balance it starts from (week 1: 375 000 + 45 000).
    balance_known: true,
    closing_balance: 375_000,
    has_risk: true,
    risk_date: "2024-05-20",
    risk_amount: -180_000,
    confidence: "MEDIUM",
    weekly_projection: [
      { week: 1, projected_balance:  420_000, projected_date: "2024-04-08", projected_revenue: 310_000, projected_expenses: 265_000 },
      { week: 2, projected_balance:  365_000, projected_date: "2024-04-15", projected_revenue: 280_000, projected_expenses: 335_000 },
      { week: 3, projected_balance:  210_000, projected_date: "2024-04-22", projected_revenue: 245_000, projected_expenses: 400_000 },
      { week: 4, projected_balance:   95_000, projected_date: "2024-04-29", projected_revenue: 260_000, projected_expenses: 375_000 },
      { week: 5, projected_balance:  -40_000, projected_date: "2024-05-13", projected_revenue: 230_000, projected_expenses: 365_000 },
      { week: 6, projected_balance: -180_000, projected_date: "2024-05-20", projected_revenue: 215_000, projected_expenses: 355_000 },
    ],
  },
};

const REPORT_RU: AIReport = {
  // The demo text is Russian; under another interface language the header
  // says so (ReportLanguageBadge) instead of looking like a mistranslation.
  language: "ru",
  executive_summary:
    "За I квартал 2024 мастерская заработала 4 145 000 ₽ при расходах 3 480 000 ₽ — прибыль 665 000 ₽, маржа 16.0%. Квартал закрыт уверенно, но траектория неровная: февраль ушёл в минус на 165 000 ₽, потому что материалы под крупный заказ были закуплены в феврале, а оплата пришла только в марте. Это классический кассовый разрыв на стыке месяцев, а не убыточность: март дал 680 000 ₽ прибыли и вытянул весь квартал. Главный риск — разрыв повторяется по одному и тому же сценарию, и при следующем крупном заказе без предоплаты мастерская снова уйдёт в минус примерно на 180 000 ₽.",

  financial_health_score: {
    score: 61,
    status: "Стабильно",
    reasoning:
      "Бизнес прибыльный: квартальная маржа 16.0%, март показал 36.0%. Балл снижают февральский минус 165 000 ₽, зависимость от единичных крупных заказов (71.9% выручки — корпусная мебель) и работа без предоплаты, из-за которой закупка материалов опережает поступление денег.",
  },

  key_insights: [
    {
      title: "Февральский минус — разрыв, а не убыток",
      severity: "medium",
      explanation:
        "Расходы февраля (1 180 000 ₽) превысили выручку (1 015 000 ₽) на 165 000 ₽. Причина — 620 000 ₽ на материалы под заказ, деньги за который пришли в марте. Заказ был прибыльным, проблема только в разнесении по времени.",
    },
    {
      title: "71.9% выручки — один тип заказов",
      severity: "high",
      explanation:
        "Корпусная мебель на заказ даёт 2 980 000 ₽ из 4 145 000 ₽. Потеря двух-трёх крупных клиентов подряд обнуляет квартал. Кухни (21.5%) и реставрация (6.6%) пока не компенсируют.",
    },
    {
      title: "Материалы съедают 43.7% расходов",
      severity: "medium",
      explanation:
        "1 520 000 ₽ за квартал при 47 закупках. Средний чек закупки 32 340 ₽ — закупки дробные, что обычно означает переплату против оптовой цены и потерю скидки за объём.",
    },
  ],

  top_risks: [
    {
      risk: "Повторение кассового разрыва",
      impact: "Прогноз: минус ~180 000 ₽ к 20 мая при том же сценарии",
      recommendation:
        "Ввести обязательную предоплату 50% на заказы дороже 300 000 ₽. Это закрывает закупку материалов деньгами клиента и убирает разрыв структурно, а не за счёт резерва.",
    },
    {
      risk: "Концентрация выручки на одном направлении",
      impact: "Потеря 2–3 крупных клиентов = квартал в ноль",
      recommendation:
        "Довести долю кухонь и реставрации до 40% выручки. Реставрация даёт короткий цикл и быстрые деньги — она же сглаживает разрывы между крупными заказами.",
    },
  ],

  growth_opportunities: [
    {
      opportunity: "Оптовый договор на ЛДСП и фурнитуру",
      potential_impact: "+ 90 000–140 000 ₽/квартал за счёт скидки за объём",
      action:
        "Свести 47 дробных закупок к 6–8 плановым по договору с одним поставщиком. При обороте 1.5 млн за квартал скидка 6–9% реалистична.",
    },
    {
      opportunity: "Реставрация как поток коротких денег",
      potential_impact: "+ 120 000–200 000 ₽/мес при загрузке простоя цеха",
      action:
        "Продвигать реставрацию на недозагруженные недели между крупными заказами: цикл 3–5 дней, предоплата почти всегда, закрывает провалы в неделях 6–7.",
    },
  ],

  expense_analysis: {
    problem_categories: [
      "Материалы — 47 дробных закупок вместо плановых, переплата против оптовой цены",
      "Логистика — 232 000 ₽ при 28 выездах, средний выезд 8 286 ₽",
    ],
    efficient_categories: [
      "Аренда цеха — фиксированные 150 000 ₽/мес без отклонений",
      "Зарплата — 980 000 ₽, ровно по месяцам, без авралов и переработок",
    ],
    notes:
      "Постоянные расходы (аренда + зарплата) — 1 430 000 ₽, это 41.1% всех затрат и они предсказуемы. Вся волатильность приходит из материалов и логистики, то есть управляема через планирование закупок.",
  },

  anomalies: [
    {
      category: "Материалы",
      issue: "Скачок +63.2% в феврале",
      severity: "high",
      explanation:
        "620 000 ₽ против 380 000 ₽ в январе. Разовая закупка под конкретный заказ, экономически оправданная — но именно она увела февраль в минус, потому что оплата заказа пришла через 4 недели.",
    },
    {
      category: "Реклама",
      issue: "Падение −75% в марте",
      severity: "low",
      explanation:
        "12 000 ₽ против 48 000 ₽ в феврале. Бюджет урезан ради закрытия разрыва. Приток заявок в марте держался на сарафане, но при повторении такой паузы воронка просядет с лагом 1–2 месяца.",
    },
  ],

  cash_flow_analysis: {
    status: "Положительный с разрывом",
    summary:
      "Итог квартала положительный: +665 000 ₽. Внутри квартала — две недели подряд в минусе (−155 000 ₽ и −85 000 ₽ в феврале), закрытые мартовским поступлением 640 000 ₽ за крупный заказ. Пик недельного потока — 395 000 ₽ на 11-й неделе. Схема «сначала материалы, потом деньги» повторится при следующем большом заказе.",
    warning_level: "medium",
  },

  forecast: {
    outlook: "Стабильный при условии предоплаты",
    confidence: "medium",
    summary:
      "База апрель–июнь: выручка 1.2–1.4 млн/мес, расходы 1.1–1.2 млн/мес, прибыль 150–250 тыс./мес. Без изменения условий оплаты к 20 мая ожидается разрыв около −180 000 ₽ при заходе следующего крупного заказа. С предоплатой 50% разрыв не возникает и квартал закрывается в диапазоне 500–700 тыс. ₽ прибыли.",
  },

  priority_actions: [
    {
      priority: 1,
      action: "Ввести предоплату 50% на все заказы дороже 300 000 ₽",
      expected_result:
        "Закупка материалов финансируется деньгами клиента. Прогнозируемый разрыв −180 000 ₽ к 20 мая не возникает. Эффект структурный — работает на каждом следующем заказе.",
    },
    {
      priority: 2,
      action: "Свести закупки материалов к плановым по договору с одним поставщиком",
      expected_result:
        "Скидка за объём 6–9% на обороте 1.5 млн ₽/квартал даёт 90 000–140 000 ₽. Побочный эффект — закупки становятся предсказуемыми по датам, что упрощает планирование потока.",
    },
    {
      priority: 3,
      action: "Загрузить простой цеха реставрацией между крупными заказами",
      expected_result:
        "Короткий цикл и предоплата дают ровный поток 120 000–200 000 ₽/мес и снижают долю корпусной мебели с 71.9% до ~55–60% — концентрационный риск падает.",
    },
  ],

  // 13 недель квартала. Сумма net = 665 000 ₽ — сходится с прибылью.
  // Недели 6–7 отрицательные (кассовый разрыв), пик — неделя 11.
  weekly_cash_flow: [
    { week: "Янв н1",  revenue: 260_000, expenses: 245_000, net:   15_000 },
    { week: "Янв н2",  revenue: 310_000, expenses: 270_000, net:   40_000 },
    { week: "Янв н3",  revenue: 335_000, expenses: 285_000, net:   50_000 },
    { week: "Янв н4",  revenue: 335_000, expenses: 290_000, net:   45_000 },
    { week: "Фев н1",  revenue: 285_000, expenses: 250_000, net:   35_000 },
    { week: "Фев н2",  revenue: 240_000, expenses: 395_000, net: -155_000 },
    { week: "Фев н3",  revenue: 215_000, expenses: 300_000, net:  -85_000 },
    { week: "Фев н4",  revenue: 275_000, expenses: 235_000, net:   40_000 },
    { week: "Мар н1",  revenue: 300_000, expenses: 265_000, net:   35_000 },
    { week: "Мар н2",  revenue: 355_000, expenses: 250_000, net:  105_000 },
    { week: "Мар н3",  revenue: 640_000, expenses: 245_000, net:  395_000 },
    { week: "Мар н4",  revenue: 330_000, expenses: 230_000, net:  100_000 },
    { week: "Мар н5",  revenue: 265_000, expenses: 220_000, net:   45_000 },
  ],
};

// ── English ──────────────────────────────────────────────────────────────────
// The same workshop, the same quarter, the same numbers (a test compares every
// numeric field with the Russian version). Only the words change.

const METRICS_EN: FinancialMetrics = {
  ...METRICS_RU,
  revenue_by_category: [
    { category: "Custom cabinet furniture", total: 2_980_000, percentage: 71.9, transaction_count: 34 },
    { category: "Kitchens",                 total:   890_000, percentage: 21.5, transaction_count: 11 },
    { category: "Repair and restoration",   total:   275_000, percentage:  6.6, transaction_count: 19 },
  ],
  expense_by_category: [
    { category: "Materials",     total: 1_520_000, percentage: 43.7, transaction_count: 47 },
    { category: "Payroll",       total:   980_000, percentage: 28.2, transaction_count: 12 },
    { category: "Workshop rent", total:   450_000, percentage: 12.9, transaction_count:  3 },
    { category: "Logistics",     total:   232_000, percentage:  6.7, transaction_count: 28 },
    { category: "Tools",         total:   148_000, percentage:  4.3, transaction_count: 22 },
    { category: "Advertising",   total:    96_000, percentage:  2.8, transaction_count:  9 },
    { category: "Other",         total:    54_000, percentage:  1.6, transaction_count: 13 },
  ],
  anomalies: [
    {
      ...METRICS_RU.anomalies[0],
      category: "Materials",
      description: "Material purchases rose 63% in February — a batch of chipboard and fittings for a RUB 1.6 million order that was only paid in March.",
    },
    {
      ...METRICS_RU.anomalies[1],
      category: "Advertising",
      description: "Advertising spend fell 75% in March — the budget went to closing February's cash gap.",
    },
  ],
};

const REPORT_EN: AIReport = {
  language: "en",
  executive_summary:
    "In Q1 2024 the workshop earned RUB 4,145,000 against expenses of RUB 3,480,000 — a profit of RUB 665,000 and a 16.0% margin. The quarter closed confidently, but the path was uneven: February went RUB 165,000 into the red because materials for a large order were bought in February while the payment only arrived in March. That is a classic cash gap at the turn of the month, not a loss-making business: March brought RUB 680,000 of profit and carried the whole quarter. The main risk is that the gap repeats the same way: with the next large order taken without a prepayment, the workshop will again go about RUB 180,000 into the red.",

  financial_health_score: {
    score: 61,
    status: "Stable",
    reasoning:
      "The business is profitable: a 16.0% quarterly margin and 36.0% in March. The score is pulled down by February's RUB 165,000 loss, dependence on single large orders (71.9% of revenue is cabinet furniture) and working without prepayment, which makes material purchases run ahead of incoming money.",
  },

  key_insights: [
    {
      title: "February's loss was a timing gap, not a loss",
      severity: "medium",
      explanation:
        "February's expenses (RUB 1,180,000) exceeded revenue (RUB 1,015,000) by RUB 165,000. The cause: RUB 620,000 of materials for an order that was paid for in March. The order was profitable; the only problem was timing.",
    },
    {
      title: "71.9% of revenue comes from one type of order",
      severity: "high",
      explanation:
        "Custom cabinet furniture brings RUB 2,980,000 of RUB 4,145,000. Losing two or three large clients in a row would wipe out the quarter. Kitchens (21.5%) and restoration (6.6%) do not make up for it yet.",
    },
    {
      title: "Materials take 43.7% of expenses",
      severity: "medium",
      explanation:
        "RUB 1,520,000 for the quarter across 47 purchases. The average purchase is RUB 32,340 — fragmented buying, which usually means paying above the wholesale price and missing volume discounts.",
    },
  ],

  top_risks: [
    {
      risk: "The cash gap repeating",
      impact: "Forecast: about −RUB 180,000 by 20 May under the same scenario",
      recommendation:
        "Require a 50% prepayment on orders above RUB 300,000. That pays for materials with the client's money and removes the gap structurally rather than from a reserve.",
    },
    {
      risk: "Revenue concentrated in one line of work",
      impact: "Losing 2–3 large clients = a break-even quarter",
      recommendation:
        "Bring kitchens and restoration up to 40% of revenue. Restoration has a short cycle and quick money, and it smooths the gaps between large orders.",
    },
  ],

  growth_opportunities: [
    {
      opportunity: "A wholesale contract for chipboard and fittings",
      potential_impact: "+ RUB 90,000–140,000 per quarter from volume discounts",
      action:
        "Turn 47 fragmented purchases into 6–8 planned ones under a contract with one supplier. On a turnover of 1.5 million per quarter a 6–9% discount is realistic.",
    },
    {
      opportunity: "Restoration as a stream of quick money",
      potential_impact: "+ RUB 120,000–200,000 a month by filling the workshop's idle time",
      action:
        "Promote restoration in the under-loaded weeks between large orders: a 3–5 day cycle, almost always prepaid, it fills the dips in weeks 6–7.",
    },
  ],

  expense_analysis: {
    problem_categories: [
      "Materials — 47 fragmented purchases instead of planned ones, paying above wholesale",
      "Logistics — RUB 232,000 over 28 trips, RUB 8,286 per trip on average",
    ],
    efficient_categories: [
      "Workshop rent — a fixed RUB 150,000 a month with no deviations",
      "Payroll — RUB 980,000, even across the months, no rush jobs or overtime",
    ],
    notes:
      "Fixed costs (rent and payroll) are RUB 1,430,000 — 41.1% of all costs, and predictable. All the volatility comes from materials and logistics, which makes it manageable through purchase planning.",
  },

  anomalies: [
    {
      category: "Materials",
      issue: "+63.2% spike in February",
      severity: "high",
      explanation:
        "RUB 620,000 against RUB 380,000 in January. A one-off purchase for a specific order, economically justified — but it is exactly what pushed February into the red, because the order was paid four weeks later.",
    },
    {
      category: "Advertising",
      issue: "−75% drop in March",
      severity: "low",
      explanation:
        "RUB 12,000 against RUB 48,000 in February. The budget was cut to close the gap. March enquiries held up on word of mouth, but if the pause repeats, the pipeline will sag with a 1–2 month lag.",
    },
  ],

  cash_flow_analysis: {
    status: "Positive with a gap",
    summary:
      "The quarter ends positive: +RUB 665,000. Inside it, two weeks in a row were negative (−RUB 155,000 and −RUB 85,000 in February), closed by a RUB 640,000 March payment for a large order. The weekly peak was RUB 395,000 in week 11. The \"materials first, money later\" pattern will repeat with the next large order.",
    warning_level: "medium",
  },

  forecast: {
    outlook: "Stable if prepayment is introduced",
    confidence: "medium",
    summary:
      "Baseline for April–June: revenue 1.2–1.4 million a month, expenses 1.1–1.2 million, profit 150–250 thousand. Without a change in payment terms, a gap of about −RUB 180,000 is expected by 20 May when the next large order comes in. With a 50% prepayment there is no gap and the quarter closes at RUB 500–700 thousand of profit.",
  },

  priority_actions: [
    {
      priority: 1,
      action: "Introduce a 50% prepayment on all orders above RUB 300,000",
      expected_result:
        "Materials are paid for with the client's money. The forecast −RUB 180,000 gap by 20 May does not occur. The effect is structural: it works on every next order.",
    },
    {
      priority: 2,
      action: "Move material purchases to planned ones under a contract with one supplier",
      expected_result:
        "A 6–9% volume discount on RUB 1.5 million a quarter gives RUB 90,000–140,000. Side effect: purchases become predictable by date, which makes cash planning easier.",
    },
    {
      priority: 3,
      action: "Fill the workshop's idle time with restoration between large orders",
      expected_result:
        "A short cycle and prepayment give an even RUB 120,000–200,000 a month and cut the share of cabinet furniture from 71.9% to about 55–60% — the concentration risk falls.",
    },
  ],

  weekly_cash_flow: (REPORT_RU.weekly_cash_flow ?? []).map((w, i) => ({
    ...w,
    week: `${["Jan", "Jan", "Jan", "Jan", "Feb", "Feb", "Feb", "Feb", "Mar", "Mar", "Mar", "Mar", "Mar"][i]} w${[1, 2, 3, 4, 1, 2, 3, 4, 1, 2, 3, 4, 5][i]}`,
  })),
};

// ── Uzbek ────────────────────────────────────────────────────────────────────
// The same workshop and numbers again, in Uzbek Cyrillic like the rest of the
// Uzbek interface. Amounts stay in roubles: the figures are pinned to the
// Russian version, and in sums they would describe a different business.

const METRICS_UZ: FinancialMetrics = {
  ...METRICS_RU,
  revenue_by_category: [
    { category: "Буюртма асосида корпус мебели", total: 2_980_000, percentage: 71.9, transaction_count: 34 },
    { category: "Ошхона мебели",                 total:   890_000, percentage: 21.5, transaction_count: 11 },
    { category: "Таъмирлаш ва реставрация",      total:   275_000, percentage:  6.6, transaction_count: 19 },
  ],
  expense_by_category: [
    { category: "Материаллар",     total: 1_520_000, percentage: 43.7, transaction_count: 47 },
    { category: "Иш ҳақи",         total:   980_000, percentage: 28.2, transaction_count: 12 },
    { category: "Цех ижараси",     total:   450_000, percentage: 12.9, transaction_count:  3 },
    { category: "Логистика",       total:   232_000, percentage:  6.7, transaction_count: 28 },
    { category: "Асбоб-ускуналар", total:   148_000, percentage:  4.3, transaction_count: 22 },
    { category: "Реклама",         total:    96_000, percentage:  2.8, transaction_count:  9 },
    { category: "Бошқа",           total:    54_000, percentage:  1.6, transaction_count: 13 },
  ],
  anomalies: [
    {
      ...METRICS_RU.anomalies[0],
      category: "Материаллар",
      description: "Февралда материаллар хариди 63% га ошди — фақат мартда тўланган 1.6 млн лик буюртма учун ЛДСП ва фурнитура партияси олинди.",
    },
    {
      ...METRICS_RU.anomalies[1],
      category: "Реклама",
      description: "Мартда реклама харажатлари 75% га қисқарди — бюджет февралдаги пул оқими узилишини ёпишга йўналтирилди.",
    },
  ],
};

const REPORT_UZ: AIReport = {
  language: "uz",
  executive_summary:
    "2024 йилнинг I чорагида устахона 3 480 000 ₽ харажат билан 4 145 000 ₽ тушум олди — фойда 665 000 ₽, маржа 16.0%. Чорак ишончли ёпилди, лекин йўл нотекис бўлди: февраль 165 000 ₽ зарар билан якунланди, чунки йирик буюртма учун материаллар февралда сотиб олинди, тўлов эса фақат мартда келди. Бу зарар кўраётган бизнес эмас, ойлар туташувидаги одатий пул оқими узилиши: март 680 000 ₽ фойда берди ва бутун чоракни тортиб чиқди. Асосий хавф — узилиш худди шу йўл билан такрорланади: навбатдаги йирик буюртма олдиндан тўловсиз олинса, устахона яна тахминан 180 000 ₽ зарарга тушади.",

  financial_health_score: {
    score: 61,
    status: "Барқарор",
    reasoning:
      "Бизнес фойдали: чораклик маржа 16.0%, мартда 36.0%. Баллни февралдаги 165 000 ₽ зарар, айрим йирик буюртмаларга боғлиқлик (тушумнинг 71.9% и — корпус мебели) ва олдиндан тўловсиз ишлаш пасайтиради: шу сабабли материаллар хариди пул тушишидан олдинга ўтиб кетади.",
  },

  key_insights: [
    {
      title: "Февралдаги зарар — вақтинчалик узилиш, зарар кўриш эмас",
      severity: "medium",
      explanation:
        "Февраль харажатлари (1 180 000 ₽) тушумдан (1 015 000 ₽) 165 000 ₽ га ошди. Сабаби — тўлови мартда келган буюртма учун материалларга сарфланган 620 000 ₽. Буюртма фойдали бўлган, муаммо фақат вақт бўйича тақсимотда.",
    },
    {
      title: "Тушумнинг 71.9% и — бир турдаги буюртмалар",
      severity: "high",
      explanation:
        "Буюртма асосидаги корпус мебели 4 145 000 ₽ дан 2 980 000 ₽ ни беради. Кетма-кет икки-уч йирик мижозни йўқотиш чоракни нолга туширади. Ошхона мебели (21.5%) ва реставрация (6.6%) ҳозирча буни қопламайди.",
    },
    {
      title: "Материаллар харажатларнинг 43.7% ини олади",
      severity: "medium",
      explanation:
        "Чорак давомида 47 та харидда 1 520 000 ₽. Ўртача харид 32 340 ₽ — харидлар майда, бу одатда улгуржи нархдан ортиқча тўлаш ва ҳажм учун чегирмани бой беришни англатади.",
    },
  ],

  top_risks: [
    {
      risk: "Пул оқими узилишининг такрорланиши",
      impact: "Прогноз: худди шу ҳолатда 20 майгача тахминан −180 000 ₽",
      recommendation:
        "300 000 ₽ дан қиммат буюртмаларга 50% мажбурий олдиндан тўлов жорий қилиш. Бу материаллар харидини мижоз пули билан ёпади ва узилишни захира ҳисобига эмас, тизимли равишда бартараф этади.",
    },
    {
      risk: "Тушумнинг битта йўналишда жамланиши",
      impact: "2–3 йирик мижозни йўқотиш = фойдасиз чорак",
      recommendation:
        "Ошхона мебели ва реставрация улушини тушумнинг 40% игача етказиш. Реставрация қисқа цикл ва тез пул беради — у йирик буюртмалар орасидаги узилишларни ҳам текислайди.",
    },
  ],

  growth_opportunities: [
    {
      opportunity: "ЛДСП ва фурнитура учун улгуржи шартнома",
      potential_impact: "Ҳажм учун чегирма ҳисобига чорагига + 90 000–140 000 ₽",
      action:
        "47 та майда харидни битта етказиб берувчи билан шартнома асосида 6–8 та режали харидга келтириш. Чорагига 1.5 млн айланмада 6–9% чегирма реал.",
    },
    {
      opportunity: "Реставрация — тез пул манбаи",
      potential_impact: "Цехнинг бўш вақтини юклаш ҳисобига ойига + 120 000–200 000 ₽",
      action:
        "Реставрацияни йирик буюртмалар орасидаги кам юкланган ҳафталарда тарғиб қилиш: цикл 3–5 кун, деярли ҳар доим олдиндан тўлов, 6–7-ҳафталардаги пасайишларни ёпади.",
    },
  ],

  expense_analysis: {
    problem_categories: [
      "Материаллар — режали харид ўрнига 47 та майда харид, улгуржи нархдан ортиқча тўлов",
      "Логистика — 28 та қатновга 232 000 ₽, ўртача қатнов 8 286 ₽",
    ],
    efficient_categories: [
      "Цех ижараси — ойига ўзгармас 150 000 ₽, четланишларсиз",
      "Иш ҳақи — 980 000 ₽, ойлар бўйича бир текис, шошилинч иш ва қўшимча соатларсиз",
    ],
    notes:
      "Доимий харажатлар (ижара ва иш ҳақи) — 1 430 000 ₽, бу барча харажатларнинг 41.1% и ва улар олдиндан маълум. Бутун ўзгарувчанлик материаллар ва логистикадан келади, яъни уни харидларни режалаштириш орқали бошқариш мумкин.",
  },

  anomalies: [
    {
      category: "Материаллар",
      issue: "Февралда +63.2% сакраш",
      severity: "high",
      explanation:
        "Январдаги 380 000 ₽ га нисбатан 620 000 ₽. Аниқ буюртма учун бир марталик, иқтисодий жиҳатдан асосли харид — лекин айнан у февралда зарарга олиб келди, чунки буюртма тўлови 4 ҳафтадан кейин келди.",
    },
    {
      category: "Реклама",
      issue: "Мартда −75% пасайиш",
      severity: "low",
      explanation:
        "Февралдаги 48 000 ₽ га нисбатан 12 000 ₽. Бюджет узилишни ёпиш учун қисқартирилди. Мартда мурожаатлар оғзаки тавсиялар ҳисобига сақланиб қолди, лекин бундай танаффус такрорланса, мижозлар оқими 1–2 ой кечикиш билан камаяди.",
    },
  ],

  cash_flow_analysis: {
    status: "Ижобий, узилиш билан",
    summary:
      "Чорак якуни ижобий: +665 000 ₽. Чорак ичида кетма-кет икки ҳафта манфий бўлди (февралда −155 000 ₽ ва −85 000 ₽), улар йирик буюртма учун мартда тушган 640 000 ₽ билан ёпилди. Ҳафталик оқим чўққиси — 11-ҳафтада 395 000 ₽. «Аввал материаллар, кейин пул» схемаси навбатдаги йирик буюртмада такрорланади.",
    warning_level: "medium",
  },

  forecast: {
    outlook: "Олдиндан тўлов жорий қилинса барқарор",
    confidence: "medium",
    summary:
      "Апрель–июнь учун база: тушум ойига 1.2–1.4 млн, харажатлар ойига 1.1–1.2 млн, фойда ойига 150–250 минг. Тўлов шартлари ўзгармаса, навбатдаги йирик буюртма келганда 20 майгача тахминан −180 000 ₽ узилиш кутилади. 50% олдиндан тўлов билан узилиш юзага келмайди ва чорак 500–700 минг ₽ фойда билан ёпилади.",
  },

  priority_actions: [
    {
      priority: 1,
      action: "300 000 ₽ дан қиммат барча буюртмаларга 50% олдиндан тўлов жорий қилиш",
      expected_result:
        "Материаллар хариди мижоз пули ҳисобидан молиялаштирилади. 20 майгача прогноз қилинган −180 000 ₽ узилиш юзага келмайди. Таъсир тизимли — ҳар бир кейинги буюртмада ишлайди.",
    },
    {
      priority: 2,
      action: "Материаллар харидини битта етказиб берувчи билан шартнома асосидаги режали харидга ўтказиш",
      expected_result:
        "Чорагига 1.5 млн ₽ айланмада 6–9% ҳажм чегирмаси 90 000–140 000 ₽ беради. Қўшимча натижа — харидлар саналари олдиндан маълум бўлади, бу пул оқимини режалаштиришни осонлаштиради.",
    },
    {
      priority: 3,
      action: "Йирик буюртмалар орасида цехнинг бўш вақтини реставрация билан тўлдириш",
      expected_result:
        "Қисқа цикл ва олдиндан тўлов ойига 120 000–200 000 ₽ бир текис оқим беради ва корпус мебели улушини 71.9% дан тахминан 55–60% гача туширади — жамланиш хавфи камаяди.",
    },
  ],

  weekly_cash_flow: (REPORT_RU.weekly_cash_flow ?? []).map((w, i) => ({
    ...w,
    week: `${["Янв", "Янв", "Янв", "Янв", "Фев", "Фев", "Фев", "Фев", "Мар", "Мар", "Мар", "Мар", "Мар"][i]} ҳ${[1, 2, 3, 4, 1, 2, 3, 4, 1, 2, 3, 4, 5][i]}`,
  })),
};

// ── Pick by interface language ───────────────────────────────────────────────

export interface DemoData {
  metrics: FinancialMetrics;
  report: AIReport;
  info: BusinessInfo;
  /** "1 January – 31 March 2024" */
  periodLabel: string;
  /** "Furniture manufacturing" — the line under the business name. */
  businessLine: string;
  /** Business and quarter, for the header on wide screens. */
  headerLabel: string;
  /** The demo's own note on the weekly cash-flow chart. */
  weeklyNote: string;
}

const RU: DemoData = {
  metrics: METRICS_RU,
  report: REPORT_RU,
  info: { name: "Мебельная мастерская «Контур»", type: "Производство", period: "1 января — 31 марта 2024", currency: "RUB" },
  periodLabel: "1 января — 31 марта 2024",
  businessLine: "Производство мебели",
  headerLabel: "Мебельная мастерская «Контур», I квартал 2024",
  weeklyNote: "Две недели февраля ушли в минус — материалы под крупный заказ были куплены раньше, чем пришла оплата. Разрыв закрылся 11-й неделей.",
};

const EN: DemoData = {
  metrics: METRICS_EN,
  report: REPORT_EN,
  info: { name: "Kontur furniture workshop", type: "Manufacturing", period: "1 January – 31 March 2024", currency: "RUB" },
  periodLabel: "1 January – 31 March 2024",
  businessLine: "Furniture manufacturing",
  headerLabel: "Kontur furniture workshop, Q1 2024",
  weeklyNote: "Two February weeks went negative — materials for a large order were bought before the payment arrived. The gap closed by week 11.",
};

const UZ: DemoData = {
  metrics: METRICS_UZ,
  report: REPORT_UZ,
  info: { name: "«Контур» мебель устахонаси", type: "Ишлаб чиқариш", period: "2024 йил 1 январь — 31 март", currency: "RUB" },
  periodLabel: "2024 йил 1 январь — 31 март",
  businessLine: "Мебель ишлаб чиқариш",
  headerLabel: "«Контур» мебель устахонаси, 2024 йил I чорак",
  weeklyNote: "Февралнинг икки ҳафтаси манфий бўлди — йирик буюртма учун материаллар тўлов келишидан олдин сотиб олинган. Узилиш 11-ҳафтада ёпилди.",
};

/** The demo in the interface language: Russian, Uzbek or English. */
export function getDemo(language: string | undefined): DemoData {
  const lang = (language || "").slice(0, 2);
  if (lang === "en") return EN;
  if (lang === "uz") return UZ;
  return RU;
}

export const DEMO_VARIANTS = { ru: RU, uz: UZ, en: EN } as const;
