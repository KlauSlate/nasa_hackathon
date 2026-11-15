"use strict";
/* Analog Mission Designer — interfaz estática.
   Lee los resultados precalculados por el pipeline (web/data/). No calcula similitud:
   solo muestra, compara y exporta lo que viene de los archivos. */

const KEYS = ["slope_p50_deg", "slope_p90_deg", "roughness_270m_m", "relief_p95_p5_m"];
const LABEL = {
  slope_p50_deg: ["Pendiente mediana", "°"], slope_p90_deg: ["Pendiente P90", "°"],
  roughness_270m_m: ["Rugosidad (270 m)", " m"], relief_p95_p5_m: ["Relieve local P95–P5", " m"],
};
const FAR_KM = 25; // más lejos que esto del sitio documentado: posible lugar nuevo
const $ = (id) => document.getElementById(id);
const S = { val: null, meta: null, lunar: [], earth: {}, ctx: {}, sel: 0, site: null, all: [], cand: 0, region: "all", heat: false, suit: "", hover: null, maps: {}, img: null };

const f1 = (x, d = 1) => Number(x).toLocaleString("es-CL", { minimumFractionDigits: d, maximumFractionDigits: d });
const lat = (x) => `${f1(Math.abs(x), 3)}° ${x < 0 ? "S" : "N"}`;
const lon = (x) => `${f1(Math.abs(x), 3)}° ${x < 0 ? "O" : "E"}`;
const pct = (x) => f1(x * 100, 0) + " %";
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function boot() {
  try {
    const [meta, lunar, earth, ctx] = await Promise.all(
      ["meta", "lunar_windows", "earth_windows", "context"].map((n) => fetch(`data/${n}.json`).then((r) => {
        if (!r.ok) throw new Error(n); return r.json();
      })));
    S.meta = meta; S.all = lunar; S.earth = earth; S.ctx = ctx;
    try { S.val = await fetch("data/validation.json").then((r) => (r.ok ? r.json() : null)); } catch (e2) { S.val = null; }
  } catch (e) {
    document.querySelector("main").innerHTML =
      `<div class="card"><h2>No se pudieron cargar los datos</h2>
       <p class="lead">Abre esta página desde un servidor local (no con doble clic):
       <code>python -m http.server 8000</code> dentro de la carpeta <code>web/</code>, y visita
       <code>http://localhost:8000</code>. Si ya lo hiciste, ejecuta antes <code>run_regions.py</code>.</p></div>`;
    return;
  }
  $("src-moon").href = S.meta.source_url_moon;
  $("src-earth").href = S.meta.earth.source_url;
  $("status").textContent = S.meta.status;
  const regs = Object.values(S.meta.regions);
  $("nreg").textContent = regs.length;
  $("regionsel").innerHTML = `<option value="all">Todas</option>` + regs.map((r) => `<option value="${r.id}">${esc(r.short)}</option>`).join("");
  $("sitesel").innerHTML = Object.values(S.meta.lunar_sites).map((x) => `<option value="${x.id}">${esc(x.short)}</option>`).join("");
  wire();
  setSite(S.meta.default_site);
  renderConfig();
}

/* Sitio lunar activo: S.lunar son solo sus ventanas; las coordenadas X/Y no se repiten entre sitios */
const SM = () => S.meta.lunar_sites[S.site];
function setSite(id) {
  S.site = id; S.hover = null;
  S.lunar = S.all.filter((w) => w.site === id);
  const ref = S.meta.reference_window;
  if (ref.site === id) S.sel = nearest(ref.center[0], ref.center[1]);
  else { const [l, b, r, t] = SM().bounds; S.sel = nearest((l + r) / 2, (b + t) / 2); }
  $("sitesel").value = id;
  $("moontitle").textContent = SM().short;
  S.cand = 0;
  S.img = new Image();
  S.img.onload = () => { drawMoon(); renderMoonPanel(); renderLive(); };
  S.img.src = SM().image;
}

function nearest(x, y) {
  let best = 0, bd = Infinity;
  S.lunar.forEach((w, i) => { const d = (w.center_x - x) ** 2 + (w.center_y - y) ** 2; if (d < bd) { bd = d; best = i; } });
  return best;
}
/* Candidatos de la ventana lunar elegida, según el filtro de región */
const entries = () => (S.region === "all" ? S.lunar[S.sel].top : (S.lunar[S.sel].by_region[S.region] || []));
const bestD = (w) => w.top[0].D;

/* ---------- Luna ---------- */
const B = () => SM().bounds; // [left,bottom,right,top] en metros
function toPx(x, y, cv) { const [l, b, r, t] = B(); return [(x - l) / (r - l) * cv.width, (t - y) / (t - b) * cv.height]; }
function toM(px, py, cv) { const [l, b, r, t] = B(); return [l + px / cv.width * (r - l), t - py / cv.height * (t - b)]; }

function heatColor(D) {
  const t = Math.max(0, Math.min(1, D / 3));
  const a = t < 0.5 ? [47, 184, 111] : [232, 212, 77], c = t < 0.5 ? [232, 212, 77] : [226, 87, 76];
  const u = t < 0.5 ? t * 2 : (t - 0.5) * 2;
  return `rgba(${a.map((v, i) => Math.round(v + (c[i] - v) * u)).join(",")},0.8)`;
}

function drawMoon() {
  const cv = $("moon"), g = cv.getContext("2d");
  g.clearRect(0, 0, cv.width, cv.height);
  g.drawImage(S.img, 0, 0, cv.width, cv.height);
  if (S.heat) S.lunar.forEach((w) => {
    const [px, py] = toPx(w.center_x, w.center_y, cv);
    g.fillStyle = heatColor(bestD(w)); g.beginPath(); g.arc(px, py, 7, 0, 7); g.fill();
  });
  if (S.suit) S.lunar.forEach((w) => {
    const sp = w.base_suitability && w.base_suitability[S.suit];
    if (!sp || !sp.meets) return;
    const [px, py] = toPx(w.center_x, w.center_y, cv);
    g.fillStyle = "rgba(47,184,111,.85)"; g.strokeStyle = "#fff"; g.lineWidth = 1.5;
    g.beginPath(); g.arc(px, py, 7, 0, 7); g.fill(); g.stroke();
  });
  const half = SM().window_m / 2;
  const box = (w, stroke, fill, lw) => {
    const [x0, y0] = toPx(w.center_x - half, w.center_y + half, cv), [x1, y1] = toPx(w.center_x + half, w.center_y - half, cv);
    g.lineWidth = lw; g.strokeStyle = stroke; if (fill) { g.fillStyle = fill; g.fillRect(x0, y0, x1 - x0, y1 - y0); }
    g.strokeRect(x0, y0, x1 - x0, y1 - y0);
  };
  if (S.hover != null && S.hover !== S.sel) box(S.lunar[S.hover], "rgba(255,255,255,.7)", null, 1.5);
  box(S.lunar[S.sel], "#4da3ff", "rgba(77,163,255,.22)", 3);
  g.fillStyle = "#fff"; g.font = "600 22px system-ui"; g.fillText("3 × 3 km", 14, 32);
  g.font = "16px system-ui"; g.fillText("N ↑", cv.width - 50, 30);
  const [sx0, sy] = [cv.width - 190, cv.height - 26], len = 2000 / (B()[2] - B()[0]) * cv.width;
  g.strokeStyle = "#fff"; g.lineWidth = 3; g.beginPath(); g.moveTo(sx0, sy); g.lineTo(sx0 + len, sy); g.stroke();
  g.fillText("2 km", sx0 + len + 8, sy + 5);
}

function renderMoonPanel() {
  const w = S.lunar[S.sel];
  $("winpos").textContent = `centro X ${f1(w.center_x, 0)} m · Y ${f1(w.center_y, 0)} m`;
  $("moonmetrics").innerHTML = KEYS.map((k) => `<dt>${LABEL[k][0]}</dt><dd>${f1(w.metrics[k])}${LABEL[k][1]}</dd>`).join("") +
    (w.illumination ? `<dt>Iluminación media</dt><dd>${pct(w.illumination.illumination_mean)}<small>promedio ~18,6 años, a nivel del suelo</small></dd>
     <dt>Visibilidad de la Tierra</dt><dd>${pct(w.illumination.earth_visibility_mean)}</dd>
     <dt>Sombra permanente</dt><dd>${pct(w.illumination.psr_fraction)} del área</dd>` : "") +
    `<dt>Fracción observada por LOLA</dt><dd>${w.lola_observed_fraction == null ? "Sin datos" : pct(w.lola_observed_fraction)}<small>el resto es interpolado</small></dd>`;
  $("moonslope").innerHTML = S.meta.slope_class_labels.map((l, i) =>
    `<div class="row"><span>${l}</span><div class="track"><div class="fill" style="width:${w.slope_classes[i] * 100}%"></div></div><span class="val">${pct(w.slope_classes[i])}</span></div>`).join("");
  renderSuitability(w);
  $("moonquality").textContent = `Mejor coincidencia en las regiones analizadas: D = ${f1(bestD(w), 2)} (menor es más parecida).`;
  S.cand = 0;
}

function renderSuitability(w) {
  const bs = w.base_suitability;
  if (!bs) { $("moonsuit").innerHTML = ""; $("suitnote").textContent = "Aptitud de base no disponible: vuelve a ejecutar run_regions.py."; return; }
  const part = (x) => `${esc(x.label)} ${x.value == null ? "sin dato" : pct(x.value)} (mín. ${pct(x.min)})`;
  $("moonsuit").innerHTML = Object.values(bs).map((p) =>
    `<div class="srow"><span class="badge ${p.meets ? "ok" : "no"}">${p.meets == null ? "Sin dato" : p.meets ? "Apta" : "No apta"}</span>
      <span><b>${esc(p.label)}</b><small>${p.parts.map(part).join(" · ")}</small></span></div>`).join("");
  const n = S.lunar.length, c = (k) => S.lunar.filter((x) => x.base_suitability && x.base_suitability[k].meets).length;
  $("suitnote").textContent = `En ${SM().short} (${n} ventanas): ${c("habitat_full")} cumplen hábitat completo, ${c("landing_habitat")} solo la topografía de aterrizaje/hábitat, ${c("power_comms")} energía y comunicaciones, ${c("isru_ice")} zona fría y ${c("rover_traverse")} rover. ` +
    "Umbrales provisionales del equipo, no requisitos de NASA. Iluminación y visibilidad de la Tierra son promedios de ~18,6 años a nivel del suelo (LOLA, 60 m); la sombra permanente es una zona fría candidata, no prueba de hielo. Falta temperatura.";
}

function wireMoon() {
  const cv = $("moon");
  const pos = (ev) => { const r = cv.getBoundingClientRect(); return toM((ev.clientX - r.left) / r.width * cv.width, (ev.clientY - r.top) / r.height * cv.height, cv); };
  cv.addEventListener("click", (ev) => { const [x, y] = pos(ev); S.sel = nearest(x, y); drawMoon(); renderMoonPanel(); renderLive(); });
  cv.addEventListener("mousemove", (ev) => { const [x, y] = pos(ev); const h = nearest(x, y); if (h !== S.hover) { S.hover = h; drawMoon(); } });
  cv.addEventListener("mouseleave", () => { S.hover = null; drawMoon(); });
  $("heat").addEventListener("change", (e) => { S.heat = e.target.checked; $("heatlegend").hidden = !S.heat; drawMoon(); });
  $("suitsel").addEventListener("change", (e) => { S.suit = e.target.value; drawMoon(); });
  $("sitesel").addEventListener("change", (e) => { setSite(e.target.value); });
  $("regionsel").addEventListener("change", (e) => { S.region = e.target.value; S.cand = 0; renderLive(); });
}

/* ---------- Regiones (paso 2) ---------- */
function renderConfig() {
  const p = S.meta.params, regs = Object.values(S.meta.regions);
  $("cfg").innerHTML = [
    ["Datos terrestres", S.meta.earth.dataset], ["Datos lunares", `LOLA 5 m, ${Object.keys(S.meta.lunar_sites).length} sitios del polo sur (mayoría interpolada)`],
    ["Regiones", String(regs.length)], ["Ventana de análisis", `${f1(p.actual_window_m, 0)} m (≈ 3 × 3 km)`],
    ["Paso del barrido", `${f1(p.actual_step_m, 0)} m`], ["Escala común", `${f1(p.analysis_scale_m, 0)} m/píxel`],
    ["Rugosidad", `residuo sobre plano local de ${p.roughness_window_m} m`],
    ["Cobertura mínima", pct(p.min_coverage) + " (umbral provisional)"],
    ["Pesos (hipótesis)", `pend. ${S.meta.weights.slope} · rug. ${S.meta.weights.rough} · rel. ${S.meta.weights.relief}`],
    ["Normalización", "MAD robusta con todas las regiones juntas"],
    ["Ventanas evaluadas", `${S.meta.earth.windows_usable.toLocaleString("es-CL")} de ${S.meta.earth.windows_total.toLocaleString("es-CL")}`],
  ].map(([a, b]) => `<dt>${a}</dt><dd>${esc(b)}</dd>`).join("");
  $("regtable").querySelector("tbody").innerHTML = regs.map((r) =>
    `<tr><td style="text-align:left">${esc(r.name)}</td><td>${statusBadge(r)}</td><td style="text-align:left">${esc(r.type)}</td><td>${r.windows_usable.toLocaleString("es-CL")}</td><td style="text-align:left">${esc(r.reference)}</td></tr>`).join("");
}
const statusBadge = (r) => r.status === "known" ? `<span class="badge">conocida</span>` : `<span class="badge w">candidata</span>`;

function baseMap(id, fillRoi = true) {
  const m = L.map(id, { scrollWheelZoom: false, worldCopyJump: true });
  const sat = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 17, attribution: "Imagery © Esri" });
  const osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 17, attribution: "© OpenStreetMap" });
  sat.addTo(m); L.control.layers({ Satélite: sat, Mapa: osm }).addTo(m);
  const group = L.featureGroup(Object.values(S.meta.regions).map((r) => {
    const o = r.roi, b = [[o.south, o.west], [o.north, o.east]];
    const rect = L.rectangle(b, fillRoi ? { color: r.status === "known" ? "#5fd08a" : "#ffb347", weight: 2, fillOpacity: 0.12 }
      : { color: "#c9c2ff", weight: 1.5, dashArray: "6 6", fill: false, interactive: false });
    if (fillRoi) rect.bindTooltip(r.short, { direction: "top" });
    return rect;
  })).addTo(m);
  m.fitBounds(group.getBounds().pad(0.1));
  m._regionsBounds = group.getBounds();
  return m;
}

/* ---------- Candidatos ---------- */
const hav = (a, b) => {
  const R = 6371, rad = Math.PI / 180, dLa = (b[0] - a[0]) * rad, dLo = (b[1] - a[1]) * rad;
  const h = Math.sin(dLa / 2) ** 2 + Math.cos(a[0] * rad) * Math.cos(b[0] * rad) * Math.sin(dLo / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
};

function candData() {
  const lw = S.lunar[S.sel], sc = S.meta.scales, W = S.meta.weights;
  return entries().map((t, i) => {
    const e = S.earth[`${t.region}:${t.row}_${t.col}`], m = lw.metrics, c = e.metrics, reg = S.meta.regions[t.region];
    const dS = 0.5 * (Math.abs(c.slope_p50_deg - m.slope_p50_deg) / sc.slope_p50_deg + Math.abs(c.slope_p90_deg - m.slope_p90_deg) / sc.slope_p90_deg);
    const dR = Math.abs(c.roughness_270m_m - m.roughness_270m_m) / sc.roughness_270m_m;
    const dL = Math.abs(c.relief_p95_p5_m - m.relief_p95_p5_m) / sc.relief_p95_p5_m;
    const D = W.slope * dS + W.rough * dR + W.relief * dL;
    if (Math.abs(D - t.D) > 1e-6) console.warn("D recalculada difiere de la del pipeline", D, t.D);
    const km = hav(e.center, reg.center);
    return { rank: i + 1, id: `candidate-${String(i + 1).padStart(3, "0")}`, e, t, reg, D: t.D, comp: { slope: dS, rough: dR, relief: dL }, km };
  });
}

function placeNote(c) {
  if (c.reg.status !== "known") return `<span class="badge w">región candidata, no catalogada</span>`;
  return c.km > FAR_KM
    ? `<span class="badge w">a ≈${f1(c.km, 0)} km del sitio documentado: posible lugar nuevo, requiere revisión</span>`
    : `<span class="badge">cerca del sitio documentado (≈${f1(c.km, 0)} km)</span>`;
}

function cardsHtml(C) {
  if (!C.length) return `<p class="note">Sin candidatos en esta región para la ventana elegida.</p>`;
  return C.map((c, i) => {
    const near = C.filter((o) => o !== c && o.rank < c.rank && hav(o.e.center, c.e.center) < 10).map((o) => `#${o.rank}`);
    return `<button class="cand ${i === S.cand ? "on" : ""}" data-i="${i}" aria-pressed="${i === S.cand}">
      <img src="${c.e.image}" alt="Relieve sombreado del candidato ${c.rank}">
      <div><h4><span>#${c.rank} · ${esc(c.reg.short)} · ${lat(c.e.center[0])}, ${lon(c.e.center[1])}</span>
        <span class="badge">D = ${f1(c.D, 2)}</span></h4>
        <div class="sub">Más parecida que el ${f1(c.t.percentile, 2)} % de las ventanas ${S.region === "all" ? "de todas las regiones" : "de la región"} ${near.length ? ` · <span class="badge w">cercana a ${near.join(", ")} (&lt;10 km)</span>` : ""}</div>
        <div class="sub">${placeNote(c)}</div>
        <div class="m"><span>P50 ${f1(c.e.metrics.slope_p50_deg)}°</span><span>P90 ${f1(c.e.metrics.slope_p90_deg)}°</span>
        <span>Rug. ${f1(c.e.metrics.roughness_270m_m)} m</span><span>Relieve ${f1(c.e.metrics.relief_p95_p5_m, 0)} m</span></div></div></button>`;
  }).join("");
}
function bindCards(id, after) {
  $(id).querySelectorAll(".cand").forEach((b) => b.addEventListener("click", () => { S.cand = +b.dataset.i; after(); }));
}
function rangeWarn(el, lw) {
  const rg = S.meta.earth.ranges, out = KEYS.filter((k) => lw.metrics[k] > rg[k][1] || lw.metrics[k] < rg[k][0]);
  el.hidden = !out.length;
  el.innerHTML = out.length ? `<b>Atención: esta ventana lunar queda fuera del rango de todas las regiones analizadas.</b> ` +
    out.map((k) => `${LABEL[k][0]}: Luna ${f1(lw.metrics[k])}${LABEL[k][1]} frente a un máximo de ${f1(rg[k][1])}${LABEL[k][1]}`).join("; ") +
    `. El percentil es relativo y puede ser alto aunque la distancia D sea grande: mira siempre D y las diferencias.` : "";
}

function drawCands(key, id, C, onPick) {
  if (!S.maps[key]) S.maps[key] = baseMap(id, false);
  const m = S.maps[key];
  if (S.maps[key + "layer"]) S.maps[key + "layer"].remove();
  const colors = ["#5fd08a", "#4da3ff", "#c58bff"];
  const items = [];
  C.forEach((c, i) => {
    const sel = i === S.cand, col = colors[i % 3];
    const poly = L.polygon(c.e.polygon.map(([lo, la]) => [la, lo]),
      { color: col, weight: sel ? 4 : 3, fillColor: col, fillOpacity: sel ? 0.45 : 0.25 });
    // Marcador en el centro: la ventana mide 3 km y a escala de región sería casi invisible
    const dot = L.circleMarker(c.e.center, { radius: sel ? 11 : 9, color: "#fff", weight: 2, fillColor: col, fillOpacity: 1 });
    dot.bindTooltip(`#${c.rank} · ${c.reg.short} · D ${f1(c.D, 2)}`, { permanent: true, direction: "top", offset: [0, -8] });
    [poly, dot].forEach((l) => l.on("click", () => { S.cand = i; onPick(); }));
    items.push(poly, dot);
  });
  m.invalidateSize();
  if (!items.length) { m.fitBounds(m._regionsBounds.pad(0.1)); return; }
  S.maps[key + "layer"] = L.featureGroup(items).addTo(m);
  m.fitBounds(S.maps[key + "layer"].getBounds().pad(0.35), { maxZoom: 11 });
}
/* Paso 1: candidatos en vivo junto a la Luna */
function renderLive() {
  const C = candData();
  S.cand = Math.min(S.cand, Math.max(C.length - 1, 0));
  $("cards1").innerHTML = cardsHtml(C);
  bindCards("cards1", renderLive);
  rangeWarn($("rangewarn1"), S.lunar[S.sel]);
  renderRobust();
  drawCands("m1", "map1", C, renderLive);
}

/* ---------- Validación ---------- */
const yn = (v) => (v == null ? "no evaluado" : v ? "sí" : "no");
function renderRobust() {
  const r = S.lunar[S.sel].robust;
  $("robust1").textContent = r
    ? `Robustez de esta ventana — región ganadora estable ante pesos alternativos: ${yn(r.weights_top1_region)}; ante otra normalización: ${yn(r.norm_top1_region)}; ante otra escala (60/150 m): ${yn(r.scale_top1_region)}.`
    : "Robustez no evaluada para este sitio lunar: la validación (V3/V4) se hizo solo con Site01.";
}
const stChip = (s) => `<span class="chip ${s === "cumple" ? "ok" : s === "con reservas" ? "w" : "bad"}">${esc(s)}</span>`;
const rng = (arr, f = (x) => pct(x)) => { const lo = Math.min(...arr), hi = Math.max(...arr); return lo === hi ? f(lo) : `${f(lo)}–${f(hi)}`; };

function renderValidation() {
  const V = S.val, tb = $("valtable").querySelector("tbody");
  if (!V) { tb.innerHTML = `<tr><td colspan="5">Sin resultados de validación. Ejecuta <code>python validate.py</code>.</td></tr>`; return; }
  const C = V.criteria, rows = [];
  const a = V.v1_discrimination;
  rows.push(["V1 · Poder discriminante", "Una ventana, sin sus vecinas de menos de 9 km, ¿encuentra su mejor coincidencia en su propia región?",
    `${pct(a.accuracy_same_region)} de aciertos frente a ${pct(a.chance)} esperado por azar (×${f1(a.lift)}; ${a.n_queries} consultas)`, `≥ ${C.recovery_lift}× el azar`, a.status]);
  const b = V.v2_noise_recovery;
  rows.push(["V2 · Recuperación con ruido", `Se agrega ruido (σ = ${b.noise_sigma_scales} escala robusta) a una ventana: ¿en qué posición queda la original entre todas?`,
    `Mediana: puesto ${f1(b.median_rank, 0)} de ${b.windows_total.toLocaleString("es-CL")} (${f1(b.median_rank_pct, 1)} %); percentil 90: ${f1(b.p90_rank_pct, 0)} %`, `mediana ≤ ${C.noise_rank_pct} %`, b.status]);
  const w = V.v3_weights_norm, wk = Object.values(w.weights);
  rows.push(["V3a · Pesos alternativos", `Se repite el ranking de las ${w.n_lunar_windows} ventanas lunares con 4 juegos de pesos distintos`,
    `Región ganadora igual en ${rng(wk.map((x) => x.same_top1_region))}; top 3 exacto idéntico solo en ${rng(wk.map((x) => x.same_set))}`, `región estable ≥ ${pct(C.stable_ok)}`, w.status_weights]);
  const nk = Object.values(w.norm);
  rows.push(["V3b · Normalización alternativa", "Otras escalas: desviación estándar, MAD por región y MAD de las ventanas lunares",
    `Región ganadora igual en ${rng(nk.map((x) => x.same_top1_region))}. Etna gana en ${pct(w.base_etna_share)} de las ventanas con la normalización base y en ${rng(nk.map((x) => x.etna_share))} con las alternativas`, `región estable ≥ ${pct(C.stable_ok)}`, w.status_norm]);
  const sc = V.v3_scale;
  rows.push(["V3c · Escala de análisis", "Todo el análisis repetido a 60 m y a 150 m (base: 90 m)",
    sc ? `Región ganadora igual en ${rng(["60", "150"].map((k) => sc[k].same_top1_region))}; correlación de Spearman del mejor D: ${rng(["60", "150"].map((k) => sc[k].spearman_bestD), (x) => f1(x, 2))}` : "No ejecutada todavía",
    `región estable ≥ ${pct(C.stable_ok)}`, sc ? sc.status : "pendiente"]);
  const l = V.v4_lola_uncertainty;
  rows.push(["V4a · Incertidumbre de LOLA", "Incertidumbre de pendiente de LOLA (capa slperr) frente a la tolerancia del método (escala robusta de pendiente)",
    `Mediana ${f1(l.median_slope_uncertainty_deg, 2)}° frente a una escala de ${f1(l.tolerance_scale_deg, 2)}° (razón ${f1(l.ratio, 2)}). ${esc(l.note)}`, `razón ≤ ${C.slope_unc_ratio}`, l.status]);
  const d = V.v4_dem_product, dm = d.metrics;
  rows.push(["V4b · Producto DEM", `Atacama con dos DEM independientes (Copernicus GLO-30 y NASADEM), ${d.windows_compared.toLocaleString("es-CL")} ventanas`,
    `Spearman: pendiente ${f1(dm.slope_p50_deg.spearman, 2)}, relieve ${f1(dm.relief_p95_p5_m.spearman, 2)}, rugosidad ${f1(dm.roughness_270m_m.spearman, 2)}; diferencia mediana de rugosidad: ${f1(dm.roughness_270m_m.median_abs_diff_in_scales, 2)} escalas`,
    `Spearman ≥ ${C.dem_spearman} y diferencia ≤ ${C.dem_delta_ratio} escalas`, d.status]);
  tb.innerHTML = rows.map(([n, q, r, c, s]) => `<tr><td>${n}</td><td>${q}</td><td>${r}</td><td>${c}</td><td>${stChip(s)}</td></tr>`).join("");
  $("valread").innerHTML = [
    `La métrica sí distingue terrenos (V1, V2): no es ruido.`,
    `Lo que se sostiene es la <b>región ganadora</b>, más que las 3 ventanas exactas: con otros pesos el top 3 cambia casi siempre (V3a), pero la región suele repetirse.`,
    `El dominio de Etna depende de la normalización elegida (V3b): no debe presentarse como un hallazgo firme sin más análisis.`,
    `La incertidumbre de pendiente de LOLA es comparable a la tolerancia del método (V4a): diferencias finas de pendiente entre candidatos no son concluyentes.`,
    `Las pendientes y el relieve coinciden entre productos DEM; la rugosidad es la métrica más sensible al producto (V4b).`,
  ].map((x) => `<li>${x}</li>`).join("");
  $("valnot").innerHTML = [
    `No hay verdad de terreno: ninguna prueba demuestra que un sitio sirva para probar un rover.`,
    `No hay validación en campo ni con datos operacionales.`,
    `No valida el contexto (temperatura, composición, sismicidad): son descriptores aparte, fuera del puntaje.`,
    `La similitud es morfológica a escala de 90 m; no cubre rocas, suelo ni obstáculos menores.`,
    `Los pesos del puntaje siguen siendo hipótesis, no coeficientes calibrados.`,
  ].map((x) => `<li>${x}</li>`).join("");
}

/* ---------- Detalle (paso 3) ---------- */
function renderResults() {
  const C = candData(), lw = S.lunar[S.sel];
  const scope = S.region === "all" ? `las ${Object.keys(S.meta.regions).length} regiones` : S.meta.regions[S.region].short;
  $("reslead").textContent = `Para la ventana lunar seleccionada se listan las ventanas más parecidas de ${scope}, sin solaparse, entre ${S.meta.earth.windows_usable.toLocaleString("es-CL")} evaluadas.`;
  $("cards").innerHTML = cardsHtml(C);
  bindCards("cards", () => { renderResults(); renderLive(); });
  rangeWarn($("rangewarn"), lw);
  drawCands("m3", "map3", C, () => { renderResults(); renderLive(); });
  $("compare").hidden = !C.length;
  if (C.length) renderCompare(C[S.cand], lw);
  const ref = S.meta.reference_window, isRef = ref.site === S.site && S.sel === nearest(ref.center[0], ref.center[1]);
  $("sensnote").textContent = isRef
    ? `Robustez de esta ventana (todas las regiones): ${ref.sensitivity_weights.stable ? "el top 3 no cambia" : "el top 3 CAMBIA"} al usar pesos alternativos. El ranking debe leerse como exploratorio.`
    : "La robustez frente a pesos alternativos aún no se ha evaluado para esta ventana (fase de validación).";
}

function mbar(k, mv, cv) {
  const mx = Math.max(mv, cv, 1e-9), u = LABEL[k][1];
  return `<div class="mbar"><div class="t"><span>${LABEL[k][0]}</span></div><div class="pair">
    <div class="track"><div class="fill m" style="width:${mv / mx * 100}%"></div></div>
    <div class="track"><div class="fill e" style="width:${cv / mx * 100}%"></div></div></div>
    <div class="vals"><span style="color:var(--moon)">Luna ${f1(mv)}${u}</span><span style="color:var(--earth)">Candidato ${f1(cv)}${u}</span></div></div>`;
}

const chip = (txt, kind) => `<span class="chip ${kind}">${txt}</span>`;
const srcLinks = (arr) => (arr || []).map((u, i) => `<a href="${u}" target="_blank" rel="noopener">fuente${arr.length > 1 ? " " + (i + 1) : ""}</a>`).join(" · ");

function contextRows(c) {
  const mc = { ...S.meta.moon_context, composition: SM().composition }, cx = S.ctx[c.reg.id], none = (t) => `<span class="mute">${t}</span>`;
  const rows = [];
  // Temperatura
  const t = cx && cx.temperature;
  rows.push(["Temperatura",
    `${chip(mc.temperature.status === "pendiente" ? "pendiente" : "dato", "w")} ${esc(mc.temperature.text)} ${srcLinks(mc.temperature.sources)}`,
    t && t.status === "ok"
      ? `${chip("dato", "ok")} Media anual ${f1(t.annual_mean_c)} °C · mes más cálido (máx. media) ${f1(t.warmest_month_mean_max_c)} °C · mes más frío (mín. media) ${f1(t.coldest_month_mean_min_c)} °C · amplitud ${f1(t.annual_range_c)} °C <small>${esc(t.caveat)} ${srcLinks([t.source])}</small>`
      : none("Sin dato")]);
  // Composición
  const k = cx && cx.composition;
  rows.push(["Composición de la superficie",
    `${chip(mc.composition.status === "pendiente" ? "pendiente" : "cualitativo", "w")} ${esc(mc.composition.text)} <small>${esc(mc.composition.caveat)} ${srcLinks(mc.composition.sources)}</small>`,
    k && k.status === "ok"
      ? `${chip("dato", "ok")} ${k.lithology.map((l) => `${esc(l.lith)} ${pct(l.share)}`).join(" · ")} <small>${k.samples_with_data}/${k.samples} puntos con dato. ${esc(k.caveat)} ${srcLinks([k.source])}</small>`
      : none("Sin dato en el mapa geológico")]);
  // Riesgo sísmico y volcánico
  const s = cx && cx.seismicity, v = cx && cx.volcanoes;
  const sTxt = s && s.status === "ok" ? `${s.count_m25} sismos M≥2,5 desde ${s.since.slice(0, 4)} en ${s.radius_km} km (${s.count_m45} con M≥4,5; máx. M ${s.max_magnitude == null ? "—" : f1(s.max_magnitude)})` : "Sismicidad sin dato";
  const vTxt = v && v.status === "ok"
    ? (v.nearest ? `volcán holocénico más cercano: ${esc(v.nearest.name)} a ${f1(v.nearest.distance_km, 0)} km${v.nearest.last_eruption_year ? ` (última erupción registrada: ${v.nearest.last_eruption_year})` : ""}; ${v.count_within_radius} en ${v.radius_km} km`
                 : `ningún volcán holocénico a menos de 300 km`) : "Volcanes sin dato";
  rows.push(["Actividad sísmica y volcánica (riesgo)",
    `${chip("no comparable", "n")} ${esc(mc.seismic_volcanic.text)}`,
    `${chip("contexto de riesgo", "ok")} ${sTxt}; ${vTxt}. <small>${s ? esc(s.caveat) : ""} ${srcLinks([s && s.source, v && v.source].filter(Boolean))}</small>`]);
  return rows;
}

function renderCompare(c, lw) {
  $("cmptitle").textContent = `Comparación: referencia lunar vs. candidato #${c.rank} (${c.reg.short})`;
  const cv = $("cmpmoon"), g = cv.getContext("2d"), im = S.img, [l, b, r, t] = B(), half = SM().window_m / 2;
  const sx = (lw.center_x - half - l) / (r - l) * im.naturalWidth, sy = (t - (lw.center_y + half)) / (t - b) * im.naturalHeight;
  const sw = SM().window_m / (r - l) * im.naturalWidth;
  g.clearRect(0, 0, cv.width, cv.height); g.drawImage(im, sx, sy, sw, sw, 0, 0, cv.width, cv.height);
  $("cmpearth").src = c.e.image;
  $("cmpmooncap").textContent = `${SM().short} · centro X ${f1(lw.center_x, 0)} m, Y ${f1(lw.center_y, 0)} m (vista sombreada del DEM)`;
  $("cmpearthcap").textContent = `${c.reg.short} · ${lat(c.e.center[0])}, ${lon(c.e.center[1])} (vista sombreada del DEM)`;
  const cls = S.meta.slope_class_labels;
  const side = (m, extra) => KEYS.map((k) => `<dt>${LABEL[k][0]}</dt><dd>${f1(m[k])}${LABEL[k][1]}</dd>`).join("") +
    cls.map((lb, i) => `<dt>Pendiente ${lb}</dt><dd>${pct(extra.classes[i])}</dd>`).join("") + extra.rows;
  $("sidemoon").innerHTML = side(lw.metrics, { classes: lw.slope_classes, rows:
    `<dt>Fuente</dt><dd>LOLA ${esc(SM().short)} (5 m)</dd><dt>Observado por LOLA</dt><dd>${lw.lola_observed_fraction == null ? "Sin datos" : pct(lw.lola_observed_fraction)}<small>el resto es interpolado</small></dd>` });
  $("sideearth").innerHTML = side(c.e.metrics, { classes: c.e.slope_classes, rows:
    `<dt>Fuente</dt><dd>${S.meta.earth.dataset}</dd><dt>Cobertura válida</dt><dd>${pct(c.e.valid_coverage_fraction)}</dd><dt>Estado de la región</dt><dd>${c.reg.status === "known" ? "conocida" : "candidata"}</dd>` });
  const sc = S.meta.scales;
  $("cmptable").querySelector("tbody").innerHTML = KEYS.map((k) => {
    const mv = lw.metrics[k], ev = c.e.metrics[k], d = ev - mv, same = Math.abs(d) / sc[k] <= 1, u = LABEL[k][1];
    return `<tr><td>${LABEL[k][0]}</td><td>${f1(mv)}${u}</td><td>${f1(ev)}${u}</td><td>${d > 0 ? "+" : ""}${f1(d)}${u}</td><td class="${same ? "yes" : "no"}">${same ? "Sí" : "No"}</td></tr>`;
  }).join("") + cls.map((lb, i) => {
    const mv = lw.slope_classes[i] * 100, ev = c.e.slope_classes[i] * 100, d = ev - mv;
    return `<tr><td>Pendiente ${lb} (% del área)</td><td>${f1(mv, 0)} %</td><td>${f1(ev, 0)} %</td><td>${d > 0 ? "+" : ""}${f1(d, 0)} pp</td><td>—</td></tr>`;
  }).join("") + `<tr><td>Distancia total D</td><td>—</td><td>—</td><td>${f1(c.D, 2)}</td><td>menor = más parecida</td></tr>`;
  $("cmpbars").innerHTML = KEYS.map((k) => mbar(k, lw.metrics[k], c.e.metrics[k])).join("");
  $("cmpcomp").innerHTML = `<b>Pendiente</b><b>${f1(c.comp.slope, 2)}</b><b>Rugosidad</b><b>${f1(c.comp.rough, 2)}</b><b>Relieve</b><b>${f1(c.comp.relief, 2)}</b><b>Total D</b><b>${f1(c.D, 2)}</b>`;
  $("ctxtable").querySelector("tbody").innerHTML = contextRows(c).map(([a, m, e]) => `<tr class="ctx"><td>${a}</td><td>${m}</td><td>${e}</td></tr>`).join("");
  $("ctxnote").textContent = `Contexto consultado el ${(S.ctx[c.reg.id] || {}).retrieved || "—"} en el centro de la región (${lat(c.reg.center[0])}, ${lon(c.reg.center[1])}); varía a escala de decenas de km y no distingue ventanas de una misma región.`;
  const mt = [], df = [];
  KEYS.forEach((k) => {
    const line = `${LABEL[k][0]}: Luna ${f1(lw.metrics[k])}${LABEL[k][1]} · candidato ${f1(c.e.metrics[k])}${LABEL[k][1]}`;
    (Math.abs(c.e.metrics[k] - lw.metrics[k]) / sc[k] <= 1 ? mt : df).push(line);
  });
  $("matches").innerHTML = mt.length ? mt.map((x) => `<li>${x}</li>`).join("") : "<li>Ninguna métrica coincide dentro de 1 escala robusta.</li>";
  $("diffs").innerHTML = df.length ? df.map((x) => `<li>${x}</li>`).join("") : "<li>Sin diferencias mayores a 1 escala robusta.</li>";
  $("pending").innerHTML = S.meta.pending_validation.map((x) => `<li>${x}</li>`).join("");
}

/* ---------- Exportación ---------- */
function download(name, text, type) {
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; a.click(); URL.revokeObjectURL(a.href);
}
function exportGeo() {
  const lw = S.lunar[S.sel];
  const fc = { type: "FeatureCollection", features: candData().map((c) => ({
    type: "Feature", geometry: { type: "Polygon", coordinates: [c.e.polygon] },
    properties: { candidate_id: c.id, rank: c.rank, region: c.reg.name, region_status: c.reg.status, km_to_documented_site: c.km,
      center: { latitude: c.e.center[0], longitude: c.e.center[1] }, normalized_distance: c.D,
      similarity_percentile: c.t.percentile, component_distances: c.comp, metrics: c.e.metrics, slope_classes: c.e.slope_classes,
      valid_coverage_fraction: c.e.valid_coverage_fraction, context: S.ctx[c.reg.id] || null,
      lunar_reference: { center_x_m: lw.center_x, center_y_m: lw.center_y, site: S.site, crs: SM().crs, metrics: lw.metrics },
      params: S.meta.params, sources: [SM().source_url, S.meta.earth.source_url], status: "preliminary" } })) };
  download("candidates.geojson", JSON.stringify(fc, null, 2), "application/geo+json");
}
function exportCsv() {
  const lw = S.lunar[S.sel];
  const head = ["rank", "region", "region_status", "latitude", "longitude", "D", "percentile", ...KEYS, "d_slope", "d_rough", "d_relief", "km_to_documented_site", "lunar_center_x_m", "lunar_center_y_m"];
  const rows = candData().map((c) => [c.rank, `"${c.reg.name}"`, c.reg.status, c.e.center[0], c.e.center[1], c.D, c.t.percentile, ...KEYS.map((k) => c.e.metrics[k]),
    c.comp.slope, c.comp.rough, c.comp.relief, c.km, lw.center_x, lw.center_y]);
  download("candidates.csv", [head, ...rows].map((r) => r.join(",")).join("\n"), "text/csv");
}

/* ---------- Navegación ---------- */
function go(n) {
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("on", v.id === `s${n}`));
  document.querySelectorAll("#steps button").forEach((b) => b.classList.toggle("on", +b.dataset.step === n));
  if (n === 1 && S.maps.m1) setTimeout(() => { S.maps.m1.invalidateSize(); renderLive(); }, 50);
  if (n === 2) { if (!S.maps.m2) S.maps.m2 = baseMap("map2"); setTimeout(() => S.maps.m2.invalidateSize(), 50); }
  if (n === 4) renderValidation();
  if (n === 3) { renderResults(); setTimeout(() => S.maps.m3 && S.maps.m3.invalidateSize(), 50); }
  window.scrollTo({ top: 0 });
}
function wire() {
  wireMoon();
  document.querySelectorAll("[data-step]").forEach((b) => b.addEventListener("click", () => go(+b.dataset.step)));
  document.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => go(+b.dataset.go)));
  $("exp-geo").addEventListener("click", exportGeo);
  $("exp-csv").addEventListener("click", exportCsv);
}
boot();
