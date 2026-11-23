/** Asset Library: search, filters, tile grid with adjustable size, sort, favourites,
 * collections and multi-select actions (WP-10: FR-049-FR-058). */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";

import { useDebounced, useProject } from "../api/generation";
import { useCharacters, useStyles } from "../api/library";
import {
  PAGE,
  SORTS,
  STATES,
  useArchiveAssets,
  useCollectionActions,
  useCollections,
  useLibrary,
  useTags,
  useUpdateAsset,
  type AssetSummary,
  type LibraryFilter,
  type Sort,
  type VersionState,
} from "../api/review";
import { useUi } from "../app/store";
import { NeedsProject, ProblemText } from "./common";
import { VERSION_CLASS, VersionImage } from "./GenerationStudio";
import r from "./review.module.css";
import s from "./workspace.module.css";

export function Library() {
  const projectId = useUi((u) => u.projectId);
  if (!projectId) return <NeedsProject module="library" />;
  return <LibraryScreen key={projectId} projectId={projectId} />;
}

type Filters = Omit<LibraryFilter, "projectId" | "offset" | "q">;

function LibraryScreen({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [filters, setFilters] = useState<Filters>({ sort: "newest" });
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [tile, setTile] = useState(160);
  const [selected, setSelected] = useState<string[]>([]);
  const [target, setTarget] = useState("");
  const [newName, setNewName] = useState("");
  const q = useDebounced(search.trim(), 300);

  const project = useProject(projectId);
  const styles = useStyles(projectId);
  const characters = useCharacters(projectId);
  const collections = useCollections(projectId);
  const tags = useTags(projectId);
  const library = useLibrary({ ...filters, q, projectId, offset });
  const update = useUpdateAsset();
  const archive = useArchiveAssets();
  const collection = useCollectionActions(projectId);

  const rows = library.data ?? [];
  const set = <K extends keyof Filters>(key: K, value: Filters[K]) => {
    setFilters((f) => ({ ...f, [key]: value || undefined }));
    setOffset(0);
  };
  const toggle = (id: string) =>
    setSelected((ids) => (ids.includes(id) ? ids.filter((i) => i !== id) : [...ids, id]));
  const chosen = rows.filter((a) => selected.includes(a.id));
  const pair = chosen.length === 2 ? chosen.map((a) => a.latest_version?.id) : [];
  const comparable = pair.length === 2 && pair.every(Boolean);
  const allArchived = chosen.length > 0 && chosen.every((a) => a.archived_at);
  const current = (collections.data ?? []).find((c) => c.id === filters.collectionId);

  return (
    <section className={`panel ${s.column}`} aria-label={t("nav.library")}>
      <div className={r.filters} role="search">
        <input
          className={`input ${r.search}`}
          type="search"
          value={search}
          placeholder={t("library.search")}
          aria-label={t("library.search")}
          onChange={(e) => {
            setSearch(e.target.value);
            setOffset(0);
          }}
        />
        <Select
          label={t("library.sort")}
          value={filters.sort}
          onChange={(v) => set("sort", (v || "newest") as Sort)}
          options={SORTS.map((o) => [o, t(`library.sorts.${o}`)])}
          bare
        />
        <label className={s.radio}>
          <span className="muted">{t("library.tileSize")}</span>
          <input
            type="range"
            min={96}
            max={320}
            step={16}
            value={tile}
            onChange={(e) => setTile(Number(e.target.value))}
          />
        </label>
      </div>

      <div className={r.filters} role="group" aria-label={t("library.filters")}>
        <Select
          label={t("library.state")}
          value={filters.state ?? ""}
          onChange={(v) => set("state", v as VersionState)}
          options={STATES.map((st) => [st, t(`versionStates.${st}`)])}
        />
        <Select
          label={t("generation.category")}
          value={filters.category ?? ""}
          onChange={(v) => set("category", v)}
          options={(project.data?.config.categories ?? []).map((c) => [c.slug, c.name])}
        />
        <Select
          label={t("generation.style")}
          value={filters.styleId ?? ""}
          onChange={(v) => set("styleId", v)}
          options={(styles.data ?? []).map((st) => [st.id, st.name])}
        />
        <Select
          label={t("generation.character")}
          value={filters.characterId ?? ""}
          onChange={(v) => set("characterId", v)}
          options={(characters.data ?? []).map((c) => [c.id, c.name])}
        />
        <Select
          label={t("library.collection")}
          value={filters.collectionId ?? ""}
          onChange={(v) => set("collectionId", v)}
          options={(collections.data ?? []).map((c) => [c.id, `${c.name} (${c.asset_count})`])}
        />
        <Select
          label={t("library.tag")}
          value={filters.tag ?? ""}
          onChange={(v) => set("tag", v)}
          options={(tags.data ?? []).map((tg) => [tg.tag, `${tg.tag} (${tg.count})`])}
        />
        <button
          type="button"
          className="btn ghost"
          aria-pressed={!!filters.favorite}
          onClick={() => set("favorite", !filters.favorite)}
        >
          ★ {t("library.favorites")}
        </button>
        <label className={s.radio}>
          <input
            type="checkbox"
            checked={!!filters.includeArchived}
            onChange={(e) => set("includeArchived", e.target.checked)}
          />
          {t("library.showArchived")}
        </label>
        {current && (
          <button
            type="button"
            className="btn ghost"
            disabled={collection.drop.isPending}
            onClick={() => {
              if (window.confirm(t("library.deleteCollectionConfirm", { name: current.name }))) {
                collection.drop.mutate(current.id, {
                  onSuccess: () => set("collectionId", undefined),
                });
              }
            }}
          >
            {t("library.deleteCollection")}
          </button>
        )}
      </div>

      <ProblemText
        error={
          library.error ??
          update.error ??
          archive.error ??
          collection.add.error ??
          collection.create.error ??
          collection.drop.error
        }
      />

      {library.isPending ? (
        <p role="status" className="muted">
          {t("inputs.loading")}
        </p>
      ) : !rows.length ? (
        <p className="muted" style={{ margin: 0 }}>
          {offset ? t("library.noMore") : t("library.empty")}{" "}
          {!offset && <Link to="/generate">{t("library.openStudio")}</Link>}
        </p>
      ) : (
        <ul
          className={r.grid}
          style={{ "--tile": `${tile}px`, listStyle: "none", margin: 0, padding: 0 } as never}
          aria-label={t("library.results", { count: rows.length })}
        >
          {rows.map((a) => (
            <AssetCard
              key={a.id}
              asset={a}
              selected={selected.includes(a.id)}
              onSelect={() => toggle(a.id)}
              onFavorite={() => update.mutate({ assetId: a.id, favorite: !a.favorite_at })}
            />
          ))}
        </ul>
      )}

      {(offset > 0 || rows.length === PAGE) && (
        <nav className={r.pager} aria-label={t("library.pages")}>
          <button
            type="button"
            className="btn"
            disabled={offset === 0}
            onClick={() => setOffset((o) => Math.max(0, o - PAGE))}
          >
            {t("library.previous")}
          </button>
          <span className="muted mono">
            {offset + 1}–{offset + rows.length}
          </span>
          <button
            type="button"
            className="btn"
            disabled={rows.length < PAGE}
            onClick={() => setOffset((o) => o + PAGE)}
          >
            {t("library.next")}
          </button>
        </nav>
      )}

      {selected.length > 0 && (
        <div className={r.selection} role="region" aria-label={t("library.selection")}>
          <strong>{t("library.selected", { count: selected.length })}</strong>
          <select
            className="input"
            style={{ width: "auto" }}
            value={target}
            aria-label={t("library.collection")}
            onChange={(e) => setTarget(e.target.value)}
          >
            <option value="">{t("library.chooseCollection")}</option>
            {(collections.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn"
            disabled={!target || collection.add.isPending}
            onClick={() => collection.add.mutate({ collectionId: target, assetIds: selected })}
          >
            {t("library.addToCollection")}
          </button>
          <form
            className={s.row}
            onSubmit={(e) => {
              e.preventDefault();
              const name = newName.trim();
              if (!name) return;
              collection.create.mutate(name, {
                onSuccess: (c) => {
                  setNewName("");
                  collection.add.mutate({ collectionId: c.id, assetIds: selected });
                },
              });
            }}
          >
            <input
              className="input"
              style={{ width: 180 }}
              value={newName}
              maxLength={120}
              placeholder={t("library.newCollection")}
              aria-label={t("library.newCollection")}
              onChange={(e) => setNewName(e.target.value)}
            />
            <button
              type="submit"
              className="btn ghost"
              disabled={!newName.trim() || collection.create.isPending}
            >
              {t("library.createAndAdd")}
            </button>
          </form>
          <button
            type="button"
            className="btn"
            disabled={!comparable}
            title={comparable ? undefined : t("library.compareHint")}
            onClick={() => navigate(`/review/compare?a=${pair[0] ?? ""}&b=${pair[1] ?? ""}`)}
          >
            {t("library.compare")}
          </button>
          <button
            type="button"
            className="btn"
            disabled={archive.isPending}
            onClick={() =>
              archive.mutate(
                { ids: selected, archived: !allArchived },
                { onSuccess: () => setSelected([]) },
              )
            }
          >
            {allArchived ? t("library.restore") : t("library.archive")}
          </button>
          <button type="button" className="btn ghost" onClick={() => setSelected([])}>
            {t("library.clear")}
          </button>
        </div>
      )}
    </section>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
  bare,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: [string, string][];
  bare?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <select
      className="input"
      value={value}
      aria-label={label}
      onChange={(e) => onChange(e.target.value)}
    >
      {!bare && <option value="">{t("library.any", { what: label })}</option>}
      {options.map(([v, text]) => (
        <option key={v} value={v}>
          {text}
        </option>
      ))}
    </select>
  );
}

function AssetCard({
  asset,
  selected,
  onSelect,
  onFavorite,
}: {
  asset: AssetSummary;
  selected: boolean;
  onSelect: () => void;
  onFavorite: () => void;
}) {
  const { t } = useTranslation();
  const v = asset.latest_version;
  const favorite = !!asset.favorite_at;
  return (
    <li className={r.card} data-selected={selected}>
      <input
        type="checkbox"
        className={r.pick}
        checked={selected}
        onChange={onSelect}
        aria-label={t("library.select", { name: asset.name })}
      />
      <button
        type="button"
        className={r.star}
        aria-pressed={favorite}
        aria-label={t("library.favoriteOf", { name: asset.name })}
        title={favorite ? t("library.unfavorite") : t("library.favorite")}
        onClick={onFavorite}
      >
        {favorite ? "★" : "☆"}
      </button>
      <Link to={`/library/${asset.id}`}>
        {v && v.state !== "deleted" ? (
          <VersionImage
            id={v.id}
            className={r.img}
            alt={t("library.thumbAlt", { name: asset.name, n: v.number })}
          />
        ) : (
          <span className={r.empty}>{t("library.noImage")}</span>
        )}
        <span className={s.name} title={asset.name}>
          {asset.name}
        </span>
      </Link>
      <span className={r.meta}>
        {v ? (
          <span className={`badge ${VERSION_CLASS[v.state] ?? ""}`}>
            <i />
            {t(`versionStates.${v.state}`)}
          </span>
        ) : (
          <span />
        )}
        <span className="mono muted">
          {asset.archived_at ? `${t("versionStates.archived")} · ` : ""}
          {t("library.versions", { count: asset.version_count })}
        </span>
      </span>
    </li>
  );
}
