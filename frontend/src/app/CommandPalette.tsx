import * as Dialog from "@radix-ui/react-dialog";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { MODULES } from "./modules";
import s from "./Shell.module.css";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Ctrl K: jump to a module. Search across assets, styles and poses joins in WP-10. */
export function CommandPalette({ open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  const options = useMemo(() => {
    const q = query.trim().toLowerCase();
    const all = [
      ...MODULES.map((m) => ({ id: m.id, path: m.path })),
      { id: "projects", path: "/projects" },
      { id: "system", path: "/system" },
    ].map((o) => ({ ...o, label: t(`nav.${o.id}`) }));
    return q ? all.filter((o) => o.label.toLowerCase().includes(q)) : all;
  }, [query, t]);

  const change = (next: boolean) => {
    if (!next) {
      setQuery("");
      setActive(0);
    }
    onOpenChange(next);
  };

  const go = (index: number) => {
    const option = options[index];
    if (!option) return;
    navigate(option.path);
    change(false);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, options.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      go(active);
    }
  };

  const activeId = options[active] ? `palette-${options[active].id}` : undefined;

  return (
    <Dialog.Root open={open} onOpenChange={change}>
      <Dialog.Portal>
        <Dialog.Overlay className={s.overlay} />
        <Dialog.Content className={s.palette} aria-describedby={undefined}>
          <Dialog.Title className="visually-hidden">{t("search.open")}</Dialog.Title>
          <input
            className={`input ${s.paletteInput}`}
            role="combobox"
            aria-expanded="true"
            aria-controls="palette-list"
            aria-activedescendant={activeId}
            aria-label={t("search.placeholder")}
            placeholder={t("search.placeholder")}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={onKeyDown}
          />
          <ul
            id="palette-list"
            role="listbox"
            className={s.paletteList}
            aria-label={t("nav.label")}
          >
            {options.map((o, i) => (
              <li
                key={o.id}
                id={`palette-${o.id}`}
                role="option"
                aria-selected={i === active}
                className={s.option}
                onMouseEnter={() => setActive(i)}
                onClick={() => go(i)}
              >
                {o.label}
              </li>
            ))}
            {options.length === 0 && (
              <li className={`${s.option} muted`} role="presentation">
                {t("search.empty", { query })}
              </li>
            )}
          </ul>
          <p className={`${s.paletteNote} muted`}>{t("search.note")}</p>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
