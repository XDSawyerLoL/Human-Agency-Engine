#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// Backend matériel interchangeable. La clé privée de signature ne doit jamais
// être retournée par cette interface.

bool qhk_se_init(void);
bool qhk_se_is_provisioned(void);
bool qhk_se_provision(void);

// SEC1 non compressé: 0x04 || X(32) || Y(32)
bool qhk_se_public_key(uint8_t out65[65]);

// Signature ECDSA P-256 au format IEEE-P1363: r(32) || s(32)
bool qhk_se_sign_sha256(const uint8_t digest32[32], uint8_t signature64[64]);

// Secret distinct du coffre. Ce secret peut être remis au host pendant que
// le périphérique est physiquement présent; la clé privée d'identité, jamais.
bool qhk_se_vault_key(uint8_t out32[32]);

// Identifiant public stable, ASCII NUL-terminated.
bool qhk_se_device_id(char *out, size_t out_len);
