#!/bin/sh
# Relevé + publication des planches Marchés tradi, lancé par la liste des tâches planifiées du serveur delta
# (minute 17, de 7 h à 21 h UTC, du lundi au vendredi ; installé le 08/10/2026, décision user).
# Relevé en échec = rien n'est publié. Fusion impossible avec GitHub = rien n'est publié. Journal : /tmp/marches_tradi.log
set -u
cd /home/classics2323/marches-tradi || exit 1
exec 9>/tmp/marches_tradi.lock
flock -n 9 || { echo "$(date -u +%FT%TZ) passage précédent encore en cours : rien"; exit 0; }
echo "=== $(date -u +%FT%TZ) relevé"
git pull -q --rebase --autostash origin main || echo "récupération GitHub impossible : relevé sur la copie locale"
timeout 600 .venv/bin/python -u releve.py
rc=$?
if [ "$rc" -ne 0 ]; then echo "relevé en échec (code $rc) : rien publié"; exit 1; fi
git add site/marches.json site/logos
if git diff --cached --quiet; then echo "aucun changement : rien publié"; exit 0; fi
git commit -q -m "relevé : $(date -u '+%Y-%m-%d %H:%M UTC')"
if ! git pull -q --rebase --autostash origin main; then
  git rebase --abort 2>/dev/null
  echo "fusion impossible avec GitHub : rien publié"; exit 1
fi
git push -q origin main && echo "publié : $(git log --oneline -1)"
