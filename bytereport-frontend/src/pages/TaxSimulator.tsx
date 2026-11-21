import { useState, useMemo } from "react";
import {
  Calculator, TrendingDown, Users, Wallet,
  AlertTriangle, CheckCircle, Info,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";

// ── UZ Simplified Tax Regime constants (Налоговый кодекс РУз, 2024) ──────────
const ANNUAL_LIMIT = 1_000_000_000;     // 1 млрд UZS — лимит упрощённого режима
const TURNOVER_TAX_RATE = 0.04;         // 4% оборотный налог
const SOCIAL_TAX_RATE = 0.12;           // 12% — работодатель
const NDFL_RATE = 0.12;                 // 12% НДФЛ — удерживается с сотрудника

const MONTHS_RU = [
  "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
];

const BUSINESS_TYPES = [
  { value: "services",      label: "Услуги" },
  { value: "trade",         label: "Торговля" },
  { value: "catering",      label: "Общественное питание" },
  { value: "manufacturing", label: "Производство" },
  { value: "it",            label: "IT / Программирование" },
];

// ── Formatters ─────────────────────────────────────────────────────────────
function fmtFull(n: number): string {
  return Math.round(n).toLocaleString("ru-RU") + " UZS";
}

function fmtShort(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)} млрд`;
  if (abs >= 1_000_000)     return `${(n / 1_000_000).toFixed(1)} млн`;
  if (abs >= 1_000)         return `${(n / 1_000).toFixed(0)} тыс`;
  return String(Math.round(n));
}

// ── KPI card ───────────────────────────────────────────────────────────────
type CardColor = "blue" | "red" | "green" | "amber" | "accent";
function ResultCard({
  label, value, sub, icon: Icon, color = "blue",
}: {
  label: string; value: string; sub?: string;
  icon: React.ElementType; color?: CardColor;
}) {
  const bg  = { blue: "bg-line/40",   red: "bg-sev-high/15",   green: "bg-line/40", amber: "bg-sev-medium/15",  accent: "bg-line/40"  }[color];
  const clr = { blue: "text-brand-blue", red: "text-sev-high", green: "text-fg-subtle", amber: "text-sev-medium", accent: "text-accent" }[color];
  return (
    <Card>
      <CardContent className="pt-5 pb-5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-brand-muted mb-1 leading-tight">{label}</p>
            <p className="text-lg font-extrabold text-brand-dark leading-tight">{value}</p>
            {sub && <p className="text-xs text-brand-muted mt-0.5">{sub}</p>}
          </div>
          <div className={`w-10 h-10 rounded-xl ${bg} flex items-center justify-center shrink-0`}>
            <Icon size={17} className={clr} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────
export default function TaxSimulator() {
  const currentMonth = new Date().getMonth() + 1;

  const [revenue, setRevenue]       = useState("");
  const [bizType, setBizType]       = useState("services");
  const [employees, setEmployees]   = useState("0");
  const [salary, setSalary]         = useState("");
  const [month, setMonth]           = useState(currentMonth);

  const calc = useMemo(() => {
    const rev  = parseFloat(revenue.replace(/[\s ]/g, ""))  || 0;
    const emp  = Math.max(0, parseInt(employees) || 0);
    const sal  = parseFloat(salary.replace(/[\s ]/g, ""))   || 0;

    const turnover_tax  = rev * TURNOVER_TAX_RATE;
    const payroll       = emp * sal;
    const social_tax    = payroll * SOCIAL_TAX_RATE;
    const ndfl          = payroll * NDFL_RATE;
    const total_employer = turnover_tax + social_tax;

    const annual_proj      = rev * 12;
    const revenue_so_far   = rev * month;
    const raw_pct          = annual_proj > 0 ? (annual_proj / ANNUAL_LIMIT) * 100 : 0;
    const limit_pct        = Math.min(raw_pct, 150);
    const remaining_limit  = Math.max(0, ANNUAL_LIMIT - revenue_so_far);
    const months_to_limit  = rev > 0 ? remaining_limit / rev : null;

    const is_over    = annual_proj > ANNUAL_LIMIT;
    const is_warning = !is_over && raw_pct >= 80;
    const eff_rate   = rev > 0 ? (total_employer / rev) * 100 : 0;

    return {
      rev, emp, sal, payroll,
      turnover_tax, social_tax, ndfl, total_employer,
      annual_proj, revenue_so_far, limit_pct, raw_pct,
      remaining_limit, months_to_limit,
      is_over, is_warning, eff_rate,
    };
  }, [revenue, employees, salary, month]);

  const hasInput = calc.rev > 0;

  return (
    <div className="p-8 max-w-5xl">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-9 h-9 rounded-xl bg-line/40 flex items-center justify-center">
            <Calculator size={18} className="text-accent" />
          </div>
          <h1 className="text-2xl font-bold text-brand-dark">Налоговый симулятор УЗ</h1>
          <Badge variant="secondary" className="text-xs">Упрощённый режим · 2024</Badge>
        </div>
        <p className="text-sm text-brand-muted">
          Рассчитайте налоговую нагрузку и проверьте лимиты упрощённого налогового режима
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
        {/* ── LEFT: Form ─────────────────────────────────────────────────── */}
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-4">
              <CardTitle className="text-xs font-semibold uppercase tracking-widest text-brand-muted">
                Данные бизнеса
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-brand-dark mb-1.5">
                  Ежемесячная выручка (UZS)
                </label>
                <input
                  type="number"
                  min="0"
                  placeholder="например, 25 000 000"
                  value={revenue}
                  onChange={(e) => setRevenue(e.target.value)}
                  className="w-full rounded-xs border border-brand-border bg-transparent px-4 pr-10 py-2.5 text-sm text-brand-dark placeholder:text-fg-subtle transition-[border-color] duration-200 ease-out focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent-fg"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-brand-dark mb-1.5">
                  Вид деятельности
                </label>
                <select
                  value={bizType}
                  onChange={(e) => setBizType(e.target.value)}
                  className="w-full rounded-xl border border-brand-border px-4 py-2.5 text-sm text-brand-dark transition-[border-color] duration-200 ease-out focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent-fg bg-transparent"
                >
                  {BUSINESS_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>

              <Separator />

              <div>
                <label className="block text-sm font-medium text-brand-dark mb-1.5">
                  Количество сотрудников
                </label>
                <input
                  type="number"
                  min="0"
                  placeholder="0"
                  value={employees}
                  onChange={(e) => setEmployees(e.target.value)}
                  className="w-full rounded-xs border border-brand-border bg-transparent px-4 pr-10 py-2.5 text-sm text-brand-dark placeholder:text-fg-subtle transition-[border-color] duration-200 ease-out focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent-fg"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-brand-dark mb-1.5">
                  Средняя зарплата на сотрудника (UZS)
                </label>
                <input
                  type="number"
                  min="0"
                  placeholder="например, 3 000 000"
                  value={salary}
                  onChange={(e) => setSalary(e.target.value)}
                  className="w-full rounded-xs border border-brand-border bg-transparent px-4 pr-10 py-2.5 text-sm text-brand-dark placeholder:text-fg-subtle transition-[border-color] duration-200 ease-out focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent-fg"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-brand-dark mb-1.5">
                  Текущий месяц (для расчёта лимита)
                </label>
                <select
                  value={month}
                  onChange={(e) => setMonth(Number(e.target.value))}
                  className="w-full rounded-xl border border-brand-border px-4 py-2.5 text-sm text-brand-dark transition-[border-color] duration-200 ease-out focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent-fg bg-transparent"
                >
                  {MONTHS_RU.map((m, i) => (
                    <option key={i + 1} value={i + 1}>{m}</option>
                  ))}
                </select>
              </div>
            </CardContent>
          </Card>

          {/* Rate reference card */}
          <Card className="bg-ground border-brand-border">
            <CardContent className="pt-4 pb-4">
              <div className="flex gap-2.5">
                <Info size={14} className="text-brand-blue shrink-0 mt-0.5" />
                <div className="text-xs text-brand-muted space-y-1.5">
                  <div className="grid grid-cols-2 gap-x-4">
                    <p>Оборотный налог</p>
                    <p className="font-semibold text-brand-dark">4% от выручки</p>
                    <p>Социальный налог</p>
                    <p className="font-semibold text-brand-dark">12% от ФОТ</p>
                    <p>НДФЛ (с сотрудника)</p>
                    <p className="font-semibold text-brand-dark">12% от зарплаты</p>
                    <p>Лимит режима / год</p>
                    <p className="font-semibold text-brand-dark">1 000 000 000 UZS</p>
                  </div>
                  <p className="text-brand-muted/70 pt-1 border-t border-brand-border">
                    Справочный расчёт. Актуальные ставки: <span className="font-medium">tax.gov.uz</span>
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* ── RIGHT: Results ──────────────────────────────────────────────── */}
        <div className="space-y-4">
          {!hasInput ? (
            <Card>
              <CardContent className="py-16 flex flex-col items-center justify-center text-center">
                <Calculator size={36} className="text-brand-border mb-3" />
                <p className="text-sm text-brand-muted">Введите выручку чтобы увидеть расчёт</p>
              </CardContent>
            </Card>
          ) : (
            <>
              {/* KPI grid */}
              <div className="grid grid-cols-2 gap-3">
                <ResultCard
                  label="Оборотный налог"
                  value={fmtShort(calc.turnover_tax)}
                  sub="4% · ежеквартально"
                  icon={TrendingDown}
                  color="blue"
                />
                <ResultCard
                  label="Социальный налог"
                  value={fmtShort(calc.social_tax)}
                  sub="12% ФОТ · ежемесячно"
                  icon={Users}
                  color="amber"
                />
                <ResultCard
                  label="Итого (работодатель)"
                  value={fmtShort(calc.total_employer)}
                  sub="налоги за ваш счёт/мес"
                  icon={Wallet}
                  color={calc.eff_rate > 15 ? "red" : "green"}
                />
                <ResultCard
                  label="Эффективная ставка"
                  value={`${calc.eff_rate.toFixed(1)}%`}
                  sub="от выручки"
                  icon={Calculator}
                  color={calc.eff_rate > 15 ? "red" : calc.eff_rate > 10 ? "amber" : "green"}
                />
              </div>

              {/* Annual limit progress */}
              <Card>
                <CardContent className="pt-5">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-semibold uppercase tracking-wide text-brand-muted">
                      Лимит упрощённого режима
                    </p>
                    <span className={`text-xs font-bold ${
                      calc.is_over ? "text-sev-high" :
                      calc.is_warning ? "text-sev-medium" :
                      "text-fg-subtle"
                    }`}>
                      {Math.min(calc.raw_pct, 100).toFixed(1)}%
                    </span>
                  </div>

                  <div className="relative mb-3">
                    <Progress
                      value={Math.min(calc.limit_pct, 100)}
                      className={`h-2.5 ${calc.is_over ? "[&>div]:bg-sev-high" : calc.is_warning ? "[&>div]:bg-sev-medium" : "[&>div]:bg-success"}`}
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-x-4 text-xs">
                    <div>
                      <p className="font-semibold text-brand-dark">{fmtFull(calc.annual_proj)}</p>
                      <p className="text-brand-muted">Годовая проекция</p>
                    </div>
                    <div>
                      <p className="font-semibold text-brand-dark">1 000 000 000 UZS</p>
                      <p className="text-brand-muted">Лимит режима</p>
                    </div>
                  </div>

                  {!calc.is_over && calc.months_to_limit !== null && calc.months_to_limit > 0 && calc.months_to_limit <= 6 && (
                    <p className="text-xs text-sev-medium mt-2 font-medium">
                      ≈ {Math.floor(calc.months_to_limit)} мес. до исчерпания лимита при текущей выручке
                    </p>
                  )}
                </CardContent>
              </Card>

              {/* Status banner */}
              {calc.is_over ? (
                <div className="flex items-start gap-3 bg-sev-high/15 border border-sev-high/40 rounded-xl px-4 py-3">
                  <AlertTriangle size={16} className="text-sev-high shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-semibold text-sev-high mb-0.5">Превышение лимита режима</p>
                    <p className="text-xs text-sev-high">
                      Годовая проекция ({fmtShort(calc.annual_proj)}) превышает 1 млрд UZS.
                      Необходим переход на общий режим налогообложения. Проконсультируйтесь с налоговым консультантом.
                    </p>
                  </div>
                </div>
              ) : calc.is_warning ? (
                <div className="flex items-start gap-3 bg-sev-medium/15 border border-sev-medium/40 rounded-xl px-4 py-3">
                  <AlertTriangle size={16} className="text-sev-medium shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-semibold text-sev-medium mb-0.5">Приближение к лимиту</p>
                    <p className="text-xs text-sev-medium">
                      Вы используете {calc.raw_pct.toFixed(0)}% лимита.
                      Рассмотрите структурирование бизнеса или подготовку к переходу на ОРН заранее.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-3 bg-line/40 border border-line rounded-xl px-4 py-3">
                  <CheckCircle size={16} className="text-fg-subtle shrink-0" />
                  <p className="text-sm text-fg-subtle font-medium">
                    Вы в пределах лимита упрощённого режима
                  </p>
                </div>
              )}

              {/* Detail breakdown */}
              <Card>
                <CardContent className="pt-5">
                  <p className="text-xs font-semibold uppercase tracking-wide text-brand-muted mb-3">
                    Детализация / месяц
                  </p>
                  <div className="space-y-0 text-sm">
                    {[
                      { label: "Выручка",                              value: fmtFull(calc.rev),           bold: false },
                      { label: "Оборотный налог (4%)",                 value: fmtFull(calc.turnover_tax),  bold: true  },
                      ...(calc.emp > 0 ? [
                        { label: `ФОТ (${calc.emp} × ${fmtShort(calc.sal)})`, value: fmtFull(calc.payroll), bold: false },
                        { label: "Социальный налог 12% (работодатель)",  value: fmtFull(calc.social_tax),  bold: true  },
                        { label: "НДФЛ 12% (удерж. с сотрудников)",      value: fmtFull(calc.ndfl),        bold: false, muted: true },
                      ] : []),
                    ].map((row, i) => (
                      <div
                        key={i}
                        className={`flex justify-between py-2.5 border-b border-brand-border last:border-0 ${row.bold ? "font-semibold" : ""}`}
                      >
                        <span className={row.muted ? "text-brand-muted" : "text-brand-dark"}>{row.label}</span>
                        <span className={row.muted ? "text-brand-muted" : "text-brand-dark"}>{row.value}</span>
                      </div>
                    ))}
                    <div className="flex justify-between py-2.5 font-bold text-brand-dark border-t-2 border-brand-dark/10">
                      <span>Итого (за счёт работодателя)</span>
                      <span>{fmtFull(calc.total_employer)}</span>
                    </div>
                  </div>
                  {/* Quarterly note */}
                  <div className="mt-3 pt-3 border-t border-brand-border grid grid-cols-2 gap-2 text-xs text-brand-muted">
                    <div>
                      <p className="font-semibold text-brand-dark">{fmtFull(calc.turnover_tax * 3)}</p>
                      <p>Оборотный налог за квартал</p>
                    </div>
                    <div>
                      <p className="font-semibold text-brand-dark">{fmtFull(calc.annual_proj)}</p>
                      <p>Годовая проекция выручки</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Recommendations */}
              <Card>
                <CardContent className="pt-5">
                  <p className="text-xs font-semibold uppercase tracking-wide text-brand-muted mb-3">
                    Рекомендации
                  </p>
                  <ul className="space-y-2 text-sm text-brand-dark">
                    <li className="flex gap-2">
                      <span className="shrink-0 mt-0.5 text-brand-blue">•</span>
                      <span>Оборотный налог уплачивается <strong>ежеквартально</strong> — до 20-го числа месяца, следующего за кварталом.</span>
                    </li>
                    <li className="flex gap-2">
                      <span className="shrink-0 mt-0.5 text-brand-blue">•</span>
                      <span>Социальный налог и НДФЛ перечисляются <strong>ежемесячно</strong> — до 15-го числа.</span>
                    </li>
                    {calc.is_over && (
                      <li className="flex gap-2">
                        <span className="shrink-0 mt-0.5 text-sev-high">•</span>
                        <span className="text-sev-high">При превышении 1 млрд UZS — переход на <strong>ОРН</strong>: налог на прибыль 15%, НДС 12%. Обратитесь к бухгалтеру заблаговременно.</span>
                      </li>
                    )}
                    {!calc.is_over && calc.raw_pct > 60 && (
                      <li className="flex gap-2">
                        <span className="shrink-0 mt-0.5 text-sev-medium">•</span>
                        <span className="text-sev-medium">Используете {calc.raw_pct.toFixed(0)}% лимита. Рассмотрите регистрацию второго ИП или оптимизацию структуры до конца года.</span>
                      </li>
                    )}
                    {calc.eff_rate > 15 && (
                      <li className="flex gap-2">
                        <span className="shrink-0 mt-0.5 text-sev-high">•</span>
                        <span className="text-sev-high">Эффективная ставка {calc.eff_rate.toFixed(1)}% высокая. Проверьте, все ли сотрудники оформлены оптимально.</span>
                      </li>
                    )}
                    <li className="flex gap-2 text-xs text-brand-muted pt-1">
                      <span className="shrink-0 mt-0.5">*</span>
                      <span>Расчёт справочный. Актуальные ставки и лимиты: <strong>tax.gov.uz</strong></span>
                    </li>
                  </ul>
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
