# Deauville Festival du Rire

Application Python de gestion du programme du festival, du 10 au 13 juin 2027.
Le site public affiche les spectacles et les artistes ; l'administration
permet de modifier le planning et d'inscrire les participants aux ateliers.
Le même modèle métier est utilisé par le terminal et l'API.

## Installation

Prérequis : Python 3.14 ou supérieur et [uv](https://docs.astral.sh/uv/).
Depuis une copie du dépôt :

```powershell
git clone https://github.com/kinsey-w/deauville-festival.git
cd deauville-festival
uv sync
```

Le dépôt est privé : son accès nécessite les droits GitHub correspondants.
`uv sync` installe le paquet, ses dépendances et les outils de développement
à partir de `pyproject.toml` et `uv.lock` dans l'environnement `.venv`.

## Utilisation

Les commandes ci-dessous passent par Python pour fonctionner aussi lorsque
Windows Smart App Control bloque les lanceurs générés comme `deauville.exe`.
Aucun changement des protections Windows n'est nécessaire.

```powershell
uv run python -m deauville
uv run python -m deauville venues
uv run python -m deauville artists
uv run python -m deauville programme 2027-06-11
uv run python -m deauville artist max-pellerin
uv run python -m deauville now 2027-06-12T01:30
uv run python -m deauville --help
```

La première commande affiche le résumé du festival. `artists` liste les
artistes avec leur nombre de spectacles, tous rôles confondus. `now` affiche
les spectacles en cours à l'instant donné puis les trois prochains.

Le paquet installe aussi la commande prévue par le parcours :
`uv run deauville programme 2027-06-11`. Elle accepte les mêmes arguments
que `uv run python -m deauville`.

### Site et administration

```powershell
uv run python -m deauville serve
```

- Site public : <http://127.0.0.1:8000/>.
- Administration : <http://127.0.0.1:8000/admin/>.
- Documentation interactive de l'API : <http://127.0.0.1:8000/docs>.

`serve --port 8001` sélectionne un autre port. L'option `--host` est
également disponible ; l'adresse par défaut est `127.0.0.1`.
Le lien `/?at=2027-06-11T21:00` simule ce moment sur le site public.
Sans cet instant explicite, l'API utilise l'heure actuelle de Paris.
Toutes les dates échangées représentent l'heure locale du festival,
sans indication de fuseau dans les données.

### Modifications et autre fichier de données

```powershell
uv run python -m deauville add
uv run python -m deauville cancel la-cabane-2027-06-13-0800
uv run python -m deauville --data data/festival.json programme 2027-06-11
uv run python -m deauville --data data/festival.json serve
```

`add` pose les questions pour un nouveau solo ; `cancel` reçoit un
identifiant existant. L'identifiant ci-dessus n'existe qu'après l'ajout d'un
spectacle dans cette salle à cette heure. L'admin permet de créer et modifier
les trois types de spectacles, d'annuler, d'ajouter des artistes et d'inscrire
des participants. Chaque modification acceptée est sauvegardée immédiatement.

Sans `--data`, le chemin utilisé est `data/festival.json` dans le dossier
courant. Hors du dépôt, si ce fichier manque, le paquet lit son édition
initiale intégrée ; le premier changement accepté crée le fichier local.
Un chemin fourni explicitement par `--data` doit exister : il n'est jamais
remplacé silencieusement par les données initiales. Les ressources installées
du paquet ne sont jamais modifiées.

## Vérification et distribution

```powershell
uv run python -m pytest -v
uv run ruff format .
uv run ruff check .
uv build
```

`uv run pytest` est aussi disponible si Windows autorise son lanceur.
Les tests couvrent les règles métier, le stockage JSON et mémoire, les
commandes et l'intégralité du contrat HTTP. Les écritures de test utilisent
des fichiers temporaires ou le stockage mémoire ; le fichier du projet reste
inchangé. Aucune ouverture de serveur réseau n'est nécessaire pour les tests
HTTP : ils utilisent `TestClient(create_app(storage))`.

`uv build` produit `dist/deauville-0.1.0-py3-none-any.whl` et
`dist/deauville-0.1.0.tar.gz`. Le site, l'admin et les données initiales sont
inclus pour permettre l'utilisation hors du dossier source.

## Structure et choix

```text
src/deauville/
    models.py       objets, héritage et règles propres à chaque type
    festival.py     collections et règles entre les spectacles
    storage.py      interface de stockage, JSON, mémoire, chargement
    service.py      opérations validées suivies d'une sauvegarde
    cli.py          commandes et affichage dans le terminal
    api.py          modèles Pydantic, routes et traduction des erreurs
    errors.py       famille d'exceptions du domaine
    web/            site public et admin fournis avec le projet
    data/           édition initiale intégrée au paquet
data/festival.json  données modifiables utilisées depuis le dépôt
tests/              tests pytest
docs/PROJECT_BRIEF.md  sujet original conservé comme référence
API.md              contrat HTTP
```

`main.py` et `api.py` à la racine sont des points d'entrée de compatibilité
avec les anciennes commandes. Le code applicatif se trouve dans le paquet.

### Classes et responsabilités

- `Venue` possède un nom, une capacité et une adresse ; `Artist` possède
  un nom, une biographie et une photo. Leur identité est leur slug : accents
  retirés, minuscules, séparateurs remplacés par un tiret unique.
- `Performance` est abstraite. Elle regroupe les horaires, la durée,
  l'identifiant, le jour du festival et les champs communs des vues.
- `SoloShow` impose un artiste et un âge minimum entre 0 et 18.
- `Lineup` impose un présentateur, au moins deux actes distincts et
  `10 × actes + 3 × (actes - 1)` minutes au minimum. Le présentateur ne peut
  pas aussi être un acte.
- `Workshop` impose un enseignant et une capacité positive. La capacité
  effective est le minimum entre les places demandées et celles de la salle.
  Les inscriptions ne dépassent pas cette limite et les noms sont uniques
  sans distinction de casse.
- `Festival` possède les salles, artistes et spectacles. Il vérifie les
  références, les jours autorisés et les intervalles de 30 minutes pour
  chaque salle et chaque artiste, quel que soit son rôle.

Le jour d'un spectacle est la date de son début moins six heures :
*After Hours*, le 12 juin à 01:00, appartient donc au vendredi 11 juin.
Les spectacles sont triés par début puis nom de salle. Les artistes sont
triés par slug, les salles conservent leur ordre d'ajout.

L'héritage évite les conditions répétées sur `kind` : seul le chargement
choisit la classe. Les propriétés calculées comme `end` restent cohérentes
avec les données. Les objets sont des dataclasses immuables, les collections
exposées sont des tuples et les vues sont de nouveaux dictionnaires.
Une modification passe par les méthodes de `Festival` et crée un nouvel objet.

### Où vivent les règles et les erreurs ?

Les règles propres à un spectacle vivent dans sa classe ; les règles entre
spectacles vivent dans `Festival`. Elles s'appliquent au chargement, au
terminal, à l'API et aux tests. Elles ne sont pas dupliquées dans les routes.

`FestivalError` est la famille commune :

| Exception | Signification | HTTP |
| --- | --- | --- |
| `NotFoundError` | référence inconnue | 404 |
| `ConflictError` | conflit, doublon ou atelier plein | 409 |
| `InvalidValueError` | valeur invalide | 422 |
| `StorageError` | lecture ou écriture impossible | 500 |

L'API utilise un seul gestionnaire pour renvoyer une phrase dans `detail`.
Pydantic vérifie la forme des requêtes ; ses erreurs 422 contiennent une
liste de problèmes. Le terminal affiche `Error: ...` et termine avec le
code 1 pour les erreurs attendues.

Par exemple, `PUT /api/performances/{id}` valide le corps avec Pydantic,
puis appelle `FestivalService.update`. Le service charge le festival,
construit le spectacle et appelle `Festival.update`, qui exclut l'ancienne
version du contrôle de conflit. Si le remplacement est accepté, le stockage
l'enregistre ; sinon l'ancien spectacle et le fichier restent inchangés.

### Pourquoi séparer le stockage ?

`FestivalStorage` définit `load()` et `save()`. `JsonStorage` et
`MemoryStorage` respectent cette interface. `create_app(storage)` et le
terminal reçoivent un stockage ; le modèle ignore les fichiers et le JSON.
`FestivalService` applique une opération à une copie fraîche avant de sauver.
Le JSON est écrit dans un fichier temporaire puis remplacé atomiquement.

Un stockage SQLite pourrait remplacer le JSON en implémentant cette même
interface et en changeant la sélection du stockage, sans modifier les
classes du festival ni leurs règles.

## État et limites

Les étapes E00 à E13 sont implémentées : commandes, trois types de spectacles,
site public, admin, toutes les routes de `API.md`, tests et paquet installable.

- L'ajout interactif dans le terminal concerne les solos ; l'admin gère les
  trois types.
- SQLite reste une extension facultative non implémentée.
- L'application est prévue pour un serveur local à un seul processus. Le
  verrou des écritures API n'organise pas des modifications simultanées par
  plusieurs processus ou par des éditeurs externes du JSON.
- Windows peut bloquer les lanceurs générés ; les commandes via
  `python -m deauville` et `python -m pytest` sont documentées ci-dessus.
