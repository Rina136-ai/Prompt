const MODE_INFO = {
  musique_clip: { title: "Musique → Clip", desc: "Importe un MP3, l'IA en tire un clip complet." },
  paroles_images: { title: "Paroles → Images", desc: "Colle tes paroles, l'IA construit des scènes." },
  paroles_musique_film: { title: "Paroles + Musique → Film musical", desc: "Combine le sens des paroles et le rythme." },
  image_musique_clip: { title: "Image → Musique / Clip", desc: "Un personnage principal pour construire l'univers." },
};

const state = {
  mode: "paroles_images",
  audioToken: null,
  characterToken: null,
  characterUrl: null,
  directorOptions: null,
  storyboard: null,
};

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => {
    if (k === "text") node.textContent = v;
    else if (k === "html") node.innerHTML = v;
    else node.setAttribute(k, v);
  });
  children.forEach((c) => node.appendChild(c));
  return node;
}

function renderModes() {
  const grid = document.getElementById("mode-grid");
  grid.innerHTML = "";
  Object.entries(MODE_INFO).forEach(([key, info]) => {
    const card = el("div", { class: "mode-card" + (key === state.mode ? " selected" : ""), "data-mode": key });
    card.appendChild(el("h3", { text: info.title }));
    card.appendChild(el("p", { text: info.desc }));
    card.addEventListener("click", () => {
      state.mode = key;
      document.querySelectorAll(".mode-card").forEach((c) => c.classList.remove("selected"));
      card.classList.add("selected");
      document.getElementById("character-row").style.display = key === "image_musique_clip" ? "block" : "none";
    });
    grid.appendChild(card);
  });
}

function renderDirectorGrid(options) {
  const grid = document.getElementById("director-grid");
  grid.innerHTML = "";
  const fields = [
    ["characters", "Personnages", options.characters],
    ["style", "Style", options.style],
    ["dance", "Danse", options.dance],
    ["era", "Époque", options.era],
    ["decor", "Décor", options.decor],
    ["camera", "Caméra", options.camera],
  ];
  fields.forEach(([id, labelText, values]) => {
    const label = el("label", { text: labelText });
    const select = el("select", { id: `director-${id}` });
    values.forEach((v) => select.appendChild(el("option", { value: v, text: v })));
    label.appendChild(select);
    grid.appendChild(label);
  });
}

function collectDirectorSettings() {
  const get = (id) => document.getElementById(`director-${id}`).value;
  return {
    characters: get("characters"),
    style: get("style"),
    dance: get("dance"),
    era: get("era"),
    decor: get("decor"),
    camera: get("camera"),
    character_reference_media_id: state.characterToken,
  };
}

async function loadConfig() {
  const config = await api("/api/config");
  state.directorOptions = config.director_options;
  document.getElementById("provider-banner").textContent =
    config.provider === "higgsfield"
      ? "Génération réelle activée (Higgsfield)"
      : "Mode démo hors-ligne (aucune clé HIGGSFIELD_API_KEY détectée) — les résultats sont simulés";
  renderModes();
  renderDirectorGrid(config.director_options);
}

document.getElementById("audio-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  document.getElementById("audio-status").textContent = "Analyse en cours…";
  try {
    const res = await api("/api/upload/audio", { method: "POST", body: form });
    state.audioToken = res.token;
    const s = res.audio_summary || {};
    document.getElementById("audio-status").textContent = s.error
      ? `Analyse indisponible: ${s.error}`
      : `Tempo ≈ ${Math.round(s.tempo_bpm)} BPM, durée ${Math.round(s.duration)}s, famille suggérée: ${s.suggested_genre_family}`;
  } catch (err) {
    document.getElementById("audio-status").textContent = `Erreur: ${err.message}`;
  }
});

document.getElementById("character-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  try {
    const res = await api("/api/upload/character", { method: "POST", body: form });
    state.characterToken = res.token;
    state.characterUrl = res.url;
    document.getElementById("character-status").textContent = "Personnage chargé ✓";
  } catch (err) {
    document.getElementById("character-status").textContent = `Erreur: ${err.message}`;
  }
});

function sceneCard(scene) {
  const card = el("div", { class: "scene-card" });
  card.appendChild(
    el("h4", { text: `${scene.section_label}${scene.is_highlight ? "  " : ""}` }, scene.is_highlight ? [el("span", { class: "highlight-badge", text: "★ moment fort" })] : [])
  );
  card.appendChild(el("div", { class: "meta", text: `Ambiance: ${scene.mood} · Énergie: ${scene.energy}` }));
  card.appendChild(el("pre", { text: scene.lyrics_excerpt }));

  const imgBtn = el("button", { class: "secondary", text: "Générer l'image de la scène" });
  const vidBtn = el("button", { class: "secondary", text: "Générer le plan vidéo" });
  const resultBox = el("div", { class: "asset-result" });

  imgBtn.addEventListener("click", async () => {
    resultBox.textContent = "Génération en cours…";
    try {
      const asset = await api("/api/generate/image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: scene.image_prompt, character_reference_url: state.characterUrl }),
      });
      resultBox.innerHTML = "";
      resultBox.appendChild(el("div", { text: `[${asset.provider}] ${asset.url}` }));
      if (asset.provider !== "mock") {
        resultBox.appendChild(el("img", { src: asset.url, style: "max-width:100%;border-radius:8px;margin-top:0.5rem;" }));
      }
    } catch (err) {
      resultBox.textContent = `Erreur: ${err.message}`;
    }
  });

  vidBtn.addEventListener("click", async () => {
    resultBox.textContent = "Génération en cours (peut prendre plusieurs minutes)…";
    try {
      const duration = scene.end_seconds && scene.start_seconds ? scene.end_seconds - scene.start_seconds : 5.0;
      const asset = await api("/api/generate/video", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: scene.video_prompt, character_reference_url: state.characterUrl, duration_seconds: duration }),
      });
      resultBox.innerHTML = "";
      resultBox.appendChild(el("div", { text: `[${asset.provider}] ${asset.url}` }));
    } catch (err) {
      resultBox.textContent = `Erreur: ${err.message}`;
    }
  });

  const row = el("div", {});
  row.appendChild(imgBtn);
  row.appendChild(vidBtn);
  card.appendChild(row);
  card.appendChild(resultBox);
  return card;
}

function renderOutputPlan(plan, scenes) {
  const container = document.getElementById("output-plan");
  container.innerHTML = "";

  const block = (title, bodyText) => {
    const b = el("div", { class: "plan-block" });
    b.appendChild(el("h4", { text: title }));
    b.appendChild(el("p", { text: bodyText }));
    return b;
  };

  container.appendChild(block("🎬 Clip musical complet", `${plan.main_clip_scene_indices.length} scènes enchaînées.`));
  plan.shorts.forEach((short) => {
    container.appendChild(block(`📱 ${short.title}`, `Scènes ${short.scene_indices.join(", ")} — ≈ ${short.approx_seconds}s`));
  });
  container.appendChild(block("🎵 Visualizer musical", `Ambiance dominante: ${plan.visualizer_mood}`));
  container.appendChild(block("📝 Lyric video", `${plan.lyric_video_scene_indices.length} sous-titres synchronisés aux scènes.`));
  container.appendChild(block("🖼️ Images de l'univers", `${plan.image_scene_indices.length} images clés, une par scène.`));
  plan.variants.forEach((v) => {
    container.appendChild(
      block(
        `🎞️ ${v.label}`,
        [v.style_override && `style: ${v.style_override}`, v.camera_override && `caméra: ${v.camera_override}`]
          .filter(Boolean)
          .join(", ") || "identique au storyboard de base"
      )
    );
  });
}

document.getElementById("build-storyboard").addEventListener("click", async () => {
  const lyrics = document.getElementById("lyrics").value;
  const genre = document.getElementById("genre").value;
  if (!lyrics.trim()) {
    alert("Merci de coller des paroles (même approximatives) pour construire le storyboard.");
    return;
  }
  const payload = {
    mode: state.mode,
    lyrics,
    genre,
    director: collectDirectorSettings(),
    audio_token: state.audioToken,
  };
  try {
    const storyboard = await api("/api/storyboard", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.storyboard = storyboard;
    document.getElementById("storyboard-output").hidden = false;
    document.getElementById("storyboard-summary").textContent =
      `Genre: ${storyboard.genre} · Ambiance générale: ${storyboard.overall_mood} · ${storyboard.scenes.length} scènes`;
    const scenesContainer = document.getElementById("scenes");
    scenesContainer.innerHTML = "";
    storyboard.scenes.forEach((scene) => scenesContainer.appendChild(sceneCard(scene)));
    renderOutputPlan(storyboard.output_plan, storyboard.scenes);
  } catch (err) {
    alert(`Erreur: ${err.message}`);
  }
});

loadConfig();
