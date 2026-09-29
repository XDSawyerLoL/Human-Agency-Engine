# AURA Personal Agent Runtime v1

AURA Personal Agent Runtime ajoute des missions persistantes et un scheduler autonome borné à Human Agency Engine. C'est la première couche d'infrastructure nécessaire pour un agent personnel toujours actif.

## Ce que v1 fait réellement

- conserve les objectifs et payloads de mission chiffrés ;
- planifie des missions périodiques et les reprend après redémarrage ;
- exécute un cycle d'agence limité à l'utilisateur ;
- synchronise Google via le connecteur existant en lecture seule ;
- lance une mission AURA Software Engine déjà autorisée dans son sandbox Docker ;
- journalise chaque exécution, résultat, erreur et besoin d'autorisation ;
- permet pause, reprise et annulation ;
- expose une surface de capacités fidèle à l'état réel.

v1 ne prétend pas fournir un ordinateur cloud graphique, le contrôle souris/clavier d'un navigateur, Slack, les SMS ou des milliers de connecteurs. Ces capacités restent marquées indisponibles tant qu'un opérateur réel n'est pas configuré.

## Frontière de sécurité

Le scheduler ne contourne pas la pile d'autorisation existante. Une mission software_patch exige autonomy_level=execute_reversible, un preflight Software Engine existant, un preflight appartenant au même utilisateur et tous les contrôles Docker/attestation déjà imposés par AURA Software Engine. Le travail reste sandbox-only : aucun push, merge, déploiement ou publication directe.

Les objectifs et payloads sont chiffrés au repos avec TOKEN_ENCRYPTION_KEY. L'API ne renvoie que le hash SHA-256 de l'objectif, jamais son texte brut ni le payload.

## Configuration runtime

Le worker reste opt-in :

PERSONAL_AGENT_ENABLED=false
PERSONAL_AGENT_TICK_SECONDS=30
PERSONAL_AGENT_MAX_MISSIONS_PER_TICK=5

## API

- GET /v1/personal-agent/runtime
- GET /v1/personal-agent/users/{external_id}/capabilities
- POST /v1/personal-agent/users/{external_id}/missions
- GET /v1/personal-agent/users/{external_id}/missions
- GET /v1/personal-agent/users/{external_id}/missions/{mission_id}
- GET /v1/personal-agent/users/{external_id}/missions/{mission_id}/runs
- POST /v1/personal-agent/users/{external_id}/missions/{mission_id}/run
- POST /v1/personal-agent/users/{external_id}/missions/{mission_id}/pause
- POST /v1/personal-agent/users/{external_id}/missions/{mission_id}/resume
- POST /v1/personal-agent/users/{external_id}/missions/{mission_id}/cancel

## Phase suivante

La prochaine couche est un Operator Bus avec fournisseurs attestables indépendamment : browser operator, graphical computer operator, Slack, SMS, puis connecteurs natifs Glide, Mail, ZOON et Studio. Chaque opérateur devra déclarer ses droits lecture/écriture, son external dispatch, son idempotence, son rollback et son niveau d'autorisation.