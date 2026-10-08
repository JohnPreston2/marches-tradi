# Marchés tradi — planches 3D

Projet séparé du tableau de bord Hermes DeFi. Il reprend la méthode de la planche Crypto
(médailles frappées d'un logo, une fiche par objet, relevé sans modèle de langage) sur quatre planches :

| Planche | Liste des sociétés | Classement et surface de la médaille |
|---|---|---|
| S&P 500 (`#sp500`) | composition de l'indice (Wikipédia) | capitalisation |
| CAC 40 (`#cac40`) | composition de l'indice (Wikipédia) | capitalisation |
| Robotique (`#robotique`) | titres du fonds Global X **BOTZ** (le plus gros fonds robotique) | poids dans le fonds |
| IA (`#ia`) | titres du fonds Global X **AIQ** (le plus gros fonds IA) | poids dans le fonds |

Un thème n'a pas de liste officielle : on prend celle d'un fonds coté du thème plutôt que de choisir
les sociétés soi-même. Classement par poids dans le fonds : décision du 7 octobre 2026 (par capitalisation,
Nvidia, Alphabet et Tesla écrasaient la robotique, et la planche IA répétait le S&P 500).

## Mise en scène

- **Médaille** : le logo au centre, sur émail ivoire s'il est sombre ou coloré. Autour, la *légende*
  (le texte gravé d'une médaille) : le nom en haut, la valeur en bas.
- **Écran large** : deux rangs à la même profondeur, les premières en haut sur des tiges. Même profondeur
  exprès : en perspective, un rang du fond paraîtrait plus petit qu'il n'est.
- **Écran haut (téléphone)** : pyramide 1-2-3-4, cadrée dans la place libre mesurée entre le texte du haut
  et la légende du bas. Une médaille touchée se place seule au-dessus de sa fiche.
- **Méthode** : le bouton en bas à gauche ouvre le détail des sources et des calculs de la planche.

Relecture du 7 octobre 2026 sur la grille Awwwards (design 40 %, usabilité 30 %, créativité 20 %,
contenu 10 %) : 6,5 / 6,4 / 6,0 / 7,0 au départ, 7,8 / 7,7 / 7,6 / 7,8 après quatre tours.

## Voir la page

La page lit `site/marches.json` : elle ne s'ouvre pas en double-cliquant sur le fichier.

```bash
python -m http.server 8812 --bind 127.0.0.1 --directory site
```

Puis ouvrir http://localhost:8812/ (ou `#cac40` pour la seconde planche).
Dans l'app Claude, le serveur s'appelle `marches-tradi` (fichier `C:\Users\HUGO\.claude\launch.json`).

## Rafraîchir les chiffres

```bash
.venv\Scripts\python releve.py
```

Environ 40 secondes. Sources :
- composition des indices : Wikipédia (gardée un jour dans `cache/`) ;
- cours, nombre d'actions, historique, fiche : Yahoo Finance via `yfinance` ;
- logos : companiesmarketcap, téléchargés une seule fois dans `site/logos/`.

Capitalisation = nombre d'actions × dernier cours, comme Yahoo. Alphabet et Berkshire Hathaway ont
deux types d'actions cotés : chaque société compte une seule fois. Dividendes = somme des versements
des 365 derniers jours (les champs annualisés de Yahoo divergent). Cours / bénéfice non affiché quand
le bénéfice est publié dans une autre devise que le cours (TotalEnergies).

Thèmes : le fichier quotidien de Global X (`assets.globalxetfs.com/funds/holdings/<fonds>_full-holdings_<date>.csv`,
daté de la veille) donne le poids de chaque titre et son prix en dollars. Le symbole Global X (`6954 JP`)
est traduit en symbole Yahoo (`6954.T`) ; il n'est accepté que si le cours Yahoo, converti en dollars,
tombe à ±15 % du prix du fichier. Capitalisations converties en dollars au cours du jour.

**Témoins** : un indice dont la composition, la couverture, le total ou le top 10 paraît faux
(par exemple LVMH absent du top 10 du CAC 40), ou un fonds sans Fanuc, ABB ni Keyence (robotique),
sans Nvidia ni Microsoft (IA) dans son top 10, garde le relevé précédent, et l'échec s'affiche sur la page.
Sans relevé précédent, rien n'est écrit. Test : `.venv\Scripts\python outils\test_temoins.py`.

**Logos** : téléchargés une seule fois ; un fichier déjà présent dans `site/logos/` n'est jamais remplacé.
Celui d'Inovance (`300124-sz.png`) a été repris de l'en-tête du site officiel (la source automatique
ne donnait qu'un fragment, « VA ») avec `python outils\logo_depuis_site.py <url> <x> <y> <largeur> <hauteur> <fichier>`.

## Contrôler

- `python outils\controle.py <dossier>` : 6 captures (bureau, fiche, téléphone) dans Chrome sans fenêtre.
- `python outils\test_clic.py` : clic, flèches, Échap, changement d'onglet.
- `.venv\Scripts\python outils\resume.py` : les chiffres du dernier relevé, lisibles.

## Publication (depuis le 8 octobre 2026)

- Site public : https://johnpreston2.github.io/marches-tradi/ — dépôt `JohnPreston2/marches-tradi`.
  Chaque envoi sur `main` republie le dossier `site/` (`.github/workflows/pages.yml`, environ une minute).
- Relevé automatique sur le serveur delta : copie du dépôt dans `~/marches-tradi`, environnement Python
  `.venv` à part, tâche planifiée `17 7-21 * * 1-5` qui lance `serveur/publier.sh` (journal `/tmp/marches_tradi.log`).
  Le serveur publie avec la clé de déploiement `delta-marches-tradi` (ce dépôt seulement ; alias SSH `github-marches`).
- **Depuis le PC, ne jamais envoyer `site/marches.json` ni `site/logos/`** : ce sont les fichiers du serveur.
  On peut envoyer le reste (page, script, outils) ; le serveur récupère ces changements avant chaque relevé.
- Retirer le relevé automatique : remettre la sauvegarde de la liste des tâches planifiées, nommée dans le journal
  d'installation (`~/backups/marches-tradi/`), ou supprimer la ligne `marches-tradi`.

## Pas encore fait

Fil d'actualités. Yahoo Finance n'est pas une source officielle, et ses conditions réservent ses données
à un usage personnel.
