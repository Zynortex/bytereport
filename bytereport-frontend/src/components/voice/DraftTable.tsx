import { Trash2, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import type { DraftField, DraftTransaction } from "@/types";

interface Props {
  rows: DraftTransaction[];
  onChange: (rows: DraftTransaction[]) => void;
  /** The business currency. Every amount in the table is in this unit — the
   *  backend has already converted anything the note stated otherwise. */
  currency: string;
  disabled?: boolean;
}

/**
 * Editable preview of what the model heard.
 *
 * Uncertainty is rendered PER CELL, not as a list beside the table: the point
 * of flagging a field is that the user's eye lands on the wrong value while
 * they are already looking at it. A separate "please check these" list would
 * make them hunt for the row it refers to.
 */
export function DraftTable({ rows, onChange, currency, disabled = false }: Props) {
  const { t } = useTranslation();

  const patch = (i: number, next: Partial<DraftTransaction>) => {
    onChange(rows.map((r, idx) => (idx === i ? { ...r, ...next } : r)));
  };

  // Editing a flagged field clears its flag — the user has now looked at it,
  // which is exactly what the flag was asking for.
  const resolve = (row: DraftTransaction, field: DraftField): DraftField[] =>
    row.uncertain.filter((f) => f !== field);

  const addRow = () => {
    onChange([
      ...rows,
      {
        date: null, amount: null, direction: "expense", description: "",
        // A hand-added row is typed in the business currency by definition —
        // there is no note for it to have stated anything else.
        category: null, currency, uncertain: [], notes: {},
      },
    ]);
  };

  const removeRow = (i: number) => onChange(rows.filter((_, idx) => idx !== i));

  const flagged = (row: DraftTransaction, field: DraftField) => row.uncertain.includes(field);

  const cellClass = (row: DraftTransaction, field: DraftField) =>
    cn(
      "w-full bg-transparent px-2 py-1.5 max-md:py-2.5 text-sm text-brand-dark rounded-xs border",
      "transition-[border-color] duration-200 ease-out",
      "focus:outline-none focus:border-accent-fg focus:ring-2 focus:ring-accent/30",
      "placeholder:text-fg-subtle disabled:opacity-60",
      flagged(row, field) ? "border-sev-medium bg-sev-medium/10" : "border-brand-border"
    );

  const Hint = ({ row, field }: { row: DraftTransaction; field: DraftField }) =>
    flagged(row, field) ? (
      <p className="mt-1 text-[11px] leading-snug text-sev-medium-fg">
        {row.notes[field] || t("voice.uncertain")}
      </p>
    ) : null;

  // One renderer per field, shared by the table and the phone cards, so the
  // two layouts cannot drift: same handlers, same uncertainty flags.
  const dateField = (row: DraftTransaction, i: number) => (
    <>
      <input
        type="date"
        value={row.date ?? ""}
        disabled={disabled}
        aria-label={t("voice.col_date")}
        onChange={(e) => patch(i, { date: e.target.value || null, uncertain: resolve(row, "date") })}
        className={cellClass(row, "date")}
      />
      <Hint row={row} field="date" />
    </>
  );
  const textField = (row: DraftTransaction, i: number, field: "description" | "category") => (
    <>
      <input
        value={(field === "category" ? row.category : row.description) ?? ""}
        disabled={disabled}
        aria-label={t(`voice.col_${field}`)}
        onChange={(e) =>
          patch(i, field === "category"
            ? { category: e.target.value || null, uncertain: resolve(row, "category") }
            : { description: e.target.value, uncertain: resolve(row, "description") })
        }
        className={cellClass(row, field)}
      />
      <Hint row={row} field={field} />
    </>
  );
  const directionField = (row: DraftTransaction, i: number) => (
    <>
      {/* Two buttons rather than a select: direction is the field most often
          misheard, and a wrong value has to be visible without opening anything. */}
      <div
        className={cn(
          "flex rounded-xs border overflow-hidden",
          flagged(row, "direction") ? "border-sev-medium" : "border-brand-border"
        )}
      >
        {(["income", "expense"] as const).map((dir) => (
          <button
            key={dir}
            type="button"
            disabled={disabled}
            aria-pressed={row.direction === dir}
            onClick={() => patch(i, { direction: dir, uncertain: resolve(row, "direction") })}
            className={cn(
              "flex-1 px-2 py-1.5 max-md:min-h-11 text-xs transition-colors duration-200 ease-out active:translate-y-px",
              row.direction === dir ? "bg-accent/20 text-brand-dark" : "text-brand-muted hover:text-brand-dark"
            )}
          >
            {t(`voice.${dir}`)}
          </button>
        ))}
      </div>
      <Hint row={row} field="direction" />
    </>
  );
  const amountField = (row: DraftTransaction, i: number) => (
    <>
      <input
        // inputMode keeps the phone keypad while still allowing an empty
        // value, which type=number does not.
        inputMode="decimal"
        value={row.amount ?? ""}
        disabled={disabled}
        aria-label={`${t("voice.col_amount")}, ${currency}`}
        onChange={(e) => {
          const raw = e.target.value.replace(/\s/g, "").replace(",", ".");
          const num = raw === "" ? null : Number(raw);
          if (num !== null && Number.isNaN(num)) return;
          patch(i, { amount: num, uncertain: resolve(row, "amount") });
        }}
        className={cn(cellClass(row, "amount"), "mono-num text-right")}
      />
      <Hint row={row} field="amount" />
    </>
  );
  const deleteButton = (i: number) => (
    <button
      type="button"
      disabled={disabled}
      onClick={() => removeRow(i)}
      title={t("voice.delete_row")}
      aria-label={t("voice.delete_row")}
      className="p-1.5 max-md:h-11 max-md:w-11 max-md:flex max-md:items-center max-md:justify-center rounded-xs text-brand-muted hover:text-sev-high-fg transition-colors duration-200 ease-out active:translate-y-px"
    >
      <Trash2 size={14} />
    </button>
  );
  const label = (key: string) => <p className="label-caps text-[10px] text-brand-muted mb-1">{key}</p>;

  return (
    <div>
      {/* Phone: one card per row, fields stacked under their labels. A
          five-column table at 390px meant scrolling sideways to reach the
          amount — the field the user most needs to check. */}
      <div className="md:hidden space-y-3">
        {rows.map((row, i) => (
          <div key={i} className="border border-brand-border bg-surface rounded-xs p-3 space-y-3">
            <div className="flex items-center justify-between gap-2">
              <span className="label-caps text-[10px] text-brand-muted">#{i + 1}</span>
              {deleteButton(i)}
            </div>
            <div>{label(t("voice.col_date"))}{dateField(row, i)}</div>
            <div>{label(t("voice.col_description"))}{textField(row, i, "description")}</div>
            <div>{label(t("voice.col_category"))}{textField(row, i, "category")}</div>
            <div>{label(t("voice.col_direction"))}{directionField(row, i)}</div>
            <div>{label(`${t("voice.col_amount")}, ${currency}`)}{amountField(row, i)}</div>
          </div>
        ))}
      </div>

      <div className="hidden md:block">
      {/* The table is wider than a narrow column; it scrolls inside its own
          box so the page body never scrolls sideways. */}
      <div className="overflow-x-auto border border-brand-border rounded-xs">
        {/* min-w is the sum of the sized columns plus a description column
            wide enough to read. Budgeted deliberately: at 760px the sized
            columns ate everything and the description showed six characters;
            at 940px the amount fell off the right edge, which is worse — it is
            the column the user most needs to check. */}
        <table className="w-full min-w-[820px] border-collapse">
          <thead>
            <tr className="border-b border-brand-border">
              {[
                ["voice.col_date", "w-[122px]"],
                ["voice.col_description", "min-w-[200px]"],
                ["voice.col_category", "w-[130px]"],
                ["voice.col_direction", "w-[150px]"],
                ["voice.col_amount", "w-[126px]"],
              ].map(([key, w]) => (
                <th key={key} className={cn("label-caps text-[10px] text-brand-muted text-left px-3 py-2.5", w)}>
                  {/* The unit rides in the header rather than taking a column:
                      every row is in the same currency after conversion. */}
                  {key === "voice.col_amount" ? `${t(key)}, ${currency}` : t(key)}
                </th>
              ))}
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-b border-brand-border last:border-b-0 align-top">
                <td className="px-2 py-2.5">{dateField(row, i)}</td>
                <td className="px-3 py-2.5">{textField(row, i, "description")}</td>
                <td className="px-3 py-2.5">{textField(row, i, "category")}</td>
                <td className="px-3 py-2.5">{directionField(row, i)}</td>
                <td className="px-3 py-2.5">{amountField(row, i)}</td>
                <td className="px-2 py-2.5">{deleteButton(i)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      </div>

      <Button variant="secondary" size="sm" className="mt-3 max-md:w-full" onClick={addRow} disabled={disabled}>
        <Plus size={13} />
        {t("voice.add_row")}
      </Button>
    </div>
  );
}
