/** Style Studio: styles and characters of the project (FR-010, FR-011, FR-015, FR-026). */
import { useState } from "react";
import { useTranslation } from "react-i18next";

import {
  type Character,
  referenceFileUrl,
  type Style,
  type StyleAttributes,
  useArchive,
  useCharacters,
  useLinkReference,
  useLoraLinkActions,
  useLoraLinks,
  useReferences,
  useSaveCharacter,
  useSaveStyle,
  useStyles,
} from "../api/library";
import { useModels } from "../api/models";
import { useUi } from "../app/store";
import { linesOf, NeedsProject, ProblemText } from "./common";
import s from "./workspace.module.css";

type Tab = "styles" | "characters";
type Pair = { key: string; value: string };

const EMPTY_STYLE: StyleAttributes = {
  description: "",
  palette: [],
  rendering: "",
  lighting: "",
  background: "",
  avoid: [],
  extra: {},
};

export function StyleStudio() {
  const projectId = useUi((u) => u.projectId);
  if (!projectId) return <NeedsProject module="styles" />;
  return <Studio key={projectId} projectId={projectId} />;
}

function Studio({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("styles");
  const [selected, setSelected] = useState<string | null>(null);
  const styles = useStyles(projectId);
  const characters = useCharacters(projectId);
  const rows: (Style | Character)[] = (tab === "styles" ? styles.data : characters.data) ?? [];
  const current = rows.find((r) => r.id === selected);

  const choose = (next: Tab) => {
    setTab(next);
    setSelected(null);
  };

  return (
    <div className={s.workspace}>
      <section className={`panel ${s.column}`} aria-label={t("styles.list")}>
        <div className={s.tabs} role="group" aria-label={t("styles.kind")}>
          {(["styles", "characters"] as const).map((k) => (
            <button
              key={k}
              type="button"
              className="btn ghost"
              aria-pressed={tab === k}
              onClick={() => choose(k)}
            >
              {t(`styles.${k}`)}
            </button>
          ))}
        </div>
        <button type="button" className="btn" onClick={() => setSelected("new")}>
          {tab === "styles" ? t("styles.newStyle") : t("styles.newCharacter")}
        </button>
        {rows.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            {tab === "styles" ? t("styles.emptyStyles") : t("styles.emptyCharacters")}
          </p>
        ) : (
          <ul className={s.list}>
            {rows.map((row) => (
              <li key={row.id}>
                <button
                  type="button"
                  className={s.item}
                  aria-current={row.id === selected}
                  onClick={() => setSelected(row.id)}
                >
                  <span className={s.name}>{row.name}</span>
                  <span className={`mono muted ${s.itemMeta}`}>v{row.version}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className={`panel ${s.column}`} aria-label={t("styles.editor")}>
        {selected === null ? (
          <p className="muted" style={{ margin: 0 }}>
            {t("styles.pick")}
          </p>
        ) : selected !== "new" && !current ? (
          // Just saved: the editor mounts with the saved row once the list has it.
          <p role="status" className="muted" style={{ margin: 0 }}>
            {t("inputs.loading")}
          </p>
        ) : tab === "styles" ? (
          <StyleEditor
            key={selected}
            projectId={projectId}
            style={current as Style | undefined}
            onSaved={setSelected}
            onArchived={() => setSelected(null)}
          />
        ) : (
          <CharacterEditor
            key={selected}
            projectId={projectId}
            character={current as Character | undefined}
            onSaved={setSelected}
            onArchived={() => setSelected(null)}
          />
        )}
      </section>
    </div>
  );
}

function pairsOf(record: Record<string, string> | undefined): Pair[] {
  return Object.entries(record ?? {}).map(([key, value]) => ({ key, value }));
}

function recordOf(pairs: Pair[]): Record<string, string> {
  return Object.fromEntries(pairs.filter((p) => p.key.trim()).map((p) => [p.key.trim(), p.value]));
}

function PairsEditor({
  label,
  pairs,
  onChange,
}: {
  label: string;
  pairs: Pair[];
  onChange: (pairs: Pair[]) => void;
}) {
  const { t } = useTranslation();
  const set = (i: number, patch: Partial<Pair>) =>
    onChange(pairs.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  return (
    <fieldset className={s.field} style={{ border: 0, padding: 0, margin: 0 }}>
      <legend className="label">{label}</legend>
      {pairs.map((p, i) => (
        <div key={i} className={s.row}>
          <input
            className={`input ${s.grow}`}
            aria-label={t("styles.attributeName")}
            placeholder="line_weight"
            value={p.key}
            onChange={(e) => set(i, { key: e.target.value })}
          />
          <input
            className={`input ${s.grow}`}
            aria-label={t("styles.attributeValue")}
            value={p.value}
            onChange={(e) => set(i, { value: e.target.value })}
          />
          <button
            type="button"
            className="btn ghost"
            onClick={() => onChange(pairs.filter((_, j) => j !== i))}
          >
            {t("styles.remove")}
          </button>
        </div>
      ))}
      <div>
        <button
          type="button"
          className="btn ghost"
          onClick={() => onChange([...pairs, { key: "", value: "" }])}
        >
          {t("styles.addAttribute")}
        </button>
      </div>
      <span className="muted" style={{ fontSize: 12 }}>
        {t("styles.attributeHint")}
      </span>
    </fieldset>
  );
}

function ArchiveButton({ onConfirm, busy }: { onConfirm: () => void; busy: boolean }) {
  const { t } = useTranslation();
  const [asking, setAsking] = useState(false);
  if (!asking) {
    return (
      <button type="button" className="btn ghost" onClick={() => setAsking(true)}>
        {t("styles.archive")}
      </button>
    );
  }
  return (
    <span className={s.actions}>
      <span>{t("styles.archiveConfirm")}</span>
      <button type="button" className="btn danger" disabled={busy} onClick={onConfirm}>
        {t("styles.archive")}
      </button>
      <button type="button" className="btn ghost" onClick={() => setAsking(false)}>
        {t("styles.cancel")}
      </button>
    </span>
  );
}

function StyleEditor({
  projectId,
  style,
  onSaved,
  onArchived,
}: {
  projectId: string;
  style?: Style;
  onSaved: (id: string) => void;
  onArchived: () => void;
}) {
  const { t } = useTranslation();
  const a = style?.attributes ?? EMPTY_STYLE;
  const [name, setName] = useState(style?.name ?? "");
  const [description, setDescription] = useState(a.description ?? "");
  const [palette, setPalette] = useState<string[]>(a.palette ?? []);
  const [rendering, setRendering] = useState(a.rendering ?? "");
  const [lighting, setLighting] = useState(a.lighting ?? "");
  const [background, setBackground] = useState(a.background ?? "");
  const [avoid, setAvoid] = useState((a.avoid ?? []).join("\n"));
  const [extra, setExtra] = useState<Pair[]>(pairsOf(a.extra));
  const save = useSaveStyle(projectId);
  const archive = useArchive(projectId);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    save.mutate(
      {
        id: style?.id,
        name,
        attributes: {
          description,
          palette,
          rendering,
          lighting,
          background,
          avoid: linesOf(avoid),
          extra: recordOf(extra),
        },
      },
      { onSuccess: (saved) => onSaved(saved.id) },
    );
  };

  return (
    <form className={s.form} onSubmit={submit} aria-label={t("styles.styleForm")}>
      <div className={s.header}>
        <h2 className="h-panel">{style ? style.name : t("styles.newStyle")}</h2>
        {style && <span className="mono muted">v{style.version}</span>}
      </div>
      <label className={s.field}>
        <span className="label">{t("styles.name")}</span>
        <input
          className="input"
          required
          maxLength={120}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label className={s.field}>
        <span className="label">{t("styles.description")}</span>
        <textarea
          className="input"
          maxLength={2000}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </label>
      <fieldset className={s.field} style={{ border: 0, padding: 0, margin: 0 }}>
        <legend className="label">{t("styles.palette")}</legend>
        <div className={s.row}>
          {palette.map((colour, i) => (
            <span key={i} className={s.row} style={{ gap: 4 }}>
              <input
                type="color"
                className={s.swatch}
                aria-label={t("styles.colour", { n: i + 1 })}
                value={colour}
                onChange={(e) => setPalette(palette.map((c, j) => (j === i ? e.target.value : c)))}
              />
              <span className="mono">{colour}</span>
              <button
                type="button"
                className="btn ghost"
                aria-label={t("styles.removeColour", { colour })}
                onClick={() => setPalette(palette.filter((_, j) => j !== i))}
              >
                ×
              </button>
            </span>
          ))}
          {palette.length < 16 && (
            <button
              type="button"
              className="btn ghost"
              onClick={() => setPalette([...palette, "#808080"])}
            >
              {t("styles.addColour")}
            </button>
          )}
        </div>
      </fieldset>
      <div className={s.row} style={{ alignItems: "start" }}>
        {(
          [
            ["rendering", rendering, setRendering],
            ["lighting", lighting, setLighting],
            ["background", background, setBackground],
          ] as const
        ).map(([key, value, set]) => (
          <label key={key} className={`${s.field} ${s.grow}`}>
            <span className="label">{t(`styles.${key}`)}</span>
            <input
              className="input"
              maxLength={500}
              value={value}
              onChange={(e) => set(e.target.value)}
            />
          </label>
        ))}
      </div>
      <label className={s.field}>
        <span className="label">{t("styles.avoid")}</span>
        <textarea
          className="input"
          value={avoid}
          placeholder={t("styles.avoidHint")}
          onChange={(e) => setAvoid(e.target.value)}
        />
      </label>
      <PairsEditor label={t("styles.extra")} pairs={extra} onChange={setExtra} />
      {style && <LinkedReferences projectId={projectId} target={{ type: "style", id: style.id }} />}
      {style && <LinkedLoras projectId={projectId} target={{ type: "style", id: style.id }} />}
      <ProblemText error={save.error ?? archive.error} />
      <div className={s.actions}>
        <button type="submit" className="btn primary" disabled={save.isPending}>
          {t("styles.save")}
        </button>
        <button type="button" className="btn" disabled title={t("styles.testLater")}>
          {t("styles.test")}
        </button>
        {style && (
          <ArchiveButton
            busy={archive.isPending}
            onConfirm={() =>
              archive.mutate({ kind: "style", id: style.id }, { onSuccess: onArchived })
            }
          />
        )}
      </div>
      <span className="muted" style={{ fontSize: 12 }}>
        {t("styles.testLater")}
      </span>
    </form>
  );
}

function CharacterEditor({
  projectId,
  character,
  onSaved,
  onArchived,
}: {
  projectId: string;
  character?: Character;
  onSaved: (id: string) => void;
  onArchived: () => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState(character?.name ?? "");
  const [description, setDescription] = useState(character?.description ?? "");
  const [traits, setTraits] = useState<Pair[]>(pairsOf(character?.attributes.traits));
  const [avoid, setAvoid] = useState((character?.attributes.avoid ?? []).join("\n"));
  const save = useSaveCharacter(projectId);
  const archive = useArchive(projectId);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    save.mutate(
      {
        id: character?.id,
        name,
        description,
        attributes: { traits: recordOf(traits), avoid: linesOf(avoid) },
      },
      { onSuccess: (saved) => onSaved(saved.id) },
    );
  };

  return (
    <form className={s.form} onSubmit={submit} aria-label={t("styles.characterForm")}>
      <div className={s.header}>
        <h2 className="h-panel">{character ? character.name : t("styles.newCharacter")}</h2>
        {character && <span className="mono muted">v{character.version}</span>}
      </div>
      <label className={s.field}>
        <span className="label">{t("styles.name")}</span>
        <input
          className="input"
          required
          maxLength={120}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label className={s.field}>
        <span className="label">{t("styles.description")}</span>
        <textarea
          className="input"
          maxLength={4000}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </label>
      <PairsEditor label={t("styles.traits")} pairs={traits} onChange={setTraits} />
      <label className={s.field}>
        <span className="label">{t("styles.avoid")}</span>
        <textarea
          className="input"
          value={avoid}
          placeholder={t("styles.avoidHint")}
          onChange={(e) => setAvoid(e.target.value)}
        />
      </label>
      {character && (
        <LinkedReferences projectId={projectId} target={{ type: "character", id: character.id }} />
      )}
      {character && (
        <LinkedLoras projectId={projectId} target={{ type: "character", id: character.id }} />
      )}
      <ProblemText error={save.error ?? archive.error} />
      <div className={s.actions}>
        <button type="submit" className="btn primary" disabled={save.isPending}>
          {t("styles.save")}
        </button>
        {character && (
          <ArchiveButton
            busy={archive.isPending}
            onConfirm={() =>
              archive.mutate({ kind: "character", id: character.id }, { onSuccess: onArchived })
            }
          />
        )}
      </div>
    </form>
  );
}

/** References linked to a style or character, and a picker to add more (FR-026). */
function LinkedReferences({
  projectId,
  target,
}: {
  projectId: string;
  target: { type: "style" | "character"; id: string };
}) {
  const { t } = useTranslation();
  const [picking, setPicking] = useState(false);
  const linked = useReferences(projectId, target);
  const all = useReferences(projectId);
  const link = useLinkReference(projectId);
  const linkedIds = new Set((linked.data ?? []).map((r) => r.id));
  const candidates = (all.data ?? []).filter((r) => !linkedIds.has(r.id));

  return (
    <section className={s.field} aria-label={t("styles.references")}>
      <div className={s.header}>
        <span className="label">{t("styles.references")}</span>
        <button
          type="button"
          className="btn ghost"
          aria-expanded={picking}
          onClick={() => setPicking(!picking)}
        >
          {picking ? t("styles.done") : t("styles.addReferences")}
        </button>
      </div>
      {(linked.data ?? []).length === 0 && !picking && (
        <span className="muted">{t("styles.noReferences")}</span>
      )}
      <div className={`${s.tiles} ${s.small}`}>
        {(linked.data ?? []).map((ref) => (
          <figure key={ref.id} className={s.tile} style={{ margin: 0 }}>
            <img className={s.thumb} src={referenceFileUrl(ref.id)} alt={ref.name} />
            <button
              type="button"
              className="btn ghost"
              disabled={link.isPending}
              onClick={() => link.mutate({ referenceId: ref.id, target, linked: false })}
            >
              {t("styles.unlink")}
            </button>
          </figure>
        ))}
      </div>
      {picking && (
        <>
          <span className="muted">{t("styles.pickReferences")}</span>
          {candidates.length === 0 ? (
            <span className="muted">{t("styles.noCandidates")}</span>
          ) : (
            <div className={`${s.tiles} ${s.small}`}>
              {candidates.map((ref) => (
                <button
                  key={ref.id}
                  type="button"
                  className={s.tile}
                  disabled={link.isPending}
                  onClick={() => link.mutate({ referenceId: ref.id, target, linked: true })}
                >
                  <img className={s.thumb} src={referenceFileUrl(ref.id)} alt="" />
                  <span className={s.name}>{ref.name}</span>
                  <span className="mono muted">{t(`references.role.${ref.role}`)}</span>
                </button>
              ))}
            </div>
          )}
        </>
      )}
      <ProblemText error={link.error} />
    </section>
  );
}

/** FR-016 / FR-075: LoRAs used whenever this style or character is used, at a strength. */
function LinkedLoras({
  projectId,
  target,
}: {
  projectId: string;
  target: { type: "style" | "character"; id: string };
}) {
  const { t } = useTranslation();
  const links = useLoraLinks(target);
  const { link, unlink } = useLoraLinkActions(target);
  const models = useModels(projectId);
  const [choice, setChoice] = useState("");
  const linked = new Set((links.data ?? []).map((l) => l.model_id));
  const available = (models.data ?? []).filter(
    (m) => m.kind === "lora" && m.status === "installed" && !linked.has(m.id),
  );
  const full = (links.data ?? []).length >= 2;
  return (
    <fieldset className={s.fieldset}>
      <legend className="label">{t("styles.loras")}</legend>
      {!links.data?.length && (
        <p className="muted" style={{ margin: 0 }}>
          {t("styles.noLoras")}
        </p>
      )}
      {(links.data ?? []).map((l) => (
        <div key={l.model_id} className={s.row}>
          <span className={s.grow}>
            {l.name}{" "}
            <span className="mono muted">
              {l.family_id ?? "?"}
              {l.trigger_word ? ` · ${l.trigger_word}` : ""}
            </span>
          </span>
          <label className={s.radio}>
            {t("styles.loraStrength")}
            <input
              type="number"
              className="input mono"
              style={{ width: 80 }}
              min={0}
              max={2}
              step={0.05}
              defaultValue={l.strength}
              aria-label={t("styles.loraStrengthFor", { name: l.name })}
              onBlur={(e) => {
                const strength = Number(e.target.value);
                if (strength !== l.strength && strength >= 0 && strength <= 2)
                  link.mutate({ modelId: l.model_id, strength });
              }}
            />
          </label>
          <button type="button" className="btn ghost" onClick={() => unlink.mutate(l.model_id)}>
            {t("styles.unlinkLora")}
          </button>
        </div>
      ))}
      {!full && (
        <div className={s.row}>
          <select
            className="input"
            aria-label={t("styles.addLora")}
            value={choice}
            onChange={(e) => setChoice(e.target.value)}
          >
            <option value="">{t("styles.chooseLora")}</option>
            {available.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name} ({m.family_id ?? "?"})
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn"
            disabled={!choice || link.isPending}
            onClick={() =>
              link.mutate({ modelId: choice, strength: 0.8 }, { onSuccess: () => setChoice("") })
            }
          >
            {t("styles.addLora")}
          </button>
        </div>
      )}
      <p className="muted" style={{ margin: 0, fontSize: 12 }}>
        {t("styles.lorasHint")}
      </p>
      <ProblemText error={link.error ?? unlink.error ?? links.error} />
    </fieldset>
  );
}
