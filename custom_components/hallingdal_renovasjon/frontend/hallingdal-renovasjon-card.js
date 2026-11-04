/**
 * Hallingdal Renovasjon card.
 *
 * Shipped with the integration and loaded automatically (no Lovelace resource
 * needed). Reads the integration's sensors for one property (device) and shows
 * them with the official sorting pictograms.
 *
 *   type: custom:hallingdal-renovasjon-card
 *   device_id: <optional, defaults to the first property>
 *   layout: list | tiles | next          (default: list)
 *   title: <optional, defaults to the address>
 *   show_title: true
 *   fractions: [restavfall, matavfall, papir, plast, glass_metall]  (filter + order)
 *   sort: date | fixed                   (default: date)
 *   date_format: both | relative | date  (default: both)
 *   highlight_days: 1                    (highlight pickups within N days, 0 = off)
 *   max_items: <optional>
 *   language: auto | nb | en             (default: auto, follows Home Assistant)
 */

const DOMAIN = "hallingdal_renovasjon";
const CARD = "hallingdal-renovasjon-card";
const ASSET_VERSION = new URL(import.meta.url).searchParams.get("v") || "";
const NEXT_KEY = "neste_henting";

const FRACTIONS = {
  restavfall: { color: "#141414", nb: "Restavfall", en: "Residual waste" },
  matavfall: { color: "#00A04B", nb: "Matavfall", en: "Food waste" },
  papir: { color: "#0082BE", nb: "Papir og papp", en: "Paper and cardboard" },
  plast: { color: "#961E82", nb: "Plastemballasje", en: "Plastic packaging" },
  glass_metall: { color: "#1CA68D", nb: "Glass- og metallemballasje", en: "Glass and metal packaging" },
};
const PAIRS = new Set(["papir", "glass_metall"]);

const STRINGS = {
  nb: {
    today: "I dag",
    tomorrow: "I morgen",
    in_days: (n) => `Om ${n} dager`,
    next: "Neste henting",
    then: "Deretter",
    none: "Ingen planlagt",
    no_device: "Fant ingen eiendom fra Hallingdal Renovasjon. Legg til integrasjonen først.",
    unavailable: "Utilgjengelig",
    card_name: "Hallingdal Renovasjon",
    card_description: "Tømmeplan med de offisielle sorteringsmerkene.",
    editor: {
      device_id: "Eiendom",
      layout: "Visning",
      title: "Tittel (standard: adressen)",
      show_title: "Vis tittel",
      fractions: "Avfallstyper (tomt = alle)",
      sort: "Rekkefølge",
      date_format: "Dato",
      highlight_days: "Uthev henting innen (dager)",
      max_items: "Maks antall rader",
      language: "Språk",
    },
    options: {
      list: "Liste",
      tiles: "Fliser",
      next: "Neste henting",
      date: "Etter dato",
      fixed: "Fast rekkefølge",
      both: "Relativ og dato",
      relative: "Bare relativ («I morgen»)",
      date_only: "Bare dato",
      auto: "Som Home Assistant",
      nb: "Norsk",
      en: "English",
    },
  },
  en: {
    today: "Today",
    tomorrow: "Tomorrow",
    in_days: (n) => `In ${n} days`,
    next: "Next pickup",
    then: "Later",
    none: "Not scheduled",
    no_device: "No Hallingdal Renovasjon property found. Add the integration first.",
    unavailable: "Unavailable",
    card_name: "Hallingdal Renovasjon",
    card_description: "Waste collection schedule with the official sorting pictograms.",
    editor: {
      device_id: "Property",
      layout: "Layout",
      title: "Title (default: the address)",
      show_title: "Show title",
      fractions: "Waste types (empty = all)",
      sort: "Order",
      date_format: "Date",
      highlight_days: "Highlight pickups within (days)",
      max_items: "Max rows",
      language: "Language",
    },
    options: {
      list: "List",
      tiles: "Tiles",
      next: "Next pickup",
      date: "By date",
      fixed: "Fixed order",
      both: "Relative and date",
      relative: "Relative only (“Tomorrow”)",
      date_only: "Date only",
      auto: "Same as Home Assistant",
      nb: "Norsk",
      en: "English",
    },
  },
};

const DEFAULTS = {
  layout: "list",
  show_title: true,
  sort: "date",
  date_format: "both",
  highlight_days: 1,
  language: "auto",
};

function langOf(hass, config) {
  const wanted = config?.language && config.language !== "auto" ? config.language : null;
  if (wanted) return wanted === "nb" ? "nb" : "en";
  const ha = (hass?.locale?.language || hass?.language || "en").toLowerCase();
  return /^(nb|nn|no)/.test(ha) ? "nb" : "en";
}

function propertyDevices(hass) {
  const ids = new Set();
  for (const entity of Object.values(hass?.entities || {})) {
    if (entity.platform === DOMAIN && entity.device_id) ids.add(entity.device_id);
  }
  return [...ids];
}

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

function localToday() {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

function parseDate(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null;
}

class HallingdalRenovasjonCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement(`${CARD}-editor`);
  }

  static getStubConfig(hass) {
    const [device_id] = propertyDevices(hass);
    return device_id ? { device_id } : {};
  }

  setConfig(config) {
    const layout = config?.layout ?? DEFAULTS.layout;
    if (!["list", "tiles", "next"].includes(layout)) {
      throw new Error(`Unknown layout: ${layout}`);
    }
    this._config = { ...DEFAULTS, ...config };
    this._signature = undefined;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    const n = this._items?.length ?? 3;
    if (this._config?.layout === "tiles") return 1 + Math.ceil(n / 3) * 2;
    if (this._config?.layout === "next") return 3 + n;
    return 1 + n;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  _t() {
    return STRINGS[langOf(this._hass, this._config)];
  }

  _deviceId() {
    return this._config.device_id || propertyDevices(this._hass)[0];
  }

  _collect() {
    const hass = this._hass;
    const deviceId = this._deviceId();
    const lang = langOf(hass, this._config);
    const device = hass.devices?.[deviceId];
    const deviceName = device?.name_by_user || device?.name || "";
    const today = localToday();
    const items = [];
    for (const entity of Object.values(hass.entities || {})) {
      if (entity.platform !== DOMAIN || entity.device_id !== deviceId) continue;
      if (!entity.entity_id.startsWith("sensor.") || entity.translation_key === NEXT_KEY) continue;
      const state = hass.states[entity.entity_id];
      if (!state) continue;
      const key = entity.translation_key || entity.entity_id.split(".")[1];
      const meta = FRACTIONS[key];
      let name = meta?.[lang];
      if (!name) {
        name = state.attributes.friendly_name || key;
        if (deviceName && name.startsWith(`${deviceName} `)) name = name.slice(deviceName.length + 1);
      }
      const date = parseDate(state.state);
      let days = state.attributes.days_until;
      if (date && typeof days !== "number") days = Math.round((date - today) / 86400000);
      items.push({
        key,
        known: Boolean(meta),
        entityId: entity.entity_id,
        name,
        color: meta?.color || "var(--secondary-text-color)",
        date,
        days: date ? days : null,
        unavailable: state.state === "unavailable",
        upcoming: state.attributes.upcoming || [],
      });
    }
    return { items, deviceName };
  }

  _select(items) {
    const cfg = this._config;
    let out = items;
    const wanted = Array.isArray(cfg.fractions) && cfg.fractions.length ? cfg.fractions : null;
    if (wanted) out = out.filter((i) => wanted.includes(i.key));
    const order = (i) => {
      const list = wanted || Object.keys(FRACTIONS);
      const idx = list.indexOf(i.key);
      return idx === -1 ? 999 : idx;
    };
    out.sort((a, b) => {
      if (cfg.sort !== "fixed") {
        const da = a.date ? a.date.getTime() : Infinity;
        const db = b.date ? b.date.getTime() : Infinity;
        if (da !== db) return da - db;
      }
      return order(a) - order(b) || a.name.localeCompare(b.name);
    });
    if (cfg.max_items > 0) out = out.slice(0, cfg.max_items);
    return out;
  }

  _relative(item) {
    const t = this._t();
    if (item.unavailable) return t.unavailable;
    if (item.days == null) return t.none;
    if (item.days <= 0) return t.today;
    if (item.days === 1) return t.tomorrow;
    return t.in_days(item.days);
  }

  _dateText(date, long = false) {
    if (!date) return "";
    const locale = langOf(this._hass, this._config) === "nb" ? "nb-NO" : this._hass?.locale?.language || "en";
    return new Intl.DateTimeFormat(locale, {
      weekday: "long",
      day: "numeric",
      month: long ? "long" : "short",
    }).format(date);
  }

  /** Primary and secondary line for an item, per date_format. */
  _when(item, long = false) {
    const rel = this._relative(item);
    const date = this._dateText(item.date, long);
    switch (this._config.date_format) {
      case "relative":
        return [rel, ""];
      case "date":
        return [date || rel, ""];
      default:
        return [rel, date];
    }
  }

  _soon(item) {
    const limit = Number(this._config.highlight_days) || 0;
    return limit > 0 && item.days != null && item.days >= 0 && item.days <= limit;
  }

  _picture(item, cls) {
    if (!item.known) {
      return `<div class="pic ${cls} unknown"><ha-icon icon="mdi:trash-can-outline"></ha-icon></div>`;
    }
    const v = ASSET_VERSION ? `?v=${encodeURIComponent(ASSET_VERSION)}` : "";
    const pair = PAIRS.has(item.key) ? " pair" : "";
    return `<img class="pic ${cls}${pair}" alt="" src="/${DOMAIN}/images/card/${item.key}.png${v}">`;
  }

  _render() {
    if (!this._config || !this._hass) return;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const t = this._t();
    const deviceId = this._deviceId();
    if (!deviceId) {
      this._paint(`<div class="empty">${escapeHtml(t.no_device)}</div>`, "no-device");
      return;
    }
    const { items, deviceName } = this._collect();
    const selected = this._select(items);
    this._items = selected;
    const signature = JSON.stringify([
      this._config,
      langOf(this._hass, this._config),
      deviceName,
      selected.map((i) => [i.entityId, i.date?.getTime(), i.days, i.unavailable, i.name]),
    ]);
    if (signature === this._signature) return;
    this._signature = signature;

    const title = this._config.show_title === false ? "" : this._config.title || deviceName;
    const header = title ? `<h1 class="title">${escapeHtml(title)}</h1>` : "";
    let body;
    if (!selected.length) body = `<div class="empty">${escapeHtml(t.none)}</div>`;
    else if (this._config.layout === "tiles") body = this._tiles(selected);
    else if (this._config.layout === "next") body = this._next(selected);
    else body = this._list(selected);
    this._paint(header + body, this._config.layout);
  }

  _list(items) {
    return `<div class="list">${items
      .map((item) => {
        const [primary, secondary] = this._when(item);
        const soon = this._soon(item) ? " soon" : "";
        return `<button class="row${soon}" data-entity="${item.entityId}" style="--fraction:${item.color}">
          <span class="pics">${this._picture(item, "small")}</span>
          <span class="text">
            <span class="name">${escapeHtml(item.name)}</span>
            ${secondary ? `<span class="sub">${escapeHtml(secondary)}</span>` : ""}
          </span>
          <span class="chip">${escapeHtml(primary)}</span>
        </button>`;
      })
      .join("")}</div>`;
  }

  _tiles(items) {
    return `<div class="tiles">${items
      .map((item) => {
        const [primary, secondary] = this._when(item);
        const soon = this._soon(item) ? " soon" : "";
        return `<button class="tile${soon}" data-entity="${item.entityId}" style="--fraction:${item.color}">
          ${this._picture(item, "large")}
          <span class="name">${escapeHtml(item.name)}</span>
          <span class="when">${escapeHtml(primary)}</span>
          ${secondary ? `<span class="sub">${escapeHtml(secondary)}</span>` : ""}
        </button>`;
      })
      .join("")}</div>`;
  }

  _next(items) {
    const t = this._t();
    const dated = items.filter((i) => i.date);
    if (!dated.length) return this._list(items);
    const first = Math.min(...dated.map((i) => i.date.getTime()));
    const now = dated.filter((i) => i.date.getTime() === first);
    const rest = items.filter((i) => !now.includes(i));
    const lead = now[0];
    const soon = this._soon(lead) ? " soon" : "";
    const rel = this._relative(lead);
    const date = this._dateText(lead.date, true);
    const big = this._config.date_format === "date" ? date : rel;
    const small = this._config.date_format === "both" ? date : "";
    const hero = `<div class="hero${soon}" style="--fraction:${lead.color}">
      <div class="label">${escapeHtml(t.next)}</div>
      <div class="big">${escapeHtml(big)}</div>
      ${small ? `<div class="sub">${escapeHtml(small)}</div>` : ""}
      <div class="hero-items">${now
        .map(
          (item) => `<button class="hero-item" data-entity="${item.entityId}">
            ${this._picture(item, "large")}
            <span class="name">${escapeHtml(item.name)}</span>
          </button>`,
        )
        .join("")}</div>
    </div>`;
    if (!rest.length) return hero;
    const later = `<div class="label later">${escapeHtml(t.then)}</div><div class="compact">${rest
      .map((item) => {
        const [primary, secondary] = this._when(item);
        const soon = this._soon(item) ? " soon" : "";
        return `<button class="crow${soon}" data-entity="${item.entityId}" style="--fraction:${item.color}">
          <span class="pics">${this._picture(item, "tiny")}</span>
          <span class="text">
            <span class="name">${escapeHtml(item.name)}</span>
            ${secondary ? `<span class="sub">${escapeHtml(secondary)}</span>` : ""}
          </span>
          <span class="chip">${escapeHtml(primary)}</span>
        </button>`;
      })
      .join("")}</div>`;
    return hero + later;
  }

  _paint(inner, layout) {
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card class="${layout}">${inner}</ha-card>`;
    for (const el of this.shadowRoot.querySelectorAll("[data-entity]")) {
      el.addEventListener("click", () =>
        this.dispatchEvent(
          new CustomEvent("hass-more-info", {
            detail: { entityId: el.dataset.entity },
            bubbles: true,
            composed: true,
          }),
        ),
      );
    }
  }
}

const STYLE = `
  :host { --gap: 12px; }
  ha-card { padding: 16px; overflow: hidden; }
  button { all: unset; box-sizing: border-box; cursor: pointer; }
  button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; border-radius: 8px; }
  .title { margin: 0 0 12px; font-size: var(--ha-card-header-font-size, 20px); font-weight: 500;
           color: var(--ha-card-header-color, var(--primary-text-color)); line-height: 1.3; }
  .empty { color: var(--secondary-text-color); padding: 8px 0; }
  .sub { color: var(--secondary-text-color); font-size: 13px; }
  .name { color: var(--primary-text-color); font-weight: 500; }
  .pic { display: block; border-radius: 4px; flex: none; }
  .pic.unknown { display: grid; place-items: center; background: var(--secondary-background-color);
                 color: var(--secondary-text-color); aspect-ratio: 1; }
  .pic.small { height: 40px; }
  .pic.tiny { height: 28px; }
  .pic.large { height: 64px; }
  .pics { width: calc(var(--pic-h) * 2 + 2px); display: flex; flex: none; }
  .pic.small.unknown { width: 40px; } .pic.tiny.unknown { width: 28px; } .pic.large.unknown { width: 64px; }

  /* list */
  .list { display: flex; flex-direction: column; gap: 4px; --pic-h: 40px; }
  .row { display: flex; align-items: center; gap: var(--gap); padding: 6px 8px; margin: 0 -8px;
         border-radius: 10px; }
  .row:hover { background: var(--secondary-background-color); }
  .row .text { display: flex; flex-direction: column; min-width: 0; flex: 1; }
  .row .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chip { flex: none; padding: 4px 10px; border-radius: 999px; font-size: 13px; font-weight: 500;
          background: var(--secondary-background-color); color: var(--secondary-text-color); white-space: nowrap; }
  .soon .chip { background: var(--fraction); color: #fff; }
  .row.soon { background: color-mix(in srgb, var(--fraction) 10%, transparent); }

  /* tiles */
  .tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(132px, 1fr)); gap: var(--gap); }
  .tile { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 4px;
          padding: 12px 8px; border-radius: 12px; border: 1px solid var(--divider-color); }
  .tile .pic { margin-bottom: 6px; }
  .tile .name { font-size: 13px; line-height: 1.25; min-height: 2.5em; display: flex; align-items: center; }
  .tile .when { font-size: 18px; font-weight: 600; color: var(--primary-text-color); }
  .tile.soon { border: 2px solid var(--fraction); background: color-mix(in srgb, var(--fraction) 8%, transparent); }
  .tile.soon .when { color: var(--fraction); }

  /* next */
  .hero { padding: 16px; border-radius: 14px; background: var(--secondary-background-color); }
  .hero.soon { background: color-mix(in srgb, var(--fraction) 14%, var(--card-background-color, #fff)); }
  .label { text-transform: uppercase; letter-spacing: .06em; font-size: 12px; font-weight: 600;
           color: var(--secondary-text-color); }
  .big { font-size: 32px; font-weight: 600; line-height: 1.15; margin-top: 4px; color: var(--primary-text-color); }
  .hero-items { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 14px; }
  .hero-item { display: flex; flex-direction: column; gap: 6px; max-width: 150px; }
  .hero-item .name { font-size: 13px; }
  .later { margin: 16px 0 6px; }
  .compact { display: flex; flex-direction: column; gap: 2px; --pic-h: 28px; }
  .crow { display: flex; align-items: center; gap: 10px; padding: 4px 8px; margin: 0 -8px; border-radius: 8px; }
  .crow:hover { background: var(--secondary-background-color); }
  .crow .text { display: flex; flex-direction: column; min-width: 0; flex: 1; line-height: 1.25; }
  .crow .name { font-weight: 400; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .crow .sub { font-size: 12px; }
`;

class HallingdalRenovasjonCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._update();
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  _schema(t) {
    const opt = (values) => values.map(([value, key]) => ({ value, label: t.options[key || value] }));
    const lang = langOf(this._hass, this._config);
    return [
      { name: "device_id", selector: { device: { integration: DOMAIN } } },
      {
        name: "layout",
        selector: { select: { mode: "dropdown", options: opt([["list"], ["tiles"], ["next"]]) } },
      },
      {
        type: "grid",
        name: "",
        schema: [
          { name: "title", selector: { text: {} } },
          { name: "show_title", selector: { boolean: {} } },
        ],
      },
      {
        name: "fractions",
        selector: {
          select: {
            multiple: true,
            mode: "list",
            options: Object.entries(FRACTIONS).map(([value, meta]) => ({ value, label: meta[lang] })),
          },
        },
      },
      {
        type: "grid",
        name: "",
        schema: [
          { name: "sort", selector: { select: { mode: "dropdown", options: opt([["date"], ["fixed"]]) } } },
          {
            name: "date_format",
            selector: {
              select: { mode: "dropdown", options: opt([["both"], ["relative"], ["date", "date_only"]]) },
            },
          },
          { name: "highlight_days", selector: { number: { min: 0, max: 14, mode: "box" } } },
          { name: "max_items", selector: { number: { min: 1, max: 20, mode: "box" } } },
          {
            name: "language",
            selector: { select: { mode: "dropdown", options: opt([["auto"], ["nb"], ["en"]]) } },
          },
        ],
      },
    ];
  }

  _update() {
    if (!this._hass || !this._config) return;
    const t = STRINGS[langOf(this._hass, this._config)];
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (field) => this._labels?.[field.name] ?? field.name;
      this._form.addEventListener("value-changed", (ev) => {
        const config = { ...ev.detail.value };
        for (const [key, value] of Object.entries(config)) {
          if (value === "" || value == null || (Array.isArray(value) && !value.length)) delete config[key];
        }
        this._config = config;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._labels = t.editor;
    this._form.hass = this._hass;
    this._form.schema = this._schema(t);
    this._form.data = { ...DEFAULTS, ...this._config };
  }
}

if (!customElements.get(CARD)) {
  customElements.define(CARD, HallingdalRenovasjonCard);
  customElements.define(`${CARD}-editor`, HallingdalRenovasjonCardEditor);
  window.customCards = window.customCards || [];
  const t = STRINGS[/^(nb|nn|no)/i.test(navigator.language) ? "nb" : "en"];
  window.customCards.push({
    type: CARD,
    name: t.card_name,
    description: t.card_description,
    preview: true,
    documentationURL: "https://github.com/slevigen/hallingdal_renovasjon#kort",
  });
}
