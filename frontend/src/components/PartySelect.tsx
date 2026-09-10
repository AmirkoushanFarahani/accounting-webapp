import { useId, useState } from "react";
import type { Party } from "../types/api";

const normalize = (value: string) => value.trim().toLowerCase().replace(/ي/g, "ی").replace(/ك/g, "ک").replace(/[۰-۹]/g, (digit) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(digit))).replace(/[٠-٩]/g, (digit) => String("٠١٢٣٤٥٦٧٨٩".indexOf(digit)));

export function matchesParty(party: Pick<Party, "name" | "email" | "phone">, query: string) {
  return [party.name, party.email ?? "", party.phone ?? ""].some((value) => normalize(value).includes(normalize(query)));
}

export function PartySelect({ parties, value, onChange, placeholder }: { parties: Party[]; value: string; onChange: (id: string) => void; placeholder: string }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const listId = useId();
  const selected = parties.find((party) => party.id === value);
  const matches = parties.filter((party) => matchesParty(party, query));
  const choose = (party: Party) => { onChange(party.id); setQuery(""); setOpen(false); setActive(-1); };
  return <div className="party-autocomplete" onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}>
    <input role="combobox" aria-label="جستجوی طرف حساب" aria-autocomplete="list" aria-expanded={open} aria-controls={listId} aria-activedescendant={open && active >= 0 && matches[active] ? `${listId}-${active}` : undefined}
      placeholder={`${placeholder} — جستجو با نام، تلفن یا ایمیل`} value={selected?.name ?? query} required autoComplete="off" disabled={parties.length === 0}
      ref={(input) => { input?.setCustomValidity(value ? "" : "لطفاً طرف حساب را از پیشنهادها انتخاب کنید."); }}
      onFocus={() => setOpen(true)}
      onChange={(event) => { setQuery(event.target.value); setOpen(true); setActive(-1); if (value) onChange(""); }}
      onKeyDown={(event) => {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault(); setOpen(true);
          setActive((index) => matches.length ? (index + (event.key === "ArrowDown" ? 1 : -1) + matches.length) % matches.length : -1);
        } else if (event.key === "Enter" && open) {
          event.preventDefault(); if (matches[active]) choose(matches[active]);
        } else if (event.key === "Escape" && open) { event.preventDefault(); event.stopPropagation(); setOpen(false); }
      }}/>
    {open && <><div id={listId} role="listbox" aria-label="طرف حساب‌های پیشنهادی" className="party-autocomplete__results">
      {matches.map((party, index) => <button type="button" role="option" id={`${listId}-${index}`} key={party.id} aria-selected={active === index} className="party-autocomplete__option" onMouseDown={(event) => event.preventDefault()} onClick={() => choose(party)}>
        <span>{party.name}</span><small>{party.phone || party.email}</small>
      </button>)}
    </div>{matches.length === 0 && <small role="status">طرف حسابی با این مشخصات پیدا نشد.</small>}</>}
  </div>;
}
