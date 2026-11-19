import { create } from "zustand";
import { api } from "@/api/endpoints";
import type { Credits } from "@/types";

/**
 * Reports left on the signed-in account.
 *
 * Shown wherever a report is about to be spent, so an empty balance is never
 * a surprise at the end of a 40-second analysis. `null` means "not loaded or
 * could not be loaded" — the UI then simply says nothing rather than guess.
 */
interface CreditsState {
  credits: Credits | null;
  load: () => Promise<void>;
  clear: () => void;
}

export const useCreditsStore = create<CreditsState>((set) => ({
  credits: null,
  load: async () => {
    try {
      set({ credits: await api.getCredits() });
    } catch {
      set({ credits: null });
    }
  },
  clear: () => set({ credits: null }),
}));

/** The sentence for an empty balance — the same one the API's 402 carries. */
export function exhaustedKey(c: Credits | null): string {
  return c?.paid ? "credits_exhausted.paid" : "credits_exhausted.free";
}

/** True when the account can run no more full reports. */
export function isOutOfReports(c: Credits | null): boolean {
  return !!c && !c.unlimited && (c.balance ?? 0) <= 0;
}
