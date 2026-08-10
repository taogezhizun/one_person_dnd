(() => {
  "use strict";

  const node = document.getElementById("dnd-i18n");
  let catalog = {};
  try {
    catalog = node ? JSON.parse(node.textContent || "{}") : {};
  } catch (_error) {
    catalog = {};
  }

  const placeholderPattern = /\{([A-Za-z_][A-Za-z0-9_]*)\}/g;
  const t = (key, values = {}) => {
    const template = Object.prototype.hasOwnProperty.call(catalog, key) ? catalog[key] : `⟦${key}⟧`;
    return String(template).replace(placeholderPattern, (_match, name) =>
      Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : `{${name}}`
    );
  };

  const locale = document.documentElement.lang || "zh-CN";
  window.DndI18n = Object.freeze({ locale, t });

  document.body.addEventListener("htmx:configRequest", (event) => {
    event.detail.headers["X-DND-UI-Locale"] = locale;
  });
})();
