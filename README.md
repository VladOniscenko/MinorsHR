# Minorkeuze-tool Hogeschool Rotterdam

Een uitbreidbare dataset van alle minors (per collegejaar en semester) plus een interactieve rapportpagina waarin een student
collegejaar, semester en opleiding kiest. De pagina vergelijkt minors, toont statistieken en markeert wat bij de opleiding past.

> **Gebruik op eigen risico.** Dit project is gemaakt met behulp van AI en kan fouten of verouderde informatie bevatten.
> De maker neemt geen enkele verantwoordelijkheid voor keuzes die hierop worden gebaseerd. Controleer altijd bij HR of de minorcoördinator.

## Snel starten

```powershell
cd minor-tool
python tools/validate.py          # controleert de dataset
python tools/build.py --sqlite    # schrijft dist/minor-advies-hr.html en dist/minors.db
```

Open `dist/minor-advies-hr.html` in een browser (één bestand, geen server of internet nodig).
Alleen Python 3.9+ (standaardbibliotheek) is nodig.

Via de URL kun je een selectie delen: `minor-advies-hr.html#y=2026-2027&t=V&s=b-informatica`
(`y` = collegejaar, `t` = semester `N` najaar of `V` voorjaar, `s` = opleiding-id, optioneel `today=YYYY-MM-DD` om een andere "vandaag" te simuleren).

## Mappen

| Map | Inhoud |
|-----|--------|
| `data/` | De dataset (JSON, bron van waarheid). Handmatig te bewerken en geschikt voor git. |
| `imports/` | Ruwe exports uit Osiris en HINT, per datum bewaard. |
| `tools/` | Importers, validatie en build. `tools/browser/` bevat de scripts die je in de browser draait. |
| `dist/` | Gegenereerde pagina en SQLite-database (mag je verwijderen en opnieuw bouwen). |

## Dataset (`data/*.json`)

| Bestand | Inhoud |
|---------|--------|
| `studies.json` | Opleidingen: `id` (slug), `name` (Osiris-naam), `label`, `level` (Bachelor / Associate degree). |
| `institutes.json` | Instituten: `code`, `name`, `match` (tekstdelen waarmee de importer ze herkent). |
| `minors.json` | Eén record per minor, jaaronafhankelijk: `id`, `name`, `aliases`, `kind` (`minor` of `programma`), `institute`, `osiris_codes`, en `by_year[jaar]` met de HINT-inhoud (url, locatie, EC-tekst, tagline, periode, omschrijving, toelatingseisen, inhoud, vorm). |
| `offerings.json` | Eén record per minor per **collegejaar + semester** (`N` = najaar/semester 1, `V` = voorjaar/semester 2): `ec`, `languages`, `enrollment {from,to}`, `target` (opleidingen waarvoor de minor bedoeld is), `admitted` (toegelaten opleidingen; `null` = onbekend), `warning`, `unconfirmed`, `enroll_note`, `sources`, `snapshot`, `active`. |
| `calendar.json` | Per collegejaar: namen en start/einddatum van de semesters en extra gebeurtenissen (voorlichting, deadlines). |
| `assessments.json` | Beoordelingsprofielen: criteria met gewichten, scores per minor en toelichting. Nu: profiel `informatica`. |
| `aliases.json` | Handmatige naamkoppelingen (minor-id naar alternatieve namen) voor het samenvoegen van bronnen. |
| `sources.json` | Beschrijving van de bronnen en een lijst van geïmporteerde snapshots. |

Relaties: `offerings.minor` verwijst naar `minors.id`; `target`/`admitted` en `assessments.profiles[].studies` verwijzen naar `studies.id`;
`offerings.year` en `term` moeten in `calendar.json` staan. `python tools/validate.py` controleert dit.

### SQLite

`python tools/build.py --sqlite` maakt `dist/minors.db` met de tabellen `institutes`, `studies`, `minors`, `minor_content`, `terms`,
`offerings`, `offering_target`, `offering_admitted`, `assessments` en de view `offering_overview`. Voorbeelden:

```sql
-- Minors in semester 2 van 2026-2027 met open inschrijving
SELECT minor, institute, ec, enroll_from, enroll_to FROM offering_overview
WHERE year='2026-2027' AND term='V' AND enroll_to IS NOT NULL ORDER BY minor;

-- Voor welke minors is Informatica een doelgroep?
SELECT m.name, o.year, o.term FROM offerings o JOIN minors m ON m.id=o.minor_id
JOIN offering_target t ON t.offering_id=o.id WHERE t.study_id='b-informatica';
```

## Een nieuw collegejaar of semester toevoegen

1. **Osiris** (semester, inschrijfperiode, doelgroep, toelating): log in, open de
   [onderwijscatalogus](https://hr.osiris-student.nl/onderwijscatalogus) (tabblad Minors), plak `tools/browser/osiris-export.js` in de
   browserconsole en klik een filter aan of uit. Er wordt `osiris-export-<datum>.json` gedownload. Zet het in `imports/` en draai:
   `python tools/import_data.py osiris imports/osiris-export-<datum>.json`.
   De importer maakt automatisch aanbiedingen voor elk collegejaar en semester dat in de export staat, voegt nieuwe minors en
   opleidingen toe en markeert aanbiedingen die niet meer in de export staan als `active: false`.
2. **Kalender**: de importer meldt als een jaar nieuw is. Vul de start- en einddatum van de semesters in `data/calendar.json` in.
3. **HINT** (omschrijving, toelatingseisen, programma): ga naar het
   [minoroverzicht](https://hint.hr.nl/nl/HR/Studie/keuzes-in-je-studie/Minors/Minoroverzicht/), voer `tools/browser/hint-export.js` uit per
   tabblad (Voltijd, Deeltijd, Duaal) en daarna `await hintDownload()`. Importeer met
   `python tools/import_data.py hint imports/hint-export-<datum>.json --year 2027-2028`.
4. **Handwerk** (optioneel): programma's die niet in Osiris staan (zoals de RBS semester 6-programma's) voeg je toe als minor met
   `"kind": "programma"` en een aanbieding met de toegelaten opleidingen in `data/`. Vul `aliases.json` aan als een minor in de ene bron
   anders heet dan in de andere. Voeg beoordelingen toe in `assessments.json`.
5. `python tools/validate.py` en `python tools/build.py --sqlite`.

Beide browserscripts lezen alleen wat jij met je eigen HR-account mag zien en wijzigen niets in Osiris of HINT.

### Wat is er nu beschikbaar?

Alleen **2026-2027** (stand 22-10-2026). Osiris toont alleen het huidige collegejaar; eerdere jaren kunnen alleen worden toegevoegd als je daar een
eigen export van hebt. De pagina en de dataset ondersteunen meerdere jaren: zodra er meer jaren in `data/` staan, verschijnen ze in de keuzelijst.

## Beoordeling

De scores (1-10) in `assessments.json` zijn een eigen inschatting voor Informatica-studenten op basis van de omschrijving op HINT
(basisjaar 2026-2027). Voor andere opleidingen toont de pagina alleen de aansluiting uit Osiris: **Verdiepend** (opleiding staat bij de doelgroep),
**Verbredend** (toegelaten), **Niet toegelaten** of **Onbekend**. Een nieuw profiel voeg je toe in `assessments.json`
(`id`, `label`, `studies`, `criteria`, `items`, `commentary`).

## Beperkingen

- Extra eisen (stage, 90 EC, intake) staan in de HINT-tekst, niet als gestructureerde velden.
- HINT en Osiris kunnen verschillen. Voor semester, inschrijving en toelating gaat Osiris voor; voor inhoud HINT.
- De inschrijfperiode in Osiris hoort bij de minor, niet bij een semester. De importer koppelt hem aan het voorjaar als een minor ook in het voorjaar draait.
- Ervaringen van studenten (werkdruk, docentkwaliteit) zitten er niet in.
