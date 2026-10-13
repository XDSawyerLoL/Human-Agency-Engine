# HORIZON — acquisition B2B

Landing indépendante, sans modification de la boutique Hostinger existante.

## Réalisé

- Landing B2B responsive avec offres **indicatives**, non payables et non présentées comme des abonnements existants.
- Formulaire de démo, consentement commercial séparé, données UTM (sans cookie), protection honeypot et anti-duplication.
- Backend serverless et table de prospects PostgreSQL Neon isolée, avec statut et journal.
- Administration par clé secrète serveur et export CSV, suppression individuelle, KPI mesurés.

## Configuration

- `DATABASE_URL` : connexion PostgreSQL Neon, stockée côté serveur.
- `ADMIN_SECRET` : clé secrète aléatoire en variable d'environnement serveur.

La clé ne doit JAMAIS être envoyée au navigateur autrement que par saisie manuelle explicite de l'administrateur, ni inscrite dans le dépôt public. Le formulaire accepte les demandes **seulement** si les variables d'environnement sont correctement définies.

## Limites

- Aucune publication sociale ou paiement activé. Le compte Metricool n'a aucun canal relié et les plans Hostinger ne sont pas accessibles pour validation.
- Pas de système d'envoi de courriels automatisé. Aucun compte Resend compatible avec l'identité HORIZON n'a été autorisé pour cette vitrine.
- Les déclarations RGPD doivent être complétées avec l'identité légale du responsable de traitement avant vente active ; purger les prospects périmés et valider le contrat du sous-traitant.
- Protection anti-abus simple : ajouter CAPTCHA et rate limit IP si formulaire ciblé par du spam.
- Pour l'exploitation durable : monitoring, sauvegarde chiffrée, test de restauration, authentification d'administration avec MFA.

## Exécuter

`npm ci` (si lockfile présent) ou `npm install`, puis `vercel dev` avec les variables d'environnement en local. De préférence utiliser un déploiement Vercel doté d'une base Neon dédiée.

## Confidentialité

Ne jamais écrire les identifiants de la base, les clés administrateur ou les données des prospects dans un dépôt public ni une métrique. La page `/privacy.html` explicite les traitements et leurs limites.