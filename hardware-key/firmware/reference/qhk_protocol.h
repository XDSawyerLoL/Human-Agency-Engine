#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define QHK_REPORT_BYTES 64u
#define QHK_HEADER_BYTES 11u
#define QHK_PAYLOAD_BYTES 53u
#define QHK_PROTOCOL_VERSION 1u

enum qhk_command {
  QHK_INFO = 0x01,
  QHK_PROVISION = 0x02,
  QHK_UNLOCK = 0x03,
  QHK_SIGN = 0x04
};

typedef struct {
  uint8_t command;
  uint16_t request_id;
  uint8_t index;
  uint8_t total;
  uint8_t length;
  uint8_t payload[QHK_PAYLOAD_BYTES];
} qhk_frame;

bool qhk_decode_frame(const uint8_t report[QHK_REPORT_BYTES], qhk_frame *out);
void qhk_encode_frame(uint8_t report[QHK_REPORT_BYTES], uint8_t command, uint16_t request_id,
                      uint8_t index, uint8_t total, const uint8_t *payload, uint8_t length);
