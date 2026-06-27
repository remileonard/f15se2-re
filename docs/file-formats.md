# F-15 Strike Eagle II — Formats des fichiers de carte

Documentation des formats binaires des fichiers de théâtre du jeu F-15 Strike Eagle II
(MicroProse, 1992). Dérivée de l'ingénierie inverse du moteur de rendu 3D et du système
de chargement de carte.

---

## Vue d'ensemble de l'architecture

Un **théâtre** (zone de combat) est défini par quatre fichiers compagnons :

```
CE.3DT  ──► Tuiles de terrain 3D
              (catalogue de formes 3D pour la géographie : building, pont, etc.)
              ↓ référence des formes
CE.3DG  ──► Grille d'index de tuiles (4 niveaux LOD, 16×16 → 1024×1024)
              (indique quelle catégorie de tuile 3DT occupe chaque cellule)
              ↓ résolution LOD
CE.3D3  ──► Bibliothèque de modèles 3D (jusqu'à 128 modèles indexés)
              (les formes réelles en wireframe/face : pont, piste, SAM, etc.)
              ↑ index de forme
CE.WLD  ──► Données monde (objets positionnés, unités de vol, chaînes de noms)
              (emplacements des cibles, bases, unités ennemies)
```

**Préfixes de théâtre** :

| Préfixe | Théâtre         |
|---------|-----------------|
| `LB`    | Libya           |
| `PG`    | Persian Gulf    |
| `VN`    | Vietnam         |
| `ME`    | Middle East     |
| `NC`    | North Cape      |
| `CE`    | Central Europe  |
| `JP`    | Japan           |
| `NA`    | North Atlantic  |

---

## Système de coordonnées monde

Le monde est un carré de **32 768 × 32 768 unités** (0x0000–0x8000).

```
  Y = 0x8000 (32768)  ←  NORD
  ┌─────────────────────────────────┐
  │                                 │
  │   X →  (0=ouest, 0x8000=est)   │
  │   Y ↑  (0=sud,   0x8000=nord)  │
  │                                 │
  └─────────────────────────────────┘
  Y = 0x0000            ←  SUD
```

**Conversion en coordonnées de grille LOD3 (16×16) :**

```
col = x_coord / 32768.0 * 16   (arrondi vers le bas)
row = (32768 - y_coord) / 32768.0 * 16   (Y inversé)
```

**Conversion vers le rendu 3D** (système de voxels du visualiseur) :

```
world_x = x_coord / 32768.0 * dim * CELL_SIZE
world_z = (32768 - y_coord) / 32768.0 * dim * CELL_SIZE
```

où `dim = 16` (LOD3), `CELL_SIZE = 1024.0`.

---

## Format .WLD — Fichier Monde

### Présentation

Le fichier `.WLD` contient :
- Les **objets monde** : positions de cibles, bases, sites SAM, ponts, etc.
- Les **unités de vol** : appareils ennemis et amis (patrouilles, escortes).
- La **table des noms** : chaînes de texte pour les lieux.
- Des métadonnées de mission (lues par `readWorldData` dans `enworld.c`).

### Disposition binaire séquentielle

```
Offset   Taille   Champ                     Description
──────   ──────   ─────────────────────────────────────────────────────────────
+0x00    2        worldWaypointCount         (u16) toujours présent
+0x02    2        worldObjectCount           (u16) nombre d'objets WorldObject
+0x04    2        worldRouteTable[0]         (u16) réservé / route table entrée 0
+0x06    2        worldRouteCount            (u16)
+0x08    objectCount×16  worldObjects[]     tableau de WorldObject (voir §2.3)
+?       2        worldSamCount              (u16) nombre d'unités SAM/vol
+?       samCount×36  worldSamTable[]        FlightUnit[] (voir §2.4)
+?       100      unitTypeTable              catégories de types d'objets (objectTypeTable[])
+?       100      worldUnitFlags             indicateurs d'unité
+?       750      worldStringBuf             noms null-terminés (voir §2.5)
+?       256      gridFlags                  grille 16×16 u8 de bits de terrain
+?       2        worldGridSize              (u16)
+?       2        worldMiscHeader            (u16)
+?       16       weaponDataBlock
+?       36       targetBlock
+?       1536     flightDataBuf              données de vol supplémentaires
```

> **Note :** Les champs après `worldStringBuf` sont utilisés par le moteur de mission
> (`stgen.c`) mais non nécessaires pour le rendu de carte.

---

### Structure WorldObject (16 octets)

Chaque entrée décrit un objet positionné dans le monde (cible, base, véhicule, etc.).

```
 Offset  Taille  Champ           Type     Description
 ──────  ──────  ──────────────  ───────  ────────────────────────────────────────
 +0x00    2      unitRef         uint16   Index dans wldOffsets[] pour le nom du lieu
 +0x02    2      x_coord         uint16   Coordonnée X monde (0–32768)
 +0x04    2      y_coord         uint16   Coordonnée Y monde (0–32768, 0=sud)
 +0x06    2      unitType        int16    Type d'objet (voir §2.6)
 +0x08    2      targetFlags     int16    Drapeaux de cible (voir §2.7)
 +0x0A    2      occupantType    int16    Type d'appareil stationné ici (voir §3.3)
 +0x0C    2      patrolCount     int16    Compteur de patrouille/spawn
 +0x0E    2      objectIdx       int16    Index dans objectTypeTable[] (masqué & 0x7F)
```

**Diagramme mémoire :**

```
Octet :  00 01 | 02 03 | 04 05 | 06 07 | 08 09 | 0A 0B | 0C 0D | 0E 0F
         ──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────
         unitRef│  x   │  y   │uType │tFlags│occup │patrol│objIdx
```

**Interprétation de `objectIdx` :**

`objectIdx & 0x7F` est un **identifiant de catégorie** utilisé par le moteur pour :
- Indexer `objectTypeTable[]` (mission category → type de mission possible)
- Indexer `wldOffsets[]` (→ nom du lieu dans worldStringBuf)
- Correspondre au champ `shape` dans les `TileSceneObject` du fichier `.3DT`

Il correspond **aussi** à l'indice de forme dans le fichier `.3D3` pour les objets statiques
(SAM, aérobase, port). Il NE doit PAS être utilisé directement comme indice CE.3D3 pour les
objets marqueurs de cible (tf & 0x0001), car ceux-ci partagent tous objectIdx=21 (indicateur
cible générique).

**Valeurs connues de `objectIdx` dans CE.WLD :**

| objectIdx | Objet typique           | Forme CE.3D3  | Nb sommets | Nb faces |
|-----------|-------------------------|---------------|------------|----------|
| 21        | Marqueur cible (tf=0x1) | Indicateur △  | 104        | 25       |
| 38        | Véhicule, pont          | (vide)        | 0          | 0        |
| 53        | Site SAM / Radar SAM    | Lanceur SAM   | 30         | 18       |
| 62        | Aérobase, waypoint      | Bâtiment      | 44         | 27       |
| 68        | Port / Raffinerie       | Structure     | 18         | 9        |

---

### Structure FlightUnit (36 octets)

Unité de vol (appareil ennemi ou ami), tableau `worldSamTable[]` / `flightUnits[]`.

```
 Offset  Taille  Champ          Type     Description
 ──────  ──────  ─────────────  ───────  ─────────────────────────────────────
 +0x00    2      waypointIdx    int16    Index dans worldObjects[] du waypoint
 +0x02    2      x              uint16   Coordonnée X monde (0 si = waypoint)
 +0x04    2      y              uint16   Coordonnée Y monde
 +0x06    2      altitude       uint16   Altitude
 +0x08    4      xPrecise       int32    X précis (non utilisé pour la carte)
 +0x0C    4      yPrecise       int32    Y précis
 +0x10    2      heading        int16    Cap (yaw)
 +0x12    2      pitch          int16
 +0x14    2      roll           int16
 +0x16    2      planeType      int16    Index dans aircraftTypes[] (voir §3.3)
 +0x18    2      flags          int16    Bits de comportement (0x80=mobile, 0x100=escorte)
 +0x1A    2      maxSpeed       int16
 +0x1C    2      fuel           uint16
 +0x1E    6      reserved       uint8[6] Chargé/sauvé, jamais utilisé
```

**Résolution de la position d'une FlightUnit :**

```
si (x == 0 et y == 0) et (0 < waypointIdx < worldObjectCount) :
    x = worldObjects[waypointIdx].x_coord
    y = worldObjects[waypointIdx].y_coord
```

---

### Table des noms (worldStringBuf)

Tampon de 750 octets contenant des chaînes null-terminées en ASCII. L'index `i` dans la table
correspond à la position séquentielle dans le tampon (séparées par `\0`).

- `wldOffsets[0]` → premier nom (offset 0 dans le tampon)
- `wldOffsets[i]` → chaîne suivant le (i-1)ième `\0`

**Résolution du nom d'un WorldObject :**

```
Priorité 1 : names[obj_array_index]         si chaîne printable
Priorité 2 : names[obj.unitRef]             si chaîne printable
Priorité 3 : _UNIT_TYPE_LABELS[obj.unitType] (table codée en dur)
```

---

### Table unitType (WorldObject.unitType)

| Valeur | Étiquette       | Valeur | Étiquette        |
|--------|-----------------|--------|------------------|
| 0      | (vide/waypoint) | 11     | SAM Radar        |
| 1      | Waypoint        | 12     | Poste de cmd     |
| 2      | Pont            | 13     | Dépôt carburant  |
| 3      | Carrefour route | 14     | Dépôt munitions  |
| 4      | Colonne blindée | 15     | Usine            |
| 5      | Infanterie      | 16     | Centrale élec.   |
| 6      | Colonne camions | 17     | Gare triag.      |
| 7      | Reconnaissance  | 18     | Aérodrome        |
| 8      | Dépôt ravitail. | 19     | Base navale      |
| 9      | Site SAM        | 20     | Raffinerie pétr. |
| 10     | Canon AA        | 21     | Port / Raffinerie|

---

### Bits de targetFlags (WorldObject.targetFlags)

| Bit (hex) | Nom logique    | Signification                                     |
|-----------|----------------|---------------------------------------------------|
| 0x0001    | TARGET         | Marqueur de cible de mission (objectIdx=21 toujours)|
| 0x0008    | OPTIONAL       | Cible optionnelle (SAM, AA)                       |
| 0x0100    | AIRBASE        | Aérobase (piste d'atterrissage)                   |
| 0x0200    | LARGE/FRIENDLY | Grande base ou base amie                          |
| 0x0400    | WAYPOINT       | Point de navigation de route                      |
| 0x0500    | BASE           | Combinaison 0x100 + 0x400 : base opérationnelle   |
| 0x0800    | DESTROYED      | Objet détruit / désactivé                         |

> **Règle de rendu :** Ne PAS rendre un modèle 3D CE.3D3 pour les objets avec
> `targetFlags & 0x0001` — ils utilisent tous objectIdx=21 (indicateur cible générique).

---

## Format .3D3 — Bibliothèque de modèles 3D

### Vue d'ensemble

Un fichier `.3D3` est une collection de modèles 3D numérotés. Chaque modèle est un flux
binaire autonome encodant : des normales de faces (back-face culling), une liste de sommets
(coordonnées 3D), une liste d'arêtes (paires de sommets), puis des primitives de rendu (faces
pleines ou lignes wireframe).

**Fichiers du moteur :**

| Fichier      | Rôle                                   | Modèles (CE) |
|--------------|----------------------------------------|-------------|
| `CE.3D3`     | Objets terrain (bâtiments, SAM, piste) | 92          |
| `15FLT.3D3`  | Appareils en vol                       | 23+         |
| `PHOTO.3D3`  | Modèles photo-reconnaissance           | —           |

---

### Structure du modèle décodé (en mémoire)

Après décodage, chaque modèle est représenté par la structure suivante :

```
DecodedModel
├── index         int        numéro du modèle dans le fichier .3D3
├── offset        int        position en octets dans object_data
│
├── face_normals  FaceNormal[]   normales de visibilité (back-face culling)
│   └─ FaceNormal
│       ├── nx         int16   composante X de la normale
│       ├── ny         int16   composante Y
│       ├── nz         int16   composante Z
│       └── threshold  int16   seuil : face visible si dot(view_dir, normal) > threshold
│
├── vertices      ModelVertex[]  liste de sommets (espace modèle)
│   └─ ModelVertex
│       ├── x  int16  coordonnée X (axe lateral droit)
│       ├── y  int16  coordonnée Y (axe vertical, haut = positif)
│       └── z  int16  coordonnée Z (axe profondeur)
│
├── edges         ModelEdge[]    liste d'arêtes (paires d'indices de sommets)
│   └─ ModelEdge
│       ├── va  int   indice du sommet A dans vertices[]
│       └── vb  int   indice du sommet B dans vertices[]
│
├── faces         ModelFace[]    polygones remplis (rendu solide)
│   └─ ModelFace
│       ├── edge_indices  int[]  indices dans edges[] formant le contour
│       ├── color         int    index dans la palette VGA (0–255)
│       └── normal_index  int    index dans face_normals[] pour le culling
│                                (si >= len(face_normals) → toujours visible)
│
└── wire_lines    ModelWireLine[]  segments wireframe (contours, cockpit, etc.)
    └─ ModelWireLine
        ├── edge_index  int  indice dans edges[]
        └── color       int  index dans la palette VGA
```

**Diagramme des relations :**

```
 vertices[]          edges[]              faces[]
 ──────────          ──────────────────   ──────────────────────────────────────
 [0] (x,y,z)    ←── va=0  │              face_indices: [0, 2, 5]
 [1] (x,y,z)    ←── vb=1  │              color: 42
 [2] (x,y,z)    ←── va=1  │              normal_index: 1 ──→ face_normals[1]
 [3] (x,y,z)    ←── vb=2  │                              (nx,ny,nz,threshold)
 ...             ←── va=2  │
                 ←── vb=0  │
                     ...   │
                           └──→ wire_lines[]: { edge_index, color }
```

**Unités de coordonnées :**

Les coordonnées de sommets sont des `int16` en espace modèle. Conversion vers l'espace monde
du visualiseur :

```
MODEL_SCALE     = CELL_SIZE / 0x1000 = 1024 / 4096 = 0.25  (objets terrain CE.3D3)
FLT_MODEL_SCALE = MODEL_SCALE × 6    = 1.5                  (appareils 15FLT.3D3)
```

---

### Structure binaire du fichier .3D3

```
Octet   Taille         Champ
──────  ─────────────  ───────────────────────────────────────────────────────
+0x00   2              signature   u16 = 0x3333  (vérification obligatoire)
+0x02   2              N           u16 = nombre de modèles dans le fichier
+0x04   N × 2          offsets[]   u16[] offsets de chaque modèle dans object_data
+0x04+N×2  2           data_size   u16 = taille du bloc object_data en octets
+?      data_size      object_data  flux de modèles concaténés (voir §4.3)
+?      1              V           u8  = 0 si pas de tables globales de sommets
                                        > 0 → V entrées dans chaque table
[seulement si V > 0 :]
+?      V              extra_a[]   u8[V]  table de réindexation axe X
+?      V              extra_b[]   u8[V]  table de réindexation axe Y
+?      V              extra_c[]   u8[V]  table de réindexation axe Z
+?      1              Cx          u8  nombre de valeurs X globales
+?      Cx × 2         vertex_x[]  u16[Cx] (réinterprété int16 signé)
+?      1              Cy          u8
+?      Cy × 2         vertex_y[]  u16[Cy]
+?      1              Cz          u8
+?      Cz × 2         vertex_z[]  u16[Cz]
```

**Accès à un modèle i :**

```python
stream_start = offsets[i]          # offset dans object_data
stream = object_data[stream_start:]
```

---

### Décodage d'un flux de modèle (object_data[offset:])

Le décodage se fait séquentiellement en 5 phases. On maintient un pointeur de lecture `pos`
qui avance au fil de la lecture.

#### Phase 1 — Octet de mode de rendu (1 octet, ignoré)

```
pos=0  render_mode  u8  (contrôle interne de rendu, ignoré au chargement)
pos=1
```

#### Phase 2 — En-têtes LOD (variable)

Le moteur stocke les données LOD (niveaux de détail croissants, du plus lointain au plus
proche) en blocs de 3 octets. Chaque bloc a son bit 7 à 1. Le LOD le plus proche (plus grand
détail) commence au premier octet sans bit 7.

```
tant que (data[pos] & 0x80 != 0) :
    sauter 3 octets   ← en-tête LOD lointain (distance de transition, non décodé)

→ pos pointe maintenant sur le début du LOD le plus détaillé
```

```
Exemple :
  pos:  [0x87][0x00][0x40]  ← LOD lointain (bit7=1, skip)
        [0xC2][0x00][0x20]  ← LOD moyen (bit7=1, skip)
        [0x0E]...           ← LOD proche (bit7=0) → décodage commence ici
```

#### Phase 3 — Opcode + normales de visibilité de faces

```
opcode_byte  u8
  bits [4:0] = face_count   (nombre de normales de visibilité)
  si face_count > 0x10 :  mask_size = 4 octets
  sinon :                  mask_size = 2 octets

  ┌──────────────────────────────────────────────────────────┐
  │ mask_size est le nombre d'octets de masque de visibilité │
  │ précédant chaque sommet, arête, et ligne wireframe.      │
  │ Ces octets encodent dans quels états LOD l'élément est   │
  │ actif. Pour le chargement, on les saute systématiquement.│
  └──────────────────────────────────────────────────────────┘

lecture de face_count × FaceNormal (8 octets chacune) :
  pour i in range(face_count) :
      nx        = read_i16()
      ny        = read_i16()
      nz        = read_i16()
      threshold = read_i16()
```

**Test de visibilité d'une face (back-face culling) :**

```
dot = view_dir.x * nx + view_dir.y * ny + view_dir.z * nz
face_visible = (dot > threshold)
```

où `view_dir` est la direction normalisée de la caméra vers le modèle.

#### Phase 4 — Sommets

```
vtx_al  u8
  bit 7   = 1 → mode indexé (sommets depuis tables globales)
          = 0 → mode inline (coordonnées explicites)
  bits [6:0] = vtx_count  (nombre de sommets)
```

**Mode inline (bit 7 = 0) :**

```
pour i in range(vtx_count) :
    sauter mask_size octets   ← masque de visibilité LOD (ignoré)
    x = read_i16()
    y = read_i16()
    z = read_i16()
    vertices.append((x, y, z))
```

**Mode indexé (bit 7 = 1) :**

Les coordonnées ne sont pas stockées directement dans le flux ; elles proviennent de tables
partagées à la fin du fichier `.3D3`. Un octet de référence indexe ces tables via trois tables
intermédiaires (`extra_a/b/c`).

```
pour i in range(vtx_count) :
    sauter mask_size octets
    ref = read_u8()           ← index dans extra_a[], extra_b[], extra_c[]

    xa = extra_a[ref]         ← réindexation axe X
    yb = extra_b[ref]         ← réindexation axe Y
    zc = extra_c[ref]         ← réindexation axe Z

    x = vertex_x[xa]          ← valeur finale X (u16 → int16 signé)
    y = vertex_y[yb]
    z = vertex_z[zc]
    vertices.append((x, y, z))

Conversion u16 → int16 signé :
    si v >= 0x8000 : v = v - 0x10000
```

**Schéma du mode indexé :**

```
  flux: ref=42
           │
           ├─ extra_a[42] = 7  ──→  vertex_x[7] = 0x01A0  →  x = +416
           ├─ extra_b[42] = 3  ──→  vertex_y[3] = 0xFF80  →  y = -128
           └─ extra_c[42] = 9  ──→  vertex_z[9] = 0x0060  →  z = +96
```

Ce mécanisme permet à plusieurs modèles de partager les mêmes tables de sommets globales,
réduisant la taille totale du fichier.

#### Phase 5 — Arêtes

```
edge_count = read_u8()

pour i in range(edge_count) :
    sauter mask_size octets   ← masque de visibilité LOD
    va = read_u8()            ← indice du sommet A (dans vertices[])
    vb = read_u8()            ← indice du sommet B
    edges.append((va, vb))
```

#### Phase 6 — Primitives de rendu

```
prim_count = read_u8()
```

**Cas A — Primitives directes (`prim_count != 0 et prim_count != 0xFF`) :**

```
pour i in range(prim_count) :
    opcode = read_u8()

    si (opcode & 3) == 1 :      ← FACE REMPLIE
        normal_index = (opcode & 0x7C) >> 2   ← bits [6:2]
        n = read_u8()                          ← nombre d'arêtes du polygone
        edge_indices = [read_u8() for _ in range(n)]
        color = read_u8()
        faces.append(ModelFace(edge_indices, color, normal_index))

    sinon :                     ← LIGNE WIREFRAME
        sauter mask_size octets
        edge_idx = read_u8()
        color    = read_u8()
        wire_lines.append(ModelWireLine(edge_idx, color))
```

**Encodage de l'opcode de face :**

```
  bit 7   bit 6   bit 5   bit 4   bit 3   bit 2   bit 1   bit 0
  ──────────────────────────────────────────────────────────────
  [  ← normal_index (6 bits) ───────────────────────────── ]  type
  normal_index = (opcode & 0x7C) >> 2       (bits 6..2)
  type         = opcode & 0x03              (bits 1..0) == 1 → face
```

**Cas B — Mode RLE (`prim_count == 0xFF`) :**

Ce mode utilise un arbre d'adjacence pour réordonner les primitives et optimiser le rendu
(partage d'arêtes entre faces adjacentes). Structure après l'octet `0xFF` :

```
root        u8                    nœud racine de l'arbre
tree[]      face_count × 2 u8    pour chaque nœud : [enfant_gauche, enfant_droit]
                                  0xFF = feuille/null
coord_offs  face_count × 2 i16   offset (signé) depuis data_base vers les primitives
                                  de ce groupe d'arêtes
run_cnts[]  face_count × 1 u8    nombre de primitives dans chaque groupe
data_base   (position courante)   primitives compressées

Décodage :
    pour i in range(face_count) :
        p = data_base + coord_offs[i]
        pour _ in range(run_cnts[i]) :
            p = decode_prim_command(data, p)   ← même logique que cas A
```

L'arbre en lui-même (nœuds `root` + `tree[]`) peut être ignoré pour un simple chargement ;
seuls `coord_offs` et `run_cnts` sont nécessaires pour accéder aux primitives.

---

### Algorithme de décodage complet (pseudocode)

```python
def decode_model(data, base_offset, extra_a, extra_b, extra_c,
                 vertex_x, vertex_y, vertex_z):
    pos = base_offset

    # Phase 1 — render mode (ignoré)
    pos += 1

    # Phase 2 — sauter les en-têtes LOD grossiers
    while data[pos] & 0x80:
        pos += 3

    # Phase 3 — opcode + normales
    opcode = data[pos]; pos += 1
    face_count = opcode & 0x1F
    mask_size  = 4 if face_count > 0x10 else 2
    normals = []
    for _ in range(face_count):
        normals.append(read_i16x4(data, pos)); pos += 8

    # Phase 4 — sommets
    vtx_al = data[pos]; pos += 1
    vtx_count = vtx_al & 0x7F
    vertices = []
    if vtx_al & 0x80:                          # mode indexé
        for _ in range(vtx_count):
            pos += mask_size
            ref = data[pos]; pos += 1
            x = to_signed(vertex_x[extra_a[ref]])
            y = to_signed(vertex_y[extra_b[ref]])
            z = to_signed(vertex_z[extra_c[ref]])
            vertices.append((x, y, z))
    else:                                       # mode inline
        for _ in range(vtx_count):
            pos += mask_size
            x = read_i16(data, pos); pos += 2
            y = read_i16(data, pos); pos += 2
            z = read_i16(data, pos); pos += 2
            vertices.append((x, y, z))

    # Phase 5 — arêtes
    edge_count = data[pos]; pos += 1
    edges = []
    for _ in range(edge_count):
        pos += mask_size
        va = data[pos]; pos += 1
        vb = data[pos]; pos += 1
        edges.append((va, vb))

    # Phase 6 — primitives
    prim_count = data[pos]; pos += 1
    faces, lines = [], []

    if prim_count == 0xFF:                     # mode RLE
        pos += 1 + face_count * 2             # skip root + tree
        coord_offs = [read_i16(data, pos + i*2) for i in range(face_count)]
        pos += face_count * 2
        run_cnts   = [data[pos + i] for i in range(face_count)]
        pos += face_count
        data_base = pos
        for i in range(face_count):
            p = data_base + coord_offs[i]
            for _ in range(run_cnts[i]):
                p, prim = decode_one_prim(data, p, mask_size)
                (faces if prim.is_face else lines).append(prim)

    else:                                      # mode direct
        for _ in range(prim_count):
            pos, prim = decode_one_prim(data, pos, mask_size)
            (faces if prim.is_face else lines).append(prim)

    return DecodedModel(normals, vertices, edges, faces, lines)


def decode_one_prim(data, pos, mask_size):
    op = data[pos]; pos += 1
    if (op & 3) == 1:                         # face remplie
        normal_idx = (op & 0x7C) >> 2
        n  = data[pos]; pos += 1
        ei = list(data[pos:pos+n]); pos += n
        color = data[pos]; pos += 1
        return pos, ModelFace(ei, color, normal_idx)
    else:                                     # ligne wireframe
        pos += mask_size
        edge_idx = data[pos]; pos += 1
        color    = data[pos]; pos += 1
        return pos, ModelWireLine(edge_idx, color)
```

---

### Rendu d'un modèle décodé

**Algorithme de rendu (vue 3D, painter's algorithm) :**

```python
def render_model(model, cam_pos, cam_basis, surface, palette):
    # 1. Projeter tous les sommets en coordonnées écran
    screen_pts = []
    for v in model.vertices:
        world = transform(v, model_pos, cam_basis)  # rotation + translation
        screen = project(world, cam_pos)            # perspective
        screen_pts.append(screen)

    # 2. Calculer la profondeur de chaque face (centroïde Z)
    face_depths = []
    for face in model.faces:
        pts = face_points(face, model.edges, screen_pts)
        z = mean_depth(pts)
        face_depths.append((z, face, pts))

    # 3. Trier par profondeur décroissante (painter's algorithm)
    face_depths.sort(key=lambda t: t[0], reverse=True)

    # 4. Dessiner les faces (back-face culling)
    view_dir = normalize(model_pos - cam_pos)
    for z, face, pts in face_depths:
        n = model.face_normals[face.normal_index]
        dot = view_dir.x*n.nx + view_dir.y*n.ny + view_dir.z*n.nz
        if dot <= n.threshold:
            continue                              # face dos à la caméra
        color_rgb = palette[face.color]
        draw_filled_polygon(surface, pts, color_rgb)

    # 5. Dessiner les arêtes wireframe par-dessus
    for line in model.wire_lines:
        edge = model.edges[line.edge_index]
        a, b = screen_pts[edge.va], screen_pts[edge.vb]
        if a and b:
            draw_line(surface, palette[line.color], a, b)
```

**Construction du polygone d'une face :**

Une face référence une liste d'indices dans `edges[]`. Chaque arête a deux sommets.
Pour reconstruire le polygone ordonné :

```python
def face_points(face, edges, screen_pts):
    pts = []
    for ei in face.edge_indices:
        e = edges[ei]
        pts.append(screen_pts[e.va])
        # vb est partagé avec l'arête suivante (les arêtes forment un cycle)
    return pts
```

---

### Palette de couleurs VGA

Les indices `color` dans les faces et lignes référencent la palette VGA 256 couleurs du jeu.
Entrées notables :

| Plage     | Contenu                            |
|-----------|------------------------------------|
| 0–15      | Couleurs EGA standard              |
| 16–31     | Rampe de gris (0 → 255)            |
| 32–55     | Spectre saturé (rouge → violet)    |
| 56–247    | Cycles à demi/quart d'intensité    |
| 248–255   | Noir (non utilisé)                 |

---

## Format .3DG — Grille d'index de terrain

### Vue d'ensemble

Le `.3DG` mappe chaque cellule de la grille de terrain à un **index de catégorie 3DT**.
Il contient 4 couches de résolution croissante (LOD 3 → LOD 0).

### Structure binaire

```
Offset  Taille  Champ
──────  ──────  ─────────────────────────────────────────────────────────────
+0x00   2       signature  0x3232
+0x02   16      header     (non interprété)
+0x12   256     layer1     16×16 bytes → LOD 3 (cellule = 2048 unités)
+0x112  512     layer2     32×32 bytes → LOD 2 (cellule = 512 unités)
+0x312  512     layer3     64×64 ? → LOD 1
+0x512  512     layer4     → LOD 0
```

### Résolution d'une cellule (process_3dg)

```python
LOD_DIM = [1024, 256, 64, 16]   # cellules par axe pour LOD 0-3

def process_3dg(grid, lod, col, row) -> int:
    """Retourne l'index de catégorie 3DT pour la cellule (col, row) au LOD donné."""
    if lod == 3:
        return layer1[col + row * 16]
    parent = process_3dg(grid, lod + 1, col >> 2, row >> 2)
    layers = [layer4, layer3, layer2]   # lod 0, 1, 2
    layer = layers[lod]
    idx = (col & 3) + ((row & 3) << 2) + (parent << 4)
    return layer[idx]
```

La valeur retournée est l'**index de tuile 3DT** (catégorie) correspondant à cette cellule.

---

## Format .3DT — Catalogue de tuiles terrain

### Vue d'ensemble

Le `.3DT` contient des **tuiles de terrain** organisées en 5 catégories (LOD 0–4).
Chaque tuile est une liste d'objets 3D positionnés (bâtiments, ponts, arbres, etc.).
Chaque objet pointe vers un modèle dans le `.3D3` via son champ `shape`.

### Structure binaire

```
Offset  Taille      Champ
──────  ──────      ────────────────────────────────────────────────────────
+0x00   2           signature  0x3131
+0x02   5×2         category_sizes[]  nombre de tuiles par catégorie (≤ 32)
+0x0C   Σ(cat_size)×2  tile_counts[]   nombre d'objets par tuile, catégorie par catégorie
+?      variable    tile_data[]      objets de tuile (7 octets chacun)
```

**Structure d'un objet de tuile (TileSceneObject, 7 octets) :**

```
Offset  Taille  Champ   Type    Description
──────  ──────  ──────  ──────  ──────────────────────────────────────────
+0x00   2       x       int16   Position X relative dans la tuile
+0x02   2       y       int16   Position Y relative (hauteur)
+0x04   2       z       int16   Position Z relative dans la tuile
+0x06   1       shape   uint8   Indice dans CE.3D3 (bits [6:0]) + flag bit7
```

Le bit 7 de `shape` indique que l'objet nécessite une résolution via la table de tuiles
dynamiques (`DynTileOverride`). Les 7 bits bas sont l'index direct dans `header_words[]`
du fichier `.3D3`.

**Lecture du tableau de tuiles :**

```python
# Première passe : lire les comptes
for category_idx in range(5):
    for tile_idx in range(category_sizes[category_idx]):
        tile_counts[category_idx][tile_idx] = read_u16()

# Deuxième passe : lire les objets
for cat, counts in enumerate(tile_counts):
    for tile_idx, obj_count in enumerate(counts):
        objects = []
        for _ in range(obj_count):
            x     = read_i16()
            y     = read_i16()
            z     = read_i16()
            shape = read_u16() & 0xFF   # seul l'octet bas est utilisé
            objects.append(TileEntry(x, y, z, shape))
```

**Note :** La lecture des counts se fait en deux passes (toutes les catégories d'abord),
puis les données d'objets, dans le même ordre. C'est l'ordre exact utilisé dans `load_3dt`.

---

## Catalogue d'appareils (aircraftTypes)

### Structure AircraftType (32 octets)

```
Offset  Taille  Champ           Description
──────  ──────  ──────────────  ─────────────────────────────────────────────
+0x00   7       name            Désignation courte (ex: "MIG-23\0")
+0x07   11      altName         " " + nom OTAN (ex: " Flogger\0\0\0")
+0x12   2       maxSpeed        int16 — vitesse maxi
+0x14   2       range           int16 — portée d'engagement
+0x16   2       maneuverability int16 — agilité
+0x18   2       modelId         int16 — index dans 15FLT.3D3 (-1 = aucun modèle)
+0x1A   2       viewModelId     int16 — modèle vue rapprochée
+0x1C   2       viewModelIdFar  int16 — modèle vue lointaine
+0x1E   2       killCount       int16 — compteur de kills
```

### Table aircraftTypes[19]

| Index | Nom court | Nom OTAN   | modelId | viewModelId |
|-------|-----------|------------|---------|-------------|
| 0     | MIG-23    | Flogger    | 17      | 10          |
| 1     | MIG-25    | Foxbat     | 18      | 0           |
| 2     | MIG-29    | Fulcrum    | 19      | 20          |
| 3     | F-1       | Mirage     | 20      | 0           |
| 4     | Su-27     | Flanker    | 19      | 20          |
| 5     | IL-76     | Mainstay   | 16      | 12          |
| 6     | F-4E      | Phantom    | 18      | 11          |
| 7     | F-14      | Tomcat     | 19      | 8           |
| 8     | F-18      | Hornet     | -1      | 0           |
| 9     | An-72     | Coaler     | 0       | 9           |
| 10    | F-18      | Hornet     | -1      | 4           |
| 11    | MIG-23    | Flogger    | 0       | 4           |
| 12    | F-14      | Tomcat     | -1      | 8           |
| 13    | F-4E      | Phantom    | -1      | 11          |
| 14    | MIG-17    | Fresco     | 17      | 16          |
| 15    | Tu-95     | Bear       | 0       | 18          |
| 16    | Mi-24     | Hind       | 17      | 19          |
| 17    | F-5       | Tiger      | 22      | 22          |
| 18    | 767       | Boeing     | -1      | 18          |

`modelId = -1` → pas de modèle 3D disponible dans 15FLT.3D3.
`modelId = 0` → utiliser le modèle 0 (forme générique).

---

## Relations entre fichiers — Schéma d'architecture

```
                    ┌──────────────────────────────────────────┐
                    │           Théâtre CE                     │
                    └──────────────────────────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────────┐
                    ▼                   ▼                       ▼
              CE.WLD                CE.3DG               CE.3D3 / 15FLT.3D3
         ─────────────────      ──────────────         ─────────────────────
         worldObjectCount        layer1 (LOD3)         header_words[N]
         worldObjects[]          layer2 (LOD2)              │
               │                 layer3 (LOD1)              ▼
               │ unitType        layer4 (LOD0)          object_data[]
               │ x_coord              │                  (modèles 3D)
               │ y_coord              │                      ▲
               │ objectIdx  ──────────┘                      │
               │ targetFlags           ▼                      │
               │ occupantType      process_3dg             CE.3DT
               │     │              (col,row,lod)       ──────────────
               │     │                  │               category_sizes
               │     ▼                  ▼               tile_counts[]
               │ aircraftTypes[]   category_idx         TerrainTile[]
               │    (modelId)           │                   shape ──►──┘
               │       │                ▼
               │       ▼           tuile 3DT[category_idx]
               │   15FLT.3D3           (objets positionnés)
               │   (modèle avion)
               │
               ▼
         flightUnits[]
         (waypointIdx → worldObjects[i].x/y)
```

---

## Guide d'implémentation

### Chargement d'un théâtre complet

```python
# 1. Charger les modèles 3D
models_3d3 = load_3d3("CE.3D3")       # objets terrain
flt_models = load_3d3("15FLT.3D3")    # appareils

# 2. Décoder les modèles (header_words[i] → objet décodé)
terrain_models = {m.index: m for m in decode_3d3_models(models_3d3)}
aircraft_models = {m.index: m for m in decode_3d3_models(flt_models)}

# 3. Charger la grille et le catalogue de tuiles
grid = load_3dg("CE.3DG")
terrain = load_3dt("CE.3DT")

# 4. Charger les données monde
wld = load_wld("CE.WLD")

# 5. Pour afficher une cellule de terrain (col, row) en LOD 3 :
category_idx = process_3dg(grid, lod=3, col=col, row=row)
tile = terrain.categories[3][category_idx]
for obj in tile.objects:
    shape_idx = obj.shape & 0x7F
    model = terrain_models.get(shape_idx)
    render_at(model, obj.x, obj.y, obj.z)
```

### Rendu des objets WLD

```python
for i, obj in enumerate(wld.objects):
    if obj.x == 0 and obj.y == 0:
        continue    # entrée nulle / placeholder

    is_target_marker = bool(obj.target_flags & 0x0001)

    if not is_target_marker:
        # Objets statiques avec modèle propre (SAM, aérobase, port)
        shape_idx = obj.object_idx    # objectIdx & 0x7F déjà appliqué
        model = terrain_models.get(shape_idx)
        if model and model.vertices:
            render_3d_model(model, obj.x_coord, obj.y_coord)
            continue

    # Fallback : marqueur point + étiquette
    name = wld.name_for(i, obj)
    render_marker(obj.x_coord, obj.y_coord, color=unit_color(obj), label=name)
```

### Rendu des unités de vol (appareils)

```python
AIRCRAFT_MODEL_IDS = [17,18,19,20,19,16,18,19,-1,0,-1,0,-1,-1,17,0,17,22,-1]

for unit in wld.units:
    x, y = unit.x, unit.y
    if x == 0 and y == 0 and 0 < unit.waypoint_idx < len(wld.objects):
        ref = wld.objects[unit.waypoint_idx]
        x, y = ref.x_coord, ref.y_coord
    if x == 0 and y == 0:
        continue

    model_id = AIRCRAFT_MODEL_IDS[unit.plane_type] if 0 <= unit.plane_type < 19 else -1
    model = aircraft_models.get(model_id) if model_id >= 0 else None

    if model and model.vertices:
        render_3d_model(model, x, y, scale=FLT_MODEL_SCALE)
    else:
        render_marker(x, y, label=aircraft_name(unit.plane_type))
```

---

## Annexe — Signatures de fichiers

| Extension | Signature (u16 LE) | Valeur hex |
|-----------|--------------------|------------|
| `.3D3`    | 0x3333             | `33 33`    |
| `.3DT`    | 0x3131             | `31 31`    |
| `.3DG`    | 0x3232             | `32 32`    |
| `.WLD`    | (aucune)           | lecture directe |

---

## Annexe — Armes SAM et menaces (aNone[23])

Tableau `aNone[]` dans `egdata.c`, indexé par type de menace :

| Index | Nom    | Létalité | Tier | Radar guidé |
|-------|--------|----------|------|-------------|
| 0     | None   | 0        | 0    | non         |
| 1     | SA-2   | 200      | 3    | non         |
| 2     | SA-5   | 350      | 2    | non         |
| 3     | SA-8B  | 125      | 5    | non         |
| 4     | SA-10  | 320      | 7    | oui         |
| 5     | SA-11  | 200      | 5    | non         |
| 6     | SA-12  | 290      | 6    | oui         |
| 7     | SA-13  | 125      | 3    | non         |
| 8     | SA-N-4 | 200      | 4    | oui         |
| 9     | SA-N-5 | 150      | 3    | non         |
| 10    | SA-N-6 | 320      | 6    | oui         |
| 11    | SA-N-7 | 200      | 5    | non         |
| 12    | Hawk   | 175      | 6    | oui         |
| 13    | Rapier | 75       | 8    | non         |
| 14    | Tiger  | 65       | 4    | non         |
| 15    | Seacat | 200      | 2    | non         |
| 16    | IL76   | 200      | 8    | oui (×3)    |
| 21    | OTH    | 500      | 5    | oui         |

---

*Document produit par ingénierie inverse du moteur F-15 Strike Eagle II (MicroProse 1992).
Sources principales : `src/enworld.c`, `src/stgen.c`, `src/struct.h`, `src/egdata.c`,
`f15se2_loader/loader.py`.*
