/** Asset details: the published (or newest) version, version history with states and
 * actions, tags, collections, regeneration and the audit trail
 * (WP-10: FR-049, FR-051-FR-057, RULE-003). */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";

import { randomSeed, useRegenerate } from "../api/generation";
import { usePublications, useTargets } from "../api/publishing";
import {
  fileUrl,
  shownVersion,
  useArchiveAssets,
  useAssetDetail,
  useAuditTrail,
  useCollectionActions,
  useCollections,
  useTags,
  useUpdateAsset,
  type AssetDetail,
} from "../api/review";
import { ProblemText } from "./common";
import { VersionImage } from "./GenerationStudio";
import {
  CommentsPanel,
  Downloads,
  DuplicatesPanel,
  MetadataPanel,
  StateBadge,
  ValidationPanel,
  VersionActions,
} from "./ReviewParts";
import r from "./review.module.css";
import s from "./workspace.module.css";

export function AssetDetails() {
  const { t } = useTranslation();
  const { assetId = "" } = useParams();
  const asset = useAssetDetail(assetId);
  if (asset.isPending) {
    return (
      <p role="status" className="muted">
        {t("inputs.loading")}
      </p>
    );
  }
  if (!asset.data) {
    return (
      <section className={`panel ${s.column}`}>
        <ProblemText error={asset.error} />
        <Link to="/library">{t("asset.back")}</Link>
      </section>
    );
  }
  return <Details key={asset.data.id} asset={asset.data} />;
}

function Details({ asset }: { asset: AssetDetail }) {
  const { t } = useTranslation();
  const versions = asset.versions;
  const [chosen, setChosen] = useState<string | null>(null);
  const version = versions.find((v) => v.id === chosen) ?? shownVersion(versions);
  const update = useUpdateAsset();
  const archive = useArchiveAssets();
  const regenerate = useRegenerate();
  const [name, setName] = useState(asset.name);
  const source = versions.find((v) => v.generation_job_id && v.state !== "deleted");

  return (
    <section className={s.stack} aria-label={asset.name}>
      <div className={`panel ${s.column}`}>
        <Link to="/library" className="muted" style={{ fontSize: 12 }}>
          ← {t("asset.back")}
        </Link>
        <div className={s.header}>
          <form
            className={s.row}
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim() && name.trim() !== asset.name) {
                update.mutate({ assetId: asset.id, name: name.trim() });
              }
            }}
          >
            <input
              className="input h-title"
              style={{ width: "min(420px, 70vw)" }}
              value={name}
              maxLength={200}
              aria-label={t("asset.name")}
              onChange={(e) => setName(e.target.value)}
            />
            {name.trim() !== asset.name && (
              <button type="submit" className="btn" disabled={!name.trim() || update.isPending}>
                {t("asset.rename")}
              </button>
            )}
          </form>
          <div className={s.actions}>
            <button
              type="button"
              className="btn ghost"
              aria-pressed={!!asset.favorite_at}
              onClick={() => update.mutate({ assetId: asset.id, favorite: !asset.favorite_at })}
            >
              {asset.favorite_at ? "★" : "☆"} {t("library.favorite")}
            </button>
            <button
              type="button"
              className="btn"
              disabled={!source || regenerate.isPending}
              title={source ? undefined : t("asset.regenerateNeedsSource")}
              onClick={() =>
                source &&
                regenerate.mutate({ versionId: source.id, changes: { seed: randomSeed() } })
              }
            >
              {t("asset.regenerate")}
            </button>
            <button
              type="button"
              className="btn ghost"
              disabled={archive.isPending}
              onClick={() => archive.mutate({ ids: [asset.id], archived: !asset.archived_at })}
            >
              {asset.archived_at ? t("library.restore") : t("asset.archive")}
            </button>
          </div>
        </div>
        <p className="muted mono" style={{ margin: 0, fontSize: 12 }}>
          {asset.slug} · {asset.category}
          {asset.archived_at && ` · ${t("versionStates.archived")}`}
        </p>
        {regenerate.isSuccess && (
          <p role="status" style={{ margin: 0 }}>
            {t("asset.regenerateQueued")} <Link to="/queue">{t("generation.openQueue")}</Link>
          </p>
        )}
        <ProblemText error={update.error ?? archive.error ?? regenerate.error} />
      </div>

      <div className={r.split}>
        <div className={s.stack}>
          <figure className="panel" style={{ margin: 0, padding: "var(--space-3)" }}>
            {version && version.state !== "deleted" ? (
              <img
                key={version.id}
                className={r.stage}
                src={fileUrl(version.id, "preview")}
                alt={t("review.previewAlt", { name: asset.name, n: version.number })}
                onError={(e) => {
                  e.currentTarget.onerror = null;
                  e.currentTarget.src = fileUrl(version.id, "original");
                }}
              />
            ) : (
              <p className="muted">{t("library.noImage")}</p>
            )}
          </figure>
          {version && (
            <div className={`panel ${s.column}`}>
              <div className={s.header}>
                <h2 className="h-panel" style={{ margin: 0 }}>
                  {t("asset.version", { n: version.number })} <StateBadge state={version.state} />
                </h2>
                <Downloads version={version} />
              </div>
              <VersionActions version={version} />
              <ValidationPanel versionId={version.id} />
              <DuplicatesPanel versionId={version.id} />
              <CommentsPanel versionId={version.id} />
              <MetadataPanel version={version} />
            </div>
          )}
        </div>

        <aside className={s.stack}>
          <div className={`panel ${s.column}`}>
            <h2 className="h-panel" style={{ margin: 0 }}>
              {t("asset.history", { count: versions.length })}
            </h2>
            <ul className={r.versions}>
              {versions.map((v) => (
                <li key={v.id}>
                  <button
                    type="button"
                    className={r.versionRow}
                    aria-current={v.id === version?.id}
                    onClick={() => setChosen(v.id)}
                  >
                    {v.state === "deleted" ? (
                      <span className={r.empty} style={{ width: 40 }} />
                    ) : (
                      <VersionImage id={v.id} className={undefined} alt="" />
                    )}
                    <span className="mono">v{v.number}</span>
                    <StateBadge state={v.state} />
                  </button>
                </li>
              ))}
            </ul>
            {version && <CompareLink versions={versions} current={version.id} />}
          </div>
          <PublicationsPanel asset={asset} />
          <TagsPanel asset={asset} />
          <CollectionsPanel asset={asset} />
          <TrailPanel asset={asset} />
        </aside>
      </div>
    </section>
  );
}

function CompareLink({
  versions,
  current,
}: {
  versions: AssetDetail["versions"];
  current: string;
}) {
  const { t } = useTranslation();
  const live = versions.filter((v) => v.state !== "deleted" && v.id !== current);
  const [other, setOther] = useState(live[0]?.id ?? "");
  if (!live.length) return null;
  return (
    <div className={s.row}>
      <select
        className="input"
        style={{ width: "auto" }}
        value={other}
        aria-label={t("asset.compareWith")}
        onChange={(e) => setOther(e.target.value)}
      >
        {live.map((v) => (
          <option key={v.id} value={v.id}>
            v{v.number}
          </option>
        ))}
      </select>
      <Link className="btn ghost" to={`/review/compare?a=${other}&b=${current}`}>
        {t("library.compare")}
      </Link>
    </div>
  );
}

/** FR-049: free tags, suggested from the project's tags. */
function TagsPanel({ asset }: { asset: AssetDetail }) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const suggestions = useTags(asset.project_id, text.trim());
  const update = useUpdateAsset();
  const tags = asset.tags ?? [];
  const save = (next: string[]) => update.mutate({ assetId: asset.id, tags: next });
  const listId = `tags-${asset.id}`;
  return (
    <div className={`panel ${s.column}`}>
      <h2 className="h-panel" style={{ margin: 0 }}>
        {t("asset.tags")}
      </h2>
      {tags.length > 0 && (
        <ul className={r.tags} style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {tags.map((tag) => (
            <li key={tag} className={r.tag}>
              {tag}
              <button
                type="button"
                aria-label={t("asset.removeTag", { tag })}
                onClick={() => save(tags.filter((x) => x !== tag))}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      <form
        className={s.row}
        onSubmit={(e) => {
          e.preventDefault();
          const tag = text.trim();
          if (tag) save([...tags, tag]);
          setText("");
        }}
      >
        <input
          className={`input ${s.grow}`}
          list={listId}
          value={text}
          maxLength={40}
          placeholder={t("asset.addTag")}
          aria-label={t("asset.addTag")}
          onChange={(e) => setText(e.target.value)}
        />
        <datalist id={listId}>
          {(suggestions.data ?? [])
            .filter((sg) => !tags.includes(sg.tag))
            .map((sg) => (
              <option key={sg.tag} value={sg.tag} />
            ))}
        </datalist>
        <button type="submit" className="btn" disabled={!text.trim() || update.isPending}>
          {t("asset.add")}
        </button>
      </form>
      <ProblemText error={update.error} />
    </div>
  );
}

/** FR-056: which collections hold the asset. */
function CollectionsPanel({ asset }: { asset: AssetDetail }) {
  const { t } = useTranslation();
  const collections = useCollections(asset.project_id);
  const actions = useCollectionActions(asset.project_id);
  const member = new Set(asset.collection_ids ?? []);
  const rows = collections.data ?? [];
  return (
    <div className={`panel ${s.column}`}>
      <h2 className="h-panel" style={{ margin: 0 }}>
        {t("asset.collections")}
      </h2>
      {!rows.length ? (
        <p className="muted" style={{ margin: 0 }}>
          {t("asset.noCollections")}
        </p>
      ) : (
        rows.map((c) => (
          <label key={c.id} className={s.radio}>
            <input
              type="checkbox"
              checked={member.has(c.id)}
              disabled={actions.add.isPending || actions.remove.isPending}
              onChange={(e) =>
                e.target.checked
                  ? actions.add.mutate({ collectionId: c.id, assetIds: [asset.id] })
                  : actions.remove.mutate({ collectionId: c.id, assetId: asset.id })
              }
            />
            {c.name}
          </label>
        ))
      )}
      <ProblemText error={actions.add.error ?? actions.remove.error} />
    </div>
  );
}

/** FR-051: what happened to the asset and its versions, newest first (RULE-006). */
function TrailPanel({ asset }: { asset: AssetDetail }) {
  const { t, i18n } = useTranslation();
  const trail = useAuditTrail([asset.id, ...asset.versions.map((v) => v.id)]);
  const number = new Map(asset.versions.map((v) => [v.id, v.number]));
  const time = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" });
  return (
    <div className={`panel ${s.column}`}>
      <h2 className="h-panel" style={{ margin: 0 }}>
        {t("asset.trail")}
      </h2>
      <ul className={r.trail}>
        {(trail.data ?? []).map((e) => {
          const n = e.subject_id ? number.get(e.subject_id) : undefined;
          const reason = (e.data as { reason?: string }).reason;
          return (
            <li key={e.id}>
              <span className="mono muted">{time.format(new Date(e.at))}</span>{" "}
              {n != null && <span className="mono">v{n} </span>}
              {t(`asset.actions.${e.action.replace(/\./g, "_")}`, { defaultValue: e.action })}
              <span className="muted">
                {" "}
                · {t(`asset.actors.${e.actor}`, { defaultValue: e.actor })}
              </span>
              {reason && <span className="muted"> · {reason}</span>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** FR-093: where the asset is published, which version and which files. */
function PublicationsPanel({ asset }: { asset: AssetDetail }) {
  const { t, i18n } = useTranslation();
  const publications = usePublications({ assetId: asset.id });
  const targets = useTargets(asset.project_id);
  const names = new Map((targets.data ?? []).map((x) => [x.id, x.name]));
  const number = new Map(asset.versions.map((v) => [v.id, v.number]));
  const time = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" });
  const rows = publications.data ?? [];
  return (
    <div className={`panel ${s.column}`}>
      <div className={s.header}>
        <h2 className="h-panel" style={{ margin: 0 }}>
          {t("asset.publications")}
        </h2>
        <Link className="btn ghost" to="/publish">
          {t("library.publish")}
        </Link>
      </div>
      {!rows.length ? (
        <p className="muted" style={{ margin: 0 }}>
          {t("asset.notPublished")}
        </p>
      ) : (
        <ul className={r.trail}>
          {rows.map((p) => (
            <li key={p.id}>
              <span className="mono">v{number.get(p.asset_version_id) ?? "?"}</span> →{" "}
              {names.get(p.target_id) ?? "?"}{" "}
              <span className="mono muted">{time.format(new Date(p.at))}</span>
              <br />
              <span className="mono muted">
                {(p.files ?? []).map((f) => f.relative_path).join(", ")}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
