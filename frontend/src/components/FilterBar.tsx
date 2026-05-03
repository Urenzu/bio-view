import { useEffect, useRef, useState } from "react";

export type FilterState = {
  subjects: string[];
  date_from: string;
  date_to: string;
};

export const defaultFilterState = (): FilterState => ({
  subjects: [],
  date_from: "",
  date_to: "",
});

export function FilterBar({
  value,
  onChange,
}: {
  value: FilterState;
  onChange: (v: FilterState) => void;
}) {
  const dirty =
    value.subjects.length > 0 || value.date_from !== "" || value.date_to !== "";

  return (
    <div className="filter-bar">
      <SubjectsPill
        value={value.subjects}
        onChange={(s) => onChange({ ...value, subjects: s })}
      />
      <DateRangePill
        from={value.date_from}
        to={value.date_to}
        onChange={(date_from, date_to) =>
          onChange({ ...value, date_from, date_to })
        }
      />
      {dirty && (
        <button
          type="button"
          className="filter-pill"
          onClick={() => onChange(defaultFilterState())}
        >
          ✕ CLEAR
        </button>
      )}
    </div>
  );
}

function SubjectsPill({
  value,
  onChange,
}: {
  value: string[];
  onChange: (v: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const wrapRef = useRef<HTMLDivElement>(null);

  useOutsideClick(wrapRef, () => setOpen(false), open);

  const add = () => {
    const t = draft.trim();
    if (t && !value.includes(t)) onChange([...value, t]);
    setDraft("");
  };

  return (
    <div style={{ position: "relative" }} ref={wrapRef}>
      <button
        type="button"
        className={`filter-pill ${value.length ? "active" : ""}`}
        onClick={() => setOpen((o) => !o)}
      >
        SUBJECTS{value.length ? ` · ${value.length}` : ""}
      </button>
      {open && (
        <div className="filter-popover">
          <label>Add subject</label>
          <input
            autoFocus
            placeholder="e.g. Cancer Biology"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
          />
          {value.length > 0 && (
            <div className="filter-tags">
              {value.map((s) => (
                <button
                  key={s}
                  type="button"
                  className="filter-pill active"
                  onClick={() => onChange(value.filter((v) => v !== s))}
                >
                  {s} ✕
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DateRangePill({
  from,
  to,
  onChange,
}: {
  from: string;
  to: string;
  onChange: (from: string, to: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  useOutsideClick(wrapRef, () => setOpen(false), open);

  const has = !!(from || to);
  const label = has ? `${from || "—"} → ${to || "—"}` : "TIME RANGE";

  return (
    <div style={{ position: "relative" }} ref={wrapRef}>
      <button
        type="button"
        className={`filter-pill ${has ? "active" : ""}`}
        onClick={() => setOpen((o) => !o)}
      >
        {label}
      </button>
      {open && (
        <div className="filter-popover">
          <div className="row">
            <div>
              <label>From</label>
              <input
                type="date"
                value={from}
                onChange={(e) => onChange(e.target.value, to)}
              />
            </div>
            <div>
              <label>To</label>
              <input
                type="date"
                value={to}
                onChange={(e) => onChange(from, e.target.value)}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function useOutsideClick(
  ref: React.RefObject<HTMLElement | null>,
  cb: () => void,
  active: boolean,
) {
  useEffect(() => {
    if (!active) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) cb();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [ref, cb, active]);
}
