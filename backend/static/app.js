const MODE_INFO = {
  musique_clip: { title: "Musique → Clip", desc: "Importe un MP3, l'IA en tire un clip complet." },
  paroles_images: { title: "Paroles → Images", desc: "Colle tes paroles, l'IA construit des scènes." },
  paroles_musique_film: { title: "Paroles + Musique → Film musical", desc: "Combine le sens des paroles et le rythme." },
  image_musique_clip: { title: "Image → Musique / Clip", desc: "Un personnage principal pour construire l'univers." },
};

const state = {
  mode: "paroles_images",
  audioFile: null,
  audioToken: null,
  characterFile: null,
  directorOptions: null,
  storyboard: null,
  isDemo: true,
  pipelinePollTimer: null,
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
  };
}

async function loadConfig() {
  const config = await api("/api/config");
  state.directorOptions = config.director_options;
  state.isDemo = config.is_demo;
  document.getElementById("provider-banner").textContent = config.is_demo
    ? "⚠️ MODE DÉMO — aucune clé Higgsfield configurée : les générations sont simulées, pas réelles."
    : "Génération réelle activée (Higgsfield)";
  renderModes();
  renderDirectorGrid(config.director_options);
}

document.getElementById("audio-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  state.audioFile = file;
});

document.getElementById("character-file").addEventListener("change", (e) => {
  const file = e.target.files[0];
  state.characterFile = file || null;
  document.getElementById("character-status").textContent = file ? `Selectionne : ${file.name}` : "";
});

document.getElementById("analyze-audio-advanced").addEventListener("click", async () => {
  if (!state.audioFile) {
    alert("Choisis d'abord un fichier audio en haut de la page.");
    return;
  }
  const form = new FormData();
  form.append("file", state.audioFile);
  document.getElementById("audio-status").textContent = "Analyse en cours…";
  try {
    const res = await api("/api/upload/audio", { method: "POST", body: form });
    state.audioToken = res.token;
    const s = res.audio_summary || {};
    document.getElementById("audio-status").textContent = s.error
      ? `Analyse indisponible: ${s.error}`
      : `Tempo ≈ ${Math.round(s.tempo_bpm)} BPM, durée ${Math.round(s.duration)}s, ${s.sections ? s.sections.length : 0} sections detectees`;
  } catch (err) {
    document.getElementById("audio-status").textContent = `Erreur: ${err.message}`;
  }
});

function demoBadge() {
  return el("div", { class: "demo-badge", text: "⚠️ MODE DÉMO — simulation, pas une génération IA réelle" });
}

function sceneCard(scene) {
  const card = el("div", { class: "scene-card" });
  card.appendChild(
    el("h4", { text: `${scene.section_label}${scene.is_highlight ? "  " : ""}` }, scene.is_highlight ? [el("span", { class: "highlight-badge", text: "★ moment fort" })] : [])
  );
  card.appendChild(el("div", { class: "meta", text: `Ambiance: ${scene.mood} · Énergie: ${scene.energy}` }));
  card.appendChild(el("pre", { text: scene.lyrics_excerpt || "(pas de paroles pour cette scene)" }));

  const imgBtn = el("button", { class: "secondary", text: "Générer l'image de la scène" });
  const resultBox = el("div", { class: "asset-result" });

  imgBtn.addEventListener("click", async () => {
    resultBox.textContent = "Génération en cours…";
    try {
      const asset = await api("/api/generate/image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: scene.image_prompt }),
      });
      resultBox.innerHTML = "";
      if (asset.provider === "mock") resultBox.appendChild(demoBadge());
      resultBox.appendChild(el("div", { text: `[${asset.provider}] ${asset.url}` }));
      if (asset.provider !== "mock") {
        resultBox.appendChild(el("img", { src: asset.url, style: "max-width:100%;border-radius:8px;margin-top:0.5rem;" }));
      }
    } catch (err) {
      resultBox.textContent = `Erreur: ${err.message}`;
    }
  });

  const row = el("div", {});
  row.appendChild(imgBtn);
  card.appendChild(row);
  card.appendChild(resultBox);
  return card;
}

function renderOutputPlan(plan) {
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
  const genre = document.getElementById("genre").value || "pop";
  if (!lyrics.trim()) {
    alert("Le mode avance necessite des paroles. Pour un MP3 seul, utilise le bouton 'Générer mon clip' en haut de page.");
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
    renderOutputPlan(storyboard.output_plan);
  } catch (err) {
    alert(`Erreur: ${err.message}`);
  }
});

// --- Priority flow: Importer -> Analyser -> Generer -> Regarder/Telecharger ---

function renderPipelineStoryboardSummary(storyboard) {
  const container = document.getElementById("pipeline-storyboard-summary");
  container.innerHTML = "";
  if (!storyboard) return;
  container.appendChild(
    el("p", { text: `Genre: ${storyboard.genre} · Ambiance: ${storyboard.overall_mood} · ${storyboard.scenes.length} scènes générées` })
  );
  renderOutputPlanInto(container, storyboard.output_plan);
}

function renderOutputPlanInto(container, plan) {
  const block = (title, bodyText) => {
    const b = el("div", { class: "plan-block" });
    b.appendChild(el("h4", { text: title }));
    b.appendChild(el("p", { text: bodyText }));
    return b;
  };
  container.appendChild(block("🎬 Clip musical complet", `${plan.main_clip_scene_indices.length} scènes enchaînées, c'est le fichier ci-dessus.`));
  plan.shorts.forEach((short) => {
    container.appendChild(block(`📱 ${short.title}`, `Scènes ${short.scene_indices.join(", ")} — ≈ ${short.approx_seconds}s (a produire separement en mode avance)`));
  });
}

document.getElementById("run-pipeline").addEventListener("click", async () => {
  if (!state.audioFile) {
    alert("Choisis d'abord un fichier MP3/WAV.");
    return;
  }

  const form = new FormData();
  form.append("audio", state.audioFile);
  const lyrics = document.getElementById("lyrics").value.trim();
  if (lyrics) form.append("lyrics", lyrics);
  const genre = document.getElementById("genre").value;
  if (genre) form.append("genre", genre);
  if (state.characterFile) form.append("character_photo", state.characterFile);
  form.append("director", JSON.stringify(collectDirectorSettings()));

  const progressBox = document.getElementById("pipeline-progress");
  const resultBox = document.getElementById("pipeline-result");
  progressBox.hidden = false;
  resultBox.hidden = true;
  document.getElementById("pipeline-status-text").textContent = "Envoi du fichier...";
  document.getElementById("run-pipeline").disabled = true;

  try {
    const { job_id } = await api("/api/pipeline/run", { method: "POST", body: form });

    if (state.pipelinePollTimer) clearInterval(state.pipelinePollTimer);
    state.pipelinePollTimer = setInterval(async () => {
      try {
        const status = await api(`/api/pipeline/status/${job_id}`);
        document.getElementById("pipeline-status-text").textContent = `${status.status} — ${status.progress}`;
        document.getElementById("pipeline-genre-text").textContent = status.genre_detected
          ? `Genre detecte: ${status.genre_detected}`
          : "";

        if (status.status === "done") {
          clearInterval(state.pipelinePollTimer);
          document.getElementById("run-pipeline").disabled = false;
          progressBox.hidden = true;
          resultBox.hidden = false;
          document.getElementById("pipeline-demo-badge").hidden = !status.is_demo;
          const videoUrl = `/api/pipeline/result/${job_id}`;
          const video = document.getElementById("pipeline-video");
          video.src = videoUrl;
          const downloadLink = document.getElementById("pipeline-download");
          downloadLink.href = videoUrl;
          renderPipelineStoryboardSummary(status.storyboard);
        } else if (status.status === "error") {
          clearInterval(state.pipelinePollTimer);
          document.getElementById("run-pipeline").disabled = false;
          document.getElementById("pipeline-status-text").textContent = `Erreur: ${status.error}`;
        }
      } catch (err) {
        clearInterval(state.pipelinePollTimer);
        document.getElementById("run-pipeline").disabled = false;
        document.getElementById("pipeline-status-text").textContent = `Erreur: ${err.message}`;
      }
    }, 1500);
  } catch (err) {
    document.getElementById("run-pipeline").disabled = false;
    document.getElementById("pipeline-status-text").textContent = `Erreur: ${err.message}`;
  }
});

loadConfig();
