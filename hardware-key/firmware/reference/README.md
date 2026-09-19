# Firmware de référence QHK/1

Cette arborescence décrit le firmware de référence pour une **Quantic Hardware Key**.

## Architecture recommandée

- microcontrôleur avec USB Device natif et TinyUSB ou équivalent open source ;
- élément sécurisé séparé capable de générer et signer avec ECDSA P-256 ;
- I²C/SPI entre MCU et élément sécurisé ;
- aucune clé privée stockée dans la flash générale du MCU.

Le protocole QHK/1 est indépendant du fabricant de l'élément sécurisé. L'implémentation fournit une interface `secure_element.h` afin de remplacer le backend matériel sans changer Identity Vault.

## Fonctions obligatoires du backend sécurisé

- génération d'une clé P-256 non exportable ;
- lecture de la clé publique ;
- signature d'un SHA-256 ;
- création et stockage d'un secret aléatoire de coffre ;
- restitution du secret de coffre uniquement lorsque le périphérique physique est présent ;
- identifiant matériel stable non secret.

## Important

Le code de protocole ne suffit pas à garantir la non-exportabilité. Cette propriété vient du composant sécurisé choisi et de sa configuration de verrouillage. Une carte de développement qui conserve la clé privée dans sa flash ordinaire est uniquement un prototype.
