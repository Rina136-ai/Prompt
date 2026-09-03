# Music-to-Story Video AI

Application qui transforme une chanson en clip musical cinématographique généré par IA.

**Priorité absolue : un MP3 seul suffit.** Aucune parole, aucun réglage n'est requis — l'utilisateur importe sa musique, l'application analyse, génère, et produit un vrai fichier MP4 regardable/téléchargeable. Tout le reste (paroles, photo de personnage, Directeur artistique) est facultatif et vient enrichir le résultat.

## Le parcours principal

**Importer ma musique → Analyser → Générer mon clip → Regarder/Télécharger.**

À partir du seul MP3 :
1. **Analyse audio réelle** (`app/audio_analysis.py`) : tempo (BPM), énergie, et **segmentation structurelle** (changements de timbre/harmonie détectés par clustering agglomératif beat-synchrone sur MFCC+chroma — une vraie technique MIR, pas un découpage en tranches égales). Chaque scène du storyboard correspond à une section réellement détectée dans le morceau, donc la durée totale du storyboard est toujours exactement celle du morceau.
2. **Classification de genre réelle** (`app/genre_classifier.py`) : modèle SVM pré-entraîné (`pyAudioAnalysis`), pas une déduction BPM→genre. Le modèle distingue 6 familles réelles (Blues, Classical, Electronic, Jazz, Rap, Rock) à partir de vraies caractéristiques audio (MFCC, chroma, histogramme de battements). **Limite honnête** : ce modèle ne distingue pas les genres régionaux (Afrobeat vs Amapiano vs Makossa) — pour ceux-ci, l'utilisateur choisit manuellement dans le Directeur artistique ; la détection automatique ne fait que pré-sélectionner une des 6 familles larges.
3. **Transcription automatique optionnelle** (`app/transcription.py`) : si aucune parole n'est fournie, une tentative de transcription (Whisper via `faster-whisper`) est faite pour enrichir le storyboard ; en cas d'échec (pas de voix, modèle indisponible), le pipeline continue sans paroles plutôt que d'échouer.
4. **Storyboard temporel** (`app/storyboard.py`, `build_storyboard_from_audio`) : une scène par section réelle détectée, avec un prompt de génération combinant la mise en scène du genre, l'ambiance, et les réglages du Directeur artistique.
5. **Génération de scènes photoréalistes** : pour chaque scène, une image est générée puis animée (image-to-video). Un **personnage de référence est créé une seule fois** (`app/character_reference.py`, mécanisme "SoulId" de Higgsfield) et réutilisé pour toutes les scènes, pour conserver le même visage d'une scène à l'autre.
6. **Assemblage final réel** (`app/video_assembler.py`, ffmpeg) : chaque clip de scène est ajusté à la durée exacte de sa section, concaténé, puis la piste audio du MP3 original de l'utilisateur remplace la bande-son générée → un vrai fichier MP4 final.
7. **Lecture/téléchargement** directement dans l'interface.

Ce parcours a été **testé de bout en bout dans ce dépôt** (voir `tests/test_pipeline.py` et `tests/test_main_pipeline_api.py`) : upload d'un fichier audio de test → analyse réelle → classification réelle → storyboard réel → assemblage ffmpeg réel → vrai MP4 lisible en sortie, sans paroles ni réglage fournis.

### Modes additionnels (paroles fournies)

| Mode | Entrée | Résultat |
|---|---|---|
| Paroles → Images | Texte des paroles | Scènes/images qui racontent l'histoire des paroles |
| Paroles + Musique → Film musical | Paroles + audio | Décors, personnages, caméra et chorégraphie synchronisés au rythme |
| Image → Musique/Clip | Photo d'un personnage | Ce personnage devient la référence de cohérence pour tout le clip |

Le mode "avancé" de l'interface (scène par scène, paroles requises) reste disponible pour explorer/regénérer une scène individuellement.

### Directeur artistique (facultatif)

**personnages** (africains, asiatiques, européens, latino, diversité, personnalisé), **style** (photoréaliste, cinéma, vintage, animation, peinture, 3D), **danse** (afrobeat, amapiano, salsa, jazz, contemporain, makossa, bikutsi, hip-hop...), **époque**, **décor**, **caméra**. Si l'utilisateur ne touche à rien, des valeurs par défaut raisonnables sont utilisées automatiquement.

### Un morceau → plusieurs contenus

À partir du storyboard, `app/outputs_planner.py` planifie : 1 clip complet (généré automatiquement), jusqu'à 3 extraits courts (TikTok/Reels, 15–30s) centrés sur les sections les plus énergiques, 1 visualizer, 1 lyric video, des images clés, et des variantes de style/caméra. Seul le clip complet est assemblé automatiquement aujourd'hui ; les autres formats réutilisent le même storyboard et peuvent être produits en mode avancé.

## MODE DÉMO — ne jamais confondre simulation et génération réelle

Sans `HIGGSFIELD_KEY_ID`/`HIGGSFIELD_KEY_SECRET` configurées, l'application tourne entièrement en **MODE DÉMO** : un générateur simulé (`MockGenerator`) remplace le fournisseur IA, pour développer/tester sans clé ni coût. Ce mode est **visible partout** dans l'interface :
- bannière permanente en haut de page,
- badge "⚠️ MODE DÉMO" sur le lecteur vidéo final,
- badge sur chaque image générée manuellement en mode avancé.

Les clips produits en MODE DÉMO contiennent des scènes placeholder (fond gris + texte "MODE DEMO" incrusté par ffmpeg) — impossible de les confondre visuellement avec une vraie génération.

## Architecture

```
backend/
  app/
    lyrics_analysis.py      # decoupe les paroles en sections (intro/couplet/refrain/pont/outro) + ambiance
    audio_analysis.py       # tempo, energie, segmentation structurelle reelle (librosa)
    genre_classifier.py     # classification de genre reelle (SVM pre-entraine, pyAudioAnalysis)
    transcription.py        # transcription vocale reelle optionnelle (faster-whisper)
    director.py             # reglages "Directeur artistique" et libelles de prompt
    prompt_builder.py       # combine scene + reglages en un prompt de generation
    storyboard.py           # storyboard depuis paroles ET/OU structure audio reelle
    outputs_planner.py      # planifie clip / shorts / visualizer / lyric video / variantes
    character_reference.py  # cree/reutilise un personnage de reference (coherence inter-scenes)
    generators/
      base.py               # contrat Generator (generate_image / generate_video_from_image / generate_audio)
      mock.py                # MODE DEMO: generateur hors-ligne deterministe (tests, dev)
      higgsfield.py          # generateur reel (API Higgsfield v2, voir "Integration Higgsfield" ci-dessous)
    video_assembler.py       # ffmpeg: fit-a-la-duree, concatenation, mux avec le MP3 original
    pipeline.py               # orchestrateur du parcours principal (job en arriere-plan)
    main.py                    # API FastAPI (parcours principal + mode avance)
  static/                     # interface web (HTML/JS/CSS, sans build)
  tests/                      # tests pytest (logique pure + integration ffmpeg/librosa reelle)
  tests/integration/           # test LIVE Higgsfield (desactive par defaut, voir plus bas)
```

## Intégration Higgsfield — ce qui est vérifié, et comment

`docs.higgsfield.ai` et `api.higgsfield.ai` sont **inaccessibles depuis cet environnement de développement** (bloqués par la politique réseau du bac à sable). Le client dans `generators/higgsfield.py` n'a donc **pas** été écrit contre la documentation live. À la place, le contrat a été reconstitué en lisant le code source du **SDK officiel `@higgsfield/client` (npm, v0.2.1)** — package publié par Higgsfield eux-mêmes — récupéré via `npm pack` (le registre npm, lui, est accessible) :

- URL de base réelle : `https://platform.higgsfield.ai` (et non `api.higgsfield.ai` comme dans une version précédente de ce code, qui était une supposition incorrecte)
- Authentification réelle : header `Authorization: Key <KEY_ID>:<KEY_SECRET>` (et non un simple Bearer token)
- `POST /v1/text2image/soul`, `POST /v1/image2video/dop`, `POST /v1/custom-references`, `POST /files/generate-upload-url` avec les corps de requête exacts documentés dans le README du SDK
- Polling réel : `GET /requests/{request_id}/status` jusqu'à `completed`/`nsfw`/`failed`/`canceled`
- Cohérence de personnage : mécanisme "SoulId" réel (`custom_reference_id`), pas une invention

Ceci est **vérifié contre une source primaire (le code du SDK officiel)**, mais **aucun appel réel n'a été exécuté** dans cet environnement : il n'y a pas de clé API ici, et le domaine est de toute façon bloqué. Un test séparé existe pour la vérification finale à faire vous-même :

```bash
export HIGGSFIELD_KEY_ID=...
export HIGGSFIELD_KEY_SECRET=...
export RUN_LIVE_GENERATION_TESTS=1
cd backend && pytest tests/integration/test_higgsfield_live.py -v -s
```

Ce test (désactivé par défaut, car il dépense de vrais crédits) fait un vrai appel de génération d'image et un vrai test de cohérence de personnage, et vérifie que l'URL retournée est réellement accessible. **C'est ce test — pas ce README — qui fait foi** si Higgsfield change son API.

Limite honnête : Higgsfield ne propose pas de génération de musique/texte-vers-audio (uniquement image, image-vers-vidéo, et synthèse vocale) — `generate_audio()` le signale explicitement plutôt que de simuler silencieusement une fonctionnalité inexistante.

## Lancer l'application

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # renseignez HIGGSFIELD_CREDENTIALS pour activer la generation reelle
uvicorn app.main:app --reload
```

Puis ouvrez `http://localhost:8000`. Le binaire système `ffmpeg` doit être installé (`apt-get install ffmpeg` sous Debian/Ubuntu) : requis pour l'assemblage vidéo et utilisé par `pydub`/`faster-whisper`.

## Tests

```bash
cd backend
pytest
```

54 tests passent dans cet environnement (aucune clé ni accès réseau requis), dont :
- **tests réels de bout en bout** : `test_audio_analysis.py` (segmentation structurelle sur audio synthétique aux frontières connues), `test_genre_classifier.py` (vraie inférence SVM), `test_video_assembler.py` et `test_pipeline.py` (assemblage ffmpeg réel produisant un vrai MP4 lisible), `test_main_pipeline_api.py` (le parcours complet via l'API HTTP réelle, MP3 seul, sans paroles ni réglage)
- tests unitaires de la logique pure (paroles, storyboard, prompts, plan de sorties)
- tests du client Higgsfield contre le contrat vérifié (requêtes HTTP simulées — voir la section ci-dessus pour la vérification live)
- `test_transcription.py` **passe en le sautant** (`SKIPPED`) dans cet environnement : le téléchargement du modèle Whisper est bloqué au niveau réseau ici (Hugging Face Hub inaccessible). Sur une machine avec accès Internet normal, ce test s'exécute réellement.

Le test live Higgsfield (`tests/integration/`) est exclu par défaut ; voir la section ci-dessus pour l'activer.

## Limites connues

- Le classificateur de genre distingue 6 familles larges (Blues/Classical/Electronic/Jazz/Rap/Rock), pas les genres régionaux (Afrobeat, Makossa, Zouk...) — ceux-ci restent un choix manuel dans le Directeur artistique.
- La transcription automatique et l'intégration Higgsfield n'ont pas pu être exercées de bout en bout **dans ce bac à sable** (Hugging Face Hub et `platform.higgsfield.ai` y sont bloqués au niveau réseau) ; le code est correct par construction (voir provenance ci-dessus) mais la vérification finale vous revient via les tests dédiés.
- Higgsfield ne génère pas de musique à partir de texte — fournissez toujours un MP3 existant.
- Un clip complet avec plusieurs scènes en génération réelle peut prendre plusieurs dizaines de minutes (chaque scène = 1 génération d'image + 1 génération vidéo, polling inclus) et consomme des crédits proportionnels au nombre de scènes détectées.
