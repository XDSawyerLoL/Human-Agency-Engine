#include "qhk_protocol.h"
#include <string.h>

static const uint8_t MAGIC[4] = {'Q','H','K','1'};

bool qhk_decode_frame(const uint8_t report[QHK_REPORT_BYTES], qhk_frame *out) {
  if (!report || !out) return false;
  if (memcmp(report, MAGIC, 4) != 0) return false;
  if (report[4] != QHK_PROTOCOL_VERSION) return false;
  if (report[10] > QHK_PAYLOAD_BYTES) return false;
  out->command = report[5];
  out->request_id = (uint16_t)report[6] | ((uint16_t)report[7] << 8);
  out->index = report[8];
  out->total = report[9];
  out->length = report[10];
  memset(out->payload, 0, sizeof(out->payload));
  memcpy(out->payload, report + QHK_HEADER_BYTES, out->length);
  return true;
}

void qhk_encode_frame(uint8_t report[QHK_REPORT_BYTES], uint8_t command, uint16_t request_id,
                      uint8_t index, uint8_t total, const uint8_t *payload, uint8_t length) {
  memset(report, 0, QHK_REPORT_BYTES);
  memcpy(report, MAGIC, 4);
  report[4] = QHK_PROTOCOL_VERSION;
  report[5] = command;
  report[6] = (uint8_t)(request_id & 0xff);
  report[7] = (uint8_t)((request_id >> 8) & 0xff);
  report[8] = index;
  report[9] = total;
  report[10] = length <= QHK_PAYLOAD_BYTES ? length : QHK_PAYLOAD_BYTES;
  if (payload && report[10]) memcpy(report + QHK_HEADER_BYTES, payload, report[10]);
}
