"""Director-artistique settings: the creative controls the user sets before generation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

CHARACTER_OPTIONS = [
    "africains", "asiatiques", "europeens", "latino", "diversite", "personnalise",
]
STYLE_OPTIONS = [
    "photorealiste", "cinema", "vintage", "animation", "peinture", "3d",
]
DANCE_OPTIONS = [
    "afrobeat", "amapiano", "salsa", "jazz", "contemporain",
    "makossa", "bikutsi", "hiphop", "aucune",
]
ERA_OPTIONS = [
    "traditionnelle", "annees60", "annees80", "contemporaine", "futuriste",
]
DECOR_OPTIONS = [
    "afrique", "new_york", "paris", "montreal", "plage", "village",
    "nightclub", "studio", "scene_concert", "personnalise",
]
CAMERA_OPTIONS = [
    "cinematographique", "drone", "travelling", "gros_plans", "plans_larges", "dynamique",
]

_LABELS = {
    "africains": "danseurs et personnages africains",
    "asiatiques": "personnages asiatiques",
    "europeens": "personnages europeens",
    "latino": "personnages latino",
    "diversite": "un casting divers et inclusif",
    "photorealiste": "photorealiste, peau et lumiere naturelles, rendu 8k",
    "cinema": "esthetique cinema, grain pellicule, eclairage dramatique",
    "vintage": "look vintage, couleurs desaturees, grain d'epoque",
    "animation": "anime en animation stylisee",
    "peinture": "rendu en peinture, coups de pinceau visibles",
    "3d": "rendu 3D stylise",
    "afrobeat": "chorégraphie afrobeat energique, jeux de jambes rapides",
    "amapiano": "chorégraphie amapiano, mouvements fluides et groove bas",
    "salsa": "chorégraphie salsa, couples tournoyants",
    "jazz": "chorégraphie jazz, mouvements syncopes",
    "contemporain": "danse contemporaine expressive",
    "makossa": "chorégraphie makossa, ondulations de hanches",
    "bikutsi": "chorégraphie bikutsi, rythme rapide et percussif",
    "hiphop": "chorégraphie hip-hop urbaine",
    "aucune": "sans chorégraphie particuliere",
    "traditionnelle": "costumes et decors traditionnels",
    "annees60": "esthetique annees 1960",
    "annees80": "esthetique annees 1980, neons et synthwave",
    "contemporaine": "epoque contemporaine",
    "futuriste": "univers futuriste",
    "afrique": "un village ou une place d'Afrique de l'Ouest baignee de lumiere doree",
    "new_york": "les rues et toits de New York",
    "paris": "les rues et monuments de Paris",
    "montreal": "le centre-ville de Montreal",
    "plage": "une plage au coucher du soleil",
    "village": "un village paisible",
    "nightclub": "un club de nuit avec projecteurs colores",
    "studio": "un studio d'enregistrement",
    "scene_concert": "une scene de concert face a la foule",
    "cinematographique": "plans cinematographiques grand angle, profondeur de champ",
    "drone": "prises de vue aeriennes au drone",
    "travelling": "travellings fluides suivant l'action",
    "gros_plans": "gros plans sur les visages et emotions",
    "plans_larges": "plans larges etablissant le decor",
    "dynamique": "montage dynamique multi-cameras",
}


def label(option: str) -> str:
    return _LABELS.get(option, option.replace("_", " "))


@dataclass
class DirectorSettings:
    characters: str = "diversite"
    characters_custom: Optional[str] = None
    style: str = "photorealiste"
    dance: str = "aucune"
    era: str = "contemporaine"
    decor: str = "studio"
    decor_custom: Optional[str] = None
    camera: str = "cinematographique"
    character_reference_media_id: Optional[str] = None
    extra_notes: str = ""

    def characters_phrase(self) -> str:
        if self.characters == "personnalise" and self.characters_custom:
            return self.characters_custom
        return label(self.characters)

    def decor_phrase(self) -> str:
        if self.decor == "personnalise" and self.decor_custom:
            return self.decor_custom
        return label(self.decor)

    def as_prompt_fragments(self) -> list[str]:
        fragments = [
            self.characters_phrase(),
            label(self.style),
            label(self.era),
            self.decor_phrase(),
            label(self.camera),
        ]
        if self.dance != "aucune":
            fragments.append(label(self.dance))
        if self.extra_notes:
            fragments.append(self.extra_notes)
        return fragments
