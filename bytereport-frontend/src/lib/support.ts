/**
 * How a customer reaches ByteReport. One constant, used by every "write to us"
 * control, so the address is changed in exactly one place.
 *
 * TODO(Азизбек): put the ByteReport support username here, e.g. "bytereport_help".
 * While it is empty, every contact control is HIDDEN rather than pointing
 * somewhere wrong — it used to link to an unrelated bot.
 */
export const SUPPORT_TELEGRAM: string = "";

/** https://t.me/<username>, or null while no contact is configured. */
export const supportUrl: string | null = SUPPORT_TELEGRAM
  ? `https://t.me/${SUPPORT_TELEGRAM.replace(/^@/, "")}`
  : null;

/** "@username" for display, or null. */
export const supportHandle: string | null = SUPPORT_TELEGRAM
  ? `@${SUPPORT_TELEGRAM.replace(/^@/, "")}`
  : null;
