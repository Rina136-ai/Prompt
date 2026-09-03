# Music-to-Story Video AI

Application qui transforme une chanson, des paroles, une image ou une vidéo en clip musical cinématographique généré par IA.

## Le concept

L'utilisateur importe un MP3/WAV, une vidéo, des paroles, ou une combinaison des deux. L'application analyse les paroles (thèmes, émotions, structure couplet/refrain/pont) et, si un fichier audio est fourni, son tempo et son énergie. Elle construit ensuite un **storyboard** scène par scène et génère les visuels correspondants — avec de vrais personnages photoréalistes si demandé (danseurs afrobeat, chanteuse et saxophoniste dans un club de jazz, etc.), pas seulement des animations abstraites.

### 4 modes de création

| Mode | Entrée | Résultat |
|---|---|---|
| Musique → Clip | MP3/WAV | Clip complet basé sur l'écoute du morceau |
| Paroles → Images | Texte des paroles | Scènes/images qui racontent l'histoire des paroles |
| Paroles + Musique → Film musical | Paroles + audio | Décors, personnages, caméra et chorégraphie synchronisés au rythme |
| Image → Musique/Clip | Photo d'un personnage | Univers musical construit autour de ce personnage |

### Directeur artistique

Avant génération, l'utilisateur choisit : **personnages** (africains, asiatiques, européens, latino, diversité, personnalisé), **style** (photoréaliste, cinéma, vintage, animation, peinture, 3D), **danse** (afrobeat, amapiano, salsa, jazz, contemporain, makossa, bikutsi, hip-hop...), **époque**, **décor** et **caméra**.

### Un morceau → plusieurs contenus

À partir d'un seul titre, l'app planifie : 1 clip complet, jusqu'à 3 extraits courts (TikTok/Reels, 15–30s) centrés sur les refrains, 1 visualizer, 1 lyric video, des images clés de l'univers, et des variantes de style/caméra.

## Architecture

```
backend/
  app/
    lyrics_analysis.py   # découpe les paroles en sections (intro/couplet/refrain/pont/outro) + détection d'ambiance
    audio_analysis.py    # tempo (BPM) et énergie par segment via librosa (optionnel)
    director.py          # les réglages "Directeur artistique" et leurs libellés de prompt
    prompt_builder.py    # combine scène + réglages en un prompt de génération
    storyboard.py         # assemble le storyboard scène par scène
    outputs_planner.py   # planifie clip / shorts / visualizer / lyric video / variantes
    generators/
      base.py            # contrat Generator (generate_image/video/audio)
      mock.py            # générateur hors-ligne déterministe (tests, démo sans clé API)
      higgsfield.py      # générateur réel via l'API Higgsfield (job asynchrone + polling)
    video_assembler.py   # assemblage ffmpeg : concaténation, recadrage vertical, sous-titres
    main.py               # API FastAPI
  static/                 # interface web (HTML/JS/CSS, sans build)
  tests/                  # tests pytest de la logique métier (sans réseau)
```

La génération réelle passe par [l'API Higgsfield](https://docs.higgsfield.ai) : soumission d'un job (`POST /v1/generations`) puis attente du résultat par polling. Sans `HIGGSFIELD_API_KEY`, l'application bascule automatiquement sur un générateur "mock" déterministe, pour développer et tester l'ensemble du pipeline sans clé ni coût.

## Lancer l'application

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # librosa/numpy sont optionnels si vous ne faites pas d'analyse audio
cp .env.example .env               # renseignez HIGGSFIELD_API_KEY pour activer la génération réelle
uvicorn app.main:app --reload
```

Puis ouvrez `http://localhost:8000`.

## Tests

```bash
cd backend
pytest
```

Les tests couvrent l'analyse des paroles, la construction du storyboard, les prompts, le plan de sorties multiples, et le client Higgsfield (requêtes HTTP simulées, sans réseau).

## Limites connues

- L'analyse "genre musical" à partir de l'audio est une heuristique tempo/énergie, pas une classification IA du genre : l'utilisateur choisit le genre explicitement dans l'interface.
- Le client Higgsfield suit le schéma documenté publiquement (job asynchrone, polling par identifiant) ; si votre compte expose des noms de champs différents, ajustez les constantes en tête de `generators/higgsfield.py`.
- L'assemblage vidéo (`video_assembler.py`) nécessite le binaire `ffmpeg` sur la machine qui exécute le backend.
